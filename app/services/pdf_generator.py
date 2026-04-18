"""
SkyBase PDF Report Generator
Renders a professional Vertiport Readiness Report using WeasyPrint + Jinja2.
"""
import os
from pathlib import Path
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
REPORTS_DIR = Path("/tmp/skybase_reports")

AGENT_META = {
    "airspace": {
        "title": "FAA Airspace Analysis",
        "icon": "✈️",
        "extract_keys": [
            ("Airspace Class", "airspace_class"),
            ("Controlled Airspace", "controlled_airspace"),
            ("LAANC Enabled", "laanc_enabled"),
            ("Part 107 Waiver Required", "part107_waiver_required"),
            ("Nearest Airport", "nearest_airport"),
            ("Airport Distance (nm)", "nearest_airport_distance_nm"),
        ],
        "table_field": "nearby_airports",
        "table_headers": ["Airport", "ICAO", "Distance (nm)", "Bearing"],
        "table_keys": ["name", "icao", "distance_nm", "bearing"],
    },
    "zoning": {
        "title": "Zoning & Land Use",
        "icon": "🏗️",
        "extract_keys": [
            ("Land Use Classification", "land_use"),
            ("Zoning Compatibility", "zoning_compatibility"),
            ("Commercial District", "commercial_district"),
            ("Industrial Proximity", "industrial_proximity"),
        ],
        "table_field": "nearby_features",
        "table_headers": ["Feature", "Type", "Distance (m)"],
        "table_keys": ["name", "type", "distance_m"],
    },
    "power": {
        "title": "Power Infrastructure",
        "icon": "⚡",
        "extract_keys": [
            ("Utility Provider", "utility_provider"),
            ("Grid Capacity Tier", "grid_capacity_tier"),
            ("Estimated Capacity (MW)", "estimated_capacity_mw"),
            ("Upgrade Cost Estimate", "upgrade_cost_estimate"),
            ("Nearest Substation (mi)", "substation_distance_mi"),
        ],
        "table_field": None,
        "table_headers": [],
        "table_keys": [],
    },
    "structural": {
        "title": "Structural Assessment",
        "icon": "🏢",
        "extract_keys": [
            ("Pad Type Recommendation", "pad_type"),
            ("Load Bearing Requirement", "load_bearing_psf"),
            ("FATO Size Required", "fato_size"),
            ("TLOF Size Required", "tlof_size"),
            ("FAA EB 105A Compliance", "eb105a_compliance"),
        ],
        "table_field": "construction_constraints",
        "table_headers": ["Constraint", "Detail"],
        "table_keys": ["constraint", "detail"],
    },
    "regulatory": {
        "title": "Regulatory Landscape",
        "icon": "📋",
        "extract_keys": [
            ("State", "state"),
            ("eVTOL Legislation Status", "legislation_status"),
            ("Timeline Estimate", "timeline_estimate"),
            ("FDOT/USDOT Funding Eligible", "funding_eligible"),
        ],
        "table_field": "permits_required",
        "table_headers": ["Permit", "Authority", "Est. Timeline"],
        "table_keys": ["permit", "authority", "timeline"],
    },
    "cost": {
        "title": "Cost Model",
        "icon": "💰",
        "extract_keys": [
            ("CapEx Low", "capex_low"),
            ("CapEx Mid", "capex_mid"),
            ("CapEx High", "capex_high"),
            ("Annual OpEx", "annual_opex"),
            ("Payback Period", "payback_period"),
        ],
        "table_field": "roi_scenarios",
        "table_headers": ["Utilization Rate", "Annual Revenue", "ROI %", "Payback (yrs)"],
        "table_keys": ["utilization", "annual_revenue", "roi_pct", "payback_years"],
    },
    "noise": {
        "title": "Environmental & Noise",
        "icon": "🌿",
        "extract_keys": [
            ("FEMA Flood Zone", "flood_zone"),
            ("Flood Risk Level", "flood_risk"),
            ("Noise Level (dBA at 500m)", "noise_dba_500m"),
            ("Sensitive Receptors Nearby", "sensitive_receptors_count"),
        ],
        "table_field": "sensitive_receptors",
        "table_headers": ["Receptor", "Type", "Distance (m)"],
        "table_keys": ["name", "type", "distance_m"],
    },
}


def _score_badge_class(score: int) -> str:
    if score is None:
        return "badge-red"
    if score >= 80:
        return "badge-green"
    if score >= 60:
        return "badge-yellow"
    if score >= 40:
        return "badge-orange"
    return "badge-red"


def _score_color_class(score: int) -> str:
    if score is None:
        return "score-red"
    if score >= 80:
        return "score-green"
    if score >= 60:
        return "score-yellow"
    if score >= 40:
        return "score-orange"
    return "score-red"


def _score_label(score: int) -> str:
    if score is None:
        return "NOT RATED"
    if score >= 80:
        return "RECOMMENDED"
    if score >= 60:
        return "CONDITIONAL"
    if score >= 40:
        return "CHALLENGING"
    return "NOT RECOMMENDED"


