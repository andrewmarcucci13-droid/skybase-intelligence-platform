"""
Analyses router — create, read, and manage site analysis jobs.
"""
import os
import re
import httpx
import stripe
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse, FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime, timezone
import uuid

from app.db.base import get_db
from app.models.analysis import Analysis, Customer, AgentResult, AnalysisStatus, PaymentStatus, AgentName, AgentStatus

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ── Geocoding helpers (Fix #1, #2) ────────────────────────────────────────────

async def geocode_address(address: str) -> tuple[float, float, str]:
    """
    Convert a free-text address to (lat, lon, formatted_address).

    Strategy:
      1. Nominatim (OpenStreetMap) — free, no key required
      2. Google Maps Geocoding API — fallback if GOOGLE_MAPS_API_KEY is set

    Raises HTTPException(422) if geocoding fails from all providers.
    """
    # --- Nominatim ---
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "SkyBase-Intelligence/0.1 (contact@skybaseintel.com)"},
        ) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "addressdetails": 1, "limit": 1},
            )
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    r = results[0]
                    lat = float(r["lat"])
                    lon = float(r["lon"])
                    formatted = r.get("display_name", address)
                    return lat, lon, formatted
    except Exception:
        pass

    # --- Google Maps fallback ---
    google_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if google_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": address, "key": google_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "OK" and data.get("results"):
                        loc = data["results"][0]["geometry"]["location"]
                        formatted = data["results"][0].get("formatted_address", address)
                        return loc["lat"], loc["lng"], formatted
        except Exception:
            pass

    raise HTTPException(
        status_code=422,
        detail=(
            "Could not geocode the provided address. "
            "Please supply a specific US street address (e.g., '123 Main St, Miami, FL 33101')."
        ),
    )


# ── Schemas ───────────────────────────────────────────────────────────────────

# US ZIP code pattern (5-digit or ZIP+4)
_US_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
# US state abbreviations
_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}


class AnalysisCreateRequest(BaseModel):
    address: str
    property_type: Optional[str] = "unknown"   # rooftop | ground | airport | garage
    customer_email: EmailStr

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """
        Fix #7: Reject blank addresses and non-US addresses.
        Heuristic: require at least 10 chars and either a US ZIP code or
        a recognisable US state abbreviation in the string.
        """
        v = v.strip()
        if not v:
            raise ValueError("Address must not be empty.")
        if len(v) < 10:
            raise ValueError(
                "Address is too short. Please provide a full US street address "
                "(e.g., '1600 Pennsylvania Ave NW, Washington, DC 20500')."
            )
        # Check for US ZIP or state abbreviation (case-insensitive token match)
        tokens = re.split(r"[\s,]+", v.upper())
        has_us_state = any(t in _US_STATES for t in tokens)
        has_us_zip   = bool(_US_ZIP_RE.search(v))
        if not (has_us_state or has_us_zip):
            raise ValueError(
                "SkyBase currently supports US addresses only. "
                "Please include a US state abbreviation or ZIP code "
                "(e.g., '123 Main St, Austin, TX 78701')."
            )
        return v

    @field_validator("property_type")
    @classmethod
    def validate_property_type(cls, v: Optional[str]) -> str:
        allowed = {"rooftop", "ground", "airport", "garage", "unknown"}
        if v and v.lower() not in allowed:
            raise ValueError(f"property_type must be one of: {', '.join(sorted(allowed))}")
        return (v or "unknown").lower()


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str
    overall_score: Optional[int]
    address_formatted: Optional[str]
    report_url: Optional[str]
    created_at: str
    completed_at: Optional[str]
    agents: list


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", summary="Create analysis and return Stripe checkout URL")
@limiter.limit("5/minute")   # Fix #8: tighter limit for the paid action
async def create_analysis(
    request: Request,
    payload: AnalysisCreateRequest,
    db: Session = Depends(get_db),
):
    """
    1. Validate address (non-empty, US)
    2. Geocode address → lat/lon   ← Fix #1/#2: geocoding happens HERE
    3. Upsert customer record
    4. Create Analysis row (status=pending, payment_status=unpaid, lat/lon populated)
    5. Create 7 AgentResult rows (status=pending)
    6. Create Stripe Checkout session
    7. Return { checkout_url, analysis_id }
    """
    # Geocode BEFORE creating the DB record so lat/lon is never null (Fix #1, #2)
    lat, lon, formatted_address = await geocode_address(payload.address)

    # Upsert customer
    customer = db.query(Customer).filter_by(email=payload.customer_email).first()
    if not customer:
        customer = Customer(email=payload.customer_email)
        db.add(customer)
        db.flush()

    # Create analysis — lat/lon are populated from geocoding result
    analysis = Analysis(
        address_input=payload.address,
        address_formatted=formatted_address,
        latitude=lat,
        longitude=lon,
        property_type=payload.property_type,
        customer_email=payload.customer_email,
        customer_id=customer.id,
    )
    db.add(analysis)
    db.flush()

    # Seed 7 agent_results rows
    for agent in AgentName:
        db.add(AgentResult(analysis_id=analysis.id, agent_name=agent))
    db.commit()
    db.refresh(analysis)

    # Geocode the address
    from app.services.geocoding import geocode_address_sync
    try:
        geo = geocode_address_sync(payload.address)
        analysis.latitude = geo["lat"]
        analysis.longitude = geo["lon"]
        analysis.address_formatted = geo["formatted"]
    except Exception as e:
        # Store error but don't fail the request — user still gets to pay
        analysis.address_formatted = payload.address
    db.commit()

    # Stripe Checkout session
    price_id = os.getenv("STRIPE_PRICE_ID", "")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=payload.customer_email,
            metadata={"analysis_id": str(analysis.id)},
            success_url=f"{frontend_url}/status/{analysis.id}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{frontend_url}/analyze?cancelled=true",
        )
        analysis.stripe_session_id = session.id
        db.commit()
    except stripe.error.StripeError as e:
        # In dev/test without Stripe keys, return a mock
        return {
            "analysis_id": str(analysis.id),
            "checkout_url": f"{frontend_url}/status/{analysis.id}?dev_bypass=true",
            "stripe_error": str(e),
            "note": "Stripe not configured — use dev_bypass flow",
        }

    return {
        "analysis_id": str(analysis.id),
        "checkout_url": session.url,
    }


