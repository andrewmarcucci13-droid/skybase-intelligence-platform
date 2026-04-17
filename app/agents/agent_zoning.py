"""
SkyBase Agent 2: Zoning Analysis Agent
========================================
Determines if vertiport use is permitted at the site based on land-use
classification from OpenStreetMap Overpass API data.

Data source:
  - OpenStreetMap Overpass API (no auth required)
    Queries landuse, aeroway, and building tags within 500 m of the site.

Scoring (0–100):
  90–100 = aeroway — aviation use already permitted
   80–89 = industrial — generally permissive for aviation/logistics
   70–79 = commercial/retail — conditional use permit likely needed
   50–69 = mixed_use / unknown — significant permitting research needed
   30–49 = residential — CUP + community opposition likely
    0–29 = parks, nature reserves, historic — likely prohibited
"""

import asyncio
import httpx
from datetime import datetime, timezone
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SEARCH_RADIUS_M = 500

# Tag → category mapping (order matters — first match wins)
LANDUSE_SCORES = {
    # Aeroway tags — best possible
    "aeroway": 95,
    # Industrial
    "industrial": 85,
    "logistics": 85,
    "depot": 82,
    "port": 82,
    # Commercial
    "commercial": 75,
    "retail": 72,
    "office": 72,
    "business_park": 74,
    # Mixed / unclear
    "mixed": 60,
    "brownfield": 58,
    "greenfield": 55,
    "construction": 55,
    # Residential
    "residential": 40,
    "apartments": 38,
    "housing": 37,
    # Parks / recreation / protected
    "park": 25,
    "recreation_ground": 25,
    "grass": 22,
    "forest": 20,
    "nature_reserve": 10,
    "conservation": 10,
    "historic": 15,
    "cemetery": 10,
    "religious": 20,
}


# ── Overpass query ─────────────────────────────────────────────────────────────

async def query_overpass_zoning(lat: float, lon: float) -> dict:
    """
    Fetch landuse, aeroway, and building tags from OSM Overpass within
    SEARCH_RADIUS_M metres of the site.

    Returns a dict with lists of tags found and raw element counts.
    """
    query = f"""
[out:json][timeout:15];
(
  way["landuse"](around:{SEARCH_RADIUS_M},{lat},{lon});
  way["aeroway"](around:{SEARCH_RADIUS_M},{lat},{lon});
  node["aeroway"](around:{SEARCH_RADIUS_M},{lat},{lon});
  way["building"](around:{SEARCH_RADIUS_M},{lat},{lon});
);
out body; >; out skel qt;
""".strip()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            return {"elements": elements, "error": None}
    except Exception as e:
        return {"elements": [], "error": str(e)}


# ── Tag extraction ─────────────────────────────────────────────────────────────

def extract_tags(elements: list) -> dict:
    """
    Aggregate all OSM tags from the returned elements.
    Returns summary dicts for landuse, aeroway, and building tags.
    """
    landuse_tags = {}
    aeroway_tags = {}
    building_tags = {}

    for el in elements:
        tags = el.get("tags", {})
        if not tags:
            continue

        lu = tags.get("landuse", "")
        if lu:
            landuse_tags[lu] = landuse_tags.get(lu, 0) + 1

        aw = tags.get("aeroway", "")
        if aw:
            aeroway_tags[aw] = aeroway_tags.get(aw, 0) + 1

        bld = tags.get("building", "")
        if bld:
            building_tags[bld] = building_tags.get(bld, 0) + 1

    return {
        "landuse": landuse_tags,
        "aeroway": aeroway_tags,
        "building": building_tags,
    }


# ── Scoring ────────────────────────────────────────────────────────────────────

def compute_zoning_score(tags: dict) -> tuple[int, str, list[str]]:
    """
    Derive a zoning score (0–100), detected_type string, and list of warnings.
    Returns (score, detected_type, warnings).
    """
    warnings = []
    landuse = tags["landuse"]
    aeroway = tags["aeroway"]
    building = tags["building"]

    # Aeroway takes priority — aviation use already present
    if aeroway:
        types = ", ".join(aeroway.keys())
        warnings.append("Aeroway/aviation use detected — vertiport likely permitted by right")
        return 95, f"aeroway ({types})", warnings

    # No OSM data at all
    if not landuse and not aeroway and not building:
        warnings.append(
            "No zoning data available — manual municipal zoning research required"
        )
        return 50, "unknown", warnings

    # Score each detected landuse tag, take the highest-scoring one
    best_score = 0
    best_type = "unknown"

    for lu_tag in landuse:
        tag_lower = lu_tag.lower()
        for pattern, score in LANDUSE_SCORES.items():
            if pattern in tag_lower:
                if score > best_score:
                    best_score = score
                    best_type = lu_tag
                break

    # Check building tags if no landuse found
    if best_score == 0 and building:
        bld_types = list(building.keys())
        for bld in bld_types:
            b_lower = bld.lower()
            if any(x in b_lower for x in ("warehouse", "industrial", "hangar")):
                best_score = 82
                best_type = f"building:{bld}"
                break
            elif any(x in b_lower for x in ("commercial", "office", "retail")):
                best_score = 72
                best_type = f"building:{bld}"
                break
            elif any(x in b_lower for x in ("residential", "apartments", "house")):
                best_score = 40
                best_type = f"building:{bld}"
                break

    # If still zero, we found tags but none matched our scoring list
    if best_score == 0:
        detected = list(landuse.keys())[:3] + list(building.keys())[:2]
        best_type = detected[0] if detected else "unknown"
        best_score = 55  # Unknown — treat as mixed

    # Generate warnings based on score
    if best_score >= 90:
        warnings.append("Industrial zoning — most permissive for vertiport installation")
    elif best_score >= 80:
        warnings.append("Industrial zoning — most permissive for vertiport installation")
    elif best_score >= 70:
        warnings.append(
            "Commercial zoning detected — conditional use permit likely needed (3–12 months)"
        )
    elif best_score >= 50:
        warnings.append(
            "Mixed or unclassified zoning — significant permitting research required"
        )
    elif best_score >= 30:
        warnings.append(
            "Residential zoning detected — conditional use permit required (6–18 months)"
        )
    else:
        warnings.append(
            "Park, conservation, or historic land use detected — vertiport likely prohibited; "
            "alternative site strongly recommended"
        )

    return best_score, best_type, warnings


