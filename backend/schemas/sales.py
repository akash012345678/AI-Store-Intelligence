"""
backend/schemas/sales.py
────────────────────────
Pydantic v2 schemas for the /sales endpoint and the /sales-analytics sub-router.

Covers:
  - SalesItemMetrics              : shared volume/revenue item (product, brand, category)
  - RevenueMetricsResponse        : aggregate GMV/NMV/tax/discount block
  - SalesAnalyticsResponse        : top-level /sales response
  - BrandPerformanceItem          : extended brand analytics
  - CategoryPerformanceItem       : extended category analytics
  - SalesProductPerformanceResponse : top-movers + slow-movers
  - RevenueAnalysisResponse       : GMV breakdown with hourly distribution
  - ConversionAnalysisResponse    : promotional / private label funnel
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ──────────────────────────────────────────────────
# Shared primitives
# ──────────────────────────────────────────────────

class SalesItemMetrics(BaseModel):
    """Volume and revenue summary for a product, brand, or category."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Name of the product, brand, or category.", example="Haldiram's")
    volume: int = Field(..., ge=0, description="Total units sold.", example=312)
    revenue: float = Field(..., ge=0.0, description="Total revenue in INR.", example=48750.50)

    @field_validator("revenue", mode="before")
    @classmethod
    def round_revenue(cls, v: float) -> float:
        return round(float(v), 2)


class RevenueMetricsResponse(BaseModel):
    """Aggregate retail store monetary KPIs."""

    model_config = ConfigDict(populate_by_name=True)

    total_gmv: float = Field(
        ...,
        ge=0.0,
        description="Gross Merchandise Value: sum of all invoice amounts before deductions.",
        example=1284350.75,
    )
    total_nmv: float = Field(
        ...,
        ge=0.0,
        description="Net Merchandise Value: GMV minus discounts.",
        example=1196000.20,
    )
    total_tax_collected: float = Field(
        ...,
        ge=0.0,
        description="Total GST/tax collected across all transactions.",
        example=173387.60,
    )
    total_discounts: float = Field(
        ...,
        ge=0.0,
        description="Total value of promotional/loyalty discounts applied.",
        example=88350.55,
    )
    hourly_sales_distribution: Dict[str, float] = Field(
        default_factory=dict,
        description="Revenue split by hour-of-day. Keys are 'HH:00' strings; values are total INR.",
        example={"10:00": 45000.0, "11:00": 62000.0, "12:00": 89000.0},
    )


# ──────────────────────────────────────────────────
# /sales primary response
# ──────────────────────────────────────────────────

class SalesAnalyticsResponse(BaseModel):
    """Full retail sales intelligence KPIs returned by GET /api/v1/sales."""

    model_config = ConfigDict(populate_by_name=True)

    top_products: List[SalesItemMetrics] = Field(
        default_factory=list,
        description="Top 5 products ranked by revenue.",
    )
    top_brands: List[SalesItemMetrics] = Field(
        default_factory=list,
        description="Top 5 brands ranked by revenue.",
    )
    top_categories: List[SalesItemMetrics] = Field(
        default_factory=list,
        description="Top 5 product categories ranked by revenue.",
    )
    revenue_metrics: RevenueMetricsResponse = Field(
        ...,
        description="Aggregate financial KPIs for the store.",
    )


# ──────────────────────────────────────────────────
# /sales-analytics sub-router schemas
# ──────────────────────────────────────────────────

class BrandPerformanceItem(BaseModel):
    """Extended brand-level performance from the retail sales dataset."""

    model_config = ConfigDict(populate_by_name=True)

    brand: str = Field(..., description="Brand name.", example="Britannia")
    total_units: int = Field(..., ge=0, description="Total units sold across all SKUs.", example=540)
    total_revenue: float = Field(..., ge=0.0, description="Total revenue attributed to the brand.", example=72300.0)
    private_label_share_pct: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Percentage of revenue from private-label products (if applicable).",
        example=18.5,
    )


class CategoryPerformanceItem(BaseModel):
    """Extended category-level performance from the retail sales dataset."""

    model_config = ConfigDict(populate_by_name=True)

    category: str = Field(..., description="Product category name.", example="Snacks & Beverages")
    total_units: int = Field(..., ge=0, description="Total units sold in this category.", example=1200)
    total_revenue: float = Field(..., ge=0.0, description="Total revenue for the category.", example=145000.0)
    total_tax: float = Field(..., ge=0.0, description="Total tax collected in this category.", example=19575.0)
    peak_hour: Optional[str] = Field(
        None,
        description="Hour window with highest sales volume in this category.",
        example="18:00-19:00",
    )


class SalesProductPerformanceResponse(BaseModel):
    """Top-moving and slow-moving product analytics."""

    model_config = ConfigDict(populate_by_name=True)

    top_moving_by_revenue: List[SalesItemMetrics] = Field(
        default_factory=list,
        description="Products ranked by highest revenue.",
    )
    top_moving_by_volume: List[SalesItemMetrics] = Field(
        default_factory=list,
        description="Products ranked by highest unit volume.",
    )
    slow_moving: List[SalesItemMetrics] = Field(
        default_factory=list,
        description="Bottom-ranked products by revenue (potential inventory risk).",
    )


class RevenueAnalysisResponse(BaseModel):
    """Detailed revenue breakdown including hourly and promotional splits."""

    model_config = ConfigDict(populate_by_name=True)

    total_gmv: float = Field(..., ge=0.0, description="Gross Merchandise Value.", example=1284350.75)
    total_nmv: float = Field(..., ge=0.0, description="Net Merchandise Value (post-discount).", example=1196000.20)
    total_tax: float = Field(..., ge=0.0, description="Total tax collected.", example=173387.60)
    total_discounts: float = Field(..., ge=0.0, description="Total discounts applied.", example=88350.55)
    discount_rate_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Average discount as a percentage of GMV.",
        example=6.88,
    )
    hourly_distribution: Dict[str, float] = Field(
        default_factory=dict,
        description="Revenue by hour-of-day slot.",
        example={"10:00": 45000.0, "18:00": 89000.0},
    )


class ConversionAnalysisResponse(BaseModel):
    """Promotional and private-label conversion funnel analytics."""

    model_config = ConfigDict(populate_by_name=True)

    total_transactions: int = Field(..., ge=0, description="Total POS transactions.", example=892)
    promotional_transactions: int = Field(
        ...,
        ge=0,
        description="Transactions that included at least one discounted item.",
        example=467,
    )
    promotional_rate_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of transactions containing promotional items.",
        example=52.35,
    )
    private_label_transactions: int = Field(
        ...,
        ge=0,
        description="Transactions containing at least one private-label SKU.",
        example=213,
    )
    private_label_rate_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of transactions containing private-label items.",
        example=23.88,
    )
