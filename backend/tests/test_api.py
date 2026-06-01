import json
from datetime import datetime, timezone

def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "timestamp" in data

def test_telemetry_ingestions_and_queries(client):
    # 1. POST Ingest Shopper Entry
    entry_payload = {
        "store_id": "store-101",
        "camera_id": "cam-1",
        "track_id": 901,
        "timestamp": "2026-05-31T12:00:00Z",
        "re_entry_detected": False
    }
    response = client.post("/api/v1/telemetry/entry", json=entry_payload)
    assert response.status_code == 201
    assert response.json()["success"] is True
    assert "session_id" in response.json()

    # 2. POST Ingest Shopper Dwell Log
    dwell_payload = {
        "store_id": "store-101",
        "camera_id": "cam-1",
        "track_id": 901,
        "zone_id": "aisle_1_fresh",
        "entered_at": "2026-05-31T12:01:00Z",
        "exited_at": "2026-05-31T12:03:00Z",
        "dwell_time_seconds": 120.0
    }
    response = client.post("/api/v1/telemetry/dwell", json=dwell_payload)
    assert response.status_code == 201
    assert response.json()["success"] is True

    # 3. POST Ingest Shopper Dwell in checkout queue (needed for POS matching!)
    queue_dwell_payload = {
        "store_id": "store-101",
        "camera_id": "cam-1",
        "track_id": 901,
        "zone_id": "checkout_queue",
        "entered_at": "2026-05-31T12:04:00Z",
        "exited_at": "2026-05-31T12:04:50Z",
        "dwell_time_seconds": 50.0
    }
    client.post("/api/v1/telemetry/dwell", json=queue_dwell_payload)

    # 4. POST Ingest Shopper Exit
    exit_payload = {
        "store_id": "store-101",
        "camera_id": "cam-1",
        "track_id": 901,
        "timestamp": "2026-05-31T12:05:00Z"
    }
    response = client.post("/api/v1/telemetry/exit", json=exit_payload)
    assert response.status_code == 200
    assert response.json()["success"] is True

    # 5. POST Ingest POS Transaction
    transaction_payload = {
        "receipt_number": "REC-9920",
        "total_amount": 100.0,
        "tax_amount": 10.0,
        "transaction_time": "2026-05-31T12:05:15Z",
        "payment_method": "Credit",
        "items": [
            {
                "sku": "SKU-99",
                "product_name": "Premium Apple Box",
                "category": "Produce",
                "brand": "OrchardFresh",
                "quantity": 2,
                "unit_price": 50.0
            }
        ]
    }
    response = client.post("/api/v1/telemetry/transaction?store_id=store-101", json=transaction_payload)
    assert response.status_code == 201
    assert response.json()["success"] is True
    # Verify temporal correlation matcher successfully mapped transaction to Shopper 901!
    assert response.json()["correlated_track_id"] == 901

    # 6. GET Query Paginated Events
    response = client.get("/api/v1/telemetry/events?store_id=store-101")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["events"]) == 2
    assert response.json()["events"][0]["zone_id"] in ["aisle_1_fresh", "checkout_queue"]

    # 7. GET Query Paginated Visitors Sessions
    response = client.get("/api/v1/telemetry/visitors?store_id=store-101")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["visitors"][0]["track_id"] == 901

