"""
SkyBase Agent 4: Structural Analysis Agent
===========================================
Rules-based structural feasibility assessment for vertiport installation.
No external API — uses FAA EB 105A requirements and industry load data.

FAA EB 105A (Engineering Brief 105A) key requirements:
  - TLOF (Touchdown/Liftoff Area): minimum 100 ft × 100 ft (30.5 m × 30.5 m)
  - Dynamic load: 150% of aircraft Maximum Takeoff Weight (MTOW)
  - Joby S4 MTOW: ~4,500 lbs loaded → required: ~6,750 lbs
  - Load distributed over TLOF = ~3 psf minimum (but peak dynamic loads much higher)
  - Structural engineering assessment: $15,000–$50,000, 4–8 weeks

Scoring by property_type:
  95 = airport      (existing aviation-rated infrastructure)
  90 = ground       (purpose-built pad, no structural constraints)
  70 = garage       (modern concrete typically handles rooftop loads)
  65 = rooftop modern (2000+): likely sufficient
  40 = rooftop older (<2000): reinforcement likely required
  50 = unknown
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

TLOF_MIN_FT = 100          # ft × ft (FAA EB 105A)
TLOF_MIN_M  = 30.5         # metres × metres
TLOF_AREA_SQFT = TLOF_MIN_FT ** 2   # 10,000 sq ft

JOBY_S4_MTOW_LBS = 4500
DYNAMIC_LOAD_FACTOR = 1.5
REQUIRED_LOAD_LBS = int(JOBY_S4_MTOW_LBS * DYNAMIC_LOAD_FACTOR)   # 6,750 lbs

# Typical rooftop live-load capacities (psf = pounds per square foot)
ROOFTOP_CAPACITY_PRE_1980_PSF  = 40    # unknown — conservative assumption
ROOFTOP_CAPACITY_1980_2000_PSF = 62    # 50–75 range, midpoint
ROOFTOP_CAPACITY_2000_PLUS_PSF = 90    # 80–100 range, midpoint

# Distributed load over TLOF (10,000 sqft) — minimal if spread, but peak loads are point loads
REQUIRED_DISTRIBUTED_LOAD_PSF = 3.0   # conservative min; actual gear loads much higher


# ── Scoring table ─────────────────────────────────────────────────────────────

PROPERTY_TYPE_SCORES = {
    "airport":  95,
    "ground":   90,
    "garage":   70,
    "rooftop":  65,   # Default for rooftop; adjusted below for age
    "unknown":  50,
}

PROPERTY_TYPE_LABELS = {
    "airport":  "Airport — existing aviation-rated infrastructure",
    "ground":   "Ground-level — purpose-built pad (most cost-effective)",
    "garage":   "Rooftop parking structure — typically engineered for loads",
    "rooftop":  "Building rooftop",
    "unknown":  "Unknown property type",
}

COST_RANGES = {
    "airport":  "Minimal — existing aviation infrastructure ($0–$500K for eVTOL pad upgrades)",
    "ground":   "Low — ground pad construction ($800K–$3M)",
    "garage":   "Moderate — structural assessment + charging infra ($500K–$2M)",
    "rooftop_modern": "Moderate — structural assessment + possible reinforcement ($500K–$1.5M)",
    "rooftop_older":  "High — structural reinforcement likely required ($500K–$2M) + pad costs",
    "unknown":  "$500K–$3M depending on actual structural condition",
}


# ── Analysis function ─────────────────────────────────────────────────────────

def analyze_structural(property_type: str, year_built: Optional[int] = None) -> dict:
    """
    Rules-based structural assessment.

    Returns (score, cost_range, reinforcement_likely, notes)
    """
    pt = (property_type or "unknown").lower().strip()

    # Normalize common aliases
    if pt in ("roof", "building_rooftop", "building"):
        pt = "rooftop"
    if pt not in PROPERTY_TYPE_SCORES:
        pt = "unknown"

    base_score = PROPERTY_TYPE_SCORES[pt]
    reinforcement_likely = False
    label = PROPERTY_TYPE_LABELS[pt]
    cost_range = COST_RANGES.get(pt, COST_RANGES["unknown"])

    # Rooftop: adjust based on construction year
    if pt == "rooftop":
        if year_built is not None:
            if year_built < 1980:
                base_score = 35
                reinforcement_likely = True
                cost_range = COST_RANGES["rooftop_older"]
                label = f"Building rooftop (built {year_built} — pre-1980, unknown load capacity)"
            elif year_built < 2000:
                base_score = 45
                reinforcement_likely = True
                cost_range = COST_RANGES["rooftop_older"]
                label = f"Building rooftop (built {year_built} — 1980–2000, capacity 50–75 psf typical)"
            else:
                base_score = 65
                reinforcement_likely = False
                cost_range = COST_RANGES["rooftop_modern"]
                label = f"Building rooftop (built {year_built} — 2000+, capacity 80–100 psf typical)"
        else:
            # No year known — use conservative default
            base_score = 50
            reinforcement_likely = True
            cost_range = COST_RANGES["rooftop_older"]
            label = "Building rooftop (construction year unknown — conservative assessment)"

    return {
        "property_type_normalized": pt,
        "property_type_label": label,
        "score": max(0, min(100, base_score)),
        "cost_range": cost_range,
        "reinforcement_likely": reinforcement_likely,
    }


def build_eb105a_compliance_notes() -> list:
    """Return list of key FAA EB 105A compliance requirements."""
    return [
        f"TLOF minimum size: {TLOF_MIN_FT} ft × {TLOF_MIN_FT} ft ({TLOF_MIN_M} m × {TLOF_MIN_M} m) = {TLOF_AREA_SQFT:,} sq ft",
        f"Dynamic load requirement: 150% of aircraft MTOW — for Joby S4 (~{JOBY_S4_MTOW_LBS:,} lbs loaded), required: ~{REQUIRED_LOAD_LBS:,} lbs",
        f"Minimum distributed load across TLOF: {REQUIRED_DISTRIBUTED_LOAD_PSF} psf (actual gear point loads will be higher)",
        "Obstacle-free approach/departure surface (OFZ) must be clear of obstructions",
        "Wind indicator (wind cone or segmented circle) required",
        "Lighting: perimeter edge lights, threshold lights, and flood lighting if night ops",
        "Marking: TLOF boundary, FATO (Final Approach/Takeoff Area) designation, 'H' marking",
        "Drainage: adequate surface drainage to prevent standing water on TLOF",
        "Safety area: minimum 10 ft clear safety area surrounding TLOF",
        "Structural engineer stamped drawings required for FAA review",
    ]


def generate_structural_warnings(pt: str, analysis: dict) -> list:
    """Generate context-specific structural warnings."""
    warnings = []
    reinforcement_likely = analysis["reinforcement_likely"]

    # Universal warnings
    warnings.append(
        "Structural engineering assessment required: estimated $15,000–$50,000 and 4–8 weeks"
    )
    warnings.append(
        f"FAA EB 105A requires TLOF minimum {TLOF_MIN_FT} ft × {TLOF_MIN_FT} ft "
        f"({TLOF_MIN_M} m × {TLOF_MIN_M} m)"
    )
    warnings.append(
        f"Dynamic load requirement: 150% of aircraft MTOW (~{REQUIRED_LOAD_LBS:,} lbs for Joby S4)"
    )

    if pt == "ground":
        warnings.append(
            "Ground-level pad: no structural constraints — most cost-effective option; "
            "soil bearing capacity test ($5,000–$15,000) still recommended"
        )
    elif pt == "airport":
        warnings.append(
            "Airport infrastructure: coordinate with airport authority for tie-down, "
            "taxiway access, and ramp space — TLOF load verification still required"
        )
    elif pt == "garage":
        warnings.append(
            "Parking structure rooftop: modern concrete garages typically rated 40–100 psf; "
            "check original structural drawings and confirm load path to foundations"
        )
    elif pt == "rooftop":
        if reinforcement_likely:
            warnings.append(
                "Pre-2000 rooftop: structural reinforcement likely required — "
                "budget $200,000–$1,000,000 for beam/column upgrades"
            )
        else:
            warnings.append(
                "Modern rooftop (2000+): likely sufficient load capacity, "
                "but stamped structural assessment is still required before permitting"
            )

    return warnings


def generate_structural_summary(score: int, analysis: dict, pt: str) -> str:
    label = analysis["property_type_label"]
    cost = analysis["cost_range"]
    reinforcement = analysis["reinforcement_likely"]

    if pt == "ground":
        return (
            f"A ground-level vertiport pad has no structural constraints — this is the most "
            f"cost-effective configuration. FAA EB 105A requires a minimum TLOF of "
            f"{TLOF_MIN_FT} × {TLOF_MIN_FT} ft. A geotechnical soil study is recommended. "
            f"Estimated structural/construction cost: {cost}."
        )
    elif pt == "airport":
        return (
            f"This airport site has existing aviation-rated infrastructure. Structural requirements "
            f"for eVTOL pads are minimal — the primary work is FAA coordination and integration "
            f"with existing airfield operations. TLOF load verification is still required. "
            f"Estimated cost: {cost}."
        )
    elif pt == "garage":
        return (
            f"A parking structure rooftop ({label}) is a viable vertiport location. Modern "
            f"concrete structures are typically engineered for 40–100 psf live loads, which "
            f"may be sufficient, but a stamped structural assessment is mandatory. "
            f"Estimated cost: {cost}."
        )
    elif pt == "rooftop":
        if reinforcement:
            return (
                f"{label}. Based on typical construction practices, structural reinforcement "
                f"is likely required to meet FAA EB 105A dynamic load requirements "
                f"({REQUIRED_LOAD_LBS:,} lbs for a Joby S4). A detailed structural engineering "
                f"assessment ($15K–$50K, 4–8 weeks) is the critical first step. "
                f"Estimated total structural cost: {cost}."
            )
        else:
            return (
                f"{label}. Modern construction (2000+) typically provides 80–100 psf live load "
                f"capacity, which may be sufficient for eVTOL operations. A stamped structural "
                f"engineering assessment is still required. Estimated cost: {cost}."
            )
    else:
        return (
            f"Property type is '{pt}'. Structural feasibility is uncertain without more "
            f"information. A structural engineering assessment ($15K–$50K) is the required "
            f"first step. FAA EB 105A TLOF requirements apply regardless of property type. "
            f"Estimated cost range: {cost}."
        )


# ── Main agent function ────────────────────────────────────────────────────────

async def run_structural_agent(
    lat: float,
    lon: float,
    property_type: str = "unknown",
    year_built: Optional[int] = None,
) -> dict:
    """
    Primary entry point for the Structural Agent.

    Args:
        lat:            Site latitude (WGS84 decimal degrees)
        lon:            Site longitude (WGS84 decimal degrees)
        property_type:  "rooftop" | "ground" | "airport" | "garage" | "unknown"
        year_built:     Optional construction year (affects rooftop scoring)

    Returns dict matching AgentResult shape:
        {
          "score": int,           # 0–100
          "summary": str,
          "warnings": [str],
          "raw_data": { ... full analysis ... }
        }
    """
    started_at = datetime.now(timezone.utc).isoformat()

    # 1. Analyze
    analysis = analyze_structural(property_type, year_built)
    pt = analysis["property_type_normalized"]
    score = analysis["score"]

    # 2. Build EB 105A compliance notes
    eb105a_notes = build_eb105a_compliance_notes()

    # 3. Warnings
    warnings = generate_structural_warnings(pt, analysis)

    # 4. Summary
    summary = generate_structural_summary(score, analysis, pt)

    # 5. Assemble raw_data
    raw_data = {
        "input": {
            "latitude": lat,
            "longitude": lon,
            "property_type_input": property_type,
            "year_built": year_built,
        },
        "property_type": pt,
        "property_type_label": analysis["property_type_label"],
        "tlof_requirement_sqft": TLOF_AREA_SQFT,
        "tlof_requirement_ft": f"{TLOF_MIN_FT} × {TLOF_MIN_FT}",
        "tlof_requirement_m": f"{TLOF_MIN_M} × {TLOF_MIN_M}",
        "min_load_requirement_psf": REQUIRED_DISTRIBUTED_LOAD_PSF,
        "dynamic_load_lbs": REQUIRED_LOAD_LBS,
        "aircraft_mtow_lbs": JOBY_S4_MTOW_LBS,
        "dynamic_load_factor": DYNAMIC_LOAD_FACTOR,
        "estimated_structural_cost_range": analysis["cost_range"],
        "reinforcement_likely": analysis["reinforcement_likely"],
        "eb105a_compliance_notes": eb105a_notes,
        "data_source": "Rules-based (FAA EB 105A + industry load data — no external API)",
        "analysis_timestamp": started_at,
    }

    return {
        "score": score,
        "summary": summary,
        "warnings": warnings,
        "raw_data": raw_data,
    }


# ── Sync wrapper for Celery ────────────────────────────────────────────────────

def run_structural_agent_sync(
    lat: float,
    lon: float,
    property_type: str = "unknown",
    year_built: Optional[int] = None,
) -> dict:
    """Synchronous wrapper — use this from Celery tasks."""
    return asyncio.run(run_structural_agent(lat, lon, property_type, year_built))
