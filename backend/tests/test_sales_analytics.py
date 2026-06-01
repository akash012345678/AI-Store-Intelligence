import pytest
import os
from sqlalchemy.orm import Session
from backend.utils.seeder import seed_database_from_csv
from backend.services.sales_analytics import SalesAnalyticsService
from backend.models.sales import SalesStore, SalesProduct, SalesOrder, SalesOrderItem

def test_sales_database_seeder_and_aggregates(test_db):
    # Verify tables are empty initially
    assert test_db.query(SalesStore).count() == 0
    assert test_db.query(SalesOrder).count() == 0

    csv_path = "c:\\Users\\Maha Monisha\\OneDrive\\Desktop\\purple\\data\\Brigade_Bangalore_10_April_26 (1)bc6219c.csv"
    
    # Check if CSV is present, otherwise fallback to mock data to keep test suite resilient
    if os.path.exists(csv_path):
        # Ingest raw CSV data
        seeded_count = seed_database_from_csv(test_db, csv_path)
        assert seeded_count > 0
        
        # Verify master relational tables populated successfully
        assert test_db.query(SalesStore).count() == 1
        assert test_db.query(SalesStore).first().id == "ST1008"
        assert test_db.query(SalesProduct).count() > 0
        assert test_db.query(SalesOrder).count() > 0
        assert test_db.query(SalesOrderItem).count() == seeded_count
        
        # Instantiate Analytics Service
        service = SalesAnalyticsService(test_db)
        
        # 1. Brand Performance
        brands = service.get_brand_performance()
        assert len(brands) > 0
        assert brands[0]["revenue"] >= brands[-1]["revenue"] # Sorted DESC
        assert "brand_name" in brands[0]
        assert "private_label_revenue_split" in brands[0]
        
        # 2. Category Performance
        categories = service.get_category_performance()
        assert len(categories) > 0
        assert "category_name" in categories[0]
        assert "peak_sales_hour" in categories[0]
        
        # 3. Product Performance
        products = service.get_product_performance()
        assert "top_moving_by_revenue" in products
        assert "slowest_moving" in products
        assert len(products["top_moving_by_revenue"]) > 0
        
        # 4. Revenue Analysis
        revenue = service.get_revenue_analysis()
        assert revenue["total_gmv"] >= revenue["total_nmv"]
        assert len(revenue["hourly_sales_distribution"]) > 0
        
        # 5. Conversion Analysis
        conversion = service.get_conversion_analysis()
        assert conversion["total_transactions"] > 0
        assert "promotional_transaction_ratio" in conversion
        
    else:
        # Fallback Mock Data seeding (in case running in environment without absolute disk access)
        store = SalesStore(id="ST1008", name="Mock Store", city="Bangalore")
        test_db.add(store)
        product = SalesProduct(sku="SKU-1", product_id=1, product_name="Wash", brand_name="Good", department_name="bath", sub_category="Wash", brand_type="PB")
        test_db.add(product)
        order = SalesOrder(id="O-1", store_id="ST1008", customer_number="C-1", salesperson_id="S-1", invoice_number="I-1", invoice_type="sales", order_date="10-04-2026", order_time="16:00:00")
        test_db.add(order)
        item = SalesOrderItem(order_id="O-1", sku="SKU-1", qty=2, gmv=100.0, nmv=80.0, coupon_amount=10.0, item_promotion=10.0, amt_without_gwp=80.0, total_amount=80.0, tax_rate=18.0, taxable_amt=67.8, tax_amt=12.2)
        test_db.add(item)
        test_db.commit()

        service = SalesAnalyticsService(test_db)
        
        # Assert math checks
        brands = service.get_brand_performance()
        assert len(brands) == 1
        assert brands[0]["brand_name"] == "Good"
        assert brands[0]["private_label_revenue_split"] == 100.0
        
        revenue = service.get_revenue_analysis()
        assert revenue["total_gmv"] == 100.0
        assert revenue["total_nmv"] == 80.0
        assert revenue["total_discounts"] == 20.0
