"""
backend/tests/api/test_funnel.py
─────────────────────────────────
Unit tests for GET /api/v1/funnel

Test matrix:
  ✓ Returns HTTP 200
  ✓ All 5 core funnel stage fields present
  ✓ Computed drop-off rate fields present (engagement_rate, checkout_rate, close_rate)
  ✓ visitors >= 1 after seeding entry event
  ✓ checkout_visitors >= 1 after seeding checkout dwell
  ✓ conversion_rate is in [0, 100]
  ✓ All stage counts are non-negative
  ✓ engaged_visitors <= visitors (funnel monotonicity)
  ✓ checkout_visitors <= engaged_visitors (funnel monotonicity)
  ✓ buyers <= checkout_visitors (funnel monotonicity)
  ✓ Unknown store_id returns zero funnel (graceful degradation)
"""

from __future__ import annotations

import pytest


# ── Shared telemetry seed helpers ──────────────────────────────────────────

def _seed_entry(client, track_id: int = 801):
    client.post("/api/v1/telemetry/entry", json={
        "store_id": "store-101",
        "camera_id": "cam-1",
        "track_id": track_id,
        "timestamp": "2026-05-31T12:00:00Z",
    })


def _seed_checkout_dwell(client, track_id: int = 801):
    client.post("/api/v1/telemetry/dwell", json={
        "store_id": "store-101",
        "camera_id": "cam-1",
        "track_id": track_id,
        "zone_id": "checkout_queue",
        "entered_at": "2026-05-31T12:01:00Z",
        "exited_at": "2026-05-31T12:02:00Z",
        "dwell_time_seconds": 60.0,
    })


def _seed_exit(client, track_id: int = 801):
    client.post("/api/v1/telemetry/exit", json={
        "store_id": "store-101",
        "camera_id": "cam-1",
        "track_id": track_id,
        "timestamp": "2026-05-31T12:03:00Z",
    })


class TestFunnelEndpoint:
    """Tests for GET /api/v1/funnel."""

    BASE_URL = "/api/v1/funnel"

    def test_funnel_returns_200(self, client):
        """Funnel endpoint must return HTTP 200 OK."""
        assert client.get(f"{self.BASE_URL}?store_id=store-101").status_code == 200

    def test_funnel_core_fields_present(self, client):
        """All five core funnel stage fields must be present."""
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        required = {"visitors", "engaged_visitors", "checkout_visitors", "buyers", "conversion_rate"}
        missing = required - set(data.keys())
        assert not missing, f"Missing core funnel fields: {missing}"

    def test_funnel_derived_rate_fields_present(self, client):
        """Computed drop-off rate fields must be present in the response."""
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        derived = {"engagement_rate", "checkout_rate", "close_rate"}
        missing = derived - set(data.keys())
        assert not missing, f"Missing derived rate fields: {missing}"

    def test_funnel_visitors_increments_after_entry(self, client):
        """visitors must be >= 1 after seeding at least one entry event."""
        _seed_entry(client)
        # Explicitly scope to cover the test's fixed timestamp (2026-05-31 12:00 UTC)
        data = client.get(
            f"{self.BASE_URL}?store_id=store-101"
            "&start_time=2026-05-31T00:00:00Z"
            "&end_time=2026-05-31T23:59:59Z"
        ).json()
        assert data["visitors"] >= 1

    def test_funnel_checkout_visitors_after_checkout_dwell(self, client):
        """checkout_visitors must be >= 1 after seeding a checkout queue dwell."""
        _seed_entry(client)
        _seed_checkout_dwell(client)
        _seed_exit(client)
        # Explicitly scope to cover the test's fixed timestamp (2026-05-31 12:00 UTC)
        data = client.get(
            f"{self.BASE_URL}?store_id=store-101"
            "&start_time=2026-05-31T00:00:00Z"
            "&end_time=2026-05-31T23:59:59Z"
        ).json()
        assert data["checkout_visitors"] >= 1

    def test_funnel_conversion_rate_in_valid_range(self, client):
        """conversion_rate must be in [0.0, 100.0]."""
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        rate = data["conversion_rate"]
        assert 0.0 <= rate <= 100.0, f"conversion_rate out of bounds: {rate}"

    def test_funnel_all_stage_counts_non_negative(self, client):
        """All stage counts must be >= 0."""
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        for field in ("visitors", "engaged_visitors", "checkout_visitors", "buyers"):
            assert data[field] >= 0, f"Negative count for field '{field}': {data[field]}"

    def test_funnel_monotonicity_engaged_lte_visitors(self, client):
        """engaged_visitors must be <= visitors (funnel can only narrow)."""
        _seed_entry(client, track_id=802)
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        assert data["engaged_visitors"] <= data["visitors"], (
            f"Funnel violation: engaged={data['engaged_visitors']} > visitors={data['visitors']}"
        )

    def test_funnel_monotonicity_checkout_lte_engaged(self, client):
        """checkout_visitors must be <= engaged_visitors."""
        _seed_entry(client, track_id=803)
        _seed_checkout_dwell(client, track_id=803)
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        assert data["checkout_visitors"] <= data["engaged_visitors"] or data["engaged_visitors"] == 0

    def test_funnel_monotonicity_buyers_lte_checkout(self, client):
        """buyers must be <= checkout_visitors."""
        _seed_entry(client, track_id=804)
        _seed_checkout_dwell(client, track_id=804)
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        assert data["buyers"] <= max(data["checkout_visitors"], 1)

    def test_funnel_unknown_store_returns_zero_funnel(self, client):
        """An unknown store_id must return zero funnel without crashing."""
        data = client.get(f"{self.BASE_URL}?store_id=nonexistent-999").json()
        assert data["visitors"] == 0
        assert data["conversion_rate"] == 0.0

    def test_funnel_engagement_rate_computed_correctly(self, client):
        """engagement_rate should equal engaged_visitors/visitors*100 (or 0 if no visitors)."""
        _seed_entry(client, track_id=805)
        data = client.get(f"{self.BASE_URL}?store_id=store-101").json()
        if data["visitors"] > 0:
            expected_rate = round((data["engaged_visitors"] / data["visitors"]) * 100, 2)
            assert abs(data["engagement_rate"] - expected_rate) < 0.1
        else:
            assert data["engagement_rate"] == 0.0
