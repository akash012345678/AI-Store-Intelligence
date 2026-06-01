from typing import List
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base, UUIDMixin, TimestampMixin

class Store(Base, UUIDMixin, TimestampMixin):
    """Represents a physical store location containing layout zones, cameras, and IoT sensors."""
    __tablename__ = "stores"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")

    # Relationships
    cameras: Mapped[List["Camera"]] = relationship(
        "Camera",
        back_populates="store",
        cascade="all, delete-orphan"
    )
    zones: Mapped[List["StoreLayoutZone"]] = relationship(
        "StoreLayoutZone",
        back_populates="store",
        cascade="all, delete-orphan"
    )
    sessions: Mapped[List["StoreSession"]] = relationship(
        "StoreSession",
        back_populates="store",
        cascade="all, delete-orphan"
    )
    dwells: Mapped[List["DwellLog"]] = relationship(
        "DwellLog",
        back_populates="store",
        cascade="all, delete-orphan"
    )
    transactions: Mapped[List["POSTransaction"]] = relationship(
        "POSTransaction",
        back_populates="store",
        cascade="all, delete-orphan"
    )
    correlations: Mapped[List["SpatialCorrelationLog"]] = relationship(
        "SpatialCorrelationLog",
        back_populates="store",
        cascade="all, delete-orphan"
    )
    alerts: Mapped[List["Alert"]] = relationship(
        "Alert",
        back_populates="store",
        cascade="all, delete-orphan"
    )
