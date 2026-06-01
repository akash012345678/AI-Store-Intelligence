import logging
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case

from backend.models import (
    SalesProduct,
    SalesOrder,
    SalesOrderItem
)

logger = logging.getLogger("PurpleInsight.SalesAnalyticsService")
logger.setLevel(logging.INFO)

class SalesAnalyticsService:
    """Provides business-intelligence analytics over seeded retail sales order transactions."""
    
    def __init__(self, db: Session):
        self.db = db

    def get_brand_performance(self) -> List[Dict]:
        """Calculates revenue, volume sold, unique SKUs, and Private Label (PB) NMV shares per brand."""
        try:
            results = self.db.query(
                SalesProduct.brand_name,
                func.sum(SalesOrderItem.nmv).label("revenue"),
                func.sum(SalesOrderItem.qty).label("volume_sold"),
                func.avg(SalesOrderItem.coupon_amount + SalesOrderItem.item_promotion).label("avg_discount"),
                func.count(func.distinct(SalesProduct.sku)).label("unique_skus_sold"),
                func.sum(case((SalesProduct.brand_type == "PB", SalesOrderItem.nmv), else_=0.0)).label("pb_revenue")
            ).join(SalesOrderItem, SalesOrderItem.sku == SalesProduct.sku).group_by(SalesProduct.brand_name).all()

            output = []
            for r in results:
                total_rev = r.revenue or 0.0
                pb_rev = r.pb_revenue or 0.0
                split = round((pb_rev / total_rev) * 100.0, 2) if total_rev > 0 else 0.0
                
                output.append({
                    "brand_name": r.brand_name,
                    "revenue": round(total_rev, 2),
                    "volume_sold": int(r.volume_sold or 0),
                    "avg_discount": round(r.avg_discount or 0.0, 2),
                    "unique_skus_sold": int(r.unique_skus_sold or 0),
                    "private_label_revenue_split": split
                })
            
            output.sort(key=lambda x: x["revenue"], reverse=True)
            return output
        except Exception as e:
            logger.error(f"Error calculating brand performance: {e}")
            return []

    def get_category_performance(self) -> List[Dict]:
        """Calculates sales summaries, average tax rates, and peak hour of day per department."""
        try:
            categories = self.db.query(SalesProduct.department_name).distinct().all()
            categories = [c[0] for c in categories if c[0]]

            output = []
            for cat in categories:
                # Sales aggregates
                agg = self.db.query(
                    func.sum(SalesOrderItem.nmv).label("revenue"),
                    func.sum(SalesOrderItem.qty).label("volume_sold"),
                    func.avg(SalesOrderItem.tax_rate).label("avg_tax")
                ).join(SalesProduct, SalesProduct.sku == SalesOrderItem.sku).filter(
                    SalesProduct.department_name == cat
                ).first()

                # Find peak hour for this category
                peak_hour_res = self.db.query(
                    func.substr(SalesOrder.order_time, 1, 2).label("hour"),
                    func.count(func.distinct(SalesOrder.id)).label("orders_count")
                ).join(SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id).join(
                    SalesProduct, SalesProduct.sku == SalesOrderItem.sku
                ).filter(
                    SalesProduct.department_name == cat
                ).group_by(func.substr(SalesOrder.order_time, 1, 2)).order_by(
                    func.count(func.distinct(SalesOrder.id)).desc()
                ).first()

                peak_hr = f"{peak_hour_res[0]}:00" if peak_hour_res else "12:00"
                revenue = agg.revenue or 0.0

                output.append({
                    "category_name": cat,
                    "revenue": round(revenue, 2),
                    "volume_sold": int(agg.volume_sold or 0),
                    "avg_tax_rate": round(agg.avg_tax or 18.0, 1),
                    "peak_sales_hour": peak_hr
                })

            output.sort(key=lambda x: x["revenue"], reverse=True)
            return output
        except Exception as e:
            logger.error(f"Error calculating category performance: {e}")
            return []

    def get_product_performance(self) -> Dict[str, List]:
        """Identifies top products by revenue/volume and flags slow-moving product lines."""
        try:
            base_query = self.db.query(
                SalesProduct.sku,
                SalesProduct.product_name,
                SalesProduct.brand_name,
                func.sum(SalesOrderItem.nmv).label("revenue"),
                func.sum(SalesOrderItem.qty).label("quantity_sold")
            ).join(SalesOrderItem, SalesOrderItem.sku == SalesProduct.sku).group_by(
                SalesProduct.sku, SalesProduct.product_name, SalesProduct.brand_name
            )

            by_revenue = base_query.order_by(func.sum(SalesOrderItem.nmv).desc()).limit(10).all()
            by_volume = base_query.order_by(func.sum(SalesOrderItem.qty).desc()).limit(10).all()
            slowest = base_query.order_by(func.sum(SalesOrderItem.qty).asc()).limit(10).all()

            def format_results(items):
                return [{
                    "sku": i.sku,
                    "product_name": i.product_name,
                    "brand_name": i.brand_name,
                    "revenue": round(i.revenue or 0.0, 2),
                    "quantity_sold": int(i.quantity_sold or 0)
                } for i in items]

            return {
                "top_moving_by_revenue": format_results(by_revenue),
                "top_moving_by_volume": format_results(by_volume),
                "slowest_moving": format_results(slowest)
            }
        except Exception as e:
            logger.error(f"Error calculating product performance: {e}")
            return {"top_moving_by_revenue": [], "top_moving_by_volume": [], "slowest_moving": []}

    def get_revenue_analysis(self) -> Dict:
        """Computes aggregate margins, net market value, taxes collected, and hourly sales spreads."""
        try:
            aggregates = self.db.query(
                func.sum(SalesOrderItem.gmv).label("gmv"),
                func.sum(SalesOrderItem.nmv).label("nmv"),
                func.sum(SalesOrderItem.tax_amt).label("tax"),
                func.sum(SalesOrderItem.coupon_amount + SalesOrderItem.item_promotion).label("discounts")
            ).first()

            hourly_results = self.db.query(
                func.substr(SalesOrder.order_time, 1, 2).label("hour"),
                func.sum(SalesOrderItem.nmv).label("revenue")
            ).join(SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id).group_by(
                func.substr(SalesOrder.order_time, 1, 2)
            ).all()

            distribution = {}
            for h, rev in hourly_results:
                if h:
                    distribution[f"{h}:00"] = round(rev or 0.0, 2)

            return {
                "total_gmv": round(aggregates.gmv or 0.0, 2) if aggregates else 0.0,
                "total_nmv": round(aggregates.nmv or 0.0, 2) if aggregates else 0.0,
                "total_tax_collected": round(aggregates.tax or 0.0, 2) if aggregates else 0.0,
                "total_discounts": round(aggregates.discounts or 0.0, 2) if aggregates else 0.0,
                "hourly_sales_distribution": distribution
            }
        except Exception as e:
            logger.error(f"Error executing revenue analysis: {e}")
            return {"total_gmv": 0.0, "total_nmv": 0.0, "total_tax_collected": 0.0, "total_discounts": 0.0, "hourly_sales_distribution": {}}

    def get_conversion_analysis(self) -> Dict:
        """Analyzes promotional receipt ratios and private label shares."""
        try:
            total_txns = self.db.query(SalesOrder.id).count()
            if total_txns == 0:
                return {
                    "total_transactions": 0,
                    "promotional_transactions": 0,
                    "promotional_transaction_ratio": 0.0,
                    "private_label_orders_count": 0,
                    "private_label_revenue_ratio": 0.0
                }

            promo_txns = self.db.query(SalesOrder.id).filter(
                and_(
                    SalesOrder.coupon_code != "",
                    SalesOrder.coupon_code.isnot(None)
                ) | and_(
                    SalesOrder.offer_name != "",
                    SalesOrder.offer_name.isnot(None)
                )
            ).distinct().count()

            pb_orders = self.db.query(SalesOrder.id).join(
                SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id
            ).join(
                SalesProduct, SalesProduct.sku == SalesOrderItem.sku
            ).filter(
                SalesProduct.brand_type == "PB"
            ).distinct().count()

            total_nmv = self.db.query(func.sum(SalesOrderItem.nmv)).scalar() or 1.0
            pb_nmv = self.db.query(func.sum(SalesOrderItem.nmv)).join(
                SalesProduct, SalesProduct.sku == SalesOrderItem.sku
            ).filter(
                SalesProduct.brand_type == "PB"
            ).scalar() or 0.0

            return {
                "total_transactions": total_txns,
                "promotional_transactions": promo_txns,
                "promotional_transaction_ratio": round((promo_txns / total_txns) * 100.0, 2),
                "private_label_orders_count": pb_orders,
                "private_label_revenue_ratio": round((pb_nmv / total_nmv) * 100.0, 2)
            }
        except Exception as e:
            logger.error(f"Error calculating conversion analysis: {e}")
            return {"total_transactions": 0, "promotional_transactions": 0, "promotional_transaction_ratio": 0.0, "private_label_orders_count": 0, "private_label_revenue_ratio": 0.0}