def test_analytics_endpoints(client):
    # Setup mock data using API endpoints to populate DB state
    client.post("/api/v1/telemetry/entry", json={"store_id": "store-101", "camera_id": "cam-1", "track_id": 901, "timestamp": "2026-05-31T12:00:00Z"})
    client.post("/api/v1/telemetry/dwell", json={"store_id": "store-101", "camera_id": "cam-1", "track_id": 901, "zone_id": "aisle_1_fresh", "entered_at": "2026-05-31T12:01:00Z", "exited_at": "2026-05-31T12:03:00Z", "dwell_time_seconds": 120.0})
    client.post("/api/v1/telemetry/dwell", json={"store_id": "store-101", "camera_id": "cam-1", "track_id": 901, "zone_id": "checkout_queue", "entered_at": "2026-05-31T12:04:00Z", "exited_at": "2026-05-31T12:04:50Z", "dwell_time_seconds": 50.0})
    client.post("/api/v1/telemetry/exit", json={"store_id": "store-101", "camera_id": "cam-1", "track_id": 901, "timestamp": "2026-05-31T12:05:00Z"})
    
    # Ingest Transaction
    client.post("/api/v1/telemetry/transaction?store_id=store-101", json={
        "receipt_number": "REC-9920", "total_amount": 100.0, "tax_amount": 10.0, "transaction_time": "2026-05-31T12:05:15Z", "payment_method": "Credit",
        "items": [{"sku": "SKU-99", "product_name": "Premium Apple Box", "category": "Produce", "brand": "OrchardFresh", "quantity": 2, "unit_price": 50.0}]
    })

    # A. GET metrics
    response = client.get("/api/v1/analytics/metrics?store_id=store-101&start_date=2026-05-31T00:00:00Z&end_date=2026-05-31T23:59:59Z")
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["total_visitors"] == 1
    assert metrics["conversion_rate"] == 100.0
    assert metrics["average_dwell_time"] == 5.0 # (12:05 - 12:00) = 5 mins

    # B. GET funnel
    response = client.get("/api/v1/analytics/funnel?store_id=store-101&start_date=2026-05-31T00:00:00Z&end_date=2026-05-31T23:59:59Z")
    assert response.status_code == 200
    funnel = response.json()
    assert funnel["visitors"] == 1
    assert funnel["engaged_visitors"] == 1
    assert funnel["buyers"] == 1

    # C. GET occupancy
    response = client.get("/api/v1/analytics/occupancy?store_id=store-101")
    assert response.status_code == 200
    assert "current" in response.json()
    assert "maximum" in response.json()

    # D. GET zones
    response = client.get("/api/v1/analytics/zones?store_id=store-101&start_date=2026-05-31T00:00:00Z&end_date=2026-05-31T23:59:59Z")
    assert response.status_code == 200
    zones = response.json()
    assert zones["most_visited_zone"] in ["Aisle 1 - Fresh Produce", "Checkout Waiting Queue"]
    assert len(zones["zone_statistics"]) == 2

    # E. GET heatmap
    response = client.get("/api/v1/analytics/heatmap?store_id=store-101&start_date=2026-05-31T00:00:00Z&end_date=2026-05-31T23:59:59Z")
    assert response.status_code == 200
    assert "zone_density" in response.json()
    assert len(response.json()["coordinates"]) > 0

    # F. GET sales
    response = client.get("/api/v1/analytics/sales?store_id=store-101&start_date=2026-05-31T00:00:00Z&end_date=2026-05-31T23:59:59Z")
    assert response.status_code == 200
    sales = response.json()
    assert len(sales["top_products"]) == 1
    assert sales["top_categories"][0]["name"] == "Produce"
    assert sales["top_brands"][0]["revenue"] == 100.0

    # G. GET alerts
    response = client.get("/api/v1/analytics/alerts?store_id=store-101&start_date=2026-05-31T00:00:00Z&end_date=2026-05-31T23:59:59Z")
    assert response.status_code == 200
    assert response.json()["alert_type"] == "operational_normal"

def test_error_handlers_and_validations(client):
    # 1. Test missing resource (404 NOT_FOUND handler)
    response = client.get("/api/v1/non_existent_route")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert "errors" in data
    assert data["errors"][0]["code"] in ["HTTP_ERROR", "NOT_FOUND"]

    # 2. Test request validation errors (Pydantic validation handler)
    # Entry with missing required parameter store_id
    bad_payload = {
        "camera_id": "cam-1",
        "track_id": 901,
        "timestamp": "2026-05-31T12:00:00Z"
    }
    response = client.post("/api/v1/telemetry/entry", json=bad_payload)
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert "errors" in data
    assert any("missing" in err["code"].lower() or "validation" in err["code"].lower() for err in data["errors"])
