from datetime import datetime
from backend.services.metrics import MetricsEngine
from backend.models.domain import StoreSession, DwellLog, POSTransaction, TransactionItem, SpatialCorrelationLog

def test_metrics_engine_calculators(test_db):
    engine = MetricsEngine(test_db)
    store_id = "store-101"
    start_time = datetime(2026, 5, 31, 8, 0, 0)
    end_time = datetime(2026, 5, 31, 18, 0, 0)

    sessions = [
        StoreSession(store_id=store_id, track_id=401, entered_at=datetime(2026, 5, 31, 9, 30, 0), exited_at=datetime(2026, 5, 31, 10, 0, 0)),
        StoreSession(store_id=store_id, track_id=402, entered_at=datetime(2026, 5, 31, 10, 15, 0), exited_at=datetime(2026, 5, 31, 11, 0, 0)),
        StoreSession(store_id=store_id, track_id=403, entered_at=datetime(2026, 5, 31, 10, 30, 0), exited_at=datetime(2026, 5, 31, 10, 45, 0)),
        StoreSession(store_id=store_id, track_id=403, entered_at=datetime(2026, 5, 31, 10, 50, 0), exited_at=datetime(2026, 5, 31, 11, 10, 0), re_entry=True, correlated_previous_track_id=403),
        StoreSession(store_id=store_id, track_id=404, entered_at=datetime(2026, 5, 31, 11, 30, 0), exited_at=None)
    ]
    test_db.add_all(sessions)

    dwells = [
        DwellLog(store_id=store_id, zone_id="aisle_1_fresh", track_id=401, entered_at=datetime(2026, 5, 31, 9, 40, 0), exited_at=datetime(2026, 5, 31, 9, 42, 0), duration_seconds=120.0),
        DwellLog(store_id=store_id, zone_id="aisle_1_fresh", track_id=402, entered_at=datetime(2026, 5, 31, 10, 20, 0), exited_at=datetime(2026, 5, 31, 10, 21, 0), duration_seconds=60.0),
        DwellLog(store_id=store_id, zone_id="aisle_2_snacks", track_id=402, entered_at=datetime(2026, 5, 31, 10, 30, 0), exited_at=datetime(2026, 5, 31, 10, 33, 0), duration_seconds=180.0),
        DwellLog(store_id=store_id, zone_id="aisle_2_snacks", track_id=403, entered_at=datetime(2026, 5, 31, 10, 55, 0), exited_at=datetime(2026, 5, 31, 11, 0, 0), duration_seconds=300.0)
    ]
    test_db.add_all(dwells)

    txn1 = POSTransaction(id="t1", store_id=store_id, receipt_number="R-1", total_amount=10.0, tax_amount=0.0, transaction_time=datetime(2026, 5, 31, 10, 1, 0))
    txn2 = POSTransaction(id="t2", store_id=store_id, receipt_number="R-2", total_amount=15.0, tax_amount=0.0, transaction_time=datetime(2026, 5, 31, 11, 2, 0))
    test_db.add_all([txn1, txn2])

    items = [
        TransactionItem(id="i1", transaction_id="t1", sku="S1", product_name="Apple", category="Produce", brand="OrchardFresh", quantity=1, unit_price=10.0),
        TransactionItem(id="i2", transaction_id="t2", sku="S2", product_name="Candy Bar", category="Snacks", brand="SweetCo", quantity=2, unit_price=7.5)
    ]
    test_db.add_all(items)

    correlations = [
        SpatialCorrelationLog(store_id=store_id, transaction_id="t1", track_id=401, correlation_confidence=0.98, correlated_at=datetime(2026, 5, 31, 10, 1, 0)),
        SpatialCorrelationLog(store_id=store_id, transaction_id="t2", track_id=402, correlation_confidence=0.95, correlated_at=datetime(2026, 5, 31, 11, 2, 0))
    ]
    test_db.add_all(correlations)
    test_db.commit()

    # Total Visitors
    visitors = engine.get_total_visitors(store_id, start_time, end_time)
    assert visitors == 4

    # Current Occupancy
    occupancy = engine.get_current_occupancy(store_id)
    assert occupancy == 1

    # Re-entry Count
    re_entries = engine.get_re_entry_count(store_id, start_time, end_time)
    assert re_entries == 1

    # Peak Hour (Hour 10)
    peak_hour = engine.get_peak_hour(store_id, start_time, end_time)
    assert peak_hour == "10:00-11:00"

    # Zone Engagement
    engagement = engine.get_zone_engagement(store_id, start_time, end_time)
    assert len(engagement) == 2
    assert engagement[0]["visit_count"] == 2

    # Visitor-to-Buyer Conversion (50.0%)
    conversion = engine.get_visitor_to_buyer_conversion(store_id, start_time, end_time)
    assert conversion == 50.0

    # Category Conversion
    category_conversion = engine.get_category_conversion(
        store_id=store_id,
        zone_id="aisle_1_fresh",
        category_name="Produce",
        start_time=start_time,
        end_time=end_time
    )
    assert category_conversion == 50.0

