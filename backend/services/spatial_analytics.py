import math
import logging
import numpy as np
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from backend.models import DwellLog, StoreSession, StoreLayoutZone

logger = logging.getLogger("PurpleInsight.SpatialAnalyticsService")
logger.setLevel(logging.INFO)

# --- Linear Kalman Filter for Trajectory Path Smoothing ---

class TrajectoryKalmanFilter:
    """A linear Kalman Filter to smooth tracked shopper positions and minimize coordinate jitter."""
    def __init__(self, dt: float = 0.2, process_noise: float = 0.1, measurement_noise: float = 1.0):
        self.dt = dt
        self.x = np.zeros((4, 1))
        self.F = np.array([
            [1, 0, dt,  0],
            [0, 1,  0, dt],
            [0, 0,  1,  0],
            [0, 0,  0,  1]
        ])
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        self.P = np.eye(4) * 10.0
        self.Q = np.eye(4) * process_noise
        self.R = np.eye(2) * measurement_noise
        self.initialized = False

    def predict(self) -> None:
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q

    def update(self, measurement: Tuple[float, float]) -> Tuple[float, float]:
        z = np.array([[measurement[0]], [measurement[1]]])
        if not self.initialized:
            self.x = np.array([[z[0, 0]], [z[1, 0]], [0.0], [0.0]])
            self.initialized = True
            return measurement

        self.predict()
        y = z - np.dot(self.H, self.x)
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))
        self.x = self.x + np.dot(K, y)
        self.P = self.P - np.dot(np.dot(K, self.H), self.P)
        return (float(self.x[0, 0]), float(self.x[1, 0]))


# --- Planar Homography Coordinate Projection ---

class PlanarHomographyProjector:
    """Calibrates and projects 2D CCTV camera pixel coordinates to ground-truth store layout coordinates."""
    def __init__(self, homography_matrix: List[List[float]] = None):
        if homography_matrix is None:
            self.H = np.eye(3)
        else:
            self.H = np.array(homography_matrix)

    def project_point(self, u: float, v: float) -> Tuple[float, float]:
        pixel_vector = np.array([[u], [v], [1.0]])
        projected = np.dot(self.H, pixel_vector)
        w = projected[2, 0]
        if abs(w) < 1e-6:
            w = 1e-6
        x = projected[0, 0] / w
        y = projected[1, 0] / w
        return (float(x), float(y))


# --- Gaussian KDE Heatmap Density Engine ---

def generate_kde_heatmap_grid(coordinates: List[Tuple[float, float]], 
                               width: int = 1200, height: int = 600, 
                               grid_scale: int = 20, sigma: float = 30.0) -> List[List[float]]:
    """Calculates spatial density over a grid using Gaussian Kernel Density Estimation (KDE)."""
    grid_cols = width // grid_scale
    grid_rows = height // grid_scale
    grid = [[0.0 for _ in range(grid_cols)] for _ in range(grid_rows)]
    
    if not coordinates:
        return grid

    max_intensity = 0.0
    for r in range(grid_rows):
        cy = r * grid_scale + (grid_scale / 2.0)
        for c in range(grid_cols):
            cx = c * grid_scale + (grid_scale / 2.0)
            density = 0.0
            for px, py in coordinates:
                dist_sq = (cx - px)**2 + (cy - py)**2
                density += math.exp(-dist_sq / (2.0 * (sigma**2)))
                
            grid[r][c] = density
            if density > max_intensity:
                max_intensity = density

    if max_intensity > 0.0:
        for r in range(grid_rows):
            for c in range(grid_cols):
                grid[r][c] = round(grid[r][c] / max_intensity, 3)

    return grid


# --- Shelf Engagement Metrics Calculator ---

class ShelfEngagementCalculator:
    """Calculates operational physical layout engagement metrics (Attractiveness, Hold Power)."""
    
    @staticmethod
    def calculate_metrics(dwell_logs: List[Dict], total_store_sessions: int) -> List[Dict]:
        zone_durations = {}
        for log in dwell_logs:
            zid = log["zone_id"]
            name = log["name"]
            dur = log["duration_seconds"]
            
            if zid not in zone_durations:
                zone_durations[zid] = {"name": name, "stays": []}
            zone_durations[zid]["stays"].append(dur)

        output = []
        for zid, data in zone_durations.items():
            stays = data["stays"]
            attractive_stops = [s for s in stays if s >= 5.0]
            pass_by_estimate = max(len(stays) + int(total_store_sessions * 0.15), 1)
            attractiveness_index = round((len(attractive_stops) / pass_by_estimate) * 100.0, 2)
            hold_power = round(sum(attractive_stops) / len(attractive_stops), 1) if attractive_stops else 0.0
            
            output.append({
                "zone_id": zid,
                "name": data["name"],
                "total_stops": len(stays),
                "attractive_stops": len(attractive_stops),
                "attractiveness_index_pct": attractiveness_index,
                "hold_power_seconds": hold_power
            })
            
        output.sort(key=lambda x: x["attractiveness_index_pct"], reverse=True)
        return output


