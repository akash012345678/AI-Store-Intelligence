from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class DwellLog(Base):
    """Tracks customer dwell times inside specific layout zones (aisles, promo bins)."""
    __tablename__ = "dwell_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    zone_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("store_layout_zones.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    track_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    exited_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="dwells")
    zone: Mapped["StoreLayoutZone"] = relationship("StoreLayoutZone", back_populates="dwell_logs")

    # Composite Index for quicker analytical lookups
    __table_args__ = (
        Index("idx_dwell_store_zone_track", "store_id", "zone_id", "track_id"),
    )
