"""
backend/schemas/metrics.py
──────────────────────────
Pydantic v2 response schemas for the /metrics endpoint.

Covers:
  - StoreMetricsResponse  : high-level KPI summary (visitors, dwell, conversion, peak hour)
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict, field_validator


class StoreMetricsResponse(BaseModel):
    """
    High-level store visitor metrics returned by GET /api/v1/metrics.

    All numeric fields use safe defaults (0) when no data is available for the
    requested time window.
    """

    model_config = ConfigDict(populate_by_name=True)

    total_visitors: int = Field(
        ...,
        ge=0,
        description="Total unique visitors who entered the store in the time window.",
        example=124,
    )
    current_occupancy: int = Field(
        ...,
        ge=0,
        description="Instantaneous count of shoppers currently inside (open sessions).",
        example=12,
    )
    avg_dwell_time: float = Field(
        ...,
        ge=0.0,
        description="Average shopper dwell time in minutes across completed sessions.",
        example=4.8,
    )
    conversion_rate: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of visitors who completed a correlated POS purchase.",
        example=29.03,
    )
    peak_hour: str = Field(
        ...,
        description="Store's busiest hour window in HH:MM-HH:MM format (or 'N/A').",
        example="18:00-19:00",
    )

    @field_validator("conversion_rate", mode="before")
    @classmethod
    def clamp_conversion_rate(cls, v: float) -> float:
        """Clamp conversion_rate to [0, 100] to guard against floating-point drift."""
        return max(0.0, min(100.0, float(v)))

    @field_validator("avg_dwell_time", mode="before")
    @classmethod
    def round_dwell_time(cls, v: float) -> float:
        """Ensure exactly one decimal place on average dwell."""
        return round(float(v), 1)
