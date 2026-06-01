"""
backend/routes/analytics.py
────────────────────────────
Spatial analytics endpoints:

  GET /zones   — Zone-level dwell stats + shelf engagement metrics
  GET /heatmap — 2-D KDE grid of visitor dwell concentration

Both endpoints accept an optional store_id + date-range window.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.services.spatial_analytics import SpatialAnalyticsService
from backend.services.metrics import MetricsService
from backend.schemas.analytics import ZonesAnalyticsResponse, HeatmapResponse
from backend.schemas.common import DateRangeParams

logger = logging.getLogger("PurpleInsight.AnalyticsRoute")

router = APIRouter(tags=["Spatial Analytics"])


@router.get(
    "/zones",
    response_model=ZonesAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Zone Dwell & Engagement Analytics",
    description=(
        "Returns per-zone analytics for the store layout: "
        "the most/least visited zones by unique visitor count, "
        "per-zone dwell time statistics (visit_count, unique_visitors, avg_dwell_seconds), "
        "and shelf engagement KPIs (attractiveness index, hold power). "
        "All metrics are scoped to the requested time window."
    ),
    responses={
        200: {"description": "Zone analytics successfully computed."},
    },
)
def get_zones_analytics(
    store_id: str = Query("store-101", description="Target store identifier.", example="store-101"),
    dates: DateRangeParams = Depends(),
    db: Session = Depends(get_db),
) -> ZonesAnalyticsResponse:
    """
    Aggregates zone-level dwell and engagement statistics.

    Uses ``MetricsService.get_most_least_visited_zones`` for peak zone identification
    and ``SpatialAnalyticsService.zone_analytics`` + ``shelf_engagement`` for detailed
    per-zone KPIs.
    """
    metrics_service = MetricsService(db)
    spatial_service = SpatialAnalyticsService(db)

    most_visited, least_visited = metrics_service.get_most_least_visited_zones(
        store_id, dates.start, dates.end
    )
    zone_dwell_stats = spatial_service.zone_analytics(store_id, dates.start, dates.end)
    shelf_engagement = spatial_service.shelf_engagement(store_id, dates.start, dates.end)

    logger.info(
        f"[zones] store={store_id} most_visited={most_visited!r} "
        f"zones_count={len(zone_dwell_stats)}"
    )

    return ZonesAnalyticsResponse(
        most_visited_zone=most_visited or "N/A",
        least_visited_zone=least_visited or "N/A",
        zone_dwell_statistics=zone_dwell_stats,
        shelf_engagement_metrics=shelf_engagement,
    )


@router.get(
    "/heatmap",
    response_model=HeatmapResponse,
    status_code=status.HTTP_200_OK,
    summary="Spatial Dwell Heatmap",
    description=(
        "Generates a 2-D Kernel Density Estimate (KDE) grid representing visitor "
        "dwell concentrations across the store floorplan. The response includes "
        "the canvas dimensions, grid cell size, and a normalised intensity matrix "
        "[0, 1] suitable for colour-mapped heatmap rendering."
    ),
    responses={
        200: {"description": "Heatmap matrix successfully generated."},
    },
)
def get_heatmap_density(
    store_id: str = Query("store-101", description="Target store identifier.", example="store-101"),
    dates: DateRangeParams = Depends(),
    db: Session = Depends(get_db),
) -> HeatmapResponse:
    """
    Delegates heatmap generation to ``SpatialAnalyticsService.heatmap_generation``.

    The service computes per-cell dwell counts, normalises them to [0, 1],
    and returns a 2-D matrix. Canvas size is fixed at 1200 × 600 px with
    a 20 px grid scale (60 × 30 cells).
    """
    spatial_service = SpatialAnalyticsService(db)
    heatmap_intensity = spatial_service.heatmap_generation(store_id, dates.start, dates.end)

    logger.info(
        f"[heatmap] store={store_id} grid_rows={len(heatmap_intensity)} "
        f"grid_cols={len(heatmap_intensity[0]) if heatmap_intensity else 0}"
    )

    return HeatmapResponse(
        width=1200,
        height=600,
        grid_scale=20,
        heatmap_intensity=heatmap_intensity,
    )
