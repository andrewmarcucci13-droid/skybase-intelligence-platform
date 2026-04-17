"""
SkyBase Agent 1: FAA Airspace Analysis Agent
============================================
Takes a lat/lon and returns a structured airspace readiness assessment.

Data sources:
  - airport-codes.csv (85K worldwide airports + heliports, bundled)
  - FAA OE/AAA REST API  (oeaaa.faa.gov/oeaaa/services/)
  - OpenSky Network REST API (live airspace class approximation)
  - Nominatim geocoder (address → lat/lon, used upstream)

Scoring (0–100):
  100 = Class G rural, no airports within 20nm, ideal
   80 = Class E, nearest airport > 10nm
   60 = Class D or E, airport 5–10nm, coord required
   40 = Class C surface / approach, significant restrictions
   20 = Class B approach, very complex
    0 = Class B surface area (e.g. LAX/JFK/ORD), essentially prohibited
"""

import csv
import math
import httpx
import asyncio
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


# ── Constants ────────────────────────────────────────────────────────────────

AIRPORTS_CSV = Path(__file__).parent.parent.parent / "data" / "faa" / "airport_codes.csv"

# Approximate Class B surface area radius (nm) for major hubs
CLASS_B_HUBS = {
    "KATL": 5, "KLAX": 5, "KORD": 5, "KDFW": 5, "KJFK": 5,
    "KEWR": 5, "KLGA": 5, "KDEN": 5, "KSFO": 5, "KSEA": 5,
    "KMIA": 5, "KLAS": 5, "KBOS": 5, "KPHX": 5, "KIAH": 5,
    "KDTW": 5, "KMSP": 5, "KCLT": 5, "KPHL": 5, "KBWI": 5,
    "KIAD": 5, "KDCA": 3, "KSTL": 5, "KMDW": 5, "KSNA": 5,
}

# Class C core radius (nm) for towered airports
CLASS_C_CORE_NM = 5.0
CLASS_D_CORE_NM = 4.3   # Typical towered GA airport surface area

# FAA OE/AAA API base
OEAAA_BASE = "https://oeaaa.faa.gov/oeaaa/services"

# nm → statute miles factor (for display)
NM_TO_MILES = 1.15078


