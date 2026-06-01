"""
backend/tests/api/test_alerts.py
─────────────────────────────────
Unit tests for GET /api/v1/alerts

Test matrix:
  ✓ Returns HTTP 200
  ✓ Response has 'metadata' and 'data' keys
  ✓ metadata contains: page, limit, total_records, total_pages
  ✓ 'data' is a list
  ✓ Pagination: page=1 with limit=5 returns at most 5 items
  ✓ Severity filter: ?severity=HIGH returns only HIGH alerts (or empty list)
  ✓ Severity filter: invalid severity returns HTTP 422
  ✓ Date range filter: ?start_time=...&end_time=... accepted without error
  ✓ total_pages is consistent with total_records and limit
  ✓ Alert record schema: id, store_id, alert_type, severity, message, timestamp
  ✓ Unknown store_id returns empty data list with zero total_records
"""

from __future__ import annotations

import pytest


class TestAlertsEndpoint:
    """Tests for GET /api/v1/alerts."""

    BASE_URL = "/api/v1/alerts"

    def test_alerts_returns_200(self, client):
        """Alerts endpoint must return HTTP 200 OK."""
        assert client.get(f"{self.BASE_URL}?store_id=store-101").status_code == 200

    def test_alerts_response_envelope_keys(self, client):
        """Response must contain 'metadata' and 'data' top-level keys."""
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        assert "metadata" in data, "'metadata' key missing from response"
        assert "data" in data, "'data' key missing from response"

    def test_alerts_metadata_has_required_fields(self, client):
        """'metadata' must contain page, limit, total_records, total_pages."""
        meta = client.get(f"{self.BASE_URL}?store_id=store-101").json()["metadata"]
        required = {"page", "limit", "total_records", "total_pages"}
        missing = required - set(meta.keys())
        assert not missing, f"Missing metadata fields: {missing}"

    def test_alerts_data_is_list(self, client):
        """'data' must be a list (even if empty)."""
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()["data"]
        assert isinstance(data, list)

    def test_alerts_pagination_limit_respected(self, client):
        """With limit=5, the 'data' list must contain at most 5 items."""
        data = client.get(f"{self.BASE_URL}?store_id=store-101&limit=5").json()
        assert len(data["data"]) <= 5

    def test_alerts_default_page_is_one(self, client):
        """Default page parameter must be 1."""
        meta = client.get(f"{self.BASE_URL}?store_id=store-101").json()["metadata"]
        assert meta["page"] == 1

    def test_alerts_severity_filter_high(self, client):
        """?severity=HIGH must return only HIGH-severity alerts (or empty list)."""
        data = client.get(
            f"{self.BASE_URL}?store_id=store-101&severity=HIGH"
        ).json()["data"]
        for alert in data:
            assert alert["severity"] == "HIGH", (
                f"Non-HIGH severity alert leaked into filtered results: {alert}"
            )

    def test_alerts_severity_filter_low(self, client):
        """?severity=LOW must return only LOW-severity alerts (or empty list)."""
        data = client.get(
            f"{self.BASE_URL}?store_id=store-101&severity=LOW"
        ).json()["data"]
        for alert in data:
            assert alert["severity"] == "LOW"

    def test_alerts_invalid_severity_returns_422(self, client):
        """An invalid severity value must return HTTP 422 Unprocessable Entity."""
        response = client.get(f"{self.BASE_URL}?store_id=store-101&severity=EXTREME")
        assert response.status_code == 422

    def test_alerts_date_range_filter_accepted(self, client):
        """Date range query params must be accepted without error."""
        response = client.get(
            f"{self.BASE_URL}?store_id=store-101"
            "&start_time=2026-05-01T00:00:00Z"
            "&end_time=2026-05-31T23:59:59Z"
        )
        assert response.status_code == 200

    def test_alerts_total_pages_consistent_with_limit(self, client):
        """total_pages must equal ceil(total_records / limit)."""
        import math
        resp = client.get(f"{self.BASE_URL}?store_id=store-101&limit=10").json()
        meta = resp["metadata"]
        total = meta["total_records"]
        limit = meta["limit"]
        expected_pages = math.ceil(total / limit) if total > 0 else 0
        assert meta["total_pages"] == expected_pages, (
            f"total_pages mismatch: expected {expected_pages}, got {meta['total_pages']}"
        )

    def test_alerts_record_schema_on_non_empty(self, client):
        """If alerts exist, each record must have the required schema fields."""
        # Force evaluation to generate an alert if conditions are met
        resp = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        alerts = resp["data"]
        if alerts:
            required_fields = {"id", "store_id", "alert_type", "severity", "message", "timestamp"}
            for alert in alerts:
                missing = required_fields - set(alert.keys())
                assert not missing, f"Alert missing fields {missing}: {alert}"

    def test_alerts_unknown_store_returns_empty_list(self, client):
        """An unknown store_id must return an empty data list with zero total_records."""
        resp = client.get(f"{self.BASE_URL}?store_id=nonexistent-store-xyz").json()
        assert resp["data"] == []
        assert resp["metadata"]["total_records"] == 0
