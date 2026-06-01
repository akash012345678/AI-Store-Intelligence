"""
PurpleInsight — CV Event Bus
==============================
Defines all typed CV events produced by the edge analytics engine and
consumed by backend services (IngestService, MetricsService, AlertService).

Event hierarchy:
    CVEvent (base)
    ├── EntryEvent       — shopper crossed entry gate inward
    ├── ExitEvent        — shopper crossed entry gate outward
    ├── DwellEvent       — shopper exited a layout zone
    ├── OccupancyEvent   — periodic store-wide occupancy snapshot
    ├── QueueEvent       — checkout queue depth + wait times
    └── AlertEvent       — threshold breach (congestion / loitering / overcrowding)

Integration:
    CVEventRouter.route(event, db_session)
        → IngestService.handle_entry / handle_exit / handle_dwell
        → MetricsService (occupancy snapshot update)
        → AlertService.evaluate_alerts / persist_alert
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.services.ingest import IngestService
from backend.services.metrics import MetricsService
from backend.services.alerts import AlertService
from backend.schemas.telemetry import EntryTelemetry, ExitTelemetry, DwellTelemetry

logger = logging.getLogger("PurpleInsight.CVEventBus")
logger.setLevel(logging.INFO)


# ─────────────────────────────────────────────────────────────────────────────
# Typed CV Event Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

class CVEvent:
    """Base class for all computer-vision generated events."""
    __slots__ = ("store_id", "camera_id", "timestamp")

    def __init__(self, store_id: str, camera_id: str, timestamp: Optional[str] = None):
        self.store_id = store_id
        self.camera_id = camera_id
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} store={self.store_id} cam={self.camera_id}>"


class EntryEvent(CVEvent):
    """
    Fired when ByteTrack detects a new track crossing the entry gate inward.

    Attributes:
        track_id:                      Unique shopper track identifier.
        confidence:                    YOLOv8 detection confidence [0, 1].
        re_entry_detected:             True if this track was stitched to a previous exit.
        correlated_previous_track_id:  The original track ID this was stitched to (re-entry).
    """
    __slots__ = ("track_id", "confidence", "re_entry_detected", "correlated_previous_track_id")

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        track_id: int,
        confidence: float,
        re_entry_detected: bool = False,
        correlated_previous_track_id: Optional[int] = None,
        timestamp: Optional[str] = None,
    ):
        super().__init__(store_id, camera_id, timestamp)
        self.track_id = track_id
        self.confidence = confidence
        self.re_entry_detected = re_entry_detected
        self.correlated_previous_track_id = correlated_previous_track_id

    def to_telemetry(self) -> EntryTelemetry:
        return EntryTelemetry(
            store_id=self.store_id,
            camera_id=self.camera_id,
            track_id=self.track_id,
            timestamp=self.timestamp,
            re_entry_detected=self.re_entry_detected,
            correlated_previous_track_id=self.correlated_previous_track_id,
        )


class ExitEvent(CVEvent):
    """
    Fired when ByteTrack detects a tracked person crossing the gate outward.

    Attributes:
        track_id:   Unique shopper track identifier.
        confidence: YOLOv8 detection confidence [0, 1].
    """
    __slots__ = ("track_id", "confidence")

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        track_id: int,
        confidence: float,
        timestamp: Optional[str] = None,
    ):
        super().__init__(store_id, camera_id, timestamp)
        self.track_id = track_id
        self.confidence = confidence

    def to_telemetry(self) -> ExitTelemetry:
        return ExitTelemetry(
            store_id=self.store_id,
            camera_id=self.camera_id,
            track_id=self.track_id,
            timestamp=self.timestamp,
        )


class DwellEvent(CVEvent):
    """
    Fired when a tracked person exits a layout zone after the dwell cooldown window.

    Attributes:
        track_id:           Shopper track identifier.
        zone_id:            Layout zone identifier (matches zone_config.json).
        zone_name:          Human-readable zone label.
        entered_at:         ISO 8601 timestamp when the person entered the zone.
        exited_at:          ISO 8601 timestamp when the person exited the zone.
        dwell_time_seconds: Total time spent inside the zone.
    """
    __slots__ = ("track_id", "zone_id", "zone_name", "entered_at", "exited_at", "dwell_time_seconds")

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        track_id: int,
        zone_id: str,
        entered_at: str,
        exited_at: str,
        dwell_time_seconds: float,
        zone_name: str = "",
        timestamp: Optional[str] = None,
    ):
        super().__init__(store_id, camera_id, timestamp)
        self.track_id = track_id
        self.zone_id = zone_id
        self.zone_name = zone_name or zone_id.replace("_", " ").title()
        self.entered_at = entered_at
        self.exited_at = exited_at
        self.dwell_time_seconds = dwell_time_seconds

    def to_telemetry(self) -> DwellTelemetry:
        return DwellTelemetry(
            store_id=self.store_id,
            camera_id=self.camera_id,
            track_id=self.track_id,
            zone_id=self.zone_id,
            entered_at=self.entered_at,
            exited_at=self.exited_at,
            dwell_time_seconds=self.dwell_time_seconds,
        )


class OccupancyEvent(CVEvent):
    """
    Periodic snapshot of store-wide occupancy and per-zone person counts.

    Emitted every `occupancy_interval` seconds by the AnalyticsEngine.

    Attributes:
        current_occupancy:   Total shoppers currently inside the store.
        active_tracks_count: Total ByteTrack IDs currently being tracked.
        zone_occupancies:    {zone_id: current_person_count} snapshot.
    """
    __slots__ = ("current_occupancy", "active_tracks_count", "zone_occupancies")

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        current_occupancy: int,
        active_tracks_count: int,
        zone_occupancies: Dict[str, int],
        timestamp: Optional[str] = None,
    ):
        super().__init__(store_id, camera_id, timestamp)
        self.current_occupancy = current_occupancy
        self.active_tracks_count = active_tracks_count
        self.zone_occupancies = zone_occupancies


class QueueEvent(CVEvent):
    """
    Checkout queue depth and wait-time snapshot.

    Attributes:
        queue_id:           Zone ID of the checkout queue being measured.
        current_length:     Number of people currently waiting in the queue.
        avg_wait_seconds:   Average wait time of shoppers in queue.
        max_wait_seconds:   Longest individual wait time currently in queue.
    """
    __slots__ = ("queue_id", "current_length", "avg_wait_seconds", "max_wait_seconds")

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        queue_id: str,
        current_length: int,
        avg_wait_seconds: float,
        max_wait_seconds: float,
        timestamp: Optional[str] = None,
    ):
        super().__init__(store_id, camera_id, timestamp)
        self.queue_id = queue_id
        self.current_length = current_length
        self.avg_wait_seconds = avg_wait_seconds
        self.max_wait_seconds = max_wait_seconds


class AlertEvent(CVEvent):
    """
    Operational threshold-breach alert from the CV analytics engine.

    Attributes:
        alert_type:  Category string (e.g. "crowding", "loitering", "overcrowding").
        severity:    "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
        message:     Human-readable alert description.
        queue_id:    Relevant queue zone ID (for queue-related alerts).
    """
    __slots__ = ("alert_type", "severity", "message", "queue_id")

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        alert_type: str,
        severity: str,
        message: str,
        queue_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        super().__init__(store_id, camera_id, timestamp)
        self.alert_type = alert_type
        self.severity = severity
        self.message = message
        self.queue_id = queue_id


# ─────────────────────────────────────────────────────────────────────────────
# CV Event Router — Backend Integration
# ─────────────────────────────────────────────────────────────────────────────

class CVEventRouter:
    """
    Routes typed CV events from the edge analytics engine to backend services.

    This is the integration bridge between:
        edge/ (CV detection)  →  backend/ (IngestService, MetricsService, AlertService)

    Each event type is handled by the appropriate service:
        EntryEvent   → IngestService.handle_entry()    → StoreSession (open)
        ExitEvent    → IngestService.handle_exit()     → StoreSession (close)
        DwellEvent   → IngestService.handle_dwell()    → DwellLog
        OccupancyEvent → MetricsService (no-op: DB is source of truth)
        QueueEvent   → AlertService queue threshold check
        AlertEvent   → AlertService.persist_alert() with debounce

    Thread Safety:
        This class is NOT thread-safe. Each CameraWorker thread should create
        its own CVEventRouter instance bound to a separate DB session.
    """

    def __init__(self, db: Session):
        self.db = db
        self.ingest = IngestService(db)
        self.metrics = MetricsService(db)
        self.alerts = AlertService(db)

    def route(self, event: CVEvent) -> None:
        """
        Dispatch a CV event to the correct backend service handler.

        Errors are caught and logged per-event to prevent one failed
        event from blocking the pipeline.
        """
        try:
            if isinstance(event, EntryEvent):
                self._on_entry(event)
            elif isinstance(event, ExitEvent):
                self._on_exit(event)
            elif isinstance(event, DwellEvent):
                self._on_dwell(event)
            elif isinstance(event, OccupancyEvent):
                self._on_occupancy(event)
            elif isinstance(event, QueueEvent):
                self._on_queue(event)
            elif isinstance(event, AlertEvent):
                self._on_alert(event)
            else:
                logger.debug(f"Unhandled CV event type: {type(event).__name__}")
        except Exception as exc:
            logger.error(
                f"CVEventRouter failed routing {type(event).__name__} "
                f"[store={event.store_id}]: {exc}",
                exc_info=True,
            )

    # ── Entry ────────────────────────────────────────────────────────────────

    def _on_entry(self, event: EntryEvent) -> None:
        """Creates/updates a StoreSession for the entering shopper."""
        session = self.ingest.handle_entry(event.to_telemetry())
        logger.info(
            f"[ENTRY] track={event.track_id} session_id={session.id} "
            f"re_entry={event.re_entry_detected}"
        )

    # ── Exit ─────────────────────────────────────────────────────────────────

    def _on_exit(self, event: ExitEvent) -> None:
        """Closes the StoreSession for the exiting shopper."""
        session = self.ingest.handle_exit(event.to_telemetry())
        if session:
            duration = None
            if session.exited_at and session.entered_at:
                duration = round((session.exited_at - session.entered_at).total_seconds(), 1)
            logger.info(
                f"[EXIT] track={event.track_id} session_id={session.id} "
                f"duration={duration}s"
            )

    # ── Dwell ────────────────────────────────────────────────────────────────

    def _on_dwell(self, event: DwellEvent) -> None:
        """Persists a DwellLog and runs post-dwell alert evaluation."""
        log = self.ingest.handle_dwell(event.to_telemetry())
        logger.info(
            f"[DWELL] track={event.track_id} zone={event.zone_id} "
            f"duration={event.dwell_time_seconds:.1f}s log_id={log.id}"
        )
        # Post-dwell loitering check
        if event.dwell_time_seconds >= 300.0:
            self.alerts.detect_loitering(event.store_id)

    # ── Occupancy ────────────────────────────────────────────────────────────

    def _on_occupancy(self, event: OccupancyEvent) -> None:
        """
        Occupancy snapshots from the edge are informational.
        The authoritative count is derived from open StoreSession records.
        This handler logs the snapshot and triggers overcrowding detection.
        """
        logger.debug(
            f"[OCCUPANCY] store={event.store_id} "
            f"live={event.current_occupancy} tracks={event.active_tracks_count}"
        )
        # Trigger overcrowding evaluation using live DB count
        self.alerts.detect_overcrowding(event.store_id, threshold=15)

    # ── Queue ────────────────────────────────────────────────────────────────

    def _on_queue(self, event: QueueEvent) -> None:
        """
        Processes queue depth snapshots.

        Emits QueueCongestion alert if threshold breached:
            - length ≥ 4 people
            - max_wait ≥ 120 seconds
        """
        logger.debug(
            f"[QUEUE] queue={event.queue_id} length={event.current_length} "
            f"avg_wait={event.avg_wait_seconds:.1f}s max_wait={event.max_wait_seconds:.1f}s"
        )
        if event.current_length >= 4 or event.max_wait_seconds >= 120.0:
            severity = "HIGH" if event.current_length >= 6 or event.max_wait_seconds >= 180.0 else "MEDIUM"
            recent = self.alerts.is_debounced(event.store_id, "crowding", debounce_seconds=60)
            if not recent:
                msg = (
                    f"Checkout queue congestion in '{event.queue_id}': "
                    f"{event.current_length} shoppers, max wait {event.max_wait_seconds:.0f}s."
                )
                self.alerts.persist_alert(event.store_id, "crowding", severity, msg)

    # ── Alert ────────────────────────────────────────────────────────────────

    def _on_alert(self, event: AlertEvent) -> None:
        """
        Persists an alert generated directly by the edge analytics engine.
        Applies service-layer debounce before writing to the database.
        """
        recent = self.alerts.is_debounced(event.store_id, event.alert_type, debounce_seconds=60)
        if not recent:
            self.alerts.persist_alert(
                event.store_id, event.alert_type, event.severity, event.message
            )
            logger.warning(
                f"[ALERT][{event.severity}] type={event.alert_type} — {event.message}"
            )
        else:
            logger.debug(f"[ALERT] Debounced: {event.alert_type} for store={event.store_id}")


# ─────────────────────────────────────────────────────────────────────────────
# Edge → Backend Event Adapter
# ─────────────────────────────────────────────────────────────────────────────

def adapt_edge_event(edge_event) -> Optional[CVEvent]:
    """
    Converts an event from edge.src.event_dispatcher into a typed CVEvent.

    This adapter bridges the edge Pydantic event models to the CVEvent
    hierarchy used by CVEventRouter, enabling the edge pipeline to
    integrate with backend services without direct imports.

    Args:
        edge_event: A BaseEvent subclass from edge.src.event_dispatcher

    Returns:
        Corresponding CVEvent subclass, or None if not mappable.
    """
    from edge.src.event_dispatcher import (
        PersonEntryEvent, PersonExitEvent, ZoneDwellEvent,
        OccupancyUpdateEvent, QueueUpdateEvent, QueueAlertEvent,
    )

    if isinstance(edge_event, PersonEntryEvent):
        return EntryEvent(
            store_id=edge_event.store_id,
            camera_id=edge_event.camera_id,
            track_id=edge_event.track_id,
            confidence=edge_event.confidence,
            re_entry_detected=edge_event.re_entry_detected,
            correlated_previous_track_id=edge_event.correlated_previous_track_id,
            timestamp=edge_event.timestamp,
        )
    elif isinstance(edge_event, PersonExitEvent):
        return ExitEvent(
            store_id=edge_event.store_id,
            camera_id=edge_event.camera_id,
            track_id=edge_event.track_id,
            confidence=edge_event.confidence,
            timestamp=edge_event.timestamp,
        )
    elif isinstance(edge_event, ZoneDwellEvent):
        return DwellEvent(
            store_id=edge_event.store_id,
            camera_id=edge_event.camera_id,
            track_id=edge_event.track_id,
            zone_id=edge_event.zone_id,
            entered_at=edge_event.entered_at,
            exited_at=edge_event.exited_at,
            dwell_time_seconds=edge_event.dwell_time_seconds,
            timestamp=edge_event.timestamp,
        )
    elif isinstance(edge_event, OccupancyUpdateEvent):
        return OccupancyEvent(
            store_id=edge_event.store_id,
            camera_id=edge_event.camera_id,
            current_occupancy=edge_event.current_occupancy,
            active_tracks_count=edge_event.active_tracks_count,
            zone_occupancies=edge_event.zone_occupancies,
            timestamp=edge_event.timestamp,
        )
    elif isinstance(edge_event, QueueUpdateEvent):
        return QueueEvent(
            store_id=edge_event.store_id,
            camera_id=edge_event.camera_id,
            queue_id=edge_event.queue_id,
            current_length=edge_event.current_length,
            avg_wait_seconds=edge_event.avg_wait_seconds,
            max_wait_seconds=edge_event.max_wait_seconds,
            timestamp=edge_event.timestamp,
        )
    elif isinstance(edge_event, QueueAlertEvent):
        return AlertEvent(
            store_id=edge_event.store_id,
            camera_id=edge_event.camera_id,
            alert_type="crowding",
            severity=edge_event.severity,
            message=edge_event.message,
            queue_id=edge_event.queue_id,
            timestamp=edge_event.timestamp,
        )
    return None
