"""
backend/schemas/__init__.py
────────────────────────────
Public re-exports for the PurpleInsight schemas package.

Importing from this module gives access to all Pydantic v2 response schemas
without needing to reference individual sub-modules.
"""

from backend.schemas.common import (
    PaginationMetadata,
    PaginatedResponse,
    SuccessResponse,
    ErrorDetail,
    ErrorResponse,
    DateRangeParams,
)
from backend.schemas.metrics import StoreMetricsResponse
from backend.schemas.funnel import StoreFunnelResponse
from backend.schemas.alerts import AlertResponse, AlertSeverity, AlertType
from backend.schemas.analytics import (
    ZoneEngagementMetrics,
    ZoneDwellStats,
    ZonesAnalyticsResponse,
    HeatmapPoint,
    HeatmapResponse,
)
from backend.schemas.sales import (
    SalesItemMetrics,
    RevenueMetricsResponse,
    SalesAnalyticsResponse,
    BrandPerformanceItem,
    CategoryPerformanceItem,
    SalesProductPerformanceResponse,
    RevenueAnalysisResponse,
    ConversionAnalysisResponse,
)

__all__ = [
    # common
    "PaginationMetadata",
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorDetail",
    "ErrorResponse",
    "DateRangeParams",
    # metrics
    "StoreMetricsResponse",
    # funnel
    "StoreFunnelResponse",
    # alerts
    "AlertResponse",
    "AlertSeverity",
    "AlertType",
    # analytics
    "ZoneEngagementMetrics",
    "ZoneDwellStats",
    "ZonesAnalyticsResponse",
    "HeatmapPoint",
    "HeatmapResponse",
    # sales
    "SalesItemMetrics",
    "RevenueMetricsResponse",
    "SalesAnalyticsResponse",
    "BrandPerformanceItem",
    "CategoryPerformanceItem",
    "SalesProductPerformanceResponse",
    "RevenueAnalysisResponse",
    "ConversionAnalysisResponse",
]
