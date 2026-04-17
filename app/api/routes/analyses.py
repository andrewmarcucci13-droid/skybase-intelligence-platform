"""
Analyses router — create, read, and manage site analysis jobs.
"""
import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timezone
import uuid

from app.db.base import get_db
from app.models.analysis import Analysis, Customer, AgentResult, AnalysisStatus, PaymentStatus, AgentName, AgentStatus

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnalysisCreateRequest(BaseModel):
    address: str
    property_type: Optional[str] = "unknown"   # rooftop | ground | airport | garage
    customer_email: EmailStr


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
def create_analysis(payload: AnalysisCreateRequest, db: Session = Depends(get_db)):
    """
    1. Upsert customer record
    2. Create Analysis row (status=pending, payment_status=unpaid)
    3. Create 7 AgentResult rows (status=pending)
    4. Create Stripe Checkout session
    5. Return { checkout_url, analysis_id }
    """
    # Upsert customer
    customer = db.query(Customer).filter_by(email=payload.customer_email).first()
    if not customer:
        customer = Customer(email=payload.customer_email)
        db.add(customer)
        db.flush()

    # Create analysis
    analysis = Analysis(
        address_input=payload.address,
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
def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
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


@router.post("/webhook/stripe", summary="Stripe webhook — triggers agent pipeline after payment")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
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
