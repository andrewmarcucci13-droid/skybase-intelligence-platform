"""
SkyBase Agent 5: Regulatory Pathway Analysis Agent
====================================================
Rules-based state and federal regulatory pathway analysis for vertiport
permitting. No external API — uses a hardcoded state ruleset database.

Priority states: Florida, Texas, New York, California, Illinois.
All other US locations: generic federal pathway.

Federal forms always required:
  - FAA Form 7480-1 (Notice of Proposed Construction or Alteration)
    → Submit at least 45 days before construction start
  - FAA Form 7460-1 (Notice of Proposed Construction or Alteration for
    structures > 200 ft AGL OR within 20,000 ft of an airport)

FAA eIPP (Enabling Infrastructure Pilot Program, March 2026):
  Participating states received federal guidance and streamlined coordination.

Scoring (0–100):
  90 = Florida  (most permissive, FDOT funding up to 100%, fast-track)
  75 = Texas    (eIPP participant, reasonable timeline)
  70 = Illinois (moderate complexity)
  65 = Other US (federal path only)
  55 = New York (complex multi-agency, PANYNJ coordination)
  40 = California (CEQA risk, longest timeline)
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional


# ── State detection bounding boxes ────────────────────────────────────────────
# (lat_min, lat_max, lon_min, lon_max)
STATE_BOUNDS = {
    "Florida":    (24.5,  31.0,  -87.6,  -80.0),
    "Texas":      (25.8,  36.5, -106.6,  -93.5),
    "New York":   (40.5,  45.0,  -79.8,  -71.9),
    "California": (32.5,  42.0, -124.4, -114.1),
    "Illinois":   (36.9,  42.5,  -91.5,  -87.0),
}


def detect_state(lat: float, lon: float) -> str:
    """
    Determine the US state from lat/lon using approximate bounding boxes.
    Returns state name or "Other" if not in the priority states.
    """
    for state, (lat_min, lat_max, lon_min, lon_max) in STATE_BOUNDS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return state
    return "Other"


# ── State ruleset database ─────────────────────────────────────────────────────

STATE_RULESETS = {
    "Florida": {
        "score": 90,
        "state_name": "Florida",
        "state_approval_required": True,
        "state_approval_body": "Florida Department of Transportation (FDOT) — District Aviation Office",
        "state_approval_timeline_weeks": "4–8 weeks",
        "fdot_funding_eligible": True,
        "fdot_funding_note": "FDOT can fund up to 100% of vertiport capital costs — apply to District Aviation Office for Site Approval Order",
        "faa_eipp_state": True,
        "faa_eipp_note": "Florida participated in FAA eIPP March 2026 launch — streamlined federal-state coordination available",
        "required_forms": [
            "FAA Form 7480-1 (Notice of Proposed Construction)",
            "FAA Form 7460-1 (if structure > 200 ft AGL or within 20,000 ft of airport)",
            "FDOT Site Approval Order Application (FDOT Form 725-040-85)",
            "FDOT Aviation Facility Development Grant Application (if seeking funding)",
            "Local building permit",
            "FAA Airport Layout Plan (ALP) amendment (if on airport property)",
        ],
        "permitting_timeline_total_weeks": "12–24 weeks",
        "fast_track_available": True,
        "fast_track_note": "Florida has expedited aviation infrastructure permitting; FDOT pre-application meeting typically reduces timeline",
        "key_contacts": [
            "FDOT Aviation and Spaceports Office: (850) 414-4500",
            "FAA Southern Region Airports Division (Atlanta): (404) 305-6600",
        ],
    },

    "Texas": {
        "score": 75,
        "state_name": "Texas",
        "state_approval_required": True,
        "state_approval_body": "Texas Department of Transportation (TxDOT) — Aviation Division",
        "state_approval_timeline_weeks": "6–12 weeks",
        "fdot_funding_eligible": False,
        "faa_eipp_state": True,
        "faa_eipp_note": "Texas participated in FAA eIPP March 2026 launch",
        "required_forms": [
            "FAA Form 7480-1 (Notice of Proposed Construction)",
            "FAA Form 7460-1 (if applicable)",
            "TxDOT Aviation Division notification (TxDOT Form AVI-101)",
            "TxDOT Airport Layout Plan amendment (for airport sites)",
            "Local zoning/building permit",
            "Texas Commission on Environmental Quality (TCEQ) review (if stormwater/environmental impacts)",
        ],
        "permitting_timeline_total_weeks": "16–32 weeks",
        "fast_track_available": False,
        "fast_track_note": None,
        "key_contacts": [
            "TxDOT Aviation Division: (512) 416-4500",
            "FAA Southwest Region Airports Division (Fort Worth): (817) 222-5600",
        ],
    },

    "New York": {
        "score": 55,
        "state_name": "New York",
        "state_approval_required": True,
        "state_approval_body": "New York State Department of Transportation (NYSDOT) — Aviation Bureau + Port Authority of NY/NJ (PANYNJ) for metro airports",
        "state_approval_timeline_weeks": "12–24 weeks",
        "fdot_funding_eligible": False,
        "faa_eipp_state": True,
        "faa_eipp_note": "New York participated in FAA eIPP March 2026 launch; PANYNJ coordination required for JFK/LGA/EWR area sites",
        "required_forms": [
            "FAA Form 7480-1 (Notice of Proposed Construction)",
            "FAA Form 7460-1 (likely required — dense airspace)",
            "NYSDOT Aviation Bureau approval",
            "Port Authority of NY/NJ review (for sites near JFK, LGA, EWR, Teterboro)",
            "New York City Zoning Resolution compliance (NYC sites)",
            "NYC Department of Buildings permit (NYC sites)",
            "SEQRA (State Environmental Quality Review Act) determination",
            "FAA TRACON (New York TRACON N90) airspace coordination",
            "Local building/zoning permits",
        ],
        "permitting_timeline_total_weeks": "24–48 weeks",
        "fast_track_available": False,
        "fast_track_note": "New York has the most complex multi-agency coordination of any priority state — early engagement with all agencies is critical",
        "key_contacts": [
            "NYSDOT Aviation Bureau: (518) 457-2820",
            "Port Authority of NY/NJ Aviation: (212) 435-7000",
            "FAA Eastern Region Airports Division (Jamaica, NY): (718) 553-3300",
        ],
    },

    "California": {
        "score": 40,
        "state_name": "California",
        "state_approval_required": True,
        "state_approval_body": "Caltrans Division of Aeronautics",
        "state_approval_timeline_weeks": "12–26 weeks (CEQA review can add 6–18 months)",
        "fdot_funding_eligible": False,
        "faa_eipp_state": False,
        "faa_eipp_note": "California was not in the FAA eIPP March 2026 pilot launch",
        "required_forms": [
            "FAA Form 7480-1 (Notice of Proposed Construction)",
            "FAA Form 7460-1 (if applicable)",
            "Caltrans Division of Aeronautics Permit to Construct",
            "CEQA (California Environmental Quality Act) Initial Study / Mitigated Negative Declaration or EIR",
            "Local zoning/conditional use permit",
            "California Building Code permit",
            "Possible AQMD (Air Quality Management District) review",
            "Airport Land Use Compatibility Plan (ALUCP) consistency determination (if near airport)",
        ],
        "permitting_timeline_total_weeks": "24–52 weeks",
        "fast_track_available": False,
        "fast_track_note": "CEQA is the primary risk — an EIR can add 12–24 months and $500K–$2M in costs",
        "key_contacts": [
            "Caltrans Division of Aeronautics: (916) 654-4959",
            "FAA Western Pacific Region Airports Division (Los Angeles): (310) 725-3800",
        ],
    },

    "Illinois": {
        "score": 70,
        "state_name": "Illinois",
        "state_approval_required": True,
        "state_approval_body": "Illinois Department of Transportation (IDOT) — Division of Aeronautics",
        "state_approval_timeline_weeks": "6–12 weeks",
        "fdot_funding_eligible": False,
        "faa_eipp_state": False,
        "faa_eipp_note": "Illinois was not in the FAA eIPP March 2026 pilot launch",
        "required_forms": [
            "FAA Form 7480-1 (Notice of Proposed Construction)",
            "FAA Form 7460-1 (if applicable)",
            "IDOT Division of Aeronautics Airport Construction Permit",
            "Chicago Department of Aviation coordination (Chicago sites)",
            "Local zoning/building permit",
            "Illinois Environmental Protection Agency (IEPA) review (if environmental impacts)",
        ],
        "permitting_timeline_total_weeks": "16–32 weeks",
        "fast_track_available": False,
        "fast_track_note": None,
        "key_contacts": [
            "IDOT Division of Aeronautics: (217) 785-8500",
            "FAA Great Lakes Region Airports Division (Chicago): (847) 294-7300",
        ],
    },

    "Other": {
        "score": 65,
        "state_name": "Other US State",
        "state_approval_required": False,
        "state_approval_body": "State aviation authority (varies by state — contact directly)",
        "state_approval_timeline_weeks": "4–12 weeks (if required)",
        "fdot_funding_eligible": False,
        "faa_eipp_state": False,
        "faa_eipp_note": "Not an FAA eIPP pilot state — federal-only pathway applies",
        "required_forms": [
            "FAA Form 7480-1 (Notice of Proposed Construction)",
            "FAA Form 7460-1 (if applicable)",
            "State aviation authority approval (verify with state DOT)",
            "Local zoning/building permit",
        ],
        "permitting_timeline_total_weeks": "16–30 weeks",
        "fast_track_available": False,
        "fast_track_note": None,
        "key_contacts": [
            "Contact your FAA Regional Airports Division office for local guidance",
        ],
    },
}


# ── Summary generator ─────────────────────────────────────────────────────────

def generate_regulatory_summary(state: str, ruleset: dict, score: int) -> str:
    timeline = ruleset["permitting_timeline_total_weeks"]
    body = ruleset["state_approval_body"]
    eipp = ruleset["faa_eipp_state"]
    forms_count = len(ruleset["required_forms"])

    if state == "Florida":
        return (
            f"Florida has the most permissive vertiport regulatory environment of the priority states. "
            f"FDOT can fund up to 100% of vertiport capital costs — the Site Approval Order "
            f"application to your FDOT District Office is the critical first step. "
            f"Florida also participated in the FAA eIPP March 2026 launch, enabling streamlined "
            f"federal-state coordination. Estimated total permitting timeline: {timeline}. "
            f"{forms_count} regulatory filings required."
        )
    elif state == "Texas":
        return (
            f"Texas has a straightforward permitting pathway through TxDOT Aviation Division. "
            f"The state participated in the FAA eIPP March 2026 launch. "
            f"No state funding equivalent to Florida's FDOT program exists, but the regulatory "
            f"burden is moderate. Estimated total permitting timeline: {timeline}. "
            f"{forms_count} regulatory filings required."
        )
    elif state == "New York":
        return (
            f"New York has the most complex multi-agency permitting process of the priority states. "
            f"Coordination with NYSDOT, the Port Authority of NY/NJ (for metro area sites), "
            f"NYC agencies, and FAA TRACON is required. Allow {timeline} for permitting. "
            f"New York participated in FAA eIPP March 2026. "
            f"{forms_count} regulatory filings required — engage a land-use attorney early."
        )
    elif state == "California":
        return (
            f"California presents the highest regulatory risk. Caltrans Division of Aeronautics "
            f"approval plus CEQA environmental review are required. A full Environmental Impact "
            f"Report (EIR) can add 12–24 months and $500K–$2M to the project timeline. "
            f"California was not an FAA eIPP participant. Budget {timeline} for permitting. "
            f"{forms_count} regulatory filings required."
        )
    elif state == "Illinois":
        return (
            f"Illinois has a moderate permitting pathway through IDOT Division of Aeronautics. "
            f"Illinois was not an FAA eIPP participant, but the state DOT is experienced with "
            f"aviation infrastructure. Chicago-area sites require additional Chicago Department "
            f"of Aviation coordination. Estimated timeline: {timeline}. "
            f"{forms_count} regulatory filings required."
        )
    else:
        return (
            f"This site is outside the five priority states. Federal permitting (FAA Forms "
            f"7480-1 and 7460-1) applies in all cases. Contact the state DOT aviation division "
            f"for state-specific requirements. Estimated federal timeline: {timeline}. "
            f"{forms_count} baseline regulatory filings required."
        )


# ── Warnings generator ────────────────────────────────────────────────────────

def generate_regulatory_warnings(state: str, ruleset: dict) -> list:
    warnings = []

    # Universal FAA warnings
    warnings.append(
        "FAA Form 7480-1 required: submit 45 days before construction start "
        "(Notice of Proposed Construction or Alteration)"
    )
    warnings.append(
        "FAA Form 7460-1 required for structures > 200 ft AGL or within 20,000 ft of an airport"
    )

    # State-specific
    if state == "Florida":
        warnings.append(
            "Florida: Apply to FDOT District Office for Site Approval Order — "
            "funding up to 100% of vertiport costs available (FDOT Aviation Grant Program)"
        )
        warnings.append(
            "Florida eIPP: Contact FAA Southern Region Airports Division for "
            "streamlined federal-state coordination under eIPP March 2026 framework"
        )
    elif state == "Texas":
        warnings.append(
            "Texas: Notify TxDOT Aviation Division early — TxDOT Form AVI-101 "
            "required before construction"
        )
    elif state == "New York":
        warnings.append(
            "New York: Coordinate with Port Authority of NY/NJ for any site near "
            "JFK, LGA, EWR, or Teterboro — PANYNJ approval adds 3–6 months"
        )
        warnings.append(
            "New York City sites: NYC Board of Standards and Appeals (BSA) or "
            "City Planning Commission review may be required for zoning variances"
        )
        warnings.append(
            "SEQRA (State Environmental Quality Review Act) environmental determination "
            "required — budget 3–6 months for lead agency coordination"
        )
    elif state == "California":
        warnings.append(
            "California: CEQA environmental review may add 6–18 months to permitting timeline — "
            "engage CEQA consultant immediately; mitigated negative declaration is best-case scenario"
        )
        warnings.append(
            "California: Airport Land Use Compatibility Plan (ALUCP) consistency determination "
            "required for sites within 2 miles of a public-use airport"
        )

    if ruleset["fast_track_available"]:
        warnings.append(
            f"Fast-track available: {ruleset['fast_track_note']}"
        )

    return warnings


# ── Main agent function ────────────────────────────────────────────────────────

async def run_regulatory_agent(lat: float, lon: float) -> dict:
    """
    Primary entry point for the Regulatory Agent.

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

    # 1. Detect state
    state = detect_state(lat, lon)
    ruleset = STATE_RULESETS[state]
    score = ruleset["score"]

    # 2. Warnings
    warnings = generate_regulatory_warnings(state, ruleset)

    # 3. Summary
    summary = generate_regulatory_summary(state, ruleset, score)

    # 4. Assemble raw_data
    raw_data = {
        "input": {"latitude": lat, "longitude": lon},
        "detected_state": state,
        "state_name": ruleset["state_name"],
        "state_approval_required": ruleset["state_approval_required"],
        "state_approval_body": ruleset["state_approval_body"],
        "state_approval_timeline_weeks": ruleset["state_approval_timeline_weeks"],
        "fdot_funding_eligible": ruleset["fdot_funding_eligible"],
        "fdot_funding_note": ruleset.get("fdot_funding_note"),
        "faa_eipp_state": ruleset["faa_eipp_state"],
        "faa_eipp_note": ruleset.get("faa_eipp_note"),
        "required_forms": ruleset["required_forms"],
        "permitting_timeline_total_weeks": ruleset["permitting_timeline_total_weeks"],
        "fast_track_available": ruleset["fast_track_available"],
        "fast_track_note": ruleset.get("fast_track_note"),
        "key_contacts": ruleset.get("key_contacts", []),
        "federal_requirements": {
            "faa_form_7480_1": {
                "name": "Notice of Proposed Construction or Alteration",
                "trigger": "Any construction near airports or of structures that may affect airspace",
                "lead_time_days": 45,
                "filing_url": "https://oeaaa.faa.gov/",
            },
            "faa_form_7460_1": {
                "name": "Notice of Proposed Construction for tall structures or airport proximity",
                "trigger": "Structures > 200 ft AGL or within 20,000 ft of a public-use airport",
                "lead_time_days": 45,
                "filing_url": "https://oeaaa.faa.gov/",
            },
        },
        "detection_method": "Approximate lat/lon bounding box (not a legal boundary determination)",
        "data_source": "Rules-based state regulatory database — verify with current state regulations",
        "analysis_timestamp": started_at,
    }

    return {
        "score": score,
        "summary": summary,
        "warnings": warnings,
        "raw_data": raw_data,
    }


# ── Sync wrapper for Celery ────────────────────────────────────────────────────

def run_regulatory_agent_sync(lat: float, lon: float) -> dict:
    """Synchronous wrapper — use this from Celery tasks."""
    return asyncio.run(run_regulatory_agent(lat, lon))
