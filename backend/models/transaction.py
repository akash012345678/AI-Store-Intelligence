from datetime import datetime
from typing import List
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base, UUIDMixin, TimestampMixin

class POSTransaction(Base, UUIDMixin, TimestampMixin):
    """Point of Sale purchase transactions metadata."""
    __tablename__ = "pos_transactions"

    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    receipt_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    transaction_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="transactions")
    items: Mapped[List["TransactionItem"]] = relationship(
        "TransactionItem",
        back_populates="transaction",
        cascade="all, delete-orphan"
    )
    correlation: Mapped["SpatialCorrelationLog | None"] = relationship(
        "SpatialCorrelationLog",
        uselist=False,
        back_populates="transaction",
        cascade="all, delete-orphan"
    )

class TransactionItem(Base, UUIDMixin):
    """Itemized rows of product purchases."""
    __tablename__ = "transaction_items"

    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pos_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    sku: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True) # e.g. "Produce", "Snacks"
    brand: Mapped[str] = mapped_column(String(100), nullable=False, index=True)    # e.g. "BrandX", "ColaCorp"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    transaction: Mapped["POSTransaction"] = relationship("POSTransaction", back_populates="items")