# ── Summary generator ──────────────────────────────────────────────────────────

def generate_zoning_summary(score: int, zoning_type: str, tags: dict, radius_m: int) -> str:
    aeroway = tags.get("aeroway", {})
    landuse = tags.get("landuse", {})

    if aeroway:
        types = ", ".join(aeroway.keys())
        return (
            f"The site is within {radius_m} m of existing aeroway infrastructure "
            f"({types}). Aviation operations are already established here, making "
            f"vertiport permitting significantly easier. FAA Form 7480-1 is still "
            f"required, but by-right approval is likely."
        )

    if not landuse and not aeroway:
        return (
            f"No OSM zoning data was found within {radius_m} m of the site. "
            f"Score defaulted to 50 (moderate). Manual review of municipal zoning maps "
            f"is required before proceeding. Contact the local planning department to "
            f"confirm the zoning classification."
        )

    if score >= 80:
        return (
            f"The site area is classified as '{zoning_type}' land use — the most permissive "
            f"category for vertiport installation. Most industrial zones allow aviation-related "
            f"infrastructure by right or with a minor use permit. Verify specific municipal code."
        )
    elif score >= 70:
        return (
            f"The site is in a '{zoning_type}' zone. Vertiport use will likely require a "
            f"Conditional Use Permit (CUP). Budget 3–12 months for the permitting process and "
            f"expect public hearings. Engage a local land-use attorney early."
        )
    elif score >= 50:
        return (
            f"The site zoning ('{zoning_type}') is mixed or unclear. Significant permitting "
            f"research is needed. A pre-application meeting with the local planning department "
            f"is strongly recommended before investing further."
        )
    elif score >= 30:
        return (
            f"The site falls in a '{zoning_type}' residential zone. Vertiport use will require "
            f"a Conditional Use Permit with community notification, likely triggering opposition. "
            f"Budget 6–18 months and $50,000–$200,000 in permitting costs. Consider alternative sites."
        )
    else:
        return (
            f"The detected land use ('{zoning_type}') is highly restrictive — parks, nature "
            f"reserves, or historic districts typically prohibit aviation infrastructure. "
            f"An alternative site is strongly recommended."
        )


# ── Main agent function ────────────────────────────────────────────────────────

async def run_zoning_agent(lat: float, lon: float) -> dict:
    """
    Primary entry point for the Zoning Agent.

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

    # 1. Query Overpass API
    overpass_result = await query_overpass_zoning(lat, lon)
    elements = overpass_result["elements"]
    api_error = overpass_result["error"]

    # 2. Extract tags
    tags = extract_tags(elements)

    # 3. Score
    if api_error and not elements:
        score = 50
        zoning_type = "unknown"
        warnings = [
            "Zoning data unavailable — manual research required",
            f"Overpass API error: {api_error}",
        ]
    else:
        score, zoning_type, warnings = compute_zoning_score(tags)

    # 4. Summary
    summary = generate_zoning_summary(score, zoning_type, tags, SEARCH_RADIUS_M)

    # 5. Assemble raw_data
    raw_data = {
        "input": {"latitude": lat, "longitude": lon, "search_radius_m": SEARCH_RADIUS_M},
        "detected_zoning_type": zoning_type,
        "tags_found": tags,
        "element_count": len(elements),
        "api_error": api_error,
        "analysis_timestamp": started_at,
        "data_source": "OpenStreetMap Overpass API",
        "notes": [
            "OSM data may not reflect current municipal zoning — always verify with local authority",
            "Zoning classifications are approximations based on OSM land-use tags",
        ],
    }

    return {
        "score": score,
        "summary": summary,
        "warnings": warnings,
        "raw_data": raw_data,
    }


# ── Sync wrapper for Celery ────────────────────────────────────────────────────

def run_zoning_agent_sync(lat: float, lon: float) -> dict:
    """Synchronous wrapper — use this from Celery tasks."""
    return asyncio.run(run_zoning_agent(lat, lon))
