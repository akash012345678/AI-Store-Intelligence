import uuid
import logging
from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, abs

from backend.src.models import (
    Store,
    StoreLayoutZone,
    StoreSession,
    DwellLog,
    POSTransaction,
    TransactionItem,
    SpatialCorrelationLog
)
from backend.src.schemas import (
    EntryTelemetry,
    ExitTelemetry,
    DwellTelemetry,
    POSTransactionPayload
)

logger = logging.getLogger("PurpleInsight.IngestService")
logger.setLevel(logging.INFO)

class IngestService:
    """Manages telemetry and transactional persistence, applying state deduplication and transaction-track correlation."""
    
    def __init__(self, db: Session, 
                 checkout_queue_zone_id: str = "checkout_queue",
                 checkout_window_before_seconds: int = 600,
                 checkout_window_after_seconds: int = 120):
        self.db = db
        self.checkout_queue_zone_id = checkout_queue_zone_id
        self.checkout_window_before_seconds = checkout_window_before_seconds
        self.checkout_window_after_seconds = checkout_window_after_seconds

    def handle_entry(self, entry: EntryTelemetry) -> StoreSession:
        """Processes a shopper entry event, creating a session and preventing double-counting."""
        # Parse ISO datetime
        entry_dt = datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))

        # Deduplication check: Is there already an active open session for this track in this store?
        existing_session = self.db.query(StoreSession).filter(
            and_(
                StoreSession.store_id == entry.store_id,
                StoreSession.track_id == entry.track_id,
                StoreSession.exited_at.is_(None)
            )
        ).first()

        if existing_session:
            logger.warning(f"Duplicate entry telemetry received for active track {entry.track_id} in store {entry.store_id}. Ignoring duplicate.")
            return existing_session

        # Create new customer session
        session = StoreSession(
            store_id=entry.store_id,
            track_id=entry.track_id,
            entered_at=entry_dt,
            exited_at=None,
            re_entry=entry.re_entry_detected,
            correlated_previous_track_id=entry.correlated_previous_track_id
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        
        logger.info(f"Initialized StoreSession #{session.id} for track {entry.track_id} (Re-entry: {entry.re_entry_detected})")
        return session

    def handle_exit(self, exit_telemetry: ExitTelemetry) -> Optional[StoreSession]:
        """Processes a shopper exit event, closing out their active session."""
        exit_dt = datetime.fromisoformat(exit_telemetry.timestamp.replace("Z", "+00:00"))

        # Find the active open session
        session = self.db.query(StoreSession).filter(
            and_(
                StoreSession.store_id == exit_telemetry.store_id,
                StoreSession.track_id == exit_telemetry.track_id,
                StoreSession.exited_at.is_(None)
            )
        ).order_by(StoreSession.entered_at.desc()).first()

        if not session:
            # Edge case: Exit received without entry. We log warning and create closed backfilled session.
            logger.warning(f"Exit telemetry received for track {exit_telemetry.track_id} with no open session. Creating backfilled session.")
            session = StoreSession(
                store_id=exit_telemetry.store_id,
                track_id=exit_telemetry.track_id,
                entered_at=exit_dt, # Fallback
                exited_at=exit_dt
            )
            self.db.add(session)
        else:
            session.exited_at = exit_dt

        self.db.commit()
        self.db.refresh(session)
        logger.info(f"Closed StoreSession #{session.id} for track {exit_telemetry.track_id} on exit.")
        return session

    def handle_dwell(self, dwell: DwellTelemetry) -> DwellLog:
        """Processes a layout zone dwell event and persists it."""
        entry_dt = datetime.fromisoformat(dwell.entered_at.replace("Z", "+00:00"))
        exit_dt = datetime.fromisoformat(dwell.exited_at.replace("Z", "+00:00"))

        # Verify layout zone exists to ensure referential integrity
        zone = self.db.query(StoreLayoutZone).filter(StoreLayoutZone.id == dwell.zone_id).first()
        if not zone:
            # Auto-provision zone if missing (edge resilience)
            logger.info(f"Zone '{dwell.zone_id}' not found in store layout. Auto-provisioning zone.")
            zone = StoreLayoutZone(
                id=dwell.zone_id,
                store_id=dwell.store_id,
                name=dwell.zone_id.replace("_", " ").title(),
                zone_type="aisle" if "checkout" not in dwell.zone_id else "checkout"
            )
            self.db.add(zone)
            self.db.commit()

        dwell_log = DwellLog(
            store_id=dwell.store_id,
            zone_id=dwell.zone_id,
            track_id=dwell.track_id,
            entered_at=entry_dt,
            exited_at=exit_dt,
            duration_seconds=dwell.dwell_time_seconds
        )
        self.db.add(dwell_log)
        self.db.commit()
        self.db.refresh(dwell_log)
        
        logger.info(f"Persisted DwellLog #{dwell_log.id} for track {dwell.track_id} in zone '{dwell.zone_id}' ({dwell.dwell_time_seconds}s)")
        return dwell_log

    def handle_transaction(self, payload: POSTransactionPayload, store_id: str) -> Tuple[POSTransaction, Optional[SpatialCorrelationLog]]:
        """Registers a POS transaction and executes the spatial-temporal track correlation matcher."""
        txn_dt = datetime.fromisoformat(payload.transaction_time.replace("Z", "+00:00"))
        txn_uuid = str(uuid.uuid4())

        # 1. Persist POS transaction
        transaction = POSTransaction(
            id=txn_uuid,
            store_id=store_id,
            receipt_number=payload.receipt_number,
            total_amount=payload.total_amount,
            tax_amount=payload.tax_amount,
            transaction_time=txn_dt,
            payment_method=payload.payment_method
        )
        self.db.add(transaction)

        # 2. Persist receipt items
        for item in payload.items:
            item_obj = TransactionItem(
                id=str(uuid.uuid4()),
                transaction_id=txn_uuid,
                sku=item.sku,
                product_name=item.product_name,
                category=item.category,
                brand=item.brand,
                quantity=item.quantity,
                unit_price=item.unit_price
            )
            self.db.add(item_obj)

        self.db.commit()
        logger.info(f"Persisted POSTransaction receipt {payload.receipt_number} with {len(payload.items)} items.")

        # 3. Spatial-Temporal Correlation Matcher
        correlation = self._correlate_transaction_to_shopper(transaction, txn_dt)
        return transaction, correlation

    def _correlate_transaction_to_shopper(self, txn: POSTransaction, txn_time: datetime) -> Optional[SpatialCorrelationLog]:
        """Correlates a POS transaction to the nearest shopper track who exited in the temporal checkout window."""
        # Calculate window timestamps
        from datetime import timedelta
        t_start = txn_time - timedelta(seconds=self.checkout_window_before_seconds)
        t_end = txn_time + timedelta(seconds=self.checkout_window_after_seconds)

        # Query candidates: shoppers who exited inside the store exit window
        candidates = self.db.query(StoreSession).filter(
            and_(
                StoreSession.store_id == txn.store_id,
                StoreSession.exited_at >= t_start,
                StoreSession.exited_at <= t_end
            )
        ).all()

        if not candidates:
            logger.warning(f"No shopper exit candidates found in matching window for transaction {txn.receipt_number}.")
            return None

        # Filter candidates who dwelled in the checkout queue zone to guarantee conversion accuracy
        valid_candidates: List[Tuple[StoreSession, float]] = []
        
        for session in candidates:
            # Query if this track has a dwell log inside the checkout queue zone prior to exit
            checkout_dwell = self.db.query(DwellLog).filter(
                and_(
                    DwellLog.store_id == txn.store_id,
                    DwellLog.track_id == session.track_id,
                    DwellLog.zone_id == self.checkout_queue_zone_id,
                    DwellLog.entered_at <= session.exited_at
                )
            ).first()

            if checkout_dwell:
                # Calculate absolute time delta (in seconds) between exit and transaction timestamp
                time_delta = abs((session.exited_at - txn_time).total_seconds())
                valid_candidates.append((session, time_delta))

        if not valid_candidates:
            # Fallback: If no candidate dwelled in checkout queue (e.g. they skipped or zone is unconfigured),
            # we correlate with the absolute nearest exit candidate in store.
            logger.info("No candidates dwelled in checkout queue zone. Falling back to nearest store exit candidate.")
            for session in candidates:
                time_delta = abs((session.exited_at - txn_time).total_seconds())
                valid_candidates.append((session, time_delta))

        # Sort by smallest time delta (Nearest temporal match)
        valid_candidates.sort(key=lambda x: x[1])
        best_session, min_delta = valid_candidates[0]

        # Verify that this customer track ID is not already correlated to a nearby transaction
        # to prevent double correlation of a single shopper to multiple adjacent receipts.
        already_correlated = self.db.query(SpatialCorrelationLog).filter(
            and_(
                SpatialCorrelationLog.store_id == txn.store_id,
                SpatialCorrelationLog.track_id == best_session.track_id,
                SpatialCorrelationLog.correlated_at >= txn_time - timedelta(seconds=60)
            )
        ).first()

        if already_correlated:
            logger.warning(f"Best matched track {best_session.track_id} is already correlated to another recent transaction. Skipping to prevent double counting.")
            if len(valid_candidates) > 1:
                best_session, min_delta = valid_candidates[1]
            else:
                return None

        # Compute confidence: 1.0 at 0s difference, decaying down as delta increases
        confidence = max(0.1, round(1.0 - (min_delta / self.checkout_window_before_seconds), 2))

        # Persist correlation record
        correlation = SpatialCorrelationLog(
            store_id=txn.store_id,
            transaction_id=txn.id,
            track_id=best_session.track_id,
            correlation_confidence=confidence,
            correlated_at=datetime.utcnow()
        )
        self.db.add(correlation)
        self.db.commit()
        self.db.refresh(correlation)

        logger.info(f"Successfully correlated transaction {txn.receipt_number} to Track #{best_session.track_id} (Delta: {min_delta:.1f}s, Confidence: {confidence:.2f})")
        return correlation
