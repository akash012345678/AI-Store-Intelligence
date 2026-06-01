import logging
from datetime import datetime
from typing import Dict
from sqlalchemy import and_
from sqlalchemy.orm import Session
from backend.models import DwellLog, SpatialCorrelationLog
from backend.services.metrics import MetricsService

logger = logging.getLogger("PurpleInsight.FunnelService")
logger.setLevel(logging.INFO)

class FunnelService:
    """Calculates the physical shopper path conversion funnel: Inbound -> Engaged -> Checkout -> Buyers."""

    def __init__(self, db: Session, checkout_queue_zone_id: str = "checkout_queue"):
        self.db = db
        self.metrics_service = MetricsService(db)
        self.checkout_queue_zone_id = checkout_queue_zone_id

    def get_visitors(self, store_id: str, start_time: datetime, end_time: datetime) -> int:
        """Returns total inbound unique visitors entering the store."""
        try:
            return self.metrics_service.get_total_visitors(store_id, start_time, end_time)
        except Exception as e:
            logger.error(f"Error calculating funnel visitors: {e}")
            return 0

    def get_engaged_visitors(self, store_id: str, start_time: datetime, end_time: datetime) -> int:
        """Returns unique tracks who dwelled in any layout zone for >= 15.0 seconds."""
        try:
            return self.db.query(DwellLog.track_id).filter(
                and_(
                    DwellLog.store_id == store_id,
                    DwellLog.entered_at >= start_time,
                    DwellLog.entered_at <= end_time,
                    DwellLog.duration_seconds >= 15.0
                )
            ).distinct().count()
        except Exception as e:
            logger.error(f"Error calculating funnel engaged visitors: {e}")
            return 0

    def get_checkout_visitors(self, store_id: str, start_time: datetime, end_time: datetime) -> int:
        """Returns unique tracks who visited the checkout queue zone."""
        try:
            return self.db.query(DwellLog.track_id).filter(
                and_(
                    DwellLog.store_id == store_id,
                    DwellLog.zone_id == self.checkout_queue_zone_id,
                    DwellLog.entered_at >= start_time,
                    DwellLog.entered_at <= end_time
                )
            ).distinct().count()
        except Exception as e:
            logger.error(f"Error calculating funnel checkout visitors: {e}")
            return 0

    def get_buyers(self, store_id: str, start_time: datetime, end_time: datetime) -> int:
        """Returns unique tracks who completed a correlated purchase transaction."""
        try:
            return self.db.query(SpatialCorrelationLog.track_id).filter(
                and_(
                    SpatialCorrelationLog.store_id == store_id,
                    SpatialCorrelationLog.correlated_at >= start_time,
                    SpatialCorrelationLog.correlated_at <= end_time
                )
            ).distinct().count()
        except Exception as e:
            logger.error(f"Error calculating funnel buyers: {e}")
            return 0

    def get_conversion_funnel(self, store_id: str, start_time: datetime, end_time: datetime) -> Dict:
        """Computes the full conversion funnel ratios."""
        try:
            visitors = self.get_visitors(store_id, start_time, end_time)
            engaged_visitors = self.get_engaged_visitors(store_id, start_time, end_time)
            checkout_visitors = self.get_checkout_visitors(store_id, start_time, end_time)
            buyers = self.get_buyers(store_id, start_time, end_time)

            conversion_rate = round((buyers / visitors) * 100, 1) if visitors > 0 else 0.0

            return {
                "visitors": visitors,
                "engaged_visitors": engaged_visitors,
                "checkout_visitors": checkout_visitors,
                "buyers": buyers,
                "conversion_rate": conversion_rate
            }
        except Exception as e:
            logger.error(f"Error calculating conversion funnel: {e}")
            return {
                "visitors": 0,
                "engaged_visitors": 0,
                "checkout_visitors": 0,
                "buyers": 0,
                "conversion_rate": 0.0
            }

    def get_funnel_analytics(self, store_id: str, start_time: datetime, end_time: datetime) -> Dict:
        """Legacy compatibility interface for old router integrations."""
        return self.get_conversion_funnel(store_id, start_time, end_time)

# Backward compatibility alias
FunnelAnalyticsService = FunnelService