@router.get("/{analysis_id}", summary="Get analysis status and agent results")
@limiter.limit("30/minute")
def get_analysis(request: Request, analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter_by(id=analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    agents_data = []
    for ar in analysis.agent_results:
        agents_data.append({
            "agent_name": ar.agent_name.value,
            "status": ar.status.value,
            "score": ar.score,
            "summary": ar.summary,
            "warnings": ar.warnings or [],
        })

    return {
        "analysis_id": str(analysis.id),
        "status": analysis.status.value,
        "overall_score": analysis.overall_score,
        "address_formatted": analysis.address_formatted,
        "address_input": analysis.address_input,
        "report_url": analysis.report_url,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
        "agents": agents_data,
    }


@router.post("/{analysis_id}/dev-run", summary="DEV ONLY: trigger pipeline without payment")
def dev_run(analysis_id: str, db: Session = Depends(get_db)):
    """Development bypass — starts the analysis pipeline without requiring Stripe payment."""
    import os
    if os.getenv("APP_ENV") != "development":
        raise HTTPException(status_code=403, detail="Only available in development mode")

    analysis = db.query(Analysis).filter_by(id=analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis.payment_status = PaymentStatus.PAID
    analysis.status = AnalysisStatus.PROCESSING
    from datetime import datetime, timezone
    analysis.paid_at = datetime.now(timezone.utc)
    analysis.processing_started = datetime.now(timezone.utc)
    db.commit()

    try:
        from app.tasks.orchestrator import run_analysis_pipeline
        run_analysis_pipeline.delay(analysis_id)
        return {"status": "pipeline_started", "analysis_id": analysis_id}
    except Exception as e:
        return {"status": "celery_not_available", "analysis_id": analysis_id, "note": str(e)}


@router.post("/webhook/stripe", summary="Stripe webhook — triggers agent pipeline after payment")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Fix #2: The Celery pipeline is only dispatched AFTER the analysis already
    has lat/lon (populated at creation time). No geocoding needed here.
    """
    payload = await request.body()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        analysis_id = session.get("metadata", {}).get("analysis_id")

        if analysis_id:
            analysis = db.query(Analysis).filter_by(id=analysis_id).first()
            if analysis:
                # Defensive guard: if lat/lon somehow missing, fail loudly here
                # rather than silently inside Celery (Fix #2)
                if analysis.latitude is None or analysis.longitude is None:
                    print(
                        f"[ERROR] Analysis {analysis_id} has no lat/lon at webhook time — "
                        "geocoding must have failed at creation. Aborting pipeline dispatch."
                    )
                    return JSONResponse(content={"received": True, "error": "missing_geocoding"})

                analysis.payment_status = PaymentStatus.PAID
                analysis.stripe_payment_intent = session.get("payment_intent")
                analysis.amount_paid_cents = session.get("amount_total")
                analysis.paid_at = datetime.now(timezone.utc)
                analysis.status = AnalysisStatus.PROCESSING
                analysis.processing_started = datetime.now(timezone.utc)
                db.commit()

                # Fire the Celery orchestration pipeline
                try:
                    from app.tasks.orchestrator import run_analysis_pipeline
                    run_analysis_pipeline.delay(analysis_id)
                except Exception as e:
                    # Log but don't fail — Celery may not be running in dev
                    print(f"[WARN] Could not enqueue Celery task: {e}")

    return JSONResponse(content={"received": True})


@router.post("/{analysis_id}/checkout", summary="Create Stripe Checkout Session")
@limiter.limit("10/minute")
async def create_checkout_session(
    request: Request,
    analysis_id: str,
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout Session for an existing analysis."""
    analysis = db.query(Analysis).filter_by(id=analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    price_id = os.getenv("STRIPE_PRICE_ID", "price_1TNhCiB6nlyxBcZvphYPYmK5")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=analysis.customer_email,
            metadata={"analysis_id": str(analysis.id)},
            success_url=f"{frontend_url}/status/{analysis.id}?payment=success",
            cancel_url=f"{frontend_url}/analyze?cancelled=true",
        )
        analysis.stripe_session_id = session.id
        db.commit()
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")


@router.get("/{analysis_id}/report", summary="Download PDF report")
@limiter.limit("20/minute")
def download_report(request: Request, analysis_id: str, db: Session = Depends(get_db)):
    """Download the generated PDF report for a completed analysis."""
    analysis = db.query(Analysis).filter_by(id=analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if analysis.status != AnalysisStatus.COMPLETE:
        raise HTTPException(status_code=400, detail="Analysis is not yet complete")

    pdf_path = analysis.report_s3_key
    if not pdf_path or not Path(pdf_path).exists():
        # Try the default path
        default_path = f"/tmp/skybase_reports/{analysis_id}.pdf"
        if Path(default_path).exists():
            pdf_path = default_path
        else:
            raise HTTPException(status_code=404, detail="Report PDF not found. It may still be generating.")

    filename = f"SkyBase_Report_{analysis_id[:8]}.pdf"
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
