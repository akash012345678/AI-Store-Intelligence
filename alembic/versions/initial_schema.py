"""initial_schema

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-05-31 11:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create stores table
    op.create_table(
        'stores',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('address', sa.String(length=200), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_stores_id', 'stores', ['id'])

    # 2. Create cameras table
    op.create_table(
        'cameras',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('store_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('rtsp_url', sa.String(length=250), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cameras_id', 'cameras', ['id'])
    op.create_index('idx_cameras_store_id', 'cameras', ['store_id'])

    # 3. Create store_layout_zones table
    op.create_table(
        'store_layout_zones',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('store_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('zone_type', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_store_layout_zones_id', 'store_layout_zones', ['id'])
    op.create_index('idx_store_layout_zones_store_id', 'store_layout_zones', ['store_id'])

    # 4. Create store_sessions table
    op.create_table(
        'store_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.String(length=36), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('entered_at', sa.DateTime(), nullable=False),
        sa.Column('exited_at', sa.DateTime(), nullable=True),
        sa.Column('re_entry', sa.Boolean(), nullable=False),
        sa.Column('correlated_previous_track_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_store_sessions_store_id', 'store_sessions', ['store_id'])
    op.create_index('idx_store_sessions_track_id', 'store_sessions', ['track_id'])
    op.create_index('idx_store_sessions_entered_at', 'store_sessions', ['entered_at'])
    op.create_index('idx_store_sessions_exited_at', 'store_sessions', ['exited_at'])
    op.create_index('idx_session_store_track', 'store_sessions', ['store_id', 'track_id'])

    # 5. Create dwell_logs table
    op.create_table(
        'dwell_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.String(length=36), nullable=False),
        sa.Column('zone_id', sa.String(length=50), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('entered_at', sa.DateTime(), nullable=False),
        sa.Column('exited_at', sa.DateTime(), nullable=False),
        sa.Column('duration_seconds', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['zone_id'], ['store_layout_zones.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_dwell_logs_store_id', 'dwell_logs', ['store_id'])
    op.create_index('idx_dwell_logs_zone_id', 'dwell_logs', ['zone_id'])
    op.create_index('idx_dwell_logs_track_id', 'dwell_logs', ['track_id'])
    op.create_index('idx_dwell_logs_entered_at', 'dwell_logs', ['entered_at'])
    op.create_index('idx_dwell_logs_exited_at', 'dwell_logs', ['exited_at'])
    op.create_index('idx_dwell_logs_duration_seconds', 'dwell_logs', ['duration_seconds'])
    op.create_index('idx_dwell_store_zone_track', 'dwell_logs', ['store_id', 'zone_id', 'track_id'])

    # 6. Create pos_transactions table
    op.create_table(
        'pos_transactions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('store_id', sa.String(length=36), nullable=False),
        sa.Column('receipt_number', sa.String(length=50), nullable=False),
        sa.Column('total_amount', sa.Float(), nullable=False),
        sa.Column('tax_amount', sa.Float(), nullable=False),
        sa.Column('transaction_time', sa.DateTime(), nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('receipt_number')
    )
    op.create_index('idx_pos_transactions_id', 'pos_transactions', ['id'])
    op.create_index('idx_pos_transactions_store_id', 'pos_transactions', ['store_id'])
    op.create_index('idx_pos_transactions_receipt_number', 'pos_transactions', ['receipt_number'])
    op.create_index('idx_pos_transactions_transaction_time', 'pos_transactions', ['transaction_time'])

    # 7. Create transaction_items table
    op.create_table(
        'transaction_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('transaction_id', sa.String(length=36), nullable=False),
        sa.Column('sku', sa.String(length=50), nullable=False),
        sa.Column('product_name', sa.String(length=150), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('brand', sa.String(length=100), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['pos_transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_transaction_items_id', 'transaction_items', ['id'])
    op.create_index('idx_transaction_items_transaction_id', 'transaction_items', ['transaction_id'])
    op.create_index('idx_transaction_items_sku', 'transaction_items', ['sku'])
    op.create_index('idx_transaction_items_category', 'transaction_items', ['category'])
    op.create_index('idx_transaction_items_brand', 'transaction_items', ['brand'])

    # 8. Create spatial_correlation_logs table
    op.create_table(
        'spatial_correlation_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.String(length=36), nullable=False),
        sa.Column('transaction_id', sa.String(length=36), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('correlation_confidence', sa.Float(), nullable=False),
        sa.Column('correlated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transaction_id'], ['pos_transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id')
    )
    op.create_index('idx_spatial_correlation_logs_store_id', 'spatial_correlation_logs', ['store_id'])
    op.create_index('idx_spatial_correlation_logs_transaction_id', 'spatial_correlation_logs', ['transaction_id'])
    op.create_index('idx_spatial_correlation_logs_track_id', 'spatial_correlation_logs', ['track_id'])
    op.create_index('idx_spatial_correlation_logs_correlated_at', 'spatial_correlation_logs', ['correlated_at'])

    # 9. Create alerts table
    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.String(length=36), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('message', sa.String(length=250), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_alerts_store_id', 'alerts', ['store_id'])
    op.create_index('idx_alerts_alert_type', 'alerts', ['alert_type'])
    op.create_index('idx_alerts_severity', 'alerts', ['severity'])
    op.create_index('idx_alerts_timestamp', 'alerts', ['timestamp'])

    # 10. Create sales_stores table
    op.create_table(
        'sales_stores',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 11. Create sales_customers table
    op.create_table(
        'sales_customers',
        sa.Column('customer_number', sa.String(length=50), nullable=False),
        sa.Column('customer_name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('customer_number')
    )

    # 12. Create salespersons table
    op.create_table(
        'salespersons',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('employee_code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 13. Create sales_products table
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
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('sku'),
        sa.UniqueConstraint('product_id')
    )
    op.create_index('idx_sales_products_product_id', 'sales_products', ['product_id'])
    op.create_index('idx_sales_products_brand_name', 'sales_products', ['brand_name'])
    op.create_index('idx_sales_products_department_name', 'sales_products', ['department_name'])
    op.create_index('idx_sales_products_sub_category', 'sales_products', ['sub_category'])

    # 14. Create sales_orders table
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
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['sales_stores.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_number'], ['sales_customers.customer_number'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['salesperson_id'], ['salespersons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sales_orders_store_id', 'sales_orders', ['store_id'])
    op.create_index('idx_sales_orders_customer_number', 'sales_orders', ['customer_number'])
    op.create_index('idx_sales_orders_salesperson_id', 'sales_orders', ['salesperson_id'])
    op.create_index('idx_sales_orders_order_date', 'sales_orders', ['order_date'])

    # 15. Create sales_order_items table
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
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['sales_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sku'], ['sales_products.sku'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sales_order_items_order_id', 'sales_order_items', ['order_id'])
    op.create_index('idx_sales_order_items_sku', 'sales_order_items', ['sku'])


def downgrade() -> None:
    # Drop tables in topological dependency order (child tables first)
    op.drop_table('sales_order_items')
    op.drop_table('sales_orders')
    op.drop_table('sales_products')
    op.drop_table('salespersons')
    op.drop_table('sales_customers')
    op.drop_table('sales_stores')
    op.drop_table('alerts')
    op.drop_table('spatial_correlation_logs')
    op.drop_table('transaction_items')
    op.drop_table('pos_transactions')
    op.drop_table('dwell_logs')
    op.drop_table('store_sessions')
    op.drop_table('store_layout_zones')
    op.drop_table('cameras')
    op.drop_table('stores')
