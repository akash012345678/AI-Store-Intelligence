"""
backend/schemas/analytics.py
─────────────────────────────
Pydantic v2 schemas for the /zones and /heatmap spatial analytics endpoints.

Covers:
  - ZoneEngagementMetrics    : attractiveness/hold-power per zone
  - ZoneDwellStats           : visit counts and avg dwell per zone
  - ZonesAnalyticsResponse   : combined zones response (/zones)
  - HeatmapPoint             : single coordinate-intensity datum
  - HeatmapResponse          : grid-based heatmap density (/heatmap)
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class ZoneEngagementMetrics(BaseModel):
    """
    Shelf-level engagement KPIs for a single layout zone.

    Attractiveness index = (visitors who stopped ≥ 15 s) / total zone visitors × 100.
    Hold power = average dwell time (seconds) for stopped visitors.
    """

    model_config = ConfigDict(populate_by_name=True)

    zone_id: str = Field(..., description="Unique zone identifier.", example="aisle_1_fresh")
    name: str = Field(..., description="Human-readable zone label.", example="Aisle 1 – Fresh Produce")
    total_stops: int = Field(..., ge=0, description="Total visitor stops recorded in this zone.", example=42)
    attractive_stops: int = Field(
        ...,
        ge=0,
        description="Stops meeting the ≥ 15-second engagement threshold.",
        example=30,
    )
    attractiveness_index_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of stops qualifying as engaged (attractive_stops / total_stops × 100).",
        example=71.43,
    )
    hold_power_seconds: float = Field(
        ...,
        ge=0.0,
        description="Average dwell time in seconds for engaged stops.",
        example=38.2,
    )


class ZoneDwellStats(BaseModel):
    """Dwell statistics aggregated per layout zone for the /zones endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    zone_id: str = Field(..., description="Unique zone identifier.", example="checkout_queue")
    name: str = Field(..., description="Human-readable zone label.", example="Checkout Waiting Queue")
    visit_count: int = Field(..., ge=0, description="Total dwell-log entries for this zone.", example=56)
    unique_visitors: int = Field(..., ge=0, description="Distinct track IDs that visited this zone.", example=48)
    avg_dwell_seconds: float = Field(
        ...,
        ge=0.0,
        description="Mean dwell duration in seconds across all visits.",
        example=92.5,
    )


class ZonesAnalyticsResponse(BaseModel):
    """
    Integrated zone analytics response returned by GET /api/v1/zones.

    Includes peak zone identification, per-zone dwell statistics, and shelf engagement metrics.
    """

    model_config = ConfigDict(populate_by_name=True)

    most_visited_zone: str = Field(
        ...,
        description="Name of the zone with the highest unique visitor count (or 'N/A').",
        example="Aisle 1 – Fresh Produce",
    )
    least_visited_zone: str = Field(
        ...,
        description="Name of the zone with the lowest unique visitor count (or 'N/A').",
        example="Aisle 2 – Snacks & Beverages",
    )
    zone_dwell_statistics: List[ZoneDwellStats] = Field(
        default_factory=list,
        description="Per-zone dwell time and visit count breakdown.",
    )
    shelf_engagement_metrics: List[ZoneEngagementMetrics] = Field(
        default_factory=list,
        description="Per-zone attractiveness and hold-power shelf engagement KPIs.",
    )


# ──────────────────────────────────────────────────
# Heatmap Schemas
# ──────────────────────────────────────────────────

class HeatmapPoint(BaseModel):
    """A single spatial coordinate sample with a heat intensity value."""

    model_config = ConfigDict(populate_by_name=True)

    x: float = Field(..., description="X-coordinate on the store floorplan canvas (pixels).", example=275.0)
    y: float = Field(..., description="Y-coordinate on the store floorplan canvas (pixels).", example=250.0)
    intensity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalised heat intensity in [0, 1]. Higher values indicate more dwell activity.",
        example=0.87,
    )


class HeatmapResponse(BaseModel):
    """
    KDE-based spatial density response returned by GET /api/v1/heatmap.

    Provides both a pre-computed 2D grid matrix and individual coordinate points
    for flexible frontend rendering (canvas grid or point-cloud overlay).
    """

    model_config = ConfigDict(populate_by_name=True)

    width: int = Field(..., gt=0, description="Floorplan canvas width in pixels.", example=1200)
    height: int = Field(..., gt=0, description="Floorplan canvas height in pixels.", example=600)
    grid_scale: int = Field(
        ...,
        gt=0,
        description="Grid cell size in pixels. Each cell aggregates all dwell events within its boundary.",
        example=20,
    )
    heatmap_intensity: List[List[float]] = Field(
        default_factory=list,
        description="2D matrix [row][col] of normalised intensity values. Dimensions: (height/grid_scale) × (width/grid_scale).",
    )

    @field_validator("heatmap_intensity", mode="before")
    @classmethod
    def validate_matrix(cls, v: List[List[float]]) -> List[List[float]]:
        """Ensure all intensity values are clamped to [0, 1]."""
        return [[max(0.0, min(1.0, cell)) for cell in row] for row in v]
