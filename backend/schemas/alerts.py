"""
backend/schemas/alerts.py
─────────────────────────
Pydantic v2 schemas for the /alerts endpoint.

Covers:
  - AlertSeverity     : string enum for severity filtering
  - AlertResponse     : single alert record schema (ORM-mapped)
  - AlertSummary      : lightweight summary for list views
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class AlertSeverity(str, Enum):
    """Valid severity levels for operational store alerts."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(str, Enum):
    """Known alert type identifiers."""

    CROWDING = "crowding"
    OVERCROWDING = "overcrowding"
    LOITERING = "loitering"
    OPERATIONAL_NORMAL = "operational_normal"


class AlertResponse(BaseModel):
    """
    Full alert record schema mapped from the ``alerts`` ORM table.

    Returned by GET /api/v1/alerts.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int = Field(..., description="Auto-incrementing alert primary key.", example=1)
    store_id: str = Field(..., description="Store identifier the alert belongs to.", example="store-101")
    alert_type: str = Field(
        ...,
        description="Machine-readable alert category (crowding | overcrowding | loitering).",
        example="crowding",
    )
    severity: str = Field(
        ...,
        description="Alert severity tier: LOW | MEDIUM | HIGH | CRITICAL.",
        example="HIGH",
    )
    message: str = Field(
        ...,
        description="Human-readable alert description with contextual metrics.",
        example="Critical congestion inside checkout queue! Current occupant count: 8",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp when the alert was generated.",
        example="2026-05-31T12:30:00",
    )
    resolved: Optional[bool] = Field(
        None,
        description="Whether the alert condition has been resolved. Null if resolution tracking not used.",
        example=False,
    )
