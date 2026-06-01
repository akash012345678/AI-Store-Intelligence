"""
backend/routes/sales.py
───────────────────────
GET /sales — Retail sales intelligence endpoint.

Returns top 5 products, brands, and categories by revenue plus
aggregate financial KPIs (GMV, NMV, tax, discounts, hourly distribution).

The endpoint delegates all aggregation to ``SalesAnalyticsService`` which
operates on the Brigade Bangalore retail dataset imported into the
``sales_*`` database tables.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.services.sales_analytics import SalesAnalyticsService
from backend.schemas.sales import SalesAnalyticsResponse

logger = logging.getLogger("PurpleInsight.SalesRoute")

router = APIRouter(tags=["Sales Intelligence"])


@router.get(
    "/sales",
    response_model=SalesAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retail Sales Intelligence",
    description=(
        "Returns business-intelligence retail sales statistics derived from the "
        "Brigade Bangalore POS dataset: top 5 products, top 5 brands, top 5 categories "
        "(all ranked by revenue), and aggregate financial KPIs including GMV, NMV, "
        "total tax collected, total discounts, and hourly revenue distribution."
    ),
    responses={
        200: {"description": "Sales analytics successfully computed."},
        503: {"description": "Sales data unavailable — dataset may not be seeded."},
    },
)
def get_sales_analytics(db: Session = Depends(get_db)) -> SalesAnalyticsResponse:
    """
    Retrieves top-performing retail items and aggregate financial KPIs.

    If the sales tables are empty (dataset not yet seeded), the service
    returns empty lists and zero revenue values rather than raising an error,
    ensuring the endpoint remains available during initial setup.
    """
    service = SalesAnalyticsService(db)

    products_perf   = service.get_product_performance()
    top_brands      = service.get_brand_performance()
    top_categories  = service.get_category_performance()
    revenue_metrics = service.get_revenue_analysis()

    # Extract top-5 products ranked by revenue
    top_products = products_perf.get("top_moving_by_revenue", [])[:5]

    logger.info(
        f"[sales] top_products={len(top_products)} brands={len(top_brands[:5])} "
        f"categories={len(top_categories[:5])} gmv={revenue_metrics.get('total_gmv', 0)}"
    )

    return SalesAnalyticsResponse(
        top_products=top_products,
        top_brands=top_brands[:5],
        top_categories=top_categories[:5],
        revenue_metrics=revenue_metrics,
    )
