"""
SkyBase Intelligence Platform — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

from app.api.routes import analyses, health

app = FastAPI(
    title="SkyBase Intelligence Platform",
    description="AI-powered vertiport site feasibility analysis",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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


@app.on_event("startup")
async def startup_event():
    """Create DB tables if they don't exist (dev convenience)."""
    from app.db.base import Base, engine
    from app.models import analysis  # noqa — ensure models are registered
    Base.metadata.create_all(bind=engine)
