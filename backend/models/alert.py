from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base


class Alert(Base):
    """System and operational alerts (e.g. queue crowding, hardware failure, anomalies)."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # e.g. "crowding", "operational_normal"
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)   # e.g. "LOW", "MEDIUM", "HIGH"
    message: Mapped[str] = mapped_column(String(250), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="alerts")
