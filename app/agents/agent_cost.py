"""
SkyBase Agent 6: Cost Estimation Agent
========================================
Rules-based financial model for vertiport installation and ROI.
No external API — uses verified industry cost data.

Cost ranges (verified research):
  - Rooftop helipad conversion (basic):        $15K–$500K
  - Rooftop helipad to eVTOL (structural + charging): $500K–$2M
  - Standalone ground pad (new build):         $800K–$8M
  - Airport-integrated vertiport:              $8M–$15M
  - Large vertihub (4+ pads):                  $30M–$150M+

Charging infrastructure (always required):
  - Grid-tied (grid available nearby):         $500K–$2M per pad
  - Microgrid approach (1 MW):                 $2.1M–$4M per MW
  - Grid upgrade (if required):                $8M–$16M one-time

Revenue model:
  - Landing fees:    $10–$30 per landing (weight-based)
  - Charging fees:   $50–$200 per session
  - Ground handling: $50–$500 per slot
  - Cell tower analog: $1,500–$15,000/month per pad

Scoring (0–100):
  90–100 = ROI payback < 5 years, cost < $2M
   75–89 = Payback 5–8 years, cost $2–8M
   60–74 = Payback 8–12 years, cost $8–20M
   40–59 = Payback > 12 years, cost $20–50M
    0–39 = Cost > $50M or negative ROI
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional


# ── Cost data by property type ─────────────────────────────────────────────────

COST_DATA = {
    "airport": {
        "label": "Airport-integrated vertiport",
        "base_low":  8_000_000,
        "base_mid":  11_500_000,
        "base_high": 15_000_000,
        "charging_low":  500_000,
        "charging_high": 2_000_000,
        "notes": "Includes FAA-compliant TLOF, lighting, FATO, passenger terminal, ATC coordination",
    },
    "ground": {
        "label": "Standalone ground-level vertiport pad",
        "base_low":    800_000,
        "base_mid":  3_000_000,
        "base_high": 8_000_000,
        "charging_low":  500_000,
        "charging_high": 2_000_000,
        "notes": "Includes civil construction, drainage, TLOF, safety area, access road",
    },
    "garage": {
        "label": "Rooftop parking structure vertiport",
        "base_low":   500_000,
        "base_mid": 1_000_000,
        "base_high": 2_000_000,
        "charging_low":  500_000,
        "charging_high": 2_000_000,
        "notes": "Structural assessment required; modern garages typically adequate",
    },
    "rooftop": {
        "label": "Building rooftop vertiport (eVTOL upgrade)",
        "base_low":   500_000,
        "base_mid": 1_200_000,
        "base_high": 2_000_000,
        "charging_low":  500_000,
        "charging_high": 2_000_000,
        "notes": "Older buildings may require structural reinforcement ($200K–$1M additional)",
    },
    "vertihub": {
        "label": "Large vertihub (4+ pads)",
        "base_low":  30_000_000,
        "base_mid":  75_000_000,
        "base_high": 150_000_000,
        "charging_low":  2_000_000,
        "charging_high":  8_000_000,
        "notes": "Includes terminal, operations center, parking, multi-pad TLOF",
    },
    "unknown": {
        "label": "Vertiport (type unknown)",
        "base_low":   800_000,
        "base_mid": 3_000_000,
        "base_high": 8_000_000,
        "charging_low":  500_000,
        "charging_high": 2_000_000,
        "notes": "Estimate assumes single-pad ground or rooftop installation",
    },
}

# Revenue assumptions
LANDINGS_PER_DAY_LOW  = 5
LANDINGS_PER_DAY_HIGH = 30
DAYS_PER_YEAR = 365

LANDING_FEE_LOW  = 10   # $/landing
LANDING_FEE_HIGH = 30   # $/landing

CHARGING_FEE_LOW  = 50   # $/session
CHARGING_FEE_HIGH = 200  # $/session

GROUND_HANDLING_LOW  = 50   # $/slot
GROUND_HANDLING_HIGH = 500  # $/slot

# Assume 80% of landings also charge; 60% need ground handling
CHARGE_UTILIZATION  = 0.80
HANDLING_UTILIZATION = 0.60


# ── Cost computation ──────────────────────────────────────────────────────────

def compute_costs(property_type: str, grid_upgrade_needed: bool = False) -> dict:
    """
    Compute capital cost ranges for the given property type.
    Optionally adds grid upgrade costs.

    Returns dict with cost_low, cost_mid, cost_high, and per-component breakdown.
    """
    pt = (property_type or "unknown").lower().strip()
    if pt not in COST_DATA:
        pt = "unknown"

    cd = COST_DATA[pt]

    # Base construction + charging
    cost_low  = cd["base_low"]  + cd["charging_low"]
    cost_mid  = cd["base_mid"]  + (cd["charging_low"] + cd["charging_high"]) // 2
    cost_high = cd["base_high"] + cd["charging_high"]

    # Grid upgrade (if power agent indicates it's needed)
    grid_upgrade_low  = 0
    grid_upgrade_high = 0
    if grid_upgrade_needed:
        grid_upgrade_low  = 8_000_000
        grid_upgrade_high = 16_000_000
        cost_low  += grid_upgrade_low
        cost_mid  += (grid_upgrade_low + grid_upgrade_high) // 2
        cost_high += grid_upgrade_high

    # Permitting / soft costs (typically 10–15% of hard costs)
    soft_cost_low  = int(cd["base_low"]  * 0.10)
    soft_cost_high = int(cd["base_high"] * 0.15)
    cost_low  += soft_cost_low
    cost_high += soft_cost_high
    cost_mid  += (soft_cost_low + soft_cost_high) // 2

    return {
        "property_type": pt,
        "label": cd["label"],
        "notes": cd["notes"],
        "components": {
            "construction_low":  cd["base_low"],
            "construction_high": cd["base_high"],
            "charging_low":  cd["charging_low"],
            "charging_high": cd["charging_high"],
            "grid_upgrade_low":  grid_upgrade_low,
            "grid_upgrade_high": grid_upgrade_high,
            "soft_costs_low":  soft_cost_low,
            "soft_costs_high": soft_cost_high,
        },
        "cost_low":  cost_low,
        "cost_mid":  cost_mid,
        "cost_high": cost_high,
    }


# ── Revenue computation ────────────────────────────────────────────────────────

def compute_revenue(landings_low: int = LANDINGS_PER_DAY_LOW,
                    landings_high: int = LANDINGS_PER_DAY_HIGH) -> dict:
    """
    Compute annual revenue potential ranges.
    Conservative: low landings, low fees.
    Optimistic: high landings, high fees.
    """
    # Conservative (low)
    annual_landings_low = landings_low * DAYS_PER_YEAR
    rev_landing_low  = annual_landings_low * LANDING_FEE_LOW
    rev_charging_low = annual_landings_low * CHARGE_UTILIZATION * CHARGING_FEE_LOW
    rev_handling_low = annual_landings_low * HANDLING_UTILIZATION * GROUND_HANDLING_LOW
    annual_rev_low = int(rev_landing_low + rev_charging_low + rev_handling_low)

    # Optimistic (high)
    annual_landings_high = landings_high * DAYS_PER_YEAR
    rev_landing_high  = annual_landings_high * LANDING_FEE_HIGH
    rev_charging_high = annual_landings_high * CHARGE_UTILIZATION * CHARGING_FEE_HIGH
    rev_handling_high = annual_landings_high * HANDLING_UTILIZATION * GROUND_HANDLING_HIGH
    annual_rev_high = int(rev_landing_high + rev_charging_high + rev_handling_high)

    return {
        "annual_revenue_potential_low":  annual_rev_low,
        "annual_revenue_potential_high": annual_rev_high,
        "revenue_components": {
            "landings_per_day_low":   landings_low,
            "landings_per_day_high":  landings_high,
            "landing_fee_low":   LANDING_FEE_LOW,
            "landing_fee_high":  LANDING_FEE_HIGH,
            "charging_fee_low":  CHARGING_FEE_LOW,
            "charging_fee_high": CHARGING_FEE_HIGH,
            "ground_handling_fee_low":  GROUND_HANDLING_LOW,
            "ground_handling_fee_high": GROUND_HANDLING_HIGH,
            "charge_utilization_pct":   int(CHARGE_UTILIZATION * 100),
            "handling_utilization_pct": int(HANDLING_UTILIZATION * 100),
        },
    }


# ── ROI computation ───────────────────────────────────────────────────────────

def compute_roi(cost_low: int, cost_high: int,
                rev_low: int, rev_high: int) -> dict:
    """
    Compute simple payback period and 5-year ROI.
    Uses cost_mid vs revenue midpoints for payback; extremes for ranges.
    """
    cost_mid = (cost_low + cost_high) // 2
    rev_mid  = (rev_low + rev_high) // 2

    # Simple payback = total cost / annual revenue
    payback_low  = cost_low  / rev_high  if rev_high  > 0 else 999.0
    payback_high = cost_high / rev_low   if rev_low   > 0 else 999.0
    payback_mid  = cost_mid  / rev_mid   if rev_mid   > 0 else 999.0

    # 5-year ROI = (5yr revenue - cost) / cost * 100
    roi_5yr_low  = ((rev_high * 5 - cost_low)  / cost_low)  * 100 if cost_low  > 0 else 0.0
    roi_5yr_high = ((rev_low  * 5 - cost_high) / cost_high) * 100 if cost_high > 0 else 0.0
    roi_5yr_mid  = ((rev_mid  * 5 - cost_mid)  / cost_mid)  * 100 if cost_mid  > 0 else 0.0

    return {
        "simple_payback_years_low":  round(payback_low,  1),
        "simple_payback_years_mid":  round(payback_mid,  1),
        "simple_payback_years_high": round(payback_high, 1),
        "roi_5yr_percent_optimistic":  round(roi_5yr_low,  1),
        "roi_5yr_percent_mid":         round(roi_5yr_mid,  1),
        "roi_5yr_percent_conservative": round(roi_5yr_high, 1),
    }


# ── Score from ROI/cost ────────────────────────────────────────────────────────

def compute_cost_score(cost_mid: int, payback_mid: float) -> int:
    """Derive score from cost and payback period."""
    if cost_mid < 2_000_000 and payback_mid < 5:
        return 90
    elif cost_mid < 8_000_000 and payback_mid < 8:
        return 80
    elif cost_mid < 20_000_000 and payback_mid < 12:
        return 65
    elif cost_mid < 50_000_000 and payback_mid < 20:
        return 50
    else:
        return 30


# ── Summary generator ─────────────────────────────────────────────────────────

def generate_cost_summary(score: int, costs: dict, revenue: dict, roi: dict) -> str:
    cost_low  = costs["cost_low"]
    cost_high = costs["cost_high"]
    rev_low   = revenue["annual_revenue_potential_low"]
    rev_high  = revenue["annual_revenue_potential_high"]
    payback_low  = roi["simple_payback_years_low"]
    payback_high = roi["simple_payback_years_high"]
    roi_mid  = roi["roi_5yr_percent_mid"]

    def fmt_m(n):
        if n >= 1_000_000:
            return f"${n / 1_000_000:.1f}M"
        return f"${n:,.0f}"

    cost_range_str   = f"{fmt_m(cost_low)}–{fmt_m(cost_high)}"
    rev_range_str    = f"{fmt_m(rev_low)}–{fmt_m(rev_high)}/year"
    payback_range_str = f"{payback_low:.1f}–{payback_high:.1f} years"

    if score >= 85:
        return (
            f"Strong financial outlook. Estimated total capital cost: {cost_range_str}. "
            f"Annual revenue potential: {rev_range_str} (based on 5–30 landings/day at "
            f"$10–$30/landing + charging + ground handling). "
            f"Simple payback: {payback_range_str}. "
            f"5-year ROI (mid scenario): {roi_mid:.0f}%. This is a highly investable vertiport site."
        )
    elif score >= 70:
        return (
            f"Moderate financial outlook. Estimated total capital cost: {cost_range_str}. "
            f"Annual revenue potential: {rev_range_str}. "
            f"Simple payback: {payback_range_str}. "
            f"5-year ROI (mid scenario): {roi_mid:.0f}%. "
            f"The economics are viable with adequate air taxi demand — a demand study is recommended."
        )
    elif score >= 50:
        return (
            f"Challenging economics. Estimated total capital cost: {cost_range_str} — "
            f"the upper range requires significant infrastructure investment. "
            f"Annual revenue potential: {rev_range_str}. "
            f"Simple payback: {payback_range_str}. A public-private partnership or "
            f"FDOT/state grant funding would materially improve the financial case."
        )
    else:
        return (
            f"High-cost site. Estimated total capital cost: {cost_range_str}. "
            f"Annual revenue potential: {rev_range_str}. "
            f"Simple payback: {payback_range_str} — this timeline may exceed acceptable "
            f"investment horizons without significant grant funding or anchor tenants. "
            f"Consider a phased development approach starting with a single-pad installation."
        )


# ── Main agent function ────────────────────────────────────────────────────────

async def run_cost_agent(
    lat: float,
    lon: float,
    property_type: str = "unknown",
    grid_upgrade_needed: bool = False,
) -> dict:
    """
    Primary entry point for the Cost Estimation Agent.

    Args:
        lat:                Site latitude (WGS84 decimal degrees)
        lon:                Site longitude (WGS84 decimal degrees)
        property_type:      "rooftop" | "ground" | "airport" | "garage" | "vertihub" | "unknown"
        grid_upgrade_needed: True if power agent indicates major grid upgrade needed

    Returns dict matching AgentResult shape:
        {
          "score": int,           # 0–100
          "summary": str,
          "warnings": [str],
          "raw_data": { ... full analysis ... }
        }
    """
    started_at = datetime.now(timezone.utc).isoformat()

    # 1. Compute costs
    costs = compute_costs(property_type, grid_upgrade_needed)

    # 2. Compute revenue
    revenue = compute_revenue()

    # 3. Compute ROI
    roi = compute_roi(
        costs["cost_low"], costs["cost_high"],
        revenue["annual_revenue_potential_low"],
        revenue["annual_revenue_potential_high"],
    )

    # 4. Score
    cost_mid    = costs["cost_mid"]
    payback_mid = roi["simple_payback_years_mid"]
    score = compute_cost_score(cost_mid, payback_mid)

    # 5. Warnings
    warnings = []

    if costs["cost_high"] > 50_000_000:
        warnings.append(
            f"High capital expenditure: up to {costs['cost_high'] / 1_000_000:.0f}M — "
            "explore FDOT/FAA grant programs, public-private partnerships, or phased development"
        )

    if roi["simple_payback_years_mid"] > 10:
        warnings.append(
            f"Long payback period ({roi['simple_payback_years_mid']:.1f} years at mid scenario) — "
            "demand study required; consider anchor tenant agreements to de-risk"
        )

    if grid_upgrade_needed:
        warnings.append(
            "Grid upgrade included in cost estimate ($8M–$16M one-time) — "
            "this is a major capital item; explore utility cost-sharing agreements"
        )

    warnings.append(
        "Revenue projections assume 5–30 landings/day — actual demand will depend on "
        "air taxi operator commitments; a demand feasibility study is recommended before investment"
    )
    warnings.append(
        "Cost estimates are pre-engineering ranges — a detailed feasibility study "
        "($50K–$150K) should be completed before committing capital"
    )

    if property_type in ("rooftop",) and not grid_upgrade_needed:
        warnings.append(
            "Rooftop site: cost estimate may increase $200K–$1M if structural "
            "reinforcement is required (see Structural Agent results)"
        )

    # 6. Summary
    summary = generate_cost_summary(score, costs, revenue, roi)

    # 7. Assemble raw_data
    raw_data = {
        "input": {
            "latitude": lat,
            "longitude": lon,
            "property_type": property_type,
            "grid_upgrade_needed": grid_upgrade_needed,
        },
        "cost_low":  costs["cost_low"],
        "cost_mid":  costs["cost_mid"],
        "cost_high": costs["cost_high"],
        "cost_components": costs["components"],
        "cost_label": costs["label"],
        "cost_notes": costs["notes"],
        "annual_revenue_potential_low":  revenue["annual_revenue_potential_low"],
        "annual_revenue_potential_high": revenue["annual_revenue_potential_high"],
        "revenue_components": revenue["revenue_components"],
        "simple_payback_years_low":  roi["simple_payback_years_low"],
        "simple_payback_years_mid":  roi["simple_payback_years_mid"],
        "simple_payback_years_high": roi["simple_payback_years_high"],
        "roi_5yr_percent_optimistic":   roi["roi_5yr_percent_optimistic"],
        "roi_5yr_percent_mid":          roi["roi_5yr_percent_mid"],
        "roi_5yr_percent_conservative": roi["roi_5yr_percent_conservative"],
        "market_context": {
            "cell_tower_analog_monthly_per_pad": "$1,500–$15,000",
            "evtol_charging_grid_tied_per_pad": "$500K–$2M",
            "evtol_charging_microgrid_per_mw": "$2.1M–$4M",
            "landing_fee_range": "$10–$30/landing (weight-based)",
            "charging_fee_range": "$50–$200/session (1 hr @ 1 MW = $80–$150 at commercial rates)",
        },
        "data_source": "Rules-based financial model — industry data from published research",
        "analysis_timestamp": started_at,
    }

    return {
        "score": score,
        "summary": summary,
        "warnings": warnings,
        "raw_data": raw_data,
    }


# ── Sync wrapper for Celery ────────────────────────────────────────────────────

def run_cost_agent_sync(
    lat: float,
    lon: float,
    property_type: str = "unknown",
    grid_upgrade_needed: bool = False,
) -> dict:
    """Synchronous wrapper — use this from Celery tasks."""
    return asyncio.run(run_cost_agent(lat, lon, property_type, grid_upgrade_needed))
