"""
backend/routes/events.py
────────────────────────
GET /events — Paginated dwell-log telemetry event stream.

Features:
  - Full pagination   : page / limit with total_records / total_pages
  - Zone filter       : ?zone_id=aisle_1_fresh
  - Track filter      : ?track_id=701
  - Date range        : ?start_time=...&end_time=...
  - Sort order        : ?sort=desc (default) | asc (by entered_at)

Each event record maps directly to a ``DwellLog`` ORM row:
  id, store_id, zone_id, track_id, entered_at, exited_at, duration_seconds
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import and_, desc, asc
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.models import DwellLog
from backend.schemas.common import PaginatedResponse, PaginationMetadata

logger = logging.getLogger("PurpleInsight.EventsRoute")

router = APIRouter(tags=["Telemetry Events"])


# ──────────────────────────────────────────────────
# Schema (inline — event-specific, no separate file needed)
# ──────────────────────────────────────────────────

class EventDwellResponse(BaseModel):
    """
    Pydantic v2 schema representing a single dwell-log telemetry event.

    Maps 1-to-1 with a ``DwellLog`` ORM row; ``from_attributes=True`` enables
    direct ORM → Pydantic coercion without manual dict conversion.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int = Field(..., description="Dwell log primary key.", example=1)
    store_id: str = Field(..., description="Store this event belongs to.", example="store-101")
    zone_id: str = Field(..., description="Layout zone ID where the dwell was recorded.", example="aisle_1_fresh")
    track_id: int = Field(..., description="CCTV tracker-assigned shopper track ID.", example=701)
    entered_at: datetime = Field(..., description="UTC timestamp when the shopper entered the zone.")
    exited_at: datetime = Field(..., description="UTC timestamp when the shopper exited the zone.")
    duration_seconds: float = Field(
        ...,
        ge=0.0,
        description="Total dwell duration in seconds.",
        example=38.5,
    )


# ──────────────────────────────────────────────────
# Route
# ──────────────────────────────────────────────────

@router.get(
    "/events",
    response_model=PaginatedResponse[EventDwellResponse],
    status_code=status.HTTP_200_OK,
    summary="Dwell Telemetry Event Log",
    description=(
        "Returns a paginated stream of dwell-log telemetry events. "
        "Supports filtering by zone, shopper track ID, and date range, "
        "plus ascending/descending sort by entry timestamp. "
        "Each event maps to a ``DwellLog`` record capturing when a shopper "
        "entered and exited a specific layout zone."
    ),
    responses={
        200: {"description": "Paginated event list successfully returned."},
    },
)
def get_events(
    store_id: str = Query("store-101", description="Target store identifier.", example="store-101"),
    zone_id: Optional[str] = Query(None, description="Filter by layout zone ID.", example="aisle_1_fresh"),
    track_id: Optional[int] = Query(None, description="Filter by shopper track ID.", example=701),
    start_time: Optional[str] = Query(
        None,
        description="ISO 8601 start datetime filter (inclusive).",
        example="2026-05-01T00:00:00Z",
    ),
    end_time: Optional[str] = Query(
        None,
        description="ISO 8601 end datetime filter (inclusive).",
        example="2026-05-31T23:59:59Z",
    ),
    sort: str = Query(
        "desc",
        description="Sort order for entered_at timestamp: 'asc' (oldest first) or 'desc' (newest first).",
        example="desc",
        pattern="^(asc|desc)$",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed).", example=1),
    limit: int = Query(20, ge=1, le=100, description="Maximum records per page.", example=20),
    db: Session = Depends(get_db),
) -> PaginatedResponse[EventDwellResponse]:
    """
    Paginated dwell-event retrieval with compound filtering and bidirectional sorting.

    All date-time parsing is guarded to return a descriptive warning log (not a 422)
    on malformed input, defaulting to no date filter for that boundary.
    """
    filters = [DwellLog.store_id == store_id]

    if zone_id:
        filters.append(DwellLog.zone_id == zone_id)
    if track_id is not None:
        filters.append(DwellLog.track_id == track_id)

    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00")).replace(tzinfo=None)
            filters.append(DwellLog.entered_at >= start_dt)
        except ValueError:
            logger.warning(f"[events] invalid start_time ignored: {start_time!r}")

    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00")).replace(tzinfo=None)
            filters.append(DwellLog.entered_at <= end_dt)
        except ValueError:
            logger.warning(f"[events] invalid end_time ignored: {end_time!r}")

    query = db.query(DwellLog).filter(and_(*filters))
    total_records = query.count()
    total_pages = (total_records + limit - 1) // limit if total_records > 0 else 0
    offset = (page - 1) * limit

    order_clause = desc(DwellLog.entered_at) if sort == "desc" else asc(DwellLog.entered_at)
    events = query.order_by(order_clause).offset(offset).limit(limit).all()

    logger.info(
        f"[events] store={store_id} zone={zone_id} track={track_id} "
        f"sort={sort} total={total_records} page={page}/{total_pages}"
    )

    return PaginatedResponse[EventDwellResponse](
        metadata=PaginationMetadata(
            page=page,
            limit=limit,
            total_records=total_records,
            total_pages=total_pages,
        ),
        data=events,
    )
