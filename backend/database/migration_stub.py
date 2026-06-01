"""Alembic DB Migration Stub

Revision ID: 88bc6219cb8a
Revises: 06e7cac5d997
Create Date: 2026-05-31 10:59:12.124800
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '88bc6219cb8a'
down_revision = '06e7cac5d997'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Applies DDL alterations, creating normalized sales analytics tables."""
    
    # 1. Create Sales Stores Table
    op.create_table(
        'sales_stores',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Create Sales Customers Table
    op.create_table(
        'sales_customers',
        sa.Column('customer_number', sa.String(length=50), nullable=False),
        sa.Column('customer_name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('customer_number')
    )

    # 3. Create Salespersons Table
    op.create_table(
        'salespersons',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('employee_code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. Create Sales Products Table
    op.create_table(
        'sales_products',
        sa.Column('sku', sa.String(length=50), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('ean', sa.String(length=50), nullable=True),
        sa.Column('product_name', sa.String(length=350), nullable=False),
        sa.Column('brand_name', sa.String(length=100), nullable=False),
        sa.Column('department_name', sa.String(length=100), nullable=False),
        sa.Column('sub_category', sa.String(length=100), nullable=False),
        sa.Column('brand_type', sa.String(length=50), nullable=False),
        sa.Column('hsn_code', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('sku'),
        sa.UniqueConstraint('product_id')
    )

    # 5. Create Sales Orders Table
    op.create_table(
        'sales_orders',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('store_id', sa.String(length=50), nullable=False),
        sa.Column('customer_number', sa.String(length=50), nullable=False),
        sa.Column('salesperson_id', sa.String(length=50), nullable=False),
        sa.Column('invoice_number', sa.String(length=50), nullable=False),
        sa.Column('invoice_type', sa.String(length=50), nullable=False),
        sa.Column('order_date', sa.String(length=50), nullable=False),
        sa.Column('order_time', sa.String(length=50), nullable=False),
        sa.Column('coupon_code', sa.String(length=50), nullable=True),
        sa.Column('offer_name', sa.String(length=150), nullable=True),
        sa.Column('discount_code', sa.String(length=50), nullable=True),
        sa.Column('return_id', sa.String(length=50), nullable=True),
        sa.Column('week_assigned', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['sales_stores.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_number'], ['sales_customers.customer_number'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['salesperson_id'], ['salespersons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. Create Sales Order Items Table
    op.create_table(
        'sales_order_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.String(length=50), nullable=False),
        sa.Column('sku', sa.String(length=50), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('gmv', sa.Float(), nullable=False),
        sa.Column('nmv', sa.Float(), nullable=False),
        sa.Column('coupon_amount', sa.Float(), nullable=False),
        sa.Column('item_promotion', sa.Float(), nullable=False),
        sa.Column('amt_without_gwp', sa.Float(), nullable=False),
        sa.Column('total_amount', sa.Float(), nullable=False),
        sa.Column('tax_rate', sa.Float(), nullable=False),
        sa.Column('tax_m', sa.Float(), nullable=False),
        sa.Column('taxable_amt', sa.Float(), nullable=False),
        sa.Column('tax_amt', sa.Float(), nullable=False),
        sa.Column('pb_eb_sale', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['sales_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sku'], ['sales_products.sku'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Rolls back DDL changes, safely dropping tables in topological dependency order."""
    op.drop_table('sales_order_items')
    op.drop_table('sales_orders')
    op.drop_table('sales_products')
    op.drop_table('salespersons')
    op.drop_table('sales_customers')
    op.drop_table('sales_stores')
