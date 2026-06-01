"""
backend/routes/alerts.py
────────────────────────
GET /alerts — Paginated operational alert log with filtering.

Features:
  - Runs live alert evaluation (queue congestion / overcrowding / loitering)
    before returning the response so the list is always up-to-date.
  - Pagination   : page / limit query params with total_records + total_pages
  - Filtering    : severity (LOW | MEDIUM | HIGH | CRITICAL), date range
  - Sorting      : newest-first by default (descending timestamp)

Query parameters:
  - store_id    (required) : target store
  - severity    (optional) : filter by alert severity level
  - start_time  (optional) : ISO 8601 window start
  - end_time    (optional) : ISO 8601 window end
  - page        (optional) : page number, default 1
  - limit       (optional) : records per page, default 20, max 100
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.models import Alert
from backend.services.alerts import AlertService
from backend.schemas.alerts import AlertResponse, AlertSeverity
from backend.schemas.common import PaginatedResponse, PaginationMetadata

logger = logging.getLogger("PurpleInsight.AlertsRoute")

router = APIRouter(tags=["Alerts"])


@router.get(
    "/alerts",
    response_model=PaginatedResponse[AlertResponse],
    status_code=status.HTTP_200_OK,
    summary="Operational Alert Log",
    description=(
        "Returns a paginated, filterable list of store operational alerts. "
        "Before returning, the endpoint runs a live evaluation cycle — checking "
        "for queue congestion, overcrowding, and loitering — so the list always "
        "reflects the current store state. Supports severity filtering and date-range "
        "scoping. Alerts are ordered newest-first."
    ),
    responses={
        200: {"description": "Paginated alert list successfully returned."},
    },
)
def get_alerts(
    store_id: str = Query("store-101", description="Target store identifier.", example="store-101"),
    severity: Optional[AlertSeverity] = Query(
        None,
        description="Filter alerts by severity level: LOW | MEDIUM | HIGH | CRITICAL.",
        example="HIGH",
    ),
    start_time: Optional[str] = Query(
        None,
        description="ISO 8601 start datetime. Only alerts after this time are returned.",
        example="2026-05-01T00:00:00Z",
    ),
    end_time: Optional[str] = Query(
        None,
        description="ISO 8601 end datetime. Only alerts before this time are returned.",
        example="2026-05-31T23:59:59Z",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed).", example=1),
    limit: int = Query(20, ge=1, le=100, description="Maximum records per page.", example=20),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AlertResponse]:
    """
    Paginated alert retrieval with live evaluation and optional filters.

    **Alert Debouncing**: The live evaluation cycle uses a 60-second debounce
    window to prevent duplicate alert flooding when the same condition persists.

    **Double-entry Prevention**: Each alert type is checked independently;
    a HIGH-severity crowding alert will not suppress a concurrent LOW-severity
    loitering alert.
    """
    # 1. Run live evaluation before querying (ensures fresh state)
    service = AlertService(db)
    service.evaluate_alerts(store_id)

    # 2. Build dynamic filter list
    filters = [Alert.store_id == store_id]

    if severity:
        filters.append(Alert.severity == severity.value)

    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00")).replace(tzinfo=None)
            filters.append(Alert.timestamp >= start_dt)
        except ValueError:
            logger.warning(f"[alerts] invalid start_time format: {start_time!r}")

    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00")).replace(tzinfo=None)
            filters.append(Alert.timestamp <= end_dt)
        except ValueError:
            logger.warning(f"[alerts] invalid end_time format: {end_time!r}")

    # 3. Count + paginate
    query = db.query(Alert).filter(and_(*filters))
    total_records = query.count()
    total_pages = (total_records + limit - 1) // limit if total_records > 0 else 0
    offset = (page - 1) * limit

    alerts = query.order_by(desc(Alert.timestamp)).offset(offset).limit(limit).all()

    logger.info(
        f"[alerts] store={store_id} severity={severity} "
        f"total={total_records} page={page}/{total_pages}"
    )

    return PaginatedResponse[AlertResponse](
        metadata=PaginationMetadata(
            page=page,
            limit=limit,
            total_records=total_records,
            total_pages=total_pages,
        ),
        data=alerts,
    )
