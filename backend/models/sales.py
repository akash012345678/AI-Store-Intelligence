from typing import List
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base, TimestampMixin

class SalesStore(Base, TimestampMixin):
    """Represents stores in sales database records (from flat file seeders)."""
    __tablename__ = "sales_stores"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # maps to store_id (e.g. ST1008)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    orders: Mapped[List["SalesOrder"]] = relationship(
        "SalesOrder",
        back_populates="store",
        cascade="all, delete-orphan"
    )

class SalesCustomer(Base, TimestampMixin):
    """Represents customers in flat retail datasets."""
    __tablename__ = "sales_customers"

    customer_number: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. 9346413680
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    orders: Mapped[List["SalesOrder"]] = relationship("SalesOrder", back_populates="customer")

class Salesperson(Base, TimestampMixin):
    """Represents sales staff in flat retail datasets."""
    __tablename__ = "salespersons"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. CL2063 or 1178
    employee_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    orders: Mapped[List["SalesOrder"]] = relationship("SalesOrder", back_populates="salesperson")

class SalesProduct(Base, TimestampMixin):
    """Represents the product master catalog loaded from flat retail sales records."""
    __tablename__ = "sales_products"

    sku: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. PPLBDD...
    product_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    ean: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_name: Mapped[str] = mapped_column(String(350), nullable=False)
    brand_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    department_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # dep_name
    sub_category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    brand_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. PB, National, Exclusive
    hsn_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    order_items: Mapped[List["SalesOrderItem"]] = relationship("SalesOrderItem", back_populates="product")

class SalesOrder(Base, TimestampMixin):
    """Represents finalized customer receipts and invoice headers."""
    __tablename__ = "sales_orders"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # order_id
    store_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("sales_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    customer_number: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("sales_customers.customer_number", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    salesperson_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("salespersons.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    invoice_type: Mapped[str] = mapped_column(String(50), nullable=False)  # sales, return
    order_date: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # e.g. 10-04-2026
    order_time: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. 16:55:36
    coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    offer_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    discount_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    return_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    week_assigned: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    store: Mapped["SalesStore"] = relationship("SalesStore", back_populates="orders")
    customer: Mapped["SalesCustomer"] = relationship("SalesCustomer", back_populates="orders")
    salesperson: Mapped["Salesperson"] = relationship("Salesperson", back_populates="orders")
    items: Mapped[List["SalesOrderItem"]] = relationship(
        "SalesOrderItem",
        back_populates="order",
        cascade="all, delete-orphan"
    )

class SalesOrderItem(Base, TimestampMixin):
    """Represents an itemized line item inside an invoice header."""
    __tablename__ = "sales_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    sku: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("sales_products.sku", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gmv: Mapped[float] = mapped_column(Float, nullable=False)
    nmv: Mapped[float] = mapped_column(Float, nullable=False)
    coupon_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    item_promotion: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    amt_without_gwp: Mapped[float] = mapped_column(Float, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    tax_rate: Mapped[float] = mapped_column(Float, nullable=False)  # tax
    tax_m: Mapped[float] = mapped_column(Float, nullable=False, default=1.18)
    taxable_amt: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amt: Mapped[float] = mapped_column(Float, nullable=False)
    pb_eb_sale: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    order: Mapped["SalesOrder"] = relationship("SalesOrder", back_populates="items")
    product: Mapped["SalesProduct"] = relationship("SalesProduct", back_populates="order_items")
