"""
SkyBase Agent 7: Noise & Environmental Analysis Agent
=======================================================
Assesses noise sensitivity and environmental constraints at the vertiport site.

Data sources (all free/no-auth):
  - OpenFEMA NFHL API: flood zone classification
      https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query
  - OpenStreetMap Overpass API: noise-sensitive uses within 500 m
      (schools, hospitals, places of worship, residential)

Scoring (0–100):
  90–100 = Industrial area, Zone X (no flood risk), no sensitive uses within 500 m
   75–89 = Commercial area, Zone X, few sensitive uses
   60–74 = Mixed area, Zone X but residential within 500 m
   40–59 = Zone AE (100-year flood), moderate sensitive uses
    0–39 = Zone A/AO (high flood risk), many sensitive uses or historic district
"""

import asyncio
import math
import httpx
from datetime import datetime, timezone
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FEMA_NFHL_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)
SEARCH_RADIUS_M = 500

# FEMA flood zone descriptions
FLOOD_ZONE_INFO = {
    # High risk
    "A":   {"risk": "high",     "desc": "100-year flood zone (no Base Flood Elevation)"},
    "AE":  {"risk": "high",     "desc": "100-year flood zone with Base Flood Elevation"},
    "AH":  {"risk": "high",     "desc": "100-year shallow flooding (ponding) area"},
    "AO":  {"risk": "high",     "desc": "100-year shallow flooding (sheet flow) — 1–3 ft depth"},
    "AR":  {"risk": "high",     "desc": "100-year flood zone — levee restoration in progress"},
    "A99": {"risk": "high",     "desc": "100-year flood zone — protected by levee under construction"},
    # Moderate/undetermined
    "B":   {"risk": "moderate", "desc": "0.2% annual chance flood zone (500-year)"},
    "X":   {"risk": "minimal",  "desc": "Minimal flood risk — outside 500-year floodplain"},
    "X500": {"risk": "moderate", "desc": "Moderate risk — 500-year floodplain"},
    # Coastal
    "V":   {"risk": "high",     "desc": "Coastal high-hazard area — wave action risk"},
    "VE":  {"risk": "high",     "desc": "Coastal high-hazard area with Base Flood Elevation"},
    # Unknown
    "D":   {"risk": "unknown",  "desc": "Unstudied area — flood risk undetermined"},
}

# Noise-sensitive OSM tags to search for
NOISE_SENSITIVE_TAGS = {
    "amenity": ["school", "hospital", "clinic", "place_of_worship", "nursing_home", "kindergarten"],
    "landuse": ["residential", "cemetery"],
    "building": ["hospital", "school", "church"],
}


# ── Haversine helper ──────────────────────────────────────────────────────────

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── FEMA NFHL flood zone query ────────────────────────────────────────────────

