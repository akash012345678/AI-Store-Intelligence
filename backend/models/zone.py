from typing import List
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base, TimestampMixin

class StoreLayoutZone(Base, TimestampMixin):
    """Represents a spatial layout zone (entrance, exit, checkout, brand shelves) inside the store."""
    __tablename__ = "store_layout_zones"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)  # Matches zone_id in configuration JSON
    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "aisle", "checkout", "entrance", "promo"

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="zones")
    dwell_logs: Mapped[List["DwellLog"]] = relationship(
        "DwellLog",
        back_populates="zone",
        cascade="all, delete-orphan"
    )
