import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from backend.src.models import (
    StoreSession,
    DwellLog,
    SpatialCorrelationLog,
    POSTransaction,
    TransactionItem
)

logger = logging.getLogger("PurpleInsight.MetricsEngine")
logger.setLevel(logging.INFO)

class MetricsEngine:
    """Computes operational and business-intelligence retail metrics from telemetry and POS correlations."""
    
    def __init__(self, db: Session):
        self.db = db

    def get_total_visitors(self, store_id: str, start_time: datetime, end_time: datetime) -> int:
        """Calculates total unique visitors entering the store, using stitched tracks to prevent double-counting."""
        return self.db.query(StoreSession.track_id).filter(
            and_(
                StoreSession.store_id == store_id,
                StoreSession.entered_at >= start_time,
                StoreSession.entered_at <= end_time
            )
        ).distinct().count()

    def get_current_occupancy(self, store_id: str) -> int:
        """Returns the instantaneous store occupancy count (active open sessions)."""
        return self.db.query(StoreSession.track_id).filter(
            and_(
                StoreSession.store_id == store_id,
                StoreSession.exited_at.is_(None)
            )
        ).distinct().count()

    def get_visitor_sessions(self, store_id: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Lists visitor sessions including entrance, exit, and calculated stay duration."""
        sessions = self.db.query(StoreSession).filter(
            and_(
                StoreSession.store_id == store_id,
                StoreSession.entered_at >= start_time,
                StoreSession.entered_at <= end_time
            )
        ).order_by(StoreSession.entered_at.asc()).all()

        output = []
        for s in sessions:
            duration = None
            if s.exited_at:
                duration = round((s.exited_at - s.entered_at).total_seconds(), 1)
            output.append({
                "session_id": s.id,
                "track_id": s.track_id,
                "entered_at": s.entered_at.isoformat(),
                "exited_at": s.exited_at.isoformat() if s.exited_at else None,
                "duration_seconds": duration,
                "re_entry": s.re_entry,
                "correlated_previous_track_id": s.correlated_previous_track_id
            })
        return output

    def get_re_entry_count(self, store_id: str, start_time: datetime, end_time: datetime) -> int:
        """Returns the total number of re-entries recorded."""
        return self.db.query(StoreSession).filter(
            and_(
                StoreSession.store_id == store_id,
                StoreSession.re_entry == True,
                StoreSession.entered_at >= start_time,
                StoreSession.entered_at <= end_time
            )
        ).count()

    def get_average_dwell_time(self, store_id: str, start_time: datetime, end_time: datetime) -> float:
        """Calculates the average shopper presence duration in seconds inside the store."""
        sessions = self.db.query(StoreSession).filter(
            and_(
                StoreSession.store_id == store_id,
                StoreSession.entered_at >= start_time,
                StoreSession.entered_at <= end_time,
                StoreSession.exited_at.isnot(None)
            )
        ).all()

        if not sessions:
            return 0.0

        durations = [(s.exited_at - s.entered_at).total_seconds() for s in sessions]
        return round(sum(durations) / len(durations), 2)

    def get_peak_hour(self, store_id: str, start_time: datetime, end_time: datetime) -> Optional[int]:
        """Identifies the peak hour of store ingress traffic, returning the 24-hour index (0-23)."""
        sessions = self.db.query(StoreSession.entered_at).filter(
            and_(
                StoreSession.store_id == store_id,
                StoreSession.entered_at >= start_time,
                StoreSession.entered_at <= end_time
            )
        ).all()

        if not sessions:
            return None

        # Count frequencies of entry hours
        hours = [s.entered_at.hour for s in sessions]
        from collections import Counter
        return Counter(hours).most_common(1)[0][0]

    def get_most_least_visited_zones(self, store_id: str, start_time: datetime, end_time: datetime) -> Tuple[Optional[str], Optional[str]]:
        """Identifies the zone_id with the highest and lowest unique visitor counts.
        
        Returns:
            Tuple[most_visited_zone_id, least_visited_zone_id]
        """
        results = self.db.query(
            DwellLog.zone_id,
            func.count(func.distinct(DwellLog.track_id)).label("unique_visitors")
        ).filter(
            and_(
                DwellLog.store_id == store_id,
                DwellLog.entered_at >= start_time,
                DwellLog.entered_at <= end_time
            )
        ).group_by(DwellLog.zone_id).order_by(func.count(func.distinct(DwellLog.track_id)).desc()).all()

        if not results:
            return None, None

        most_visited = results[0][0]
        least_visited = results[-1][0]
        return most_visited, least_visited

    def get_zone_engagement(self, store_id: str, start_time: datetime, end_time: datetime) -> Dict[str, Dict]:
        """Computes engagement parameters (dwell volume, distinct traffic, averages) across all zones."""
        results = self.db.query(
            DwellLog.zone_id,
            func.count(DwellLog.id).label("visit_count"),
            func.count(func.distinct(DwellLog.track_id)).label("unique_visitors"),
            func.avg(DwellLog.duration_seconds).label("avg_duration")
        ).filter(
            and_(
                DwellLog.store_id == store_id,
                DwellLog.entered_at >= start_time,
                DwellLog.entered_at <= end_time
            )
        ).group_by(DwellLog.zone_id).all()

        engagement = {}
        for r in results:
            engagement[r.zone_id] = {
                "visit_count": r.visit_count,
                "unique_visitors": r.unique_visitors,
                "avg_dwell_seconds": round(r.avg_duration, 2)
            }
        return engagement

    def get_visitor_to_buyer_conversion(self, store_id: str, start_time: datetime, end_time: datetime) -> float:
        """Computes store-wide shopper-to-buyer conversion percentage."""
        total_visitors = self.get_total_visitors(store_id, start_time, end_time)
        if total_visitors == 0:
            return 0.0

        # Unique shopper track IDs correlated to purchase receipts
        buyers = self.db.query(SpatialCorrelationLog.track_id).filter(
            and_(
                SpatialCorrelationLog.store_id == store_id,
                SpatialCorrelationLog.correlated_at >= start_time,
                SpatialCorrelationLog.correlated_at <= end_time
            )
        ).distinct().count()

        return round((buyers / total_visitors) * 100, 2)

    def get_category_conversion(self, store_id: str, zone_id: str, category_name: str, 
                                 start_time: datetime, end_time: datetime) -> float:
        """Computes category conversion rate: shoppers entering [zone_id] who purchased items of [category_name]."""
        # Step 1: Find unique tracks that dwelled in the specified layout zone
        zone_track_ids = [r[0] for r in self.db.query(DwellLog.track_id).filter(
            and_(
                DwellLog.store_id == store_id,
                DwellLog.zone_id == zone_id,
                DwellLog.entered_at >= start_time,
                DwellLog.entered_at <= end_time
            )
        ).distinct().all()]

        if not zone_track_ids:
            logger.info(f"No unique visitors recorded inside zone '{zone_id}' during window.")
            return 0.0

        # Step 2: Find distinct track IDs in that set associated with POS transactions purchasing the target category
        converted_tracks = self.db.query(SpatialCorrelationLog.track_id).join(
            POSTransaction, SpatialCorrelationLog.transaction_id == POSTransaction.id
        ).join(
            TransactionItem, TransactionItem.transaction_id == POSTransaction.id
        ).filter(
            and_(
                SpatialCorrelationLog.store_id == store_id,
                SpatialCorrelationLog.track_id.in_(zone_track_ids),
                TransactionItem.category == category_name,
                POSTransaction.transaction_time >= start_time,
                POSTransaction.transaction_time <= end_time
            )
        ).distinct().count()

        conversion = (converted_tracks / len(zone_track_ids)) * 100
        return round(conversion, 2)

    def get_brand_conversion(self, store_id: str, zone_id: str, brand_name: str, 
                             start_time: datetime, end_time: datetime) -> float:
        """Computes brand conversion rate: shoppers entering [zone_id] who purchased items of [brand_name]."""
        # Step 1: Find unique tracks that dwelled in the specified layout zone
        zone_track_ids = [r[0] for r in self.db.query(DwellLog.track_id).filter(
            and_(
                DwellLog.store_id == store_id,
                DwellLog.zone_id == zone_id,
                DwellLog.entered_at >= start_time,
                DwellLog.entered_at <= end_time
            )
        ).distinct().all()]

        if not zone_track_ids:
            logger.info(f"No unique visitors recorded inside zone '{zone_id}' during window.")
            return 0.0

        # Step 2: Find distinct track IDs in that set associated with POS transactions purchasing the target brand
        converted_tracks = self.db.query(SpatialCorrelationLog.track_id).join(
            POSTransaction, SpatialCorrelationLog.transaction_id == POSTransaction.id
        ).join(
            TransactionItem, TransactionItem.transaction_id == POSTransaction.id
        ).filter(
            and_(
                SpatialCorrelationLog.store_id == store_id,
                SpatialCorrelationLog.track_id.in_(zone_track_ids),
                TransactionItem.brand == brand_name,
                POSTransaction.transaction_time >= start_time,
                POSTransaction.transaction_time <= end_time
            )
        ).distinct().count()

        conversion = (converted_tracks / len(zone_track_ids)) * 100
        return round(conversion, 2)
