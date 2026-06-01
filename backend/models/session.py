from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class StoreSession(Base):
    """Tracks overall presence of a customer inside the physical store."""
    __tablename__ = "store_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    track_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    re_entry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correlated_previous_track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="sessions")

    # Composite Index for faster visitor session checking
    __table_args__ = (
        Index("idx_session_store_track", "store_id", "track_id"),
    )