async def query_fema_flood_zone(lat: float, lon: float) -> dict:
    """
    Query OpenFEMA NFHL API for flood zone at the given point.
    Returns flood zone code and metadata, or error if unavailable.
    """
    try:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DEPTH",
            "f": "json",
            "inSR": "4326",
            "outSR": "4326",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(FEMA_NFHL_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                if features:
                    attrs = features[0].get("attributes", {})
                    zone = attrs.get("FLD_ZONE", "X") or "X"
                    zone = zone.strip().upper()
                    sfha = attrs.get("SFHA_TF", "F")   # T = Special Flood Hazard Area
                    bfe   = attrs.get("STATIC_BFE")
                    depth = attrs.get("DEPTH")
                    return {
                        "flood_zone": zone,
                        "sfha": sfha == "T",
                        "base_flood_elevation": bfe,
                        "depth_ft": depth,
                        "error": None,
                    }
                else:
                    # No features returned — likely Zone X (outside mapped flood area)
                    return {
                        "flood_zone": "X",
                        "sfha": False,
                        "base_flood_elevation": None,
                        "depth_ft": None,
                        "error": None,
                        "note": "No FEMA NFHL features at this location — likely Zone X (minimal risk)",
                    }
    except Exception as e:
        pass

    return {
        "flood_zone": None,
        "sfha": None,
        "base_flood_elevation": None,
        "depth_ft": None,
        "error": "FEMA NFHL API unavailable",
    }


# ── Overpass noise-sensitive uses ─────────────────────────────────────────────

async def query_overpass_noise(lat: float, lon: float) -> dict:
    """
    Query OSM Overpass for noise-sensitive land uses within SEARCH_RADIUS_M.
    Returns lists of schools, hospitals, residential areas, places of worship.
    """
    # Build a compound query for all noise-sensitive tags
    tag_filters = []
    for key, values in NOISE_SENSITIVE_TAGS.items():
        for val in values:
            tag_filters.append(f'node["{key}"="{val}"](around:{SEARCH_RADIUS_M},{lat},{lon});')
            tag_filters.append(f'way["{key}"="{val}"](around:{SEARCH_RADIUS_M},{lat},{lon});')

    query = f"""
[out:json][timeout:15];
(
  {''.join(tag_filters)}
);
out body; >; out skel qt;
""".strip()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            return {"elements": resp.json().get("elements", []), "error": None}
    except Exception as e:
        return {"elements": [], "error": str(e)}


def parse_noise_elements(lat: float, lon: float, elements: list) -> dict:
    """
    Parse and categorize noise-sensitive elements by type.
    """
    schools     = []
    hospitals   = []
    residential = []
    worship     = []
    other       = []

    for el in elements:
        tags = el.get("tags", {})
        el_type = el.get("type", "")

        if el_type == "node":
            el_lat = el.get("lat")
            el_lon = el.get("lon")
        elif el_type == "way":
            bounds = el.get("bounds", {})
            if bounds:
                el_lat = (bounds["minlat"] + bounds["maxlat"]) / 2
                el_lon = (bounds["minlon"] + bounds["maxlon"]) / 2
            else:
                continue
        else:
            continue

        if el_lat is None or el_lon is None:
            continue

        dist = haversine_m(lat, lon, el_lat, el_lon)
        name = tags.get("name", "Unnamed")
        amenity  = tags.get("amenity", "")
        landuse  = tags.get("landuse", "")
        building = tags.get("building", "")

        entry = {
            "id":         el.get("id"),
            "name":       name,
            "amenity":    amenity,
            "landuse":    landuse,
            "building":   building,
            "distance_m": round(dist, 1),
        }

        if amenity in ("school", "kindergarten") or building == "school":
            schools.append(entry)
        elif amenity in ("hospital", "clinic", "nursing_home") or building == "hospital":
            hospitals.append(entry)
        elif landuse == "residential":
            residential.append(entry)
        elif amenity == "place_of_worship" or building == "church":
            worship.append(entry)
        else:
            other.append(entry)

    # Sort each list by distance
    for lst in (schools, hospitals, residential, worship, other):
        lst.sort(key=lambda x: x["distance_m"])

    return {
        "schools":     schools,
        "hospitals":   hospitals,
        "residential": residential,
        "worship":     worship,
        "other":       other,
        "total_sensitive_uses": len(schools) + len(hospitals) + len(residential) + len(worship),
    }


# ── Scoring ────────────────────────────────────────────────────────────────────

def compute_noise_score(flood_zone: Optional[str], noise_data: dict) -> tuple[int, list[str]]:
    """
    Returns (score, warnings) based on flood zone and noise-sensitive uses.
    """
    warnings = []

    # Flood zone scoring
    zone = (flood_zone or "X").strip().upper()
    zone_info = FLOOD_ZONE_INFO.get(zone, {"risk": "unknown", "desc": "Unknown zone"})
    flood_risk = zone_info["risk"]

    if flood_risk == "minimal":
        flood_score = 95
    elif flood_risk == "moderate":
        flood_score = 70
    elif flood_risk == "high":
        flood_score = 30
    else:
        flood_score = 55  # Unknown

    # Add flood zone warning
    if flood_zone:
        desc = zone_info["desc"]
        if flood_risk == "high":
            warnings.append(
                f"FEMA flood zone {zone}: {desc} — flood-proofing required; "
                "NFIP flood insurance mandatory; elevation certificate needed"
            )
        elif flood_risk == "moderate":
            warnings.append(
                f"FEMA flood zone {zone}: {desc} — flood insurance recommended; "
                "verify grading and drainage design"
            )
        else:
            # Zone X — minimal risk, no warning needed unless SFHA nearby
            pass
    else:
        warnings.append(
            "Flood zone data unavailable — manual FEMA FIRM map review required "
            "(visit msc.fema.gov to check the Flood Insurance Rate Map)"
        )

    # Noise-sensitive use scoring
    schools     = noise_data["schools"]
    hospitals   = noise_data["hospitals"]
    residential = noise_data["residential"]
    total       = noise_data["total_sensitive_uses"]

    noise_penalty = 0

    if schools:
        closest = schools[0]["distance_m"]
        warnings.append(
            f"School within {SEARCH_RADIUS_M} m (nearest: {closest:.0f} m) — "
            "noise mitigation study required; operating hour restrictions likely"
        )
        noise_penalty += 15 if closest < 200 else 10

    if hospitals:
        closest = hospitals[0]["distance_m"]
        warnings.append(
            f"Hospital/clinic within {SEARCH_RADIUS_M} m (nearest: {closest:.0f} m) — "
            "strict noise operating hours may be imposed; coordinate with facility management"
        )
        noise_penalty += 15 if closest < 200 else 10

    if residential:
        closest = residential[0]["distance_m"]
        if closest < 200:
            warnings.append(
                f"Residential area within 200 m ({closest:.0f} m) — "
                "community opposition likely; noise analysis required per FAA Part 150"
            )
            noise_penalty += 20
        else:
            warnings.append(
                f"Residential area within {SEARCH_RADIUS_M} m ({closest:.0f} m) — "
                "noise analysis recommended per FAA Part 150"
            )
            noise_penalty += 10

    if total > 5:
        warnings.append(
            f"High density of noise-sensitive uses ({total} identified within {SEARCH_RADIUS_M} m) — "
            "community engagement plan required before permitting"
        )
        noise_penalty += 10

    # Combined score
    score = max(0, min(100, flood_score - noise_penalty))

    return score, warnings


# ── Summary generator ─────────────────────────────────────────────────────────

def generate_noise_summary(score: int, flood_zone: Optional[str],
                            noise_data: dict, lat: float, lon: float) -> str:
    zone = flood_zone or "Unknown"
    zone_info = FLOOD_ZONE_INFO.get(zone.upper(), {"risk": "unknown", "desc": "Unknown"})
    total = noise_data["total_sensitive_uses"]
    schools    = len(noise_data["schools"])
    hospitals  = len(noise_data["hospitals"])
    residential = len(noise_data["residential"])

    flood_txt = f"FEMA flood zone {zone} ({zone_info['desc']})"

    if score >= 85:
        return (
            f"Excellent noise and environmental profile. {flood_txt} — minimal flood risk. "
            f"{total} noise-sensitive uses within {SEARCH_RADIUS_M} m. "
            f"Standard vertiport noise analysis is still recommended, but no major "
            f"community opposition or environmental hurdles are anticipated."
        )
    elif score >= 70:
        return (
            f"Good noise and environmental profile. {flood_txt}. "
            f"{total} noise-sensitive uses within {SEARCH_RADIUS_M} m "
            f"({schools} school(s), {hospitals} hospital(s), {residential} residential area(s)). "
            f"A noise study and community outreach plan are recommended before permitting."
        )
    elif score >= 50:
        return (
            f"Moderate noise and environmental concerns. {flood_txt}. "
            f"{total} noise-sensitive uses within {SEARCH_RADIUS_M} m "
            f"({schools} school(s), {hospitals} hospital(s), {residential} residential area(s)). "
            f"A formal FAA Part 150 noise analysis and community engagement plan are required."
        )
    elif score >= 30:
        return (
            f"Significant environmental and noise challenges. {flood_txt} — elevated flood risk. "
            f"{total} noise-sensitive uses within {SEARCH_RADIUS_M} m. "
            f"Flood-proofing, NFIP insurance, and a comprehensive noise mitigation plan will be "
            f"required. Operating hour restrictions are likely."
        )
    else:
        return (
            f"High environmental and noise risk. {flood_txt} — high flood hazard. "
            f"{total} noise-sensitive uses within {SEARCH_RADIUS_M} m. "
            f"This site faces significant environmental and community challenges. "
            f"An alternative site with lower flood risk and fewer sensitive receptors is "
            f"strongly recommended."
        )


# ── Main agent function ────────────────────────────────────────────────────────

async def run_noise_agent(lat: float, lon: float) -> dict:
    """
    Primary entry point for the Noise & Environmental Agent.

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

    # 1. Run FEMA + Overpass queries in parallel
    fema_result, overpass_result = await asyncio.gather(
        query_fema_flood_zone(lat, lon),
        query_overpass_noise(lat, lon),
    )

    # 2. Parse noise elements
    noise_data = parse_noise_elements(lat, lon, overpass_result["elements"])

    # 3. Get flood zone
    flood_zone = fema_result.get("flood_zone")

    # 4. Score
    score, warnings = compute_noise_score(flood_zone, noise_data)

    # 5. Add Overpass error warning if needed
    if overpass_result["error"] and not overpass_result["elements"]:
        warnings.append(
            "Noise-sensitive use data unavailable (Overpass API error) — "
            "manual review of adjacent land uses required"
        )

    # 6. Always add standard Part 150 note
    warnings.append(
        "FAA Part 150 Noise Compatibility Study recommended for all vertiport sites near "
        "populated areas — identifies noise-sensitive receptors and mitigation measures"
    )

    # 7. Summary
    summary = generate_noise_summary(score, flood_zone, noise_data, lat, lon)

    # 8. Get flood zone info
    fz_upper = (flood_zone or "X").upper()
    fz_info = FLOOD_ZONE_INFO.get(fz_upper, {"risk": "unknown", "desc": "Unknown"})

    # 9. Assemble raw_data
    raw_data = {
        "input": {
            "latitude": lat,
            "longitude": lon,
            "search_radius_m": SEARCH_RADIUS_M,
        },
        "flood_zone": flood_zone,
        "flood_zone_description": fz_info["desc"],
        "flood_risk_level": fz_info["risk"],
        "sfha": fema_result.get("sfha"),
        "base_flood_elevation": fema_result.get("base_flood_elevation"),
        "fema_api_error": fema_result.get("error"),
        "fema_note": fema_result.get("note"),
        "noise_sensitive_uses": {
            "total": noise_data["total_sensitive_uses"],
            "schools":     noise_data["schools"][:5],
            "hospitals":   noise_data["hospitals"][:5],
            "residential": noise_data["residential"][:3],
            "worship":     noise_data["worship"][:3],
            "other":       noise_data["other"][:3],
        },
        "overpass_api_error": overpass_result["error"],
        "data_sources": [
            "OpenFEMA NFHL (National Flood Hazard Layer) ArcGIS REST API",
            "OpenStreetMap Overpass API",
        ],
        "references": {
            "fema_firm_map": "https://msc.fema.gov/portal/search",
            "faa_part_150":  "https://www.faa.gov/airports/environmental/airport_noise/part_150",
        },
        "analysis_timestamp": started_at,
    }

    return {
        "score": score,
        "summary": summary,
        "warnings": warnings,
        "raw_data": raw_data,
    }


# ── Sync wrapper for Celery ────────────────────────────────────────────────────

def run_noise_agent_sync(lat: float, lon: float) -> dict:
    """Synchronous wrapper — use this from Celery tasks."""
    return asyncio.run(run_noise_agent(lat, lon))
