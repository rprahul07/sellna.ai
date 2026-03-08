"""Sales Agentic AI — FastAPI Application Entry Point.

This is the main application that wires together:
  - FastAPI app with CORS and exception handling
  - Logging configuration (structlog)
  - Database lifecycle (create tables on startup)
  - All API routers under /api/v1/
  - Prometheus metrics endpoint
  - OpenAPI docs at /docs
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.postgres import create_all_tables, dispose_engine

# ---------------------------------------------------------------------------
# Bootstrap logging before anything else
# ---------------------------------------------------------------------------
configure_logging()
logger = get_logger(__name__)
_settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handles startup and graceful shutdown."""
    logger.info(
        "startup",
        app=_settings.app_name,
        version=_settings.app_version,
        env=_settings.environment,
    )
    # Create all database tables
    await create_all_tables()
    logger.info("startup.db.tables_created")

    yield

    logger.info("shutdown.start")
    await dispose_engine()
    logger.info("shutdown.complete")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


app = FastAPI(
    title=_settings.app_name,
    version=_settings.app_version,
    description=(
        "**Sales Agentic AI** — enterprise-grade multi-agent sales intelligence platform.\n\n"
        "Uses a chain of autonomous agents to analyze markets, discover competitors, "
        "generate ICPs, create buyer personas, and produce personalized outreach content.\n\n"
        "### Pipeline\n"
        "`Company Input → Domain Intelligence → Competitor Discovery → "
        "Web Intelligence → Data Cleaning → Gap Analysis (RAG) → "
        "ICP Generation → Persona Generation → Outreach Generation`"
    ),
    openapi_tags=[
        {"name": "Company Intelligence", "description": "Module 1 — Foundation"},
        {"name": "Competitive Intelligence", "description": "Competitor discovery & scraping"},
        {"name": "ICP Generation", "description": "Ideal Customer Profile generation"},
        {"name": "Persona Generation", "description": "Buyer persona generation"},
        {"name": "Outreach Generation", "description": "Personalized outreach content"},
        {"name": "Analytics", "description": "Performance tracking & optimization"},
        {"name": "Pipeline Orchestration", "description": "Run the full end-to-end pipeline"},
        {"name": "Auth", "description": "JWT token endpoint"},
        {"name": "Health", "description": "Health & readiness checks"},
    ],
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request timing middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def add_process_time_header(request: Request, call_next) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    logger.debug(
        "http.request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return response

# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(api_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Auth endpoint (token generation — for development/testing)
# ---------------------------------------------------------------------------

from fastapi import APIRouter as _R
from app.core.security import create_access_token
from pydantic import BaseModel

_auth_router = _R(tags=["Auth"])


class TokenRequest(BaseModel):
    sub: str = "admin"
    role: str = "admin"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@_auth_router.post("/api/auth/token", response_model=TokenResponse, summary="Generate a JWT token")
async def generate_token(payload: TokenRequest) -> TokenResponse:
    """Development utility — generates a JWT for testing protected endpoints."""
    token = create_access_token(sub=payload.sub, role=payload.role)
    return TokenResponse(access_token=token)


app.include_router(_auth_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

_health_router = _R(tags=["Health"])


@_health_router.get("/health", summary="Health check")
async def health() -> dict:
    return {"status": "ok", "app": _settings.app_name, "version": _settings.app_version}


@_health_router.get("/ready", summary="Readiness check")
async def ready() -> dict:
    """Returns 200 when the app is fully initialized."""
    return {"status": "ready"}


app.include_router(_health_router)


# ---------------------------------------------------------------------------
# Prometheus metrics (optional)
# ---------------------------------------------------------------------------

if _settings.prometheus_enabled:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore
        Instrumentator().instrument(app).expose(app, endpoint=_settings.prometheus_path)
        logger.info("prometheus.enabled", path=_settings.prometheus_path)
    except ImportError:
        logger.warning("prometheus.disabled", reason="prometheus-fastapi-instrumentator not installed")


# ---------------------------------------------------------------------------
# Dev server runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=_settings.environment == "development",
        log_level=_settings.log_level.lower(),
    )
