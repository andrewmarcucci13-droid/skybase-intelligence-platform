"""
SkyBase Agent 3: Power Grid Analysis Agent
============================================
Assesses electrical infrastructure availability near the vertiport site.

Data sources (all free/no-auth):
  - NREL Utility Rates API (DEMO_KEY — low-volume, no registration):
      https://developer.nrel.gov/api/utility_rates/v3.json
  - OpenStreetMap Overpass API:
      Substations, power lines, and transformers within 2 km

eVTOL charging requirement: 1–2 MW per pad.
Grid upgrade timeline if capacity constrained: 12–36 months.

Scoring (0–100):
  90–100 = Substation ≤ 200 m AND power lines ≤ 100 m
   75–89 = Substation ≤ 500 m, power lines ≤ 200 m
   60–74 = Substation ≤ 1 km, power infrastructure present
   40–59 = No nearby substation; grid upgrade likely
   20–39 = No power infrastructure within 2 km; major investment needed
    0–19 = Remote/off-grid; microgrid required
"""

import asyncio
import math
import httpx
from datetime import datetime, timezone
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NREL_RATES_URL = "https://developer.nrel.gov/api/utility_rates/v3.json"
NREL_DEMO_KEY = "DEMO_KEY"

# Distances in metres
SUBSTATION_CLOSE_M = 200
SUBSTATION_NEAR_M = 500
SUBSTATION_MEDIUM_M = 1000
SUBSTATION_FAR_M = 2000
POWER_LINE_CLOSE_M = 100
POWER_LINE_NEAR_M = 200
POWER_LINE_FAR_M = 500


# ── Haversine helper ──────────────────────────────────────────────────────────

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── NREL Utility Rates ────────────────────────────────────────────────────────

