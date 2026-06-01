"""
backend/schemas/funnel.py
─────────────────────────
Pydantic v2 response schemas for the /funnel conversion analytics endpoint.

Covers:
  - StoreFunnelResponse  : 4-stage conversion funnel (visitors → buyers)
  - FunnelStageBreakdown : extended per-stage drop-off metadata
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator


class StoreFunnelResponse(BaseModel):
    """
    Physical shopper-path conversion funnel returned by GET /api/v1/funnel.

    Stages:
        1. visitors          – all unique entrants
        2. engaged_visitors  – dwelled ≥ 15 seconds in any zone
        3. checkout_visitors – reached the checkout waiting queue
        4. buyers            – completed a correlated POS transaction

    The ``conversion_rate`` reflects buyers / visitors × 100.
    """

    model_config = ConfigDict(populate_by_name=True)

    visitors: int = Field(
        ...,
        ge=0,
        description="Total unique visitors entering the store.",
        example=124,
    )
    engaged_visitors: int = Field(
        ...,
        ge=0,
        description="Visitors who dwelled ≥ 15 seconds in at least one layout zone.",
        example=95,
    )
    checkout_visitors: int = Field(
        ...,
        ge=0,
        description="Visitors who entered the checkout queue zone.",
        example=48,
    )
    buyers: int = Field(
        ...,
        ge=0,
        description="Visitors with a spatially-correlated POS transaction.",
        example=36,
    )
    conversion_rate: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Shopper-to-buyer conversion percentage (buyers / visitors × 100).",
        example=29.03,
    )

    # ── derived drop-off ratios (computed, not stored) ─────────────────────

    engagement_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Engaged visitors as a percentage of total visitors.",
        example=76.61,
    )
    checkout_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Checkout visitors as a percentage of engaged visitors.",
        example=50.53,
    )
    close_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Buyers as a percentage of checkout visitors.",
        example=75.0,
    )

    @field_validator("conversion_rate", mode="before")
    @classmethod
    def clamp_conversion(cls, v: float) -> float:
        return round(max(0.0, min(100.0, float(v))), 2)

    @model_validator(mode="after")
    def compute_derived_rates(self) -> "StoreFunnelResponse":
        """Auto-compute engagement_rate, checkout_rate, and close_rate after field validation."""
        if self.visitors > 0:
            self.engagement_rate = round((self.engaged_visitors / self.visitors) * 100, 2)
        else:
            self.engagement_rate = 0.0

        if self.engaged_visitors > 0:
            self.checkout_rate = round((self.checkout_visitors / self.engaged_visitors) * 100, 2)
        else:
            self.checkout_rate = 0.0

        if self.checkout_visitors > 0:
            self.close_rate = round((self.buyers / self.checkout_visitors) * 100, 2)
        else:
            self.close_rate = 0.0

        return self
