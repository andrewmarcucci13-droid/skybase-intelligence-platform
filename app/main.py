"""
SkyBase Intelligence Platform — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
from dotenv import load_dotenv

load_dotenv()

from app.api.routes import analyses, health

# ── Rate limiter (Fix #8) ─────────────────────────────────────────────────────
# 10 requests / minute per IP globally; individual endpoints can override.
limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])


# ── Lifespan context manager (Fix #6: replaces deprecated @on_event) ─────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup (dev convenience). Clean up on shutdown."""
    from app.db.base import Base, engine
    from app.models import analysis  # noqa — ensure models are registered
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: dispose connection pool
    engine.dispose()


app = FastAPI(
    title="SkyBase Intelligence Platform",
    description="AI-powered vertiport site feasibility analysis",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate-limit exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
        "https://skybaseintel.com",
        "https://www.skybaseintel.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, tags=["health"])
app.include_router(analyses.router, prefix="/api/v1/analyses", tags=["analyses"])
