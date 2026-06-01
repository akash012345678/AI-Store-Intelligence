from datetime import datetime
from backend.services.ingest import IngestService
from backend.schemas.telemetry import EntryTelemetry, ExitTelemetry, DwellTelemetry, POSTransactionPayload, POSItemPayload
from backend.models.domain import StoreSession, DwellLog, POSTransaction, SpatialCorrelationLog

def test_handle_entry_deduplication(test_db):
    service = IngestService(test_db)
    
    # 1. First entry
    entry_1 = EntryTelemetry(
        store_id="store-101",
        camera_id="cam-1",
        track_id=401,
        timestamp="2026-05-31T10:00:00Z",
        re_entry_detected=False
    )
    session_1 = service.handle_entry(entry_1)
    
    assert session_1.id is not None
    assert session_1.track_id == 401
    assert session_1.exited_at is None
    
    # 2. Duplicate entry (duplicate telemetry from second camera)
    entry_2 = EntryTelemetry(
        store_id="store-101",
        camera_id="cam-1",
        track_id=401,
        timestamp="2026-05-31T10:00:02Z",
        re_entry_detected=False
    )
    session_2 = service.handle_entry(entry_2)
    
    # Assert it returns the same session and didn't insert a second row
    assert session_2.id == session_1.id
    assert test_db.query(StoreSession).filter(StoreSession.store_id == "store-101").count() == 1

def test_handle_exit(test_db):
    service = IngestService(test_db)
    
    # Ingest entry
    service.handle_entry(EntryTelemetry(
        store_id="store-101",
        camera_id="cam-1",
        track_id=401,
        timestamp="2026-05-31T10:00:00Z"
    ))
    
    # Ingest exit
    exit_telemetry = ExitTelemetry(
        store_id="store-101",
        camera_id="cam-1",
        track_id=401,
        timestamp="2026-05-31T10:05:00Z"
    )
    session = service.handle_exit(exit_telemetry)
    
    assert session.exited_at is not None
    assert session.exited_at.hour == 10
    assert session.exited_at.minute == 5

def test_handle_dwell(test_db):
    service = IngestService(test_db)
    
    dwell_tel = DwellTelemetry(
        store_id="store-101",
        camera_id="cam-1",
        track_id=401,
        zone_id="aisle_1_fresh",
        entered_at="2026-05-31T10:00:05Z",
        exited_at="2026-05-31T10:00:45Z",
        dwell_time_seconds=40.0
    )
    
    dwell_log = service.handle_dwell(dwell_tel)
    assert dwell_log.id is not None
    assert dwell_log.duration_seconds == 40.0
    assert dwell_log.zone_id == "aisle_1_fresh"

def test_pos_transaction_spatial_correlation(test_db):
    service = IngestService(test_db, checkout_queue_zone_id="checkout_queue")

    # Persist Shopper 1 sessions & dwells
    service.handle_entry(EntryTelemetry(store_id="store-101", camera_id="cam-1", track_id=401, timestamp="2026-05-31T10:00:00Z"))
    service.handle_dwell(DwellTelemetry(
        store_id="store-101", camera_id="cam-1", track_id=401, zone_id="checkout_queue",
        entered_at="2026-05-31T10:04:00Z", exited_at="2026-05-31T10:04:50Z", dwell_time_seconds=50.0
    ))
    service.handle_exit(ExitTelemetry(store_id="store-101", camera_id="cam-1", track_id=401, timestamp="2026-05-31T10:05:00Z"))

    # Persist Shopper 2 sessions & dwells
    service.handle_entry(EntryTelemetry(store_id="store-101", camera_id="cam-1", track_id=402, timestamp="2026-05-31T10:01:00Z"))
    service.handle_dwell(DwellTelemetry(
        store_id="store-101", camera_id="cam-1", track_id=402, zone_id="checkout_queue",
        entered_at="2026-05-31T10:08:00Z", exited_at="2026-05-31T10:08:40Z", dwell_time_seconds=40.0
    ))
    service.handle_exit(ExitTelemetry(store_id="store-101", camera_id="cam-1", track_id=402, timestamp="2026-05-31T10:09:00Z"))
    
    payload = POSTransactionPayload(
        receipt_number="REC-10029",
        total_amount=59.90,
        tax_amount=5.00,
        transaction_time="2026-05-31T10:05:15Z",
        payment_method="Debit",
        items=[
            POSItemPayload(sku="PROD-01", product_name="Organic Apples", category="Produce", brand="OrchardFresh", quantity=2, unit_price=4.95),
            POSItemPayload(sku="PROD-02", product_name="Premium Chocolates", category="Snacks", brand="SweetCo", quantity=1, unit_price=50.00)
        ]
    )

    txn, correlation = service.handle_transaction(payload, store_id="store-101")

    assert txn.id is not None
    assert correlation is not None
    assert correlation.track_id == 401 # Correctly matched to Shopper 1!
    assert correlation.correlation_confidence >= 0.95
