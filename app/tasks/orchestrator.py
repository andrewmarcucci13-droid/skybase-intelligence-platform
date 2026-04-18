"""
SkyBase Celery Orchestration Layer
====================================
Uses celery.group + chord to run all 7 agents in parallel,
then aggregate results when all complete.
"""
import os
from celery import Celery, group, chord
from datetime import datetime, timezone

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "skybase",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.pdf_task"],  # ensure pipeline.pdf task is registered on the worker
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.task_track_started = True


# ── Individual agent tasks ────────────────────────────────────────────────────

@celery_app.task(bind=True, name="agents.airspace")
def task_airspace(self, analysis_id: str, lat: float, lon: float):
    return _run_agent(analysis_id, "airspace", lat, lon)


@celery_app.task(bind=True, name="agents.zoning")
def task_zoning(self, analysis_id: str, lat: float, lon: float):
    return _run_agent(analysis_id, "zoning", lat, lon)


@celery_app.task(bind=True, name="agents.power")
def task_power(self, analysis_id: str, lat: float, lon: float):
    return _run_agent(analysis_id, "power", lat, lon)


@celery_app.task(bind=True, name="agents.structural")
def task_structural(self, analysis_id: str, lat: float, lon: float, property_type: str = "unknown"):
    # Fix #4: property_type is forwarded as a kwarg; _run_agent accepts **kwargs
    return _run_agent(analysis_id, "structural", lat, lon, property_type=property_type)


@celery_app.task(bind=True, name="agents.regulatory")
def task_regulatory(self, analysis_id: str, lat: float, lon: float):
    return _run_agent(analysis_id, "regulatory", lat, lon)


@celery_app.task(bind=True, name="agents.cost")
def task_cost(self, analysis_id: str, lat: float, lon: float, property_type: str = "unknown"):
    # Fix #4: property_type is forwarded as a kwarg; _run_agent accepts **kwargs
    return _run_agent(analysis_id, "cost", lat, lon, property_type=property_type)


@celery_app.task(bind=True, name="agents.noise")
def task_noise(self, analysis_id: str, lat: float, lon: float):
    return _run_agent(analysis_id, "noise", lat, lon)


# ── Generic agent runner ──────────────────────────────────────────────────────

def _run_agent(analysis_id: str, agent_name: str, lat: float, lon: float, **kwargs) -> dict:
    """
    Generic runner that calls the correct agent module.

    Fix #4: **kwargs is accepted so callers like task_structural / task_cost
    can pass property_type=... without a TypeError.  Each agent module that
    needs extra kwargs must accept them explicitly in its own signature.
    """
    from app.db.base import SessionLocal
    from app.models.analysis import AgentResult, AgentName, AgentStatus
    from datetime import datetime, timezone

    db = SessionLocal()
    result_row = None
    try:
        result_row = db.query(AgentResult).filter_by(
            analysis_id=analysis_id, agent_name=AgentName(agent_name)
        ).first()
        if result_row:
            result_row.status = AgentStatus.RUNNING
            result_row.started_at = datetime.now(timezone.utc)
            db.commit()

        # Dispatch to the correct agent module
        if agent_name == "airspace":
            from app.agents.agent_airspace import run_airspace_agent_sync
            result = run_airspace_agent_sync(lat, lon)
        elif agent_name == "zoning":
            from app.agents.agent_zoning import run_zoning_agent_sync
            result = run_zoning_agent_sync(lat, lon)
        elif agent_name == "power":
            from app.agents.agent_power import run_power_agent_sync
            result = run_power_agent_sync(lat, lon)
        elif agent_name == "structural":
            from app.agents.agent_structural import run_structural_agent_sync
            result = run_structural_agent_sync(lat, lon, **kwargs)
        elif agent_name == "regulatory":
            from app.agents.agent_regulatory import run_regulatory_agent_sync
            result = run_regulatory_agent_sync(lat, lon)
        elif agent_name == "cost":
            from app.agents.agent_cost import run_cost_agent_sync
            result = run_cost_agent_sync(lat, lon, **kwargs)
        elif agent_name == "noise":
            from app.agents.agent_noise import run_noise_agent_sync
            result = run_noise_agent_sync(lat, lon)
        else:
            result = {
                "score": 50,
                "summary": f"{agent_name.capitalize()} agent not recognized.",
                "warnings": [f"Unknown agent: {agent_name}"],
                "raw_data": {"status": "unknown_agent", "agent": agent_name},
            }

        # Persist result
        if result_row:
            result_row.status      = AgentStatus.COMPLETE
            result_row.score       = result["score"]
            result_row.summary     = result["summary"]
            result_row.warnings    = result["warnings"]
            result_row.raw_data    = result["raw_data"]
            result_row.completed_at = datetime.now(timezone.utc)
            db.commit()

        return {"agent": agent_name, "analysis_id": analysis_id, **result}

    except Exception as e:
        if result_row:
            result_row.status = AgentStatus.FAILED
            result_row.error_message = str(e)
            db.commit()
        raise
    finally:
        db.close()


