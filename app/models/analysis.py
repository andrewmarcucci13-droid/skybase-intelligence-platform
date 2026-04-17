"""
SkyBase Database Models
PostgreSQL schema for analyses, agent_results, and customers.
"""
import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, DateTime, Text, Integer,
    ForeignKey, Enum as SAEnum, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


# ── Enums ────────────────────────────────────────────────────────────────────

class AnalysisStatus(str, enum.Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETE   = "complete"
    FAILED     = "failed"


class PaymentStatus(str, enum.Enum):
    UNPAID   = "unpaid"
    PAID     = "paid"
    REFUNDED = "refunded"


class AgentName(str, enum.Enum):
    AIRSPACE   = "airspace"
    ZONING     = "zoning"
    POWER      = "power"
    STRUCTURAL = "structural"
    REGULATORY = "regulatory"
    COST       = "cost"
    NOISE      = "noise"


class AgentStatus(str, enum.Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    COMPLETE = "complete"
    FAILED   = "failed"


# ── Models ───────────────────────────────────────────────────────────────────

class Analysis(Base):
    """
    Core analysis record. Created when user submits address.
    Transitions: pending → (after payment) processing → complete | failed
    """
    __tablename__ = "analyses"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Input
    address_input      = Column(String(500), nullable=False)
    address_formatted  = Column(String(500), nullable=True)
    latitude           = Column(Float, nullable=True)
    longitude          = Column(Float, nullable=True)
    property_type      = Column(String(100), nullable=True)   # rooftop | ground | airport | garage

    # Workflow state
    status             = Column(SAEnum(AnalysisStatus), default=AnalysisStatus.PENDING, nullable=False)
    overall_score      = Column(Integer, nullable=True)       # 0-100, set after aggregation

    # Payment
    payment_status     = Column(SAEnum(PaymentStatus), default=PaymentStatus.UNPAID, nullable=False)
    stripe_session_id  = Column(String(200), nullable=True, unique=True)
    stripe_payment_intent = Column(String(200), nullable=True)
    amount_paid_cents  = Column(Integer, nullable=True)

    # Customer
    customer_email     = Column(String(255), nullable=False)
    customer_id        = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)

    # Output
    report_url         = Column(String(1000), nullable=True)  # S3 presigned or public URL
    report_s3_key      = Column(String(500), nullable=True)

    # Timestamps
    created_at         = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    paid_at            = Column(DateTime(timezone=True), nullable=True)
    processing_started = Column(DateTime(timezone=True), nullable=True)
    completed_at       = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    agent_results      = relationship("AgentResult", back_populates="analysis", cascade="all, delete-orphan")
    customer           = relationship("Customer", back_populates="analyses")

    __table_args__ = (
        Index("ix_analyses_customer_email", "customer_email"),
        Index("ix_analyses_status", "status"),
        Index("ix_analyses_stripe_session", "stripe_session_id"),
    )

    def __repr__(self):
        return f"<Analysis id={self.id} address={self.address_input!r} status={self.status}>"


class AgentResult(Base):
    """
    One row per agent per analysis. Populated as each Celery task completes.
    raw_data holds the full JSON payload from the agent.
    """
    __tablename__ = "agent_results"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False)
    agent_name  = Column(SAEnum(AgentName), nullable=False)
    status      = Column(SAEnum(AgentStatus), default=AgentStatus.PENDING, nullable=False)

    # Results
    raw_data    = Column(JSON, nullable=True)     # Full agent output dict
    score       = Column(Integer, nullable=True)  # 0-100 readiness score
    summary     = Column(Text, nullable=True)     # Human-readable 1-paragraph summary
    warnings    = Column(JSON, nullable=True)     # List[str] of warning strings
    error_message = Column(Text, nullable=True)

    # Timestamps
    started_at  = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship
    analysis    = relationship("Analysis", back_populates="agent_results")

    __table_args__ = (
        Index("ix_agent_results_analysis_id", "analysis_id"),
        Index("ix_agent_results_agent_name", "agent_name"),
    )

    def __repr__(self):
        return f"<AgentResult analysis={self.analysis_id} agent={self.agent_name} score={self.score}>"


class Customer(Base):
    """
    Customer record. Created on first analysis. Enables subscription tracking.
    """
    __tablename__ = "customers"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email              = Column(String(255), nullable=False, unique=True, index=True)
    stripe_customer_id = Column(String(200), nullable=True, unique=True)
    tier               = Column(String(50), default="single", nullable=False)  # single | bulk | api
    analyses_count     = Column(Integer, default=0, nullable=False)
    created_at         = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_active_at     = Column(DateTime(timezone=True), nullable=True)

    # Relationship
    analyses           = relationship("Analysis", back_populates="customer")

    def __repr__(self):
        return f"<Customer email={self.email!r} tier={self.tier}>"
