from datetime import datetime, timezone
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.services.metrics import MetricsService
from backend.services.funnel import FunnelService
from backend.services.spatial_analytics import SpatialAnalyticsService
from backend.services.sales_analytics import SalesAnalyticsService
from backend.services.alerts import AlertService
from backend.models import StoreSession, DwellLog, StoreLayoutZone

router = APIRouter(prefix="/analytics", tags=["Legacy Store Business Intelligence"])

def get_datetime_bounds(start_date: Optional[str], end_date: Optional[str]):
    from datetime import timedelta
    now = datetime.utcnow()
    if start_date:
        start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00")).replace(tzinfo=None)
    else:
        start_dt = now - timedelta(hours=24)
    if end_date:
        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00")).replace(tzinfo=None)
    else:
        end_dt = now
    return start_dt, end_dt

@router.get("/metrics")
def get_store_metrics_legacy(
    store_id: str = Query(..., description="Store UUID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    start_dt, end_dt = get_datetime_bounds(start_date, end_date)
    service = MetricsService(db)
    
    total_visitors = service.get_total_visitors(store_id, start_dt, end_dt)
    current_occupancy = service.get_current_occupancy(store_id)
    average_dwell = service.get_average_dwell_time(store_id, start_dt, end_dt)
    peak_hour = service.get_peak_hour(store_id, start_dt, end_dt)
    conversion_rate = service.get_conversion_rate(store_id, start_dt, end_dt)

    return {
        "total_visitors": total_visitors,
        "current_occupancy": current_occupancy,
        "average_dwell_time": average_dwell,
        "peak_hour": peak_hour,
        "conversion_rate": conversion_rate
    }

@router.get("/funnel")
def get_conversion_funnel_legacy(
    store_id: str = Query(..., description="Store UUID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    start_dt, end_dt = get_datetime_bounds(start_date, end_date)
    service = FunnelService(db)
    return service.get_conversion_funnel(store_id, start_dt, end_dt)

@router.get("/occupancy")
def get_store_occupancy_legacy(
    store_id: str = Query(..., description="Store UUID"),
    db: Session = Depends(get_db)
):
    service = MetricsService(db)
    current = service.get_current_occupancy(store_id)
    total_sessions_count = db.query(StoreSession).filter(StoreSession.store_id == store_id).count()
    maximum = max(20, total_sessions_count)
    average = max(5, int(total_sessions_count / 2))

    return {
        "current": current,
        "maximum": maximum,
        "average": average
    }

@router.get("/zones")
def get_zone_analytics_legacy(
    store_id: str = Query(..., description="Store UUID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    start_dt, end_dt = get_datetime_bounds(start_date, end_date)
    metrics_service = MetricsService(db)
    spatial_service = SpatialAnalyticsService(db)
    
    most_visited, least_visited = metrics_service.get_most_least_visited_zones(store_id, start_dt, end_dt)
    zone_stats = spatial_service.zone_analytics(store_id, start_dt, end_dt)

    return {
        "most_visited_zone": most_visited or "N/A",
        "least_visited_zone": least_visited or "N/A",
        "zone_statistics": zone_stats
    }

@router.get("/heatmap")
def get_heatmap_density_legacy(
    store_id: str = Query(..., description="Store UUID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    start_dt, end_dt = get_datetime_bounds(start_date, end_date)
    spatial_service = SpatialAnalyticsService(db)
    stats = spatial_service.zone_analytics(store_id, start_dt, end_dt)
    
    zone_densities = {}
    max_visits = max([z["visit_count"] for z in stats], default=1)
    for z in stats:
        density = round((z["visit_count"] / max_visits) * 100.0, 1)
        zone_densities[z["zone_id"]] = density

    spatial_points = []
    for z in stats:
        visits = z["visit_count"]
        center_x, center_y = 100, 100
        if "fresh" in z["zone_id"]:
            center_x, center_y = 275, 250
        elif "snacks" in z["zone_id"]:
            center_x, center_y = 675, 275
        elif "checkout" in z["zone_id"]:
            center_x, center_y = 1050, 350
            
        import random
        random.seed(42)
        for _ in range(min(15, visits)):
            dx = random.randint(-40, 40)
            dy = random.randint(-40, 40)
            spatial_points.append({
                "x": float(center_x + dx),
                "y": float(center_y + dy),
                "intensity": float(round(random.random(), 2))
            })

    return {
        "zone_density": zone_densities,
        "coordinates": spatial_points
    }

@router.get("/sales")
def get_sales_analytics_legacy(
    store_id: str = Query(..., description="Store UUID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    start_dt, end_dt = get_datetime_bounds(start_date, end_date)
    service = MetricsService(db)
    return service.get_sales_analytics(store_id, start_dt, end_dt)

@router.get("/alerts")
def get_crowd_alerts_legacy(
    store_id: str = Query(..., description="Store UUID"),
    db: Session = Depends(get_db)
):
    service = AlertService(db)
    alerts = service.get_historical_alerts(store_id, limit=1)
    
    if alerts:
        latest = alerts[0]
        return {
            "alert_type": latest.alert_type,
            "severity": latest.severity.lower(),
            "timestamp": latest.timestamp.isoformat(),
            "message": latest.message
        }
        
    return {
        "alert_type": "operational_normal",
        "severity": "low",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "All store layout zones are flowing smoothly."
    }
