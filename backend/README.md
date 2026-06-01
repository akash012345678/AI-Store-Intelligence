# PurpleInsight: Backend Business Logic Layer

This module provides the central business logic layer for the Store Intelligence System. It ingests, validates, and persists edge telemetry events and POS transactional data, matches purchase receipts to individual customer tracking IDs using a spatial-temporal correlation algorithm, and calculates operational and business metrics.

---

## Folder Structure

```text
backend/
├── config/
│   └── backend_config.yaml     # DB connection string, POS checkout matching parameters
├── src/
│   ├── __init__.py
│   ├── database.py             # Declarative Base & SQLite/Postgres session manager
│   ├── models.py               # ORM Database Models (Stores, Layouts, Dwells, Sales)
│   ├── schemas.py              # Pydantic v2 schemas for incoming telemetry ingestion
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ingest_service.py   # Ingestion, state deduplication, and POS correlation matcher
│   │   └── metrics_engine.py   # Stateful metrics engine calculating operational & BI funnels
│   └── main.py                 # Core application entrypoint (REST API stubs)
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Isolated SQLite in-memory DB fixture
│   ├── test_ingest.py          # Data ingestion and correlation unit tests
│   └── test_metrics.py         # Business logic and conversion unit tests
└── requirements.txt            # Module python dependencies
```

---

## Core Algorithms & Business Rules

### 1. Distinct Visitor Deduplication (No Double Counting)
Shoppers re-entering the store or triggering multiple cameras could cause duplicate entry counts.
*   **Edge Level**: The tracking module stitches active tracks together across spatial-temporal dropouts.
*   **Database Level**: `StoreSession` tracks overall presence. When an entry event occurs, `IngestService` checks if an active session (where `exited_at` is None) is already open for this `track_id` in this store. If it is, the duplicate entry telemetry is ignored, completely preventing double counting of active visitors.
*   **Analytics Level**: When calculating `total_visitors` over a time range, the `MetricsEngine` executes a `distinct().count()` over the `track_id` field in `StoreSession`, ensuring each customer is counted exactly once regardless of how many times they walked in and out or re-entered during their shopping trip.

### 2. Transaction-to-Track Correlation (Nearest Temporal Matcher)
To map receipts to shopper trails without biometrics, we correlate them in time.
1.  When a POS transaction occurs at time $T$, we query for all shoppers who exited the store within the temporal window $[T - 10\text{ minutes}, T + 2\text{ minutes}]$.
2.  We filter this set for candidates who dwelled inside the configured `checkout_queue` zone prior to their exit to guarantee they actually checked out.
3.  We calculate the absolute time delta $|\text{exited\_at} - T|$ for each candidate.
4.  The shopper with the **smallest temporal delta** is selected, and a link is written to `spatial_correlation_logs`.
5.  To prevent duplicate correlation, we verify the chosen shopper is not already linked to another transaction within a 60-second window.

### 3. Retail Funnel Metrics (Conversion Formulas)
*   **Visitor-to-Buyer Conversion**:
    $$\text{Conversion} = \left( \frac{\text{Unique Shoppers with a Correlated Purchase}}{\text{Total Unique Inbound Shoppers}} \right) \times 100$$
*   **Category-Specific Conversion**:
    $$\text{Category Conversion} = \left( \frac{\text{Unique Visitors who dwelled in [Category Zone] AND purchased an item of that Category}}{\text{Total Unique Visitors who dwelled in [Category Zone]}} \right) \times 100$$
*   **Brand-Specific Conversion**:
    $$\text{Brand Conversion} = \left( \frac{\text{Unique Visitors who dwelled in [Brand Zone] AND purchased an item of that Brand}}{\text{Total Unique Visitors who dwelled in [Brand Zone]}} \right) \times 100$$

---

## Installation & Setup

### 1. Install Dependencies
Run from the backend directory:
```bash
pip install -r backend/requirements.txt
```

### 2. Initialize Database
By default, the backend config is set to use a local SQLite database (`sqlite:///store_intelligence.db`).
To change the database settings, modify [backend_config.yaml](file:///c:/Users/Maha%20Monisha/OneDrive/Desktop/purple/backend/config/backend_config.yaml).

---

## Running Unit Tests

The backend includes a high-density, isolated test suite running on an in-memory SQLite database instance:
```bash
pytest backend/tests/
```
These tests verify:
*   Duplicate telemetry ingestion is cleanly deduplicated.
*   The transaction correlation engine correctly resolves nearest exits.
*   Conversion math (buyer, category, brand) prevents double counting and aligns perfectly with pre-calculated aggregates.