async def query_nrel_utility_rates(lat: float, lon: float) -> dict:
    """
    Query NREL Utility Rates API for utility name and commercial rate.
    Uses DEMO_KEY — rate limited but functional for low-volume use.
    Returns dict with utility_name and commercial_rate_per_kwh (or None on error).
    """
    try:
        params = {
            "api_key": NREL_DEMO_KEY,
            "lat": lat,
            "lon": lon,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(NREL_RATES_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                outputs = data.get("outputs", {})
                utility_name = outputs.get("utility_name", "Unknown Utility")
                # Commercial rate — may be a list or a single value
                commercial = outputs.get("commercial", None)
                if isinstance(commercial, list) and commercial:
                    rate = float(commercial[0])
                elif isinstance(commercial, (int, float)):
                    rate = float(commercial)
                else:
                    rate = None
                return {
                    "utility_name": utility_name,
                    "commercial_rate_per_kwh": rate,
                    "error": None,
                }
    except Exception as e:
        pass
    return {
        "utility_name": "Unknown",
        "commercial_rate_per_kwh": None,
        "error": "NREL API unavailable",
    }


# ── Overpass power infrastructure ────────────────────────────────────────────

async def query_overpass_power(lat: float, lon: float) -> dict:
    """
    Query OSM Overpass for substations, power lines, and transformers within 2 km.
    Returns lists of elements with their distances.
    """
    query = f"""
[out:json][timeout:15];
(
  node["power"="substation"](around:2000,{lat},{lon});
  way["power"="substation"](around:2000,{lat},{lon});
  way["power"="line"](around:500,{lat},{lon});
  node["power"="transformer"](around:500,{lat},{lon});
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


def parse_power_elements(lat: float, lon: float, elements: list) -> dict:
    """
    Parse Overpass elements, compute distances, and extract power infrastructure summary.
    """
    substations = []
    power_lines = []
    transformers = []

    for el in elements:
        tags = el.get("tags", {})
        el_type = el.get("type", "")
        power_tag = tags.get("power", "")

        # Get coordinates — nodes have lat/lon directly; ways have a centroid approx
        if el_type == "node":
            el_lat = el.get("lat")
            el_lon = el.get("lon")
        elif el_type == "way":
            # Use bounding box center if available, else skip
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

        entry = {
            "id": el.get("id"),
            "type": el_type,
            "power": power_tag,
            "name": tags.get("name", ""),
            "voltage": tags.get("voltage", ""),
            "distance_m": round(dist, 1),
        }

        if power_tag == "substation":
            substations.append(entry)
        elif power_tag == "line":
            power_lines.append(entry)
        elif power_tag == "transformer":
            transformers.append(entry)

    # Sort by distance
    substations.sort(key=lambda x: x["distance_m"])
    power_lines.sort(key=lambda x: x["distance_m"])
    transformers.sort(key=lambda x: x["distance_m"])

    nearest_sub = substations[0]["distance_m"] if substations else None
    nearest_line = power_lines[0]["distance_m"] if power_lines else None
    lines_within_500m = sum(1 for l in power_lines if l["distance_m"] <= 500)

    return {
        "substations": substations[:5],
        "power_lines": power_lines[:5],
        "transformers": transformers[:5],
        "nearest_substation_m": nearest_sub,
        "nearest_power_line_m": nearest_line,
        "power_lines_within_500m": lines_within_500m,
    }


# ── Scoring ────────────────────────────────────────────────────────────────────

def compute_power_score(nearest_sub: Optional[float], nearest_line: Optional[float],
                        lines_within_500m: int) -> tuple[int, str, str]:
    """
    Returns (score, estimated_upgrade_cost, estimated_upgrade_months).
    """
    if nearest_sub is None and nearest_line is None:
        # No data at all — treat as remote
        return (25, "$8M–$16M", "24–36+")

    sub = nearest_sub if nearest_sub is not None else 99999.0
    line = nearest_line if nearest_line is not None else 99999.0

    # Excellent: substation very close + power lines on-site
    if sub <= SUBSTATION_CLOSE_M and line <= POWER_LINE_CLOSE_M:
        return (92, "None required", "0–6")

    # Very good: substation close
    if sub <= SUBSTATION_NEAR_M and line <= POWER_LINE_NEAR_M:
        return (82, "$500K–$2M", "6–12")

    # Good: substation within 1 km
    if sub <= SUBSTATION_MEDIUM_M and lines_within_500m > 0:
        return (68, "$500K–$2M", "6–12")

    # Fair: substation within 2 km
    if sub <= SUBSTATION_FAR_M:
        return (50, "$2M–$8M", "12–24")

    # No substation found; power lines exist
    if lines_within_500m > 0:
        return (40, "$2M–$8M", "12–24")

    # No infrastructure at all within search area
    return (22, "$8M–$16M", "24–36+")


# ── Summary generator ─────────────────────────────────────────────────────────

def generate_power_summary(score: int, utility_name: str, nearest_sub: Optional[float],
                           lines_within_500m: int, upgrade_cost: str,
                           upgrade_months: str, rate: Optional[float]) -> str:
    rate_txt = f"${rate:.3f}/kWh" if rate else "rate unavailable"
    utility_txt = utility_name if utility_name and utility_name != "Unknown" else "the local utility"
    sub_txt = f"{nearest_sub:.0f} m" if nearest_sub else "none found within 2 km"
    lines_txt = f"{lines_within_500m} power line(s)" if lines_within_500m > 0 else "no power lines"

    if score >= 85:
        return (
            f"Excellent power infrastructure at this site. The nearest electrical substation is "
            f"{sub_txt} away with {lines_txt} within 500 m. Served by {utility_txt} at "
            f"{rate_txt}. eVTOL charging (1–2 MW per pad) can likely be served with minimal "
            f"grid upgrades. Estimated infrastructure cost: {upgrade_cost}."
        )
    elif score >= 60:
        return (
            f"Adequate power infrastructure. Nearest substation is {sub_txt} with {lines_txt} "
            f"within 500 m. Served by {utility_txt} at {rate_txt}. A grid upgrade will likely "
            f"be required to support 1–2 MW eVTOL charging loads. Estimated upgrade: "
            f"{upgrade_cost}, timeline {upgrade_months} months."
        )
    elif score >= 40:
        return (
            f"Limited power infrastructure. Nearest substation is {sub_txt}. A significant "
            f"grid upgrade will be required to support eVTOL operations. Served by {utility_txt}. "
            f"Commercial rate: {rate_txt}. Estimated upgrade: {upgrade_cost}, "
            f"timeline {upgrade_months} months. Engage the utility early."
        )
    else:
        return (
            f"Power infrastructure is minimal or absent within 2 km. A new grid connection "
            f"or on-site microgrid ($2.1–$4M/MW) will be required for eVTOL charging. "
            f"Utility: {utility_txt}. Estimated infrastructure cost: {upgrade_cost}, "
            f"timeline {upgrade_months} months. This is a significant project risk."
        )


# ── Main agent function ────────────────────────────────────────────────────────

async def run_power_agent(lat: float, lon: float) -> dict:
    """
    Primary entry point for the Power Grid Agent.

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

    # 1. Run NREL + Overpass queries in parallel
    nrel_result, overpass_result = await asyncio.gather(
        query_nrel_utility_rates(lat, lon),
        query_overpass_power(lat, lon),
    )

    # 2. Parse Overpass data
    power_data = parse_power_elements(lat, lon, overpass_result["elements"])
    nearest_sub = power_data["nearest_substation_m"]
    nearest_line = power_data["nearest_power_line_m"]
    lines_within_500m = power_data["power_lines_within_500m"]

    utility_name = nrel_result["utility_name"]
    commercial_rate = nrel_result["commercial_rate_per_kwh"]

    # 3. Score
    score, upgrade_cost, upgrade_months = compute_power_score(
        nearest_sub, nearest_line, lines_within_500m
    )

    # 4. Warnings
    warnings = []

    if nearest_sub is None:
        warnings.append(
            "No electrical substation found within 2 km — major grid investment required; "
            "contact utility for capacity study ($2M–$8M, 12–24 months)"
        )
    elif nearest_sub > SUBSTATION_MEDIUM_M:
        warnings.append(
            f"Nearest substation is {nearest_sub:.0f} m away — "
            "grid upgrade likely required to support 1–2 MW eVTOL charging loads"
        )

    if lines_within_500m == 0:
        warnings.append(
            "No power lines within 500 m — new distribution line required; "
            "coordinate with local utility for extension"
        )

    if upgrade_cost not in ("None required",):
        warnings.append(
            f"Estimated grid upgrade cost: {upgrade_cost} | Timeline: {upgrade_months} months — "
            "begin utility coordination immediately; grid upgrades are often on the critical path"
        )

    warnings.append(
        "eVTOL charging requirement: 1–2 MW per pad (Joby S4 requires ~1 MW/60-min charge); "
        "confirm grid capacity with utility before finalizing site selection"
    )

    if overpass_result["error"] and not overpass_result["elements"]:
        warnings.append(
            f"Power infrastructure data unavailable (Overpass API error) — "
            "manual utility mapping required"
        )

    # 5. Summary
    summary = generate_power_summary(
        score, utility_name, nearest_sub, lines_within_500m,
        upgrade_cost, upgrade_months, commercial_rate
    )

    # 6. Assemble raw_data
    raw_data = {
        "input": {"latitude": lat, "longitude": lon},
        "utility_name": utility_name,
        "commercial_rate_per_kwh": commercial_rate,
        "nearest_substation_m": nearest_sub,
        "nearest_power_line_m": nearest_line,
        "power_lines_within_500m": lines_within_500m,
        "estimated_upgrade_cost": upgrade_cost,
        "estimated_upgrade_months": upgrade_months,
        "charging_infrastructure_note": (
            "eVTOL charging requires 1–2 MW per pad. Grid-tied cost: $500K–$2M per pad if "
            "grid available. Microgrid approach: $2.1–$4M per MW. "
            "Grid upgrade (if needed): $8M–$16M one-time infrastructure cost."
        ),
        "substations_nearby": power_data["substations"],
        "power_lines_nearby": power_data["power_lines"],
        "transformers_nearby": power_data["transformers"],
        "nrel_api_error": nrel_result.get("error"),
        "overpass_api_error": overpass_result["error"],
        "analysis_timestamp": started_at,
        "data_sources": ["NREL Utility Rates API (DEMO_KEY)", "OpenStreetMap Overpass API"],
    }

    return {
        "score": score,
        "summary": summary,
        "warnings": warnings,
        "raw_data": raw_data,
    }


# ── Sync wrapper for Celery ────────────────────────────────────────────────────

def run_power_agent_sync(lat: float, lon: float) -> dict:
    """Synchronous wrapper — use this from Celery tasks."""
    return asyncio.run(run_power_agent(lat, lon))