def test_funnel_and_alerts_engines(test_db):
    from backend.services.funnel import FunnelAnalyticsService
    from backend.services.alerts import AlertEngine
    from backend.models.domain import DwellLog, Alert, StoreSession, SpatialCorrelationLog, POSTransaction
    from datetime import datetime, timedelta
    
    store_id = "store-101"
    start_time = datetime(2026, 5, 31, 8, 0, 0)
    end_time = datetime(2026, 5, 31, 18, 0, 0)
    
    # 1. Test Funnel Service
    funnel_service = FunnelAnalyticsService(test_db)
    
    test_db.add(StoreSession(store_id=store_id, track_id=501, entered_at=datetime(2026, 5, 31, 9, 0, 0), exited_at=datetime(2026, 5, 31, 9, 10, 0)))
    test_db.add(DwellLog(store_id=store_id, zone_id="aisle_1_fresh", track_id=501, entered_at=datetime(2026, 5, 31, 9, 1, 0), exited_at=datetime(2026, 5, 31, 9, 5, 0), duration_seconds=240.0))
    test_db.add(POSTransaction(id="t501", store_id=store_id, receipt_number="R-501", total_amount=50.0, transaction_time=datetime(2026, 5, 31, 9, 12, 0)))
    test_db.add(SpatialCorrelationLog(store_id=store_id, transaction_id="t501", track_id=501, correlation_confidence=0.95, correlated_at=datetime(2026, 5, 31, 9, 12, 0)))
    test_db.commit()
    
    funnel = funnel_service.get_funnel_analytics(store_id, start_time, end_time)
    assert funnel["visitors"] == 1
    assert funnel["engaged_visitors"] == 1
    assert funnel["buyers"] == 1
    assert funnel["conversion_rate"] == 100.0
    
    # 2. Test AlertEngine
    alert_engine = AlertEngine(test_db)
    
    # Empty waiting queue initially, should return None
    alert_1 = alert_engine.evaluate_alerts(store_id)
    assert alert_1 is None
    
    # Insert 5 active queue occupants inside DwellLog
    now = datetime.utcnow()
    for tid in range(601, 606):
        test_db.add(DwellLog(
            store_id=store_id,
            zone_id="checkout_queue",
            track_id=tid,
            entered_at=now - timedelta(seconds=10),
            exited_at=now,
            duration_seconds=10.0
        ))
    test_db.commit()
    
    # Evaluate alerts, should trigger and persist HIGH alert
    alert_2 = alert_engine.evaluate_alerts(store_id)
    assert alert_2 is not None
    assert alert_2.alert_type == "crowding"
    assert alert_2.severity == "HIGH"
    assert "Critical congestion" in alert_2.message
    
    # Evaluate again, should trigger debouncing (returns the same alert from last 60 seconds)
    alert_3 = alert_engine.evaluate_alerts(store_id)
    assert alert_3.id == alert_2.id
    
    # Check historical alerts retrieval
    history = alert_engine.get_historical_alerts(store_id, limit=5)
    assert len(history) == 1
    assert history[0].id == alert_2.id
