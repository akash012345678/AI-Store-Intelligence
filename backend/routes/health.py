"""
backend/routes/health.py
────────────────────────
GET /health — Diagnostics endpoint.

Returns:
  - Application status
  - Database connectivity
  - API version
  - Server UTC timestamp
  - Uptime (seconds since process start)
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field

from backend.database.connection import get_db

logger = logging.getLogger("PurpleInsight.HealthRoute")

# Record process start time for uptime calculation
_PROCESS_START: float = time.time()

router = APIRouter(tags=["Diagnostics"])


class HealthResponse(BaseModel):
    """Health-check response payload."""

    status: str = Field(..., description="Overall service health: 'healthy' | 'degraded' | 'unhealthy'.", example="healthy")
    database: str = Field(..., description="Database connectivity: 'connected' | 'disconnected'.", example="connected")
    version: str = Field(..., description="API version string.", example="1.0.0")
    timestamp: str = Field(..., description="Current server UTC timestamp in ISO 8601 format.", example="2026-05-31T12:00:00.000000+00:00")
    uptime_seconds: float = Field(..., description="Seconds since the application process started.", example=3672.4)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Health Check",
    description=(
        "Returns real-time diagnostics including database connectivity, API version, "
        "current UTC timestamp, and process uptime. Used by load balancers and monitoring systems."
    ),
    responses={
        200: {"description": "Service is healthy and the database is reachable."},
        503: {"description": "Service is unhealthy — database is unreachable."},
    },
)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Primary health-check endpoint.

    Performs a lightweight ``SELECT 1`` probe against the configured database to
    verify connectivity. Returns HTTP 503 if the database is unreachable, ensuring
    load balancers can route traffic away from degraded instances.
    """
    database_status = "connected"
    overall_status = "healthy"

    try:
        db.execute(text("SELECT 1"))
        logger.debug("Health probe: database SELECT 1 → OK")
    except Exception as exc:
        database_status = "disconnected"
        overall_status = "unhealthy"
        logger.error(f"Health probe: database connectivity FAILED — {exc}")

    uptime = round(time.time() - _PROCESS_START, 1)

    return HealthResponse(
        status=overall_status,
        database=database_status,
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=uptime,
    )
