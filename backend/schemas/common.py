"""
backend/schemas/common.py
─────────────────────────
Shared Pydantic v2 schemas used across all PurpleInsight API routes.

Provides:
  - PaginationMetadata  : page / limit / total metadata block
  - PaginatedResponse   : generic wrapper for list endpoints
  - SuccessResponse     : simple success acknowledgment
  - ErrorDetail         : structured error payload
  - ErrorResponse       : top-level error envelope
  - DateRangeParams     : reusable query-parameter dependency
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Generic, List, Optional, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field, ConfigDict


T = TypeVar("T")


# ──────────────────────────────────────────────────
# Pagination
# ──────────────────────────────────────────────────

class PaginationMetadata(BaseModel):
    """Describes the current page slice within a paginated result set."""

    model_config = ConfigDict(populate_by_name=True)

    page: int = Field(..., ge=1, description="Current page number (1-indexed).", example=1)
    limit: int = Field(..., ge=1, le=100, description="Maximum records returned per page.", example=20)
    total_records: int = Field(..., ge=0, description="Total records matching the query.", example=124)
    total_pages: int = Field(..., ge=0, description="Total number of pages available.", example=7)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated list envelope used by /alerts, /events, and other list endpoints."""

    model_config = ConfigDict(populate_by_name=True)

    metadata: PaginationMetadata = Field(..., description="Pagination cursor information.")
    data: List[T] = Field(..., description="Payload items for the current page.")


# ──────────────────────────────────────────────────
# Success / Error envelopes
# ──────────────────────────────────────────────────

class SuccessResponse(BaseModel):
    """Generic success acknowledgment returned by write/action endpoints."""

    success: bool = Field(True, description="Always True for a successful response.")
    message: str = Field(..., description="Human-readable success description.", example="Operation completed.")


class ErrorDetail(BaseModel):
    """Structured representation of a single validation or application error."""

    field: Optional[str] = Field(None, description="Field that caused the error, if applicable.", example="store_id")
    message: str = Field(..., description="Human-readable error description.", example="Store not found.")
    code: Optional[str] = Field(None, description="Machine-readable error code.", example="NOT_FOUND")


class ErrorResponse(BaseModel):
    """Top-level error envelope returned on all 4xx / 5xx responses."""

    success: bool = Field(False, description="Always False for an error response.")
    request_id: Optional[str] = Field(None, description="Trace ID from X-Request-ID header.", example="abc123")
    errors: List[ErrorDetail] = Field(default_factory=list, description="List of structured error details.")


# ──────────────────────────────────────────────────
# Reusable date-range dependency
# ──────────────────────────────────────────────────

class DateRangeParams:
    """
    FastAPI dependency that parses optional ISO 8601 start/end query params
    and defaults to the last 30 days when omitted.

    Usage::

        @router.get("/metrics")
        def get_metrics(dates: DateRangeParams = Depends()):
            service.compute(dates.start, dates.end)
    """

    def __init__(
        self,
        start_time: Optional[str] = Query(
            None,
            alias="start_time",
            description="ISO 8601 start datetime (e.g. 2026-05-01T00:00:00Z). Defaults to 30 days ago.",
            example="2026-05-01T00:00:00Z",
        ),
        end_time: Optional[str] = Query(
            None,
            alias="end_time",
            description="ISO 8601 end datetime (e.g. 2026-05-31T23:59:59Z). Defaults to now.",
            example="2026-05-31T23:59:59Z",
        ),
    ):
        now = datetime.utcnow()
        self.start: datetime = (
            datetime.fromisoformat(start_time.replace("Z", "+00:00")).replace(tzinfo=None)
            if start_time
            else now - timedelta(days=365)
        )
        self.end: datetime = (
            datetime.fromisoformat(end_time.replace("Z", "+00:00")).replace(tzinfo=None)
            if end_time
            else now
        )
