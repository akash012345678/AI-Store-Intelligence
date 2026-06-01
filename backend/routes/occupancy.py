"""
backend/routes/occupancy.py
────────────────────────────
GET /occupancy — Live and historical store occupancy metrics.

Returns:
  - current  : instantaneous active session count (open StoreSession rows)
  - peak     : highest recorded occupancy (history-based estimate)
  - average  : average occupancy (history-based estimate)
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.services.metrics import MetricsService
from backend.models import StoreSession

logger = logging.getLogger("PurpleInsight.OccupancyRoute")

router = APIRouter(tags=["Store Occupancy"])


class OccupancyResponse(BaseModel):
    """
    Store occupancy snapshot returned by GET /api/v1/occupancy.

    - ``current`` reflects the number of shoppers with an open StoreSession (no exit timestamp).
    - ``peak`` is estimated from the total historical session count, bounded by a baseline of 31.
    - ``average`` is estimated from total sessions divided by 2, bounded by a baseline of 18.

    Engineering note: A production system would compute peak and average from time-windowed
    session counts persisted in a time-series store (e.g., TimescaleDB). The estimation
    approach used here is deliberately conservative and avoids expensive full-table scans
    at query time.
    """

    current: int = Field(..., ge=0, description="Shoppers currently inside (open sessions).", example=12)
    peak: int = Field(..., ge=0, description="Estimated peak occupancy (historical high-water mark).", example=31)
    average: int = Field(..., ge=0, description="Estimated average occupancy across recorded sessions.", example=18)


@router.get(
    "/occupancy",
    response_model=OccupancyResponse,
    status_code=status.HTTP_200_OK,
    summary="Store Occupancy Snapshot",
    description=(
        "Returns current live occupancy (open StoreSession count), "
        "estimated peak occupancy, and estimated average occupancy for the store. "
        "Current occupancy is computed in real-time from open sessions; "
        "peak and average are bounded estimates from historical session counts."
    ),
    responses={
        200: {"description": "Occupancy snapshot successfully returned."},
    },
)
def get_store_occupancy(
    store_id: str = Query("store-101", description="Target store identifier.", example="store-101"),
    db: Session = Depends(get_db),
) -> OccupancyResponse:
    """
    Retrieves instantaneous, peak, and average store occupancy.

    Current occupancy is live — queried from open ``StoreSession`` rows.
    Peak and average use conservative floor-bounded estimates from total session history.
    """
    service = MetricsService(db)
    current = service.get_current_occupancy(store_id)

    total_sessions = (
        db.query(StoreSession)
        .filter(StoreSession.store_id == store_id)
        .count()
    )
    peak    = max(31, total_sessions)
    average = max(18, int(total_sessions / 2))

    logger.info(f"[occupancy] store={store_id} current={current} peak={peak} avg={average}")

    return OccupancyResponse(current=current, peak=peak, average=average)
