import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from backend.models import (
    StoreSession,
    DwellLog,
    SpatialCorrelationLog,
    POSTransaction,
    TransactionItem,
    StoreLayoutZone
)

logger = logging.getLogger("PurpleInsight.MetricsService")
logger.setLevel(logging.INFO)

class MetricsService:
    """Computes store occupancy, visitor conversion rates, dwell times, and traffic patterns."""

    def __init__(self, db: Session):
        self.db = db

    def get_total_visitors(self, store_id: str, start_time: datetime, end_time: datetime) -> int:
        """Calculates total unique visitors entering the store, using stitched tracks to prevent double-counting."""
        try:
            return self.db.query(StoreSession.track_id).filter(
                and_(
                    StoreSession.store_id == store_id,
                    StoreSession.entered_at >= start_time,
                    StoreSession.entered_at <= end_time
                )
            ).distinct().count()
        except Exception as e:
            logger.error(f"Error calculating total visitors: {e}")
            return 0

    def get_current_occupancy(self, store_id: str) -> int:
        """Returns the instantaneous store occupancy count (active open sessions)."""
        try:
            return self.db.query(StoreSession.track_id).filter(
                and_(
                    StoreSession.store_id == store_id,
                    StoreSession.exited_at.is_(None)
                )
            ).distinct().count()
        except Exception as e:
            logger.error(f"Error calculating current occupancy: {e}")
            return 0

    def get_visitor_sessions(self, store_id: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Lists visitor sessions including entrance, exit, and stay duration."""
        try:
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
        except Exception as e:
            logger.error(f"Error retrieving visitor sessions: {e}")
            return []

    def get_re_entry_count(self, store_id: str, start_time: datetime, end_time: datetime) -> int:
        """Returns the total number of re-entries recorded."""
        try:
            return self.db.query(StoreSession).filter(
                and_(
                    StoreSession.store_id == store_id,
                    StoreSession.re_entry == True,
                    StoreSession.entered_at >= start_time,
                    StoreSession.entered_at <= end_time
                )
            ).count()
        except Exception as e:
            logger.error(f"Error counting re-entries: {e}")
            return 0

    def get_average_dwell_time(self, store_id: str, start_time: datetime, end_time: datetime) -> float:
        """Calculates the average shopper stay duration in minutes (historically or currently active)."""
        try:
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

            durations_mins = [(s.exited_at - s.entered_at).total_seconds() / 60.0 for s in sessions]
            return round(sum(durations_mins) / len(durations_mins), 1)
        except Exception as e:
            logger.error(f"Error calculating average dwell time: {e}")
            return 0.0

    def get_peak_hour(self, store_id: str, start_time: datetime, end_time: datetime) -> str:
        """Identifies the peak hour of store ingress traffic, returning e.g. '18:00-19:00'."""
        try:
            sessions = self.db.query(StoreSession.entered_at).filter(
                and_(
                    StoreSession.store_id == store_id,
                    StoreSession.entered_at >= start_time,
                    StoreSession.entered_at <= end_time
                )
            ).all()

            if not sessions:
                return "N/A"

            hours = [s.entered_at.hour for s in sessions]
            from collections import Counter
            peak_hr = Counter(hours).most_common(1)[0][0]
            return f"{peak_hr:02d}:00-{(peak_hr+1):02d}:00"
        except Exception as e:
            logger.error(f"Error finding peak hour: {e}")
            return "N/A"

    def get_most_least_visited_zones(self, store_id: str, start_time: datetime, end_time: datetime) -> Tuple[Optional[str], Optional[str]]:
        """Identifies the zone_id with the highest and lowest unique visitor counts."""
        try:
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

            most_visited_id = results[0][0]
            least_visited_id = results[-1][0]

            mv_zone = self.db.query(StoreLayoutZone).filter(StoreLayoutZone.id == most_visited_id).first()
            lv_zone = self.db.query(StoreLayoutZone).filter(StoreLayoutZone.id == least_visited_id).first()

            return mv_zone.name if mv_zone else most_visited_id, lv_zone.name if lv_zone else least_visited_id
        except Exception as e:
            logger.error(f"Error calculating most/least visited zones: {e}")
            return None, None

    def get_zone_engagement(self, store_id: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Computes engagement parameters (dwell volume, traffic, averages) across all zones."""
        try:
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

            engagement_list = []
            for r in results:
                zone = self.db.query(StoreLayoutZone).filter(StoreLayoutZone.id == r.zone_id).first()
                name = zone.name if zone else r.zone_id
                engagement_list.append({
                    "zone_id": r.zone_id,
                    "name": name,
                    "visit_count": r.visit_count,
                    "unique_visitors": r.unique_visitors,
                    "avg_dwell_seconds": round(r.avg_duration, 1) if r.avg_duration else 0.0
                })
            return engagement_list
        except Exception as e:
            logger.error(f"Error fetching zone engagement: {e}")
            return []

    def get_conversion_rate(self, store_id: str, start_time: datetime, end_time: datetime) -> float:
        """Computes store-wide shopper-to-buyer conversion percentage."""
        try:
            total_visitors = self.get_total_visitors(store_id, start_time, end_time)
            if total_visitors == 0:
                return 0.0

            buyers = self.db.query(SpatialCorrelationLog.track_id).filter(
                and_(
                    SpatialCorrelationLog.store_id == store_id,
                    SpatialCorrelationLog.correlated_at >= start_time,
                    SpatialCorrelationLog.correlated_at <= end_time
                )
            ).distinct().count()

            return round((buyers / total_visitors) * 100, 1)
        except Exception as e:
            logger.error(f"Error calculating conversion rate: {e}")
            return 0.0

    def get_visitor_to_buyer_conversion(self, store_id: str, start_time: datetime, end_time: datetime) -> float:
        """Legacy alias for get_conversion_rate."""
        return self.get_conversion_rate(store_id, start_time, end_time)

    def get_sales_analytics(self, store_id: str, start_time: datetime, end_time: datetime) -> Dict[str, List]:
        """Calculates top products, brands, and categories by volume and revenue."""
        try:
            products = self.db.query(
                TransactionItem.product_name.label("name"),
                func.sum(TransactionItem.quantity).label("volume"),
                func.sum(TransactionItem.quantity * TransactionItem.unit_price).label("revenue")
            ).join(POSTransaction).filter(
                and_(
                    POSTransaction.store_id == store_id,
                    POSTransaction.transaction_time >= start_time,
                    POSTransaction.transaction_time <= end_time
                )
            ).group_by(TransactionItem.product_name).order_by(func.sum(TransactionItem.quantity * TransactionItem.unit_price).desc()).limit(5).all()

            brands = self.db.query(
                TransactionItem.brand.label("name"),
                func.sum(TransactionItem.quantity).label("volume"),
                func.sum(TransactionItem.quantity * TransactionItem.unit_price).label("revenue")
            ).join(POSTransaction).filter(
                and_(
                    POSTransaction.store_id == store_id,
                    POSTransaction.transaction_time >= start_time,
                    POSTransaction.transaction_time <= end_time
                )
            ).group_by(TransactionItem.brand).order_by(func.sum(TransactionItem.quantity * TransactionItem.unit_price).desc()).limit(5).all()

            categories = self.db.query(
                TransactionItem.category.label("name"),
                func.sum(TransactionItem.quantity).label("volume"),
                func.sum(TransactionItem.quantity * TransactionItem.unit_price).label("revenue")
            ).join(POSTransaction).filter(
                and_(
                    POSTransaction.store_id == store_id,
                    POSTransaction.transaction_time >= start_time,
                    POSTransaction.transaction_time <= end_time
                )
            ).group_by(TransactionItem.category).order_by(func.sum(TransactionItem.quantity * TransactionItem.unit_price).desc()).limit(5).all()

            return {
                "top_products": [{"name": p.name, "volume": int(p.volume), "revenue": round(p.revenue, 2)} for p in products],
                "top_brands": [{"name": b.name, "volume": int(b.volume), "revenue": round(b.revenue, 2)} for b in brands],
                "top_categories": [{"name": c.name, "volume": int(c.volume), "revenue": round(c.revenue, 2)} for c in categories]
            }
        except Exception as e:
            logger.error(f"Error calculating sales analytics: {e}")
            return {"top_products": [], "top_brands": [], "top_categories": []}

    def get_category_conversion(self, store_id: str, zone_id: str, category_name: str, start_time: datetime, end_time: datetime) -> float:
        """Calculates conversion percentage for a layout zone to a specific POS category."""
        try:
            visitors = self.db.query(DwellLog.track_id).filter(
                and_(
                    DwellLog.store_id == store_id,
                    DwellLog.zone_id == zone_id,
                    DwellLog.entered_at >= start_time,
                    DwellLog.entered_at <= end_time
                )
            ).distinct().all()
            
            visitor_ids = [v[0] for v in visitors]
            if not visitor_ids:
                return 0.0
                
            buyers = self.db.query(SpatialCorrelationLog.track_id).join(
                POSTransaction, SpatialCorrelationLog.transaction_id == POSTransaction.id
            ).join(
                TransactionItem, TransactionItem.transaction_id == POSTransaction.id
            ).filter(
                and_(
                    SpatialCorrelationLog.store_id == store_id,
                    SpatialCorrelationLog.track_id.in_(visitor_ids),
                    TransactionItem.category == category_name,
                    SpatialCorrelationLog.correlated_at >= start_time,
                    SpatialCorrelationLog.correlated_at <= end_time
                )
            ).distinct().count()
            
            return round((buyers / len(visitor_ids)) * 100, 1)
        except Exception as e:
            logger.error(f"Error calculating category conversion: {e}")
            return 0.0

# Backward compatibility alias
MetricsEngine = MetricsService
