from fastapi import APIRouter, Depends, Query, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from datetime import datetime

from backend.database.connection import get_db
from backend.services.ingest import IngestService
from backend.models.domain import DwellLog, StoreSession
from backend.schemas.telemetry import (
    EntryTelemetry,
    ExitTelemetry,
    DwellTelemetry,
    POSTransactionPayload
)

router = APIRouter(prefix="/telemetry", tags=["Telemetry Ingestion & Queries"])

# Ingestion Endpoints

@router.post("/entry", status_code=201)
def ingest_entry(entry: EntryTelemetry, db: Session = Depends(get_db)):
    """Ingests shopper entry telemetry from cameras."""
    service = IngestService(db)
    session = service.handle_entry(entry)
    return {"success": True, "session_id": session.id}

@router.post("/exit", status_code=200)
def ingest_exit(exit_telemetry: ExitTelemetry, db: Session = Depends(get_db)):
    """Ingests shopper exit telemetry from cameras."""
    service = IngestService(db)
    session = service.handle_exit(exit_telemetry)
    return {"success": True, "session_id": session.id if session else None}

@router.post("/dwell", status_code=201)
def ingest_dwell(dwell: DwellTelemetry, db: Session = Depends(get_db)):
    """Ingests customer layout zone dwell logs from tracking nodes."""
    service = IngestService(db)
    log = service.handle_dwell(dwell)
    return {"success": True, "dwell_log_id": log.id}

@router.post("/transaction", status_code=201)
def ingest_transaction(
    payload: POSTransactionPayload, 
    store_id: str = Query(..., description="Store UUID where the transaction occurred"),
    db: Session = Depends(get_db)
):
    """Registers POS transactions and executes the temporal shopper correlation matcher."""
    service = IngestService(db)
    txn, correlation = service.handle_transaction(payload, store_id)
    return {
        "success": True, 
        "transaction_id": txn.id,
        "correlated_track_id": correlation.track_id if correlation else None,
        "correlation_confidence": correlation.correlation_confidence if correlation else 0.0
    }

# Query Endpoints

@router.get("/events")
def query_dwell_events(
    store_id: str = Query(..., description="Filter by store UUID"),
    zone_id: Optional[str] = Query(None, description="Filter by layout zone ID"),
    start_date: Optional[str] = Query(None, description="ISO datetime bounds start"),
    end_date: Optional[str] = Query(None, description="ISO datetime bounds end"),
    page: int = Query(1, ge=1, description="Pagination index"),
    limit: int = Query(50, ge=1, le=100, description="Page volume limit"),
    db: Session = Depends(get_db)
):
    """Lists paginated zone dwell telemetry logs, supporting date-range filtering."""
    query = db.query(DwellLog).filter(DwellLog.store_id == store_id)

    if zone_id:
        query = query.filter(DwellLog.zone_id == zone_id)

    if start_date:
        start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        query = query.filter(DwellLog.entered_at >= start_dt)

    if end_date:
        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        query = query.filter(DwellLog.exited_at <= end_dt)

    # Count total matching for metadata pagination headers
    total_count = query.count()

    # Apply pagination and sorting (latest first)
    offset = (page - 1) * limit
    results = query.order_by(DwellLog.entered_at.desc()).offset(offset).limit(limit).all()

    output = []
    for r in results:
        output.append({
            "id": r.id,
            "track_id": r.track_id,
            "zone_id": r.zone_id,
            "entered_at": r.entered_at.isoformat(),
            "exited_at": r.exited_at.isoformat(),
            "duration_seconds": r.duration_seconds
        })

    return {
        "total": total_count,
        "page": page,
        "limit": limit,
        "events": output
    }

@router.get("/visitors")
def query_visitors(
    store_id: str = Query(..., description="Filter by store UUID"),
    track_id: Optional[int] = Query(None, description="Filter by unique shopper ID"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists paginated overall visitor sessions inside the store, supporting search filters."""
    query = db.query(StoreSession).filter(StoreSession.store_id == store_id)

    if track_id:
        query = query.filter(StoreSession.track_id == track_id)

    total_count = query.count()
    offset = (page - 1) * limit
    results = query.order_by(StoreSession.entered_at.desc()).offset(offset).limit(limit).all()

    output = []
    for r in results:
        duration = None
        if r.exited_at:
            duration = round((r.exited_at - r.entered_at).total_seconds(), 1)
        output.append({
            "session_id": r.id,
            "track_id": r.track_id,
            "entered_at": r.entered_at.isoformat(),
            "exited_at": r.exited_at.isoformat() if r.exited_at else None,
            "duration_seconds": duration,
            "re_entry": r.re_entry,
            "correlated_previous_track_id": r.correlated_previous_track_id
        })

    return {
        "total": total_count,
        "page": page,
        "limit": limit,
        "visitors": output
    }
