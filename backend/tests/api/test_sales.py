"""
backend/tests/api/test_sales.py
────────────────────────────────
Unit tests for GET /api/v1/sales

Test matrix:
  ✓ Returns HTTP 200
  ✓ Response has all four top-level keys
  ✓ top_products is a list
  ✓ top_brands is a list
  ✓ top_categories is a list
  ✓ revenue_metrics has required financial keys
  ✓ top_products length <= 5 (capped at top 5)
  ✓ top_brands length <= 5
  ✓ top_categories length <= 5
  ✓ If products exist, each item has 'name', 'volume', 'revenue'
  ✓ revenue_metrics.total_gmv >= 0
  ✓ revenue_metrics.total_nmv <= total_gmv (NMV is GMV minus discounts)
  ✓ revenue_metrics.total_tax_collected >= 0
  ✓ revenue_metrics.total_discounts >= 0
  ✓ hourly_sales_distribution is a dict
"""

from __future__ import annotations

import pytest


class TestSalesEndpoint:
    """Tests for GET /api/v1/sales."""

    BASE_URL = "/api/v1/sales"

    def test_sales_returns_200(self, client):
        """Sales endpoint must return HTTP 200 OK."""
        assert client.get(self.BASE_URL).status_code == 200

    def test_sales_top_level_keys_present(self, client):
        """Response must contain all four top-level keys."""
        data = client.get(self.BASE_URL).json()
        required = {"top_products", "top_brands", "top_categories", "revenue_metrics"}
        missing = required - set(data.keys())
        assert not missing, f"Missing top-level keys: {missing}"

    def test_sales_top_products_is_list(self, client):
        """top_products must be a list."""
        data = client.get(self.BASE_URL).json()
        assert isinstance(data["top_products"], list)

    def test_sales_top_brands_is_list(self, client):
        """top_brands must be a list."""
        data = client.get(self.BASE_URL).json()
        assert isinstance(data["top_brands"], list)

    def test_sales_top_categories_is_list(self, client):
        """top_categories must be a list."""
        data = client.get(self.BASE_URL).json()
        assert isinstance(data["top_categories"], list)

    def test_sales_top_products_capped_at_five(self, client):
        """top_products must contain at most 5 items."""
        data = client.get(self.BASE_URL).json()
        assert len(data["top_products"]) <= 5

    def test_sales_top_brands_capped_at_five(self, client):
        """top_brands must contain at most 5 items."""
        data = client.get(self.BASE_URL).json()
        assert len(data["top_brands"]) <= 5

    def test_sales_top_categories_capped_at_five(self, client):
        """top_categories must contain at most 5 items."""
        data = client.get(self.BASE_URL).json()
        assert len(data["top_categories"]) <= 5

    def test_sales_product_item_schema(self, client):
        """Each item in top_products must have 'name', 'volume', 'revenue'."""
        data = client.get(self.BASE_URL).json()
        for item in data["top_products"]:
            assert "name" in item,   f"'name' missing from product item: {item}"
            assert "volume" in item, f"'volume' missing from product item: {item}"
            assert "revenue" in item, f"'revenue' missing from product item: {item}"

    def test_sales_brand_item_schema(self, client):
        """Each item in top_brands must have 'name', 'volume', 'revenue'."""
        data = client.get(self.BASE_URL).json()
        for item in data["top_brands"]:
            assert "name" in item
            assert "volume" in item
            assert "revenue" in item

    def test_sales_category_item_schema(self, client):
        """Each item in top_categories must have 'name', 'volume', 'revenue'."""
        data = client.get(self.BASE_URL).json()
        for item in data["top_categories"]:
            assert "name" in item
            assert "volume" in item
            assert "revenue" in item

    def test_sales_revenue_metrics_keys_present(self, client):
        """revenue_metrics must contain all required financial KPI keys."""
        revenue = client.get(self.BASE_URL).json()["revenue_metrics"]
        required = {
            "total_gmv", "total_nmv", "total_tax_collected",
            "total_discounts", "hourly_sales_distribution",
        }
        missing = required - set(revenue.keys())
        assert not missing, f"Missing revenue_metrics keys: {missing}"

    def test_sales_total_gmv_non_negative(self, client):
        """total_gmv must be >= 0."""
        revenue = client.get(self.BASE_URL).json()["revenue_metrics"]
        assert revenue["total_gmv"] >= 0.0

    def test_sales_total_nmv_lte_gmv(self, client):
        """total_nmv must be <= total_gmv (NMV = GMV - discounts)."""
        revenue = client.get(self.BASE_URL).json()["revenue_metrics"]
        assert revenue["total_nmv"] <= revenue["total_gmv"], (
            f"NMV ({revenue['total_nmv']}) > GMV ({revenue['total_gmv']}) — impossible"
        )

    def test_sales_total_tax_non_negative(self, client):
        """total_tax_collected must be >= 0."""
        revenue = client.get(self.BASE_URL).json()["revenue_metrics"]
        assert revenue["total_tax_collected"] >= 0.0

    def test_sales_total_discounts_non_negative(self, client):
        """total_discounts must be >= 0."""
        revenue = client.get(self.BASE_URL).json()["revenue_metrics"]
        assert revenue["total_discounts"] >= 0.0

    def test_sales_hourly_distribution_is_dict(self, client):
        """hourly_sales_distribution must be a dict."""
        revenue = client.get(self.BASE_URL).json()["revenue_metrics"]
        assert isinstance(revenue["hourly_sales_distribution"], dict)

    def test_sales_revenue_values_are_numeric(self, client):
        """All revenue values must be numeric (int or float)."""
        revenue = client.get(self.BASE_URL).json()["revenue_metrics"]
        for key in ("total_gmv", "total_nmv", "total_tax_collected", "total_discounts"):
            assert isinstance(revenue[key], (int, float)), (
                f"Non-numeric value for '{key}': {revenue[key]!r}"
            )
