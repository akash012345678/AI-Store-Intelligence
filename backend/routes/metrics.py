"""
backend/routes/metrics.py
─────────────────────────
GET /metrics — Aggregate store visitor KPIs.

Returns:
  - total_visitors      : unique entrant count (double-counting prevented via distinct track_id)
  - current_occupancy   : live open-session count
  - avg_dwell_time      : mean shopper dwell in minutes
  - conversion_rate     : buyers / visitors × 100
  - peak_hour           : busiest one-hour window (HH:MM-HH:MM)

Query parameters:
  - store_id   (required) : target store
  - start_time (optional) : ISO 8601 window start; defaults to 30 days ago
  - end_time   (optional) : ISO 8601 window end;   defaults to now
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.services.metrics import MetricsService
from backend.schemas.metrics import StoreMetricsResponse
from backend.schemas.common import DateRangeParams

logger = logging.getLogger("PurpleInsight.MetricsRoute")

router = APIRouter(tags=["Metrics"])


@router.get(
    "/metrics",
    response_model=StoreMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Store Visitor KPIs",
    description=(
        "Returns aggregate visitor analytics for a given store and time window: "
        "unique entry count, live occupancy, average dwell time, shopper-to-buyer "
        "conversion rate, and peak traffic hour. All counts use distinct ``track_id`` "
        "to prevent double-counting re-entering shoppers."
    ),
    responses={
        200: {"description": "Metrics successfully computed for the requested store and window."},
    },
)
def get_store_metrics(
    store_id: str = Query(
        "store-101",
        description="Target store identifier.",
        example="store-101",
    ),
    dates: DateRangeParams = Depends(),
    db: Session = Depends(get_db),
) -> StoreMetricsResponse:
    """
    Retrieves high-level visitor KPIs for the specified ``store_id`` and date window.

    The ``MetricsService`` is responsible for all SQL aggregations, including:
    - Distinct track-based occupancy queries (prevents double-counting)
    - Open-session instantaneous count for live occupancy
    - Dwell time averaging across completed sessions only
    - Spatial-correlation-log join for conversion calculation
    - Peak hour extraction via ``Counter`` on entry timestamps
    """
    service = MetricsService(db)

    total_visitors    = service.get_total_visitors(store_id, dates.start, dates.end)
    current_occupancy = service.get_current_occupancy(store_id)
    avg_dwell_time    = service.get_average_dwell_time(store_id, dates.start, dates.end)
    conversion_rate   = service.get_conversion_rate(store_id, dates.start, dates.end)
    peak_hour         = service.get_peak_hour(store_id, dates.start, dates.end)

    logger.info(
        f"[metrics] store={store_id} visitors={total_visitors} "
        f"occupancy={current_occupancy} conversion={conversion_rate}%"
    )

    return StoreMetricsResponse(
        total_visitors=total_visitors,
        current_occupancy=current_occupancy,
        avg_dwell_time=avg_dwell_time,
        conversion_rate=conversion_rate,
        peak_hour=peak_hour,
    )
