"""
backend/routes/funnel.py
────────────────────────
GET /funnel — Visitor-to-buyer conversion funnel.

Returns a 4-stage physical shopper path:
  1. visitors           – all entrants (distinct track_id)
  2. engaged_visitors   – dwelled ≥ 15 s in any zone
  3. checkout_visitors  – entered checkout queue zone
  4. buyers             – completed a correlated POS purchase

Plus computed drop-off ratios:
  - engagement_rate  (%)
  - checkout_rate    (%)
  - close_rate       (%)
  - conversion_rate  (%)

Query parameters:
  - store_id   (required) : target store
  - start_time (optional) : ISO 8601 window start
  - end_time   (optional) : ISO 8601 window end
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.services.funnel import FunnelService
from backend.schemas.funnel import StoreFunnelResponse
from backend.schemas.common import DateRangeParams

logger = logging.getLogger("PurpleInsight.FunnelRoute")

router = APIRouter(tags=["Conversion Funnel"])


@router.get(
    "/funnel",
    response_model=StoreFunnelResponse,
    status_code=status.HTTP_200_OK,
    summary="Shopper Conversion Funnel",
    description=(
        "Returns the physical shopper-path conversion funnel across four stages: "
        "Inbound → Engaged → Checkout → Buyers. "
        "Also includes computed drop-off ratios (engagement_rate, checkout_rate, close_rate) "
        "for granular funnel-step analysis. All stage counts use distinct track IDs to "
        "prevent double-counting re-entering shoppers."
    ),
    responses={
        200: {"description": "Funnel successfully computed for the requested store and window."},
    },
)
def get_conversion_funnel(
    store_id: str = Query(
        "store-101",
        description="Target store identifier.",
        example="store-101",
    ),
    dates: DateRangeParams = Depends(),
    db: Session = Depends(get_db),
) -> StoreFunnelResponse:
    """
    Computes the full 4-stage conversion funnel by delegating to ``FunnelService``.

    The ``StoreFunnelResponse`` Pydantic model automatically computes
    ``engagement_rate``, ``checkout_rate``, and ``close_rate`` via its
    ``model_validator``, so the route only needs to populate the four core counts.
    """
    service = FunnelService(db)
    result = service.get_conversion_funnel(store_id, dates.start, dates.end)

    logger.info(
        f"[funnel] store={store_id} visitors={result['visitors']} "
        f"buyers={result['buyers']} conversion={result['conversion_rate']}%"
    )

    return StoreFunnelResponse(**result)
