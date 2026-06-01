from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base, UUIDMixin, TimestampMixin

class Camera(Base, UUIDMixin, TimestampMixin):
    """Represents a physical edge camera deployed inside a store mapping RTSP streams."""
    __tablename__ = "cameras"

    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(String(250), nullable=False)

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="cameras")
