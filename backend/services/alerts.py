from datetime import datetime, timedelta
import logging
from typing import List, Optional
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session
from backend.models import Alert, DwellLog, StoreSession

logger = logging.getLogger("PurpleInsight.AlertService")
logger.setLevel(logging.INFO)

class AlertService:
    """Evaluates real-time store metrics against operational thresholds to persist and debounce alerts."""

    def __init__(self, db: Session):
        self.db = db

    def is_debounced(self, store_id: str, alert_type: str, debounce_seconds: int = 60) -> Optional[Alert]:
        """Checks if a similar alert type was raised within debounce_seconds to prevent flooding."""
        try:
            debounce_threshold = datetime.utcnow() - timedelta(seconds=debounce_seconds)
            return self.db.query(Alert).filter(
                and_(
                    Alert.store_id == store_id,
                    Alert.alert_type == alert_type,
                    Alert.timestamp >= debounce_threshold
                )
            ).order_by(desc(Alert.timestamp)).first()
        except Exception as e:
            logger.error(f"Error checking alert debouncing: {e}")
            return None

    def persist_alert(self, store_id: str, alert_type: str, severity: str, message: str) -> Alert:
        """Persists a generated operational alert to the database."""
        try:
            alert = Alert(
                store_id=store_id,
                alert_type=alert_type,
                severity=severity,
                message=message,
                timestamp=datetime.utcnow()
            )
            self.db.add(alert)
            self.db.commit()
            self.db.refresh(alert)
            logger.warning(f"Alert persisted [{severity}]: {message}")
            return alert
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error persisting alert: {e}")
            raise

    def detect_queue_congestion(self, store_id: str, threshold: int = 5, debounce_seconds: int = 60) -> Optional[Alert]:
        """Checks checkout waiting queue congestion (threshold unique tracks in last 2 mins)."""
        try:
            t_threshold = datetime.utcnow() - timedelta(minutes=2)
            queue_occupants = self.db.query(DwellLog.track_id).filter(
                and_(
                    DwellLog.store_id == store_id,
                    DwellLog.zone_id == "checkout_queue",
                    DwellLog.entered_at >= t_threshold
                )
            ).distinct().count()

            if queue_occupants >= threshold:
                recent_alert = self.is_debounced(store_id, "crowding", debounce_seconds)
                if not recent_alert:
                    msg = f"Critical congestion alert inside checkout waiting queue! Current occupant count: {queue_occupants}"
                    return self.persist_alert(store_id, "crowding", "HIGH", msg)
                return recent_alert
            return None
        except Exception as e:
            logger.error(f"Error detecting queue congestion: {e}")
            return None

    def detect_overcrowding(self, store_id: str, threshold: int = 15, debounce_seconds: int = 60) -> Optional[Alert]:
        """Triggers a warning if store-wide current active visitor occupancy exceeds limits."""
        try:
            current_occupancy = self.db.query(StoreSession.track_id).filter(
                and_(
                    StoreSession.store_id == store_id,
                    StoreSession.exited_at.is_(None)
                )
            ).distinct().count()

            if current_occupancy >= threshold:
                recent_alert = self.is_debounced(store_id, "overcrowding", debounce_seconds)
                if not recent_alert:
                    msg = f"Store occupancy warning! High crowd density detected. Current count: {current_occupancy}"
                    return self.persist_alert(store_id, "overcrowding", "MEDIUM", msg)
                return recent_alert
            return None
        except Exception as e:
            logger.error(f"Error detecting overcrowding: {e}")
            return None

    def detect_loitering(self, store_id: str, threshold_seconds: float = 300.0, debounce_seconds: int = 60) -> Optional[Alert]:
        """Flags long dwell times (e.g. loitering > 5 mins) in aisle or layout promo zones."""
        try:
            loiter_record = self.db.query(DwellLog).filter(
                and_(
                    DwellLog.store_id == store_id,
                    DwellLog.duration_seconds >= threshold_seconds,
                    DwellLog.entered_at >= datetime.utcnow() - timedelta(minutes=5)
                )
            ).order_by(desc(DwellLog.duration_seconds)).first()

            if loiter_record:
                recent_alert = self.is_debounced(store_id, "loitering", debounce_seconds)
                if not recent_alert:
                    msg = f"Shopper track #{loiter_record.track_id} flagged for loitering in zone '{loiter_record.zone_id}' ({loiter_record.duration_seconds:.1f}s)"
                    return self.persist_alert(store_id, "loitering", "LOW", msg)
                return recent_alert
            return None
        except Exception as e:
            logger.error(f"Error detecting loitering: {e}")
            return None

    def evaluate_alerts(self, store_id: str) -> Optional[Alert]:
        """Runs the queue congestion, overcrowding, and loitering evaluation scans, returning the primary alert."""
        # 1. Queue crowding is high-severity, scan it first
        queue_alert = self.detect_queue_congestion(store_id)
        if queue_alert:
            return queue_alert

        # 2. Overcrowding next
        crowd_alert = self.detect_overcrowding(store_id)
        if crowd_alert:
            return crowd_alert

        # 3. Loitering
        loiter_alert = self.detect_loitering(store_id)
        if loiter_alert:
            return loiter_alert

        return None

    def get_historical_alerts(self, store_id: str, limit: int = 20) -> List[Alert]:
        """Retrieves history of triggered system warnings, running a preemptive scan beforehand."""
        try:
            self.evaluate_alerts(store_id)
            return self.db.query(Alert).filter(
                Alert.store_id == store_id
            ).order_by(desc(Alert.timestamp)).limit(limit).all()
        except Exception as e:
            logger.error(f"Error querying historical alerts: {e}")
            return []

# Backward compatibility alias
AlertEngine = AlertService
