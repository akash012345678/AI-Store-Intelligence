import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.database.connection import Base, get_db
from backend.models.domain import (
    Store, StoreLayoutZone, Camera, StoreSession, DwellLog,
    POSTransaction, TransactionItem, SpatialCorrelationLog, Alert
)
from backend.models.sales import (
    SalesStore, SalesCustomer, Salesperson, SalesProduct,
    SalesOrder, SalesOrderItem
)
from backend.main import create_app

@pytest.fixture(scope="function")
def test_db():
    """Provides an isolated in-memory SQLite database session populated with layout configurations."""
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    
    # Enforce foreign key constraints inside SQLite memory engine
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Build schema
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    try:
        # Pre-populate Master metadata
        store = Store(
            id="store-101",
            name="Supermarket Alfa",
            address="100 Retail Boulevard",
            timezone="UTC"
        )
        session.add(store)

        camera = Camera(
            id="cam-1",
            store_id="store-101",
            name="Front Gate Camera",
            rtsp_url="rtsp://localhost/stream"
        )
        session.add(camera)

        # Pre-populate Layout Zones
        zones = [
            StoreLayoutZone(id="checkout_queue", store_id="store-101", name="Checkout Waiting Queue", zone_type="checkout"),
            StoreLayoutZone(id="aisle_1_fresh", store_id="store-101", name="Aisle 1 - Fresh Produce", zone_type="aisle"),
            StoreLayoutZone(id="aisle_2_snacks", store_id="store-101", name="Aisle 2 - Snacks & Beverages", zone_type="aisle")
        ]
        session.add_all(zones)
        session.commit()

        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(test_db):
    """Provides a FastAPI TestClient with overrides injected for the isolated test database."""
    app = create_app()

    def override_get_db():
        try:
            yield test_db
        finally:
            pass # conftest fixture handles closing

    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