# ── Aggregation chord callback ────────────────────────────────────────────────

@celery_app.task(name="pipeline.aggregate")
def aggregate_results(agent_results: list, analysis_id: str):
    """
    Called when all 7 agent tasks complete.
    Computes overall score (weighted average) and triggers PDF generation.
    """
    from app.db.base import SessionLocal
    from app.models.analysis import Analysis, AnalysisStatus
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        # Weighted scoring (can tune weights)
        WEIGHTS = {
            "airspace":   0.20,
            "zoning":     0.20,
            "power":      0.15,
            "structural": 0.15,
            "regulatory": 0.15,
            "cost":       0.10,
            "noise":      0.05,
        }
        total_weight = 0.0
        weighted_sum = 0.0
        for r in agent_results:
            if r and "agent" in r and r.get("score") is not None:
                w = WEIGHTS.get(r["agent"], 0.10)
                weighted_sum += r["score"] * w
                total_weight += w

        overall_score = int(weighted_sum / total_weight) if total_weight > 0 else 0

        analysis = db.query(Analysis).filter_by(id=analysis_id).first()
        if analysis:
            analysis.overall_score = overall_score
            analysis.status = AnalysisStatus.COMPLETE
            analysis.completed_at = datetime.now(timezone.utc)
            db.commit()

            # Trigger PDF generation
            try:
                from app.tasks.pdf_task import generate_report_pdf
                generate_report_pdf.delay(analysis_id)
            except Exception:
                pass  # PDF generation is non-blocking

        return {"analysis_id": analysis_id, "overall_score": overall_score}
    finally:
        db.close()


# ── Main pipeline dispatcher ──────────────────────────────────────────────────

@celery_app.task(name="pipeline.run")
def run_analysis_pipeline(analysis_id: str):
    """
    Entry point: dispatches all 7 agent tasks as a parallel group,
    then calls aggregate_results when all complete.

    Fix #3: Geocoding now happens in create_analysis (the API route) BEFORE
    the Analysis row is written to the DB.  By the time this task runs, lat/lon
    are guaranteed to be populated.  A defensive geocoding fallback is included
    here to handle any edge-case where the record somehow still lacks coordinates
    (e.g., a legacy row or a direct DB insert in tests).
    """
    import httpx
    import asyncio
    from app.db.base import SessionLocal
    from app.models.analysis import Analysis

    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter_by(id=analysis_id).first()
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")

        lat = analysis.latitude
        lon = analysis.longitude
        prop_type = analysis.property_type or "unknown"

        # Fix #3: defensive geocoding fallback — should normally not be needed
        # because geocoding is done at creation time in the API route.
        if lat is None or lon is None:
            address = analysis.address_input
            if not address:
                raise ValueError(
                    f"Analysis {analysis_id} is missing both lat/lon and address_input. "
                    "Cannot proceed."
                )

            async def _geocode(addr: str):
                async with httpx.AsyncClient(
                    timeout=10.0,
                    headers={"User-Agent": "SkyBase-Intelligence/0.1"},
                ) as client:
                    resp = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={"q": addr, "format": "json", "limit": 1},
                    )
                    if resp.status_code == 200:
                        results = resp.json()
                        if results:
                            return float(results[0]["lat"]), float(results[0]["lon"]), results[0].get("display_name", addr)
                # Fallback: Google Maps
                google_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
                if google_key:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(
                            "https://maps.googleapis.com/maps/api/geocode/json",
                            params={"address": addr, "key": google_key},
                        )
                        data = resp.json()
                        if data.get("status") == "OK" and data.get("results"):
                            loc = data["results"][0]["geometry"]["location"]
                            fmt = data["results"][0].get("formatted_address", addr)
                            return loc["lat"], loc["lng"], fmt
                raise ValueError(
                    f"Analysis {analysis_id} missing lat/lon — geocoding fallback also failed "
                    f"for address: {addr!r}"
                )

            lat, lon, formatted = asyncio.run(_geocode(address))
            analysis.latitude = lat
            analysis.longitude = lon
            analysis.address_formatted = formatted
            db.commit()

    finally:
        db.close()

    agent_tasks = group(
        task_airspace.s(analysis_id, lat, lon),
        task_zoning.s(analysis_id, lat, lon),
        task_power.s(analysis_id, lat, lon),
        task_structural.s(analysis_id, lat, lon, prop_type),
        task_regulatory.s(analysis_id, lat, lon),
        task_cost.s(analysis_id, lat, lon, prop_type),
        task_noise.s(analysis_id, lat, lon),
    )

    pipeline = chord(agent_tasks)(aggregate_results.s(analysis_id=analysis_id))
    return pipeline