# --- Spatial Analytics Service Layer ---

class SpatialAnalyticsService:
    """Enterprise service conducting Homography, KDE path tracking, zone stay averages, and shelf conversions."""

    ZONE_COORDINATE_MAP = {
        "entrance": (100.0, 100.0),
        "exit": (1100.0, 100.0),
        "checkout_queue": (600.0, 500.0),
        "makeup_unit": (300.0, 300.0),
        "aisle_1_fresh": (200.0, 200.0),
        "aisle_2_snacks": (800.0, 400.0),
        "promo_bin_fresh": (400.0, 200.0),
        "product_shelves": (500.0, 350.0),
        "brand_zones": (700.0, 350.0)
    }

    def __init__(self, db: Session):
        self.db = db

    def shelf_engagement(self, store_id: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Computes Attractiveness and Hold Power metrics across layout shelves based on dwell limits."""
        try:
            dwells = self.db.query(DwellLog).filter(
                and_(
                    DwellLog.store_id == store_id,
                    DwellLog.entered_at >= start_time,
                    DwellLog.entered_at <= end_time
                )
            ).all()

            dwell_list = []
            for d in dwells:
                zone = self.db.query(StoreLayoutZone).filter(StoreLayoutZone.id == d.zone_id).first()
                name = zone.name if zone else d.zone_id
                dwell_list.append({
                    "zone_id": d.zone_id,
                    "name": name,
                    "duration_seconds": d.duration_seconds
                })

            total_sessions = self.db.query(StoreSession).filter(
                and_(
                    StoreSession.store_id == store_id,
                    StoreSession.entered_at >= start_time,
                    StoreSession.entered_at <= end_time
                )
            ).distinct().count()

            return ShelfEngagementCalculator.calculate_metrics(dwell_list, total_sessions)
        except Exception as e:
            logger.error(f"Error calculating shelf engagement: {e}")
            return []

    def heatmap_generation(self, store_id: str, start_time: datetime, end_time: datetime, width: int = 1200, height: int = 600) -> List[List[float]]:
        """Maps zone-dwell occurrences into continuous spatial coordinate values using KDE grid projections."""
        try:
            dwells = self.db.query(DwellLog.zone_id, DwellLog.track_id).filter(
                and_(
                    DwellLog.store_id == store_id,
                    DwellLog.entered_at >= start_time,
                    DwellLog.entered_at <= end_time
                )
            ).all()

            coordinates = []
            for d in dwells:
                # Resolve coordinates for zones, mapping to grid points
                coord = self.ZONE_COORDINATE_MAP.get(d.zone_id, (600.0, 300.0))
                coordinates.append(coord)

            return generate_kde_heatmap_grid(coordinates, width=width, height=height, grid_scale=20, sigma=30.0)
        except Exception as e:
            logger.error(f"Error generating heatmap grid: {e}")
            return [[0.0 for _ in range(width // 20)] for _ in range(height // 20)]

    def zone_analytics(self, store_id: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Compiles unique visitor volumes, dwell totals, and standard averages per store zone."""
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

            zones_data = []
            for r in results:
                zone = self.db.query(StoreLayoutZone).filter(StoreLayoutZone.id == r.zone_id).first()
                name = zone.name if zone else r.zone_id
                zones_data.append({
                    "zone_id": r.zone_id,
                    "name": name,
                    "visit_count": r.visit_count,
                    "unique_visitors": r.unique_visitors,
                    "avg_dwell_seconds": round(r.avg_duration, 1) if r.avg_duration else 0.0
                })
            return zones_data
        except Exception as e:
            logger.error(f"Error compiling zone analytics: {e}")
            return []

    def dwell_analysis(self, store_id: str, start_time: datetime, end_time: datetime) -> Dict:
        """Runs overall dwell analysis including stay distribution and average layout dwells."""
        try:
            dwells = self.db.query(DwellLog.duration_seconds).filter(
                and_(
                    DwellLog.store_id == store_id,
                    DwellLog.entered_at >= start_time,
                    DwellLog.entered_at <= end_time
                )
            ).all()

            if not dwells:
                return {"total_duration_seconds": 0.0, "average_dwell_seconds": 0.0, "stops_count": 0}

            durations = [d[0] for d in dwells]
            return {
                "total_duration_seconds": round(sum(durations), 1),
                "average_dwell_seconds": round(sum(durations) / len(durations), 1),
                "stops_count": len(durations)
            }
        except Exception as e:
            logger.error(f"Error executing dwell analysis: {e}")
            return {"total_duration_seconds": 0.0, "average_dwell_seconds": 0.0, "stops_count": 0}
