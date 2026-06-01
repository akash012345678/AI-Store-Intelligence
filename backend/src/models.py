from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.src.database import Base

class Store(Base):
    __tablename__ = "stores"

    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(100), nullable=False)
    address = Column(String(200), nullable=True)
    timezone = Column(String(50), nullable=False, default="UTC")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    cameras = relationship("Camera", back_populates="store", cascade="all, delete-orphan")
    zones = relationship("StoreLayoutZone", back_populates="store", cascade="all, delete-orphan")
    sessions = relationship("StoreSession", back_populates="store", cascade="all, delete-orphan")
    dwells = relationship("DwellLog", back_populates="store", cascade="all, delete-orphan")
    transactions = relationship("POSTransaction", back_populates="store", cascade="all, delete-orphan")
    correlations = relationship("SpatialCorrelationLog", back_populates="store", cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String(36), primary_key=True)  # UUID
    store_id = Column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    rtsp_url = Column(String(250), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    store = relationship("Store", back_populates="cameras")


class StoreLayoutZone(Base):
    __tablename__ = "store_layout_zones"

    id = Column(String(50), primary_key=True) # Matches zone_id in config
    store_id = Column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    zone_type = Column(String(50), nullable=False) # e.g. "aisle", "checkout", "entrance", "promo"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    store = relationship("Store", back_populates="zones")
    dwell_logs = relationship("DwellLog", back_populates="zone", cascade="all, delete-orphan")


class StoreSession(Base):
    """Tracks overall presence of a customer inside the physical store."""
    __tablename__ = "store_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    track_id = Column(Integer, nullable=False) # Original (stitched) track ID
    entered_at = Column(DateTime, nullable=False)
    exited_at = Column(DateTime, nullable=True) # None indicates currently inside
    re_entry = Column(Boolean, nullable=False, default=False)
    correlated_previous_track_id = Column(Integer, nullable=True)

    # Relationships
    store = relationship("Store", back_populates="sessions")


class DwellLog(Base):
    """Tracks customer dwell times inside specific layout zones (aisles, promo bins)."""
    __tablename__ = "dwell_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    zone_id = Column(String(50), ForeignKey("store_layout_zones.id", ondelete="CASCADE"), nullable=False)
    track_id = Column(Integer, nullable=False) # Original (stitched) track ID
    entered_at = Column(DateTime, nullable=False)
    exited_at = Column(DateTime, nullable=False)
    duration_seconds = Column(Float, nullable=False)

    # Relationships
    store = relationship("Store", back_populates="dwells")
    zone = relationship("StoreLayoutZone", back_populates="dwell_logs")


class POSTransaction(Base):
    """Point of Sale purchase transactions metadata."""
    __tablename__ = "pos_transactions"

    id = Column(String(36), primary_key=True) # UUID
    store_id = Column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    receipt_number = Column(String(50), nullable=False, unique=True)
    total_amount = Column(Float, nullable=False)
    tax_amount = Column(Float, nullable=False, default=0.0)
    transaction_time = Column(DateTime, nullable=False)
    payment_method = Column(String(50), nullable=True)

    # Relationships
    store = relationship("Store", back_populates="transactions")
    items = relationship("TransactionItem", back_populates="transaction", cascade="all, delete-orphan")
    correlation = relationship("SpatialCorrelationLog", uselist=False, back_populates="transaction", cascade="all, delete-orphan")


class TransactionItem(Base):
    """Itemized rows of product purchases."""
    __tablename__ = "transaction_items"

    id = Column(String(36), primary_key=True) # UUID
    transaction_id = Column(String(36), ForeignKey("pos_transactions.id", ondelete="CASCADE"), nullable=False)
    sku = Column(String(50), nullable=False)
    product_name = Column(String(150), nullable=False)
    category = Column(String(100), nullable=False) # e.g. "Produce", "Snacks"
    brand = Column(String(100), nullable=False)    # e.g. "BrandX", "ColaCorp"
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)

    # Relationships
    transaction = relationship("POSTransaction", back_populates="items")


class SpatialCorrelationLog(Base):
    """Links physical shoppers (track_id) to purchase receipts (transaction_id)."""
    __tablename__ = "spatial_correlation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    transaction_id = Column(String(36), ForeignKey("pos_transactions.id", ondelete="CASCADE"), nullable=False, unique=True)
    track_id = Column(Integer, nullable=False) # Original (stitched) track ID correlated
    correlation_confidence = Column(Float, nullable=False, default=1.0)
    correlated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    store = relationship("Store", back_populates="correlations")
    transaction = relationship("POSTransaction", back_populates="correlation")