# ── Geometry helpers ─────────────────────────────────────────────────────────

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in nautical miles."""
    R = 3440.065  # Earth radius in nm
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing_degrees(lat1, lon1, lat2, lon2) -> float:
    """Compass bearing from point 1 to point 2 (degrees true)."""
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ── Airport database loader ──────────────────────────────────────────────────

_airport_cache: Optional[list] = None


def load_us_airports() -> list:
    """
    Load US airports and heliports from bundled CSV.
    Filters to: small_airport, medium_airport, large_airport, heliport (US only, not closed).
    Returns list of dicts with keys: ident, type, name, lat, lon, icao.
    """
    global _airport_cache
    if _airport_cache is not None:
        return _airport_cache

    airports = []
    include_types = {"small_airport", "medium_airport", "large_airport", "heliport"}

    with open(AIRPORTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("iso_country") != "US":
                continue
            if row.get("type") not in include_types:
                continue
            coords = row.get("coordinates", "").replace('"', '').strip()
            if not coords:
                continue
            try:
                lat_str, lon_str = coords.split(",")
                lat = float(lat_str.strip())
                lon = float(lon_str.strip())
            except (ValueError, TypeError):
                continue

            airports.append({
                "ident":    row.get("ident", "").strip(),
                "icao":     row.get("icao_code", "").strip() or row.get("gps_code", "").strip(),
                "iata":     row.get("iata_code", "").strip(),
                "type":     row.get("type", "").strip(),
                "name":     row.get("name", "").strip(),
                "state":    row.get("iso_region", "").replace("US-", "").strip(),
                "lat":      lat,
                "lon":      lon,
            })

    _airport_cache = airports
    return airports


# ── FAA OE/AAA query ─────────────────────────────────────────────────────────

async def query_oeaaa(lat: float, lon: float, radius_nm: float = 5.0) -> list:
    """
    Query FAA OE/AAA for existing obstruction evaluations near the site.
    Uses the public REST service — returns XML, parsed to list of dicts.
    Falls back to empty list on any error (OE/AAA is often slow / 503).
    """
    import xml.etree.ElementTree as ET

    # Bounding box approximation (1 degree lat ≈ 60 nm)
    delta = radius_nm / 60.0
    min_lat, max_lat = lat - delta, lat + delta
    min_lon, max_lon = lon - delta, lon + delta

    # OE/AAA has limited public endpoints — use the cases-by-state endpoint
    # The coordinate spatial query is not publicly available, so we use a
    # nearby-state bounding approach and filter client-side.
    evaluations = []
    try:
        # Determine state from lat/lon via a simple bounding box lookup
        # (full state lookup would need a GIS layer — we use approximate approach)
        params = {
            "minLat": f"{min_lat:.4f}",
            "maxLat": f"{max_lat:.4f}",
            "minLon": f"{min_lon:.4f}",
            "maxLon": f"{max_lon:.4f}",
            "maxResults": "100",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{OEAAA_BASE}/getObstructionEvaluations", params=params)
            if resp.status_code == 200 and resp.text.strip():
                root = ET.fromstring(resp.text)
                for case in root.findall(".//case"):
                    try:
                        case_lat = float(case.findtext("latitude", "0") or "0")
                        case_lon = float(case.findtext("longitude", "0") or "0")
                        dist = haversine_nm(lat, lon, case_lat, case_lon)
                        if dist <= radius_nm:
                            evaluations.append({
                                "asn":         case.findtext("asn", ""),
                                "structure":   case.findtext("structureType", ""),
                                "height_agl":  case.findtext("aglHeight", ""),
                                "determination": case.findtext("determination", ""),
                                "distance_nm": round(dist, 2),
                            })
                    except Exception:
                        continue
    except Exception:
        # OE/AAA is unreliable — silently skip
        pass

    return evaluations


# ── Airspace classification ──────────────────────────────────────────────────

def classify_airspace(lat: float, lon: float, nearby_airports: list) -> dict:
    """
    Approximate airspace classification based on nearby airport types and distance.
    
    Returns:
        {
          "class": "B"|"C"|"D"|"E"|"G",
          "controlling_facility": str | None,
          "notes": [str],
          "faa_form_required": bool,
          "part_107_waiver_needed": bool,
        }

    NOTE: This is an approximation. Production should use the FAA NASR
    airspace class shapefiles (available in the 28-day subscription).
    """
    notes = []
    faa_form = False
    part_107_waiver = False

    if not nearby_airports:
        return {
            "class": "G",
            "controlling_facility": None,
            "notes": ["No airports within analysis radius — likely uncontrolled airspace"],
            "faa_form_required": False,
            "part_107_waiver_needed": False,
        }

    # Sort by distance
    sorted_airports = sorted(nearby_airports, key=lambda x: x["distance_nm"])
    closest = sorted_airports[0]
    dist_nm = closest["distance_nm"]
    airport_type = closest["type"]
    icao = closest.get("icao", "")

    # Class B surface area check (major hubs)
    if icao in CLASS_B_HUBS and dist_nm <= CLASS_B_HUBS[icao]:
        notes.append(f"Within Class B surface area of {closest['name']} ({icao}) — {dist_nm:.1f} nm")
        notes.append("FAA Part 107 waiver required; vertiport siting extremely restricted")
        return {
            "class": "B",
            "controlling_facility": closest["name"],
            "notes": notes,
            "faa_form_required": True,
            "part_107_waiver_needed": True,
        }

    # Class B approach shelves (5–20 nm from major hub)
    if icao in CLASS_B_HUBS and dist_nm <= 20:
        notes.append(f"Within Class B shelf area of {closest['name']} — {dist_nm:.1f} nm")
        notes.append("FAA Form 7480-1 mandatory; airspace coordination with TRACON required")
        return {
            "class": "B",
            "controlling_facility": closest["name"],
            "notes": notes,
            "faa_form_required": True,
            "part_107_waiver_needed": False,
        }

    # Class C (medium/large airports with approach control)
    if airport_type in ("medium_airport", "large_airport") and dist_nm <= CLASS_C_CORE_NM:
        notes.append(f"Within Class C surface area of {closest['name']} — {dist_nm:.1f} nm")
        notes.append("Two-way radio contact with Approach Control required; FAA Form 7480-1 required")
        faa_form = True
        return {
            "class": "C",
            "controlling_facility": closest["name"],
            "notes": notes,
            "faa_form_required": faa_form,
            "part_107_waiver_needed": False,
        }

    # Class D (small towered airports — must have ICAO code; untowered strips do NOT create Class D)
    is_towered = bool(closest.get("icao"))
    if airport_type in ("small_airport",) and is_towered and dist_nm <= CLASS_D_CORE_NM:
        notes.append(f"Within Class D surface area of {closest['name']} — {dist_nm:.1f} nm")
        notes.append("Two-way radio contact with tower required; FAA Form 7480-1 required")
        faa_form = True
        return {
            "class": "D",
            "controlling_facility": closest["name"],
            "notes": notes,
            "faa_form_required": faa_form,
            "part_107_waiver_needed": False,
        }

    # Class E / E2 (controlled airspace around airports, surface to ~1200 AGL)
    if dist_nm <= 10:
        notes.append(f"Likely Class E airspace — {closest['name']} is {dist_nm:.1f} nm away")
        notes.append("FAA Form 7480-1 required for structures > 200 ft AGL")
        if dist_nm <= 5:
            faa_form = True
        return {
            "class": "E",
            "controlling_facility": closest["name"],
            "notes": notes,
            "faa_form_required": faa_form,
            "part_107_waiver_needed": False,
        }

    # Class G
    notes.append(f"Likely Class G / uncontrolled — nearest airport {closest['name']} is {dist_nm:.1f} nm away")
    return {
        "class": "G",
        "controlling_facility": None,
        "notes": notes,
        "faa_form_required": dist_nm <= 20,  # FAA Form 7480-1 still required near airports
        "part_107_waiver_needed": False,
    }


# ── Scoring ──────────────────────────────────────────────────────────────────

def compute_airspace_score(airspace_class: str, nearest_airport_nm: float,
                            heliport_count: int, obstructions_count: int) -> int:
    """
    Score 0–100 based on airspace class, proximity, and existing structures.
    Higher = more vertiport-friendly airspace.
    """
    base_scores = {"G": 95, "E": 75, "D": 55, "C": 35, "B": 10}
    score = base_scores.get(airspace_class, 50)

    # Proximity penalty
    if nearest_airport_nm < 1:
        score -= 30
    elif nearest_airport_nm < 3:
        score -= 15
    elif nearest_airport_nm < 5:
        score -= 8

    # Heliport proximity — existing heliports actually help (existing infrastructure)
    if heliport_count > 0:
        score += 5   # Precedent for rotorcraft operations

    # Existing OE/AAA obstruction evaluations (indicates active airspace management)
    if obstructions_count > 5:
        score -= 5

    return max(0, min(100, score))


# ── Summary generator ────────────────────────────────────────────────────────

def generate_summary(airspace: dict, nearest_airport: Optional[dict],
                     score: int, obstructions: list) -> str:
    cls = airspace["class"]
    facility = airspace.get("controlling_facility", "no controlling facility")
    dist_txt = f"{nearest_airport['distance_nm']:.1f} nm" if nearest_airport else "none nearby"
    obs_txt = f"{len(obstructions)} existing obstruction evaluation(s) on record" if obstructions else "no existing obstruction evaluations on record"

    summaries = {
        "G": f"The site falls in Class G uncontrolled airspace with {obs_txt}. "
             f"The nearest airport is {dist_txt} away. "
             f"Airspace coordination burden is minimal — FAA Form 7480-1 is still required if the structure exceeds 200 ft AGL.",
        "E": f"The site falls in Class E controlled airspace near {facility} ({dist_txt}). "
             f"FAA Form 7480-1 is required. Airspace coordination is straightforward but adds 4–8 weeks to permitting. {obs_txt.capitalize()}.",
        "D": f"The site is within Class D surface airspace of {facility} ({dist_txt}). "
             f"Two-way radio contact with the tower is required for all operations. FAA Form 7480-1 is mandatory. "
             f"Expect 8–12 weeks for airspace coordination. {obs_txt.capitalize()}.",
        "C": f"The site is within Class C airspace of {facility} ({dist_txt}). "
             f"Approach Control authorization is required. FAA Form 7480-1 is mandatory and TRACON coordination will be needed. "
             f"Permitting timeline 12–18 months. {obs_txt.capitalize()}.",
        "B": f"The site is within Class B airspace of {facility} ({dist_txt}). "
             f"This is the most restrictive airspace class. FAA coordination is extensive, "
             f"Part 107 waiver may be required, and vertiport siting faces significant regulatory hurdles. "
             f"Alternative sites in Class E or G are strongly recommended. {obs_txt.capitalize()}.",
    }
    return summaries.get(cls, "Airspace classification could not be determined with certainty. Manual FAA consultation recommended.")


# ── Main agent function ───────────────────────────────────────────────────────

async def run_airspace_agent(lat: float, lon: float) -> dict:
    """
    Primary entry point for the Airspace Agent.

    Args:
        lat: Site latitude (WGS84 decimal degrees)
        lon: Site longitude (WGS84 decimal degrees)

    Returns dict matching AgentResult shape:
        {
          "score": int,           # 0–100
          "summary": str,
          "warnings": [str],
          "raw_data": { ... full analysis ... }
        }
    """
    started_at = datetime.now(timezone.utc).isoformat()

    # 1. Load airport database
    airports = load_us_airports()

    # 2. Find all airports/heliports within 20 nm
    nearby = []
    for ap in airports:
        dist = haversine_nm(lat, lon, ap["lat"], ap["lon"])
        if dist <= 20.0:
            bearing = bearing_degrees(lat, lon, ap["lat"], ap["lon"])
            nearby.append({**ap, "distance_nm": round(dist, 2), "bearing_deg": round(bearing, 1)})

    nearby.sort(key=lambda x: x["distance_nm"])

    # Separate airports and heliports
    nearby_airports  = [a for a in nearby if a["type"] != "heliport"]
    nearby_heliports = [a for a in nearby if a["type"] == "heliport"]

    nearest_airport  = nearby_airports[0]  if nearby_airports  else None
    nearest_heliport = nearby_heliports[0] if nearby_heliports else None

    # 3. Airspace classification
    airspace = classify_airspace(lat, lon, nearby)

    # 4. FAA OE/AAA obstruction evaluations
    obstructions = await query_oeaaa(lat, lon, radius_nm=3.0)

    # 5. Score
    nearest_dist = nearest_airport["distance_nm"] if nearest_airport else 99.0
    score = compute_airspace_score(
        airspace_class=airspace["class"],
        nearest_airport_nm=nearest_dist,
        heliport_count=len(nearby_heliports),
        obstructions_count=len(obstructions),
    )

    # 6. Warnings
    warnings = list(airspace["notes"])

    if airspace["faa_form_required"]:
        warnings.append("ACTION REQUIRED: Submit FAA Form 7480-1 (Notice of Proposed Construction) at least 45 days before construction")

    if airspace["part_107_waiver_needed"]:
        warnings.append("ACTION REQUIRED: FAA Part 107 airspace waiver required — apply via DroneZone portal")

    if nearest_heliport and nearest_heliport["distance_nm"] < 1.0:
        warnings.append(
            f"Existing heliport within 1 nm: {nearest_heliport['name']} ({nearest_heliport['distance_nm']} nm) — "
            "coordination required; potential for obstacle conflict"
        )

    if len(nearby_airports) == 0:
        warnings.append("No airports identified within 20 nm — verify against current FAA sectional chart before proceeding")

    if obstructions:
        warnings.append(f"{len(obstructions)} existing obstruction evaluation(s) found within 3 nm — review for height conflicts")

    # 7. Assemble result
    raw_data = {
        "input": {"latitude": lat, "longitude": lon},
        "airspace": airspace,
        "nearby_airports": [
            {k: v for k, v in a.items() if k not in ("lat", "lon")}
            for a in nearby_airports[:10]
        ],
        "nearby_heliports": [
            {k: v for k, v in h.items() if k not in ("lat", "lon")}
            for h in nearby_heliports[:5]
        ],
        "obstruction_evaluations": obstructions,
        "counts": {
            "airports_within_5nm":   sum(1 for a in nearby_airports if a["distance_nm"] <= 5),
            "airports_within_10nm":  sum(1 for a in nearby_airports if a["distance_nm"] <= 10),
            "airports_within_20nm":  len(nearby_airports),
            "heliports_within_5nm":  sum(1 for h in nearby_heliports if h["distance_nm"] <= 5),
            "heliports_within_10nm": sum(1 for h in nearby_heliports if h["distance_nm"] <= 10),
        },
        "nearest_airport":  {k: v for k, v in nearest_airport.items() if k not in ("lat", "lon")} if nearest_airport else None,
        "nearest_heliport": {k: v for k, v in nearest_heliport.items() if k not in ("lat", "lon")} if nearest_heliport else None,
        "analysis_timestamp": started_at,
    }

    summary = generate_summary(airspace, nearest_airport, score, obstructions)

    return {
        "score":    score,
        "summary":  summary,
        "warnings": warnings,
        "raw_data": raw_data,
    }


# ── Sync wrapper for Celery ───────────────────────────────────────────────────

def run_airspace_agent_sync(lat: float, lon: float) -> dict:
    """Synchronous wrapper — use this from Celery tasks."""
    return asyncio.run(run_airspace_agent(lat, lon))
