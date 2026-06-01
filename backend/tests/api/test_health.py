"""
backend/tests/api/test_health.py
────────────────────────────────
Unit tests for GET /api/v1/health

Test matrix:
  ✓ Returns HTTP 200
  ✓ status == "healthy"
  ✓ database == "connected" (test DB is always up)
  ✓ version == "1.0.0"
  ✓ timestamp field is present and ISO 8601 parseable
  ✓ uptime_seconds is present and non-negative
  ✓ X-Request-ID response header is present
  ✓ X-Process-Time response header is present
"""

from __future__ import annotations

import pytest
from datetime import datetime


class TestHealthEndpoint:
    """Tests for GET /api/v1/health."""

    BASE_URL = "/api/v1/health"

    def test_health_returns_200(self, client):
        """Health endpoint must return HTTP 200 OK for a connected database."""
        response = client.get(self.BASE_URL)
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. Body: {response.text}"
        )

    def test_health_status_is_healthy(self, client):
        """'status' field must equal 'healthy' when the database is reachable."""
        data = client.get(self.BASE_URL).json()
        assert data["status"] == "healthy"

    def test_health_database_connected(self, client):
        """'database' field must equal 'connected' (test DB is always available)."""
        data = client.get(self.BASE_URL).json()
        assert data["database"] == "connected"

    def test_health_version_is_correct(self, client):
        """'version' must be the published API version '1.0.0'."""
        data = client.get(self.BASE_URL).json()
        assert data["version"] == "1.0.0"

    def test_health_timestamp_is_iso8601(self, client):
        """'timestamp' must be present and parseable as an ISO 8601 datetime string."""
        data = client.get(self.BASE_URL).json()
        assert "timestamp" in data, "'timestamp' key missing from response"
        # Should not raise
        parsed = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        assert parsed is not None

    def test_health_uptime_seconds_present_and_non_negative(self, client):
        """'uptime_seconds' must be present and >= 0."""
        data = client.get(self.BASE_URL).json()
        assert "uptime_seconds" in data, "'uptime_seconds' key missing from response"
        assert data["uptime_seconds"] >= 0.0

    def test_health_request_id_header_present(self, client):
        """The X-Request-ID response header must be present for distributed tracing."""
        response = client.get(self.BASE_URL)
        # TestClient lowercases header names
        assert (
            "x-request-id" in response.headers
        ), "X-Request-ID header missing from health response"

    def test_health_process_time_header_present(self, client):
        """The X-Process-Time response header must be present for latency monitoring."""
        response = client.get(self.BASE_URL)
        assert (
            "x-process-time" in response.headers
        ), "X-Process-Time header missing from health response"

    def test_health_response_schema_complete(self, client):
        """All expected top-level keys must be present in the response body."""
        data = client.get(self.BASE_URL).json()
        required_keys = {"status", "database", "version", "timestamp", "uptime_seconds"}
        missing = required_keys - set(data.keys())
        assert not missing, f"Missing keys in health response: {missing}"