def _safe_get(data: dict, key: str, default="N/A"):
    """Safely extract a value from potentially nested or missing data."""
    if not data or not isinstance(data, dict):
        return default
    val = data.get(key)
    if val is None:
        return default
    return val


def _extract_agent_data(agent_name: str, raw_data: dict, score: int, summary: str, warnings: list, status: str) -> dict:
    """Build template-ready dict for a single agent."""
    meta = AGENT_META.get(agent_name, {})
    title = meta.get("title", agent_name.replace("_", " ").title())
    icon = meta.get("icon", "📌")

    # Key-value pairs
    kv_pairs = []
    for label, key in meta.get("extract_keys", []):
        val = _safe_get(raw_data, key)
        if isinstance(val, bool):
            val = "Yes" if val else "No"
        elif isinstance(val, (int, float)):
            if isinstance(val, float):
                val = f"{val:,.2f}"
            else:
                val = f"{val:,}"
        kv_pairs.append({"label": label, "value": str(val)})

    # Table data
    table_headers = meta.get("table_headers", [])
    table_rows = []
    table_field = meta.get("table_field")
    if table_field and raw_data and isinstance(raw_data, dict):
        items = raw_data.get(table_field)
        if isinstance(items, list):
            for item in items[:10]:
                if isinstance(item, dict):
                    row = [str(item.get(k, "N/A")) for k in meta.get("table_keys", [])]
                    table_rows.append(row)
                elif isinstance(item, str):
                    table_rows.append([item] + [""] * (len(table_headers) - 1))

    return {
        "name": agent_name,
        "title": title,
        "icon": icon,
        "score": score if score is not None else 0,
        "badge_class": _score_badge_class(score if score is not None else 0),
        "status": status or "pending",
        "summary": summary or "",
        "warnings": warnings or [],
        "kv_pairs": kv_pairs,
        "table_headers": table_headers,
        "table_rows": table_rows,
    }


def _derive_findings(agents_data: list) -> tuple:
    """Derive top strengths and risks from agent results."""
    strengths = []
    risks = []

    sorted_agents = sorted(agents_data, key=lambda a: a["score"], reverse=True)

    for agent in sorted_agents[:3]:
        if agent["score"] >= 60:
            strengths.append(f"{agent['title']}: Score {agent['score']}/100 — {agent['summary'][:100]}" if agent['summary'] else f"{agent['title']}: Score {agent['score']}/100")
        else:
            strengths.append(f"{agent['title']}: Score {agent['score']}/100")

    for agent in sorted_agents[-3:]:
        if agent["score"] < 70:
            risk_text = agent['warnings'][0] if agent['warnings'] else f"Score {agent['score']}/100 indicates potential challenges"
            risks.append(f"{agent['title']}: {risk_text}")
        else:
            risks.append(f"{agent['title']}: No significant risks identified (Score {agent['score']}/100)")

    if not strengths:
        strengths = ["Analysis data pending", "Additional evaluation recommended", "Contact SkyBase for details"]
    if not risks:
        risks = ["No significant risks identified", "Standard due diligence recommended", "Monitor regulatory changes"]

    return strengths[:3], risks[:3]


def generate_report(analysis_id: str, db_session) -> str:
    """
    Generate PDF report for a completed analysis.
    Returns: absolute file path to the generated PDF.
    """
    from app.models.analysis import Analysis, AgentResult

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    analysis = db_session.query(Analysis).filter_by(id=analysis_id).first()
    if not analysis:
        raise ValueError(f"Analysis {analysis_id} not found")

    agent_results = db_session.query(AgentResult).filter_by(analysis_id=analysis_id).all()

    # Build agent data for template
    agent_order = ["airspace", "zoning", "power", "structural", "regulatory", "cost", "noise"]
    agents_data = []
    result_map = {ar.agent_name.value: ar for ar in agent_results}

    for name in agent_order:
        ar = result_map.get(name)
        if ar:
            agents_data.append(_extract_agent_data(
                agent_name=name,
                raw_data=ar.raw_data or {},
                score=ar.score,
                summary=ar.summary,
                warnings=ar.warnings,
                status=ar.status.value if ar.status else "pending",
            ))
        else:
            agents_data.append(_extract_agent_data(
                agent_name=name,
                raw_data={},
                score=0,
                summary="Agent did not complete.",
                warnings=["No data available for this agent"],
                status="failed",
            ))

    overall_score = analysis.overall_score or 0
    strengths, risks = _derive_findings(agents_data)

    address = analysis.address_formatted or analysis.address_input or "Unknown Address"

    template_context = {
        "address": address,
        "overall_score": overall_score,
        "score_badge_class": _score_badge_class(overall_score),
        "score_color_class": _score_color_class(overall_score),
        "score_label": _score_label(overall_score),
        "generated_date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
        "agents": agents_data,
        "strengths": strengths,
        "risks": risks,
    }

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html")
    html_content = template.render(**template_context)

    pdf_path = str(REPORTS_DIR / f"{analysis_id}.pdf")
    HTML(string=html_content).write_pdf(pdf_path)

    return pdf_path
