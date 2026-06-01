from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class SpatialCorrelationLog(Base):
    """Links physical shoppers (track_id) to purchase receipts (transaction_id)."""
    __tablename__ = "spatial_correlation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pos_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    track_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    correlation_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    correlated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="correlations")
    transaction: Mapped["POSTransaction"] = relationship("POSTransaction", back_populates="correlation")
