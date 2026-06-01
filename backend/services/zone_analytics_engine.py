"""
PurpleInsight Zone Analytics Engine
=====================================
Spatial zone intelligence for the Brigade Road Purplle store.

Integrates:
    - zone_config.json (25-zone Brigade Road layout)
    - StoreSession (visitor entry/exit tracking)
    - DwellLog (zone-level engagement records)
    - Planar homography coordinate projection
    - KDE heatmap grid generation
    - Shelf engagement metrics (Attractiveness, Hold Power)
    - Brand zone performance ranking
    - Checkout queue intelligence

Usage:
    engine = ZoneAnalyticsEngine(db_session, store_id="store-7ef38ab2-...")
    report = engine.full_report(start_time, end_time)
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from backend.models import DwellLog, StoreLayoutZone, StoreSession

logger = logging.getLogger("PurpleInsight.ZoneAnalyticsEngine")
logger.setLevel(logging.INFO)

# Default path to zone configuration
_DEFAULT_ZONE_CONFIG = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "edge", "config", "zone_config.json"
)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration Loader
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ZoneDefinition:
    """Strongly-typed representation of a single zone from zone_config.json."""
    zone_id: str
    zone_name: str
    zone_type: str
    zone_subtype: str
    polygon: List[Tuple[int, int]]
    centroid: Tuple[float, float]
    heatmap_weight: float
    engagement_type: str
    alert_capacity: Optional[int]
    brand: Optional[str] = None
    department: Optional[str] = None
    queue_alert_thresholds: Optional[Dict] = None
    notes: str = ""


@dataclass
class ZoneConfig:
    """Full parsed zone configuration for the Brigade Road store."""
    store_id: str
    store_name: str
    frame_width: int
    frame_height: int
    zones: List[ZoneDefinition] = field(default_factory=list)
    heatmap_config: Dict = field(default_factory=dict)
    shelf_engagement_config: Dict = field(default_factory=dict)
    coordinate_mapping: Dict = field(default_factory=dict)

    @property
    def zone_map(self) -> Dict[str, ZoneDefinition]:
        return {z.zone_id: z for z in self.zones}

    @property
    def shelf_zone_ids(self) -> Set[str]:
        return set(self.shelf_engagement_config.get("shelf_zones", []))

    @property
    def brand_zone_ids(self) -> Set[str]:
        return set(self.shelf_engagement_config.get("brand_zone_ids", []))

    @property
    def queue_zone_ids(self) -> Set[str]:
        return {z.zone_id for z in self.zones if z.zone_subtype == "queue_zone"}

    @property
    def checkout_zone_ids(self) -> Set[str]:
        return {z.zone_id for z in self.zones if z.zone_type == "checkout"}


def load_zone_config(config_path: str = None) -> ZoneConfig:
    """
    Parses zone_config.json into a strongly-typed ZoneConfig instance.

    Args:
        config_path: Absolute path to zone_config.json.
                     Defaults to edge/config/zone_config.json.
    """
    path = config_path or os.path.abspath(_DEFAULT_ZONE_CONFIG)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Zone config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    meta = raw.get("_meta", {})
    zones: List[ZoneDefinition] = []
    for z in raw.get("zones", []):
        zones.append(ZoneDefinition(
            zone_id=z["zone_id"],
            zone_name=z["zone_name"],
            zone_type=z["zone_type"],
            zone_subtype=z.get("zone_subtype", "generic"),
            polygon=[tuple(p) for p in z["polygon"]],
            centroid=tuple(z.get("centroid", [0, 0])),
            heatmap_weight=z.get("heatmap_weight", 1.0),
            engagement_type=z.get("engagement_type", "passage"),
            alert_capacity=z.get("alert_capacity"),
            brand=z.get("brand"),
            department=z.get("department"),
            queue_alert_thresholds=z.get("queue_alert_thresholds"),
            notes=z.get("notes", ""),
        ))

    return ZoneConfig(
        store_id=meta.get("store_id", ""),
        store_name=meta.get("store_name", ""),
        frame_width=meta.get("frame_width", 1280),
        frame_height=meta.get("frame_height", 720),
        zones=zones,
        heatmap_config=raw.get("heatmap_config", {}),
        shelf_engagement_config=raw.get("shelf_engagement_config", {}),
        coordinate_mapping=raw.get("coordinate_mapping", {}),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Geometry Utilities
# ─────────────────────────────────────────────────────────────────────────────

def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[int, int]]) -> bool:
    """Ray-casting algorithm: check if (x, y) lies inside a polygon."""
    x, y = point
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def polygon_centroid(polygon: List[Tuple[int, int]]) -> Tuple[float, float]:
    """Computes the geometric centroid of a convex polygon."""
    n = len(polygon)
    if n == 0:
        return (0.0, 0.0)
    cx = sum(p[0] for p in polygon) / n
    cy = sum(p[1] for p in polygon) / n
    return (cx, cy)


# ─────────────────────────────────────────────────────────────────────────────
# Coordinate Mapping (Homography Projection)
# ─────────────────────────────────────────────────────────────────────────────

class HomographyProjector:
    """
    Projects CCTV pixel coordinates (u, v) into store floor-plan
    millimetre coordinates using a calibrated 3×3 homography matrix.

    The matrix is sourced from coordinate_mapping.homography_matrix
    in zone_config.json and can be recalibrated using
    cv2.findHomography() with 4+ reference point pairs.
    """

    def __init__(self, homography_matrix: List[List[float]]):
        self.H = np.array(homography_matrix, dtype=np.float64)

    def pixel_to_floor(self, u: float, v: float) -> Tuple[float, float]:
        """
        Projects pixel (u, v) → floor (x_mm, y_mm).

        Returns:
            (x_mm, y_mm) floor plan coordinates.
        """
        vec = np.array([[u], [v], [1.0]])
        proj = self.H @ vec
        w = proj[2, 0]
        if abs(w) < 1e-9:
            w = 1e-9
        return (float(proj[0, 0] / w), float(proj[1, 0] / w))

    def floor_to_pixel(self, x_mm: float, y_mm: float) -> Tuple[float, float]:
        """
        Inverts projection: floor (x_mm, y_mm) → pixel (u, v).
        Uses the inverse homography matrix.
        """
        H_inv = np.linalg.inv(self.H)
        vec = np.array([[x_mm], [y_mm], [1.0]])
        proj = H_inv @ vec
        w = proj[2, 0]
        if abs(w) < 1e-9:
            w = 1e-9
        return (float(proj[0, 0] / w), float(proj[1, 0] / w))

    @classmethod
    def from_zone_config(cls, config: ZoneConfig) -> "HomographyProjector":
        """Builds a HomographyProjector directly from a loaded ZoneConfig."""
        matrix = config.coordinate_mapping.get("homography_matrix")
        if matrix is None:
            logger.warning("No homography_matrix in zone_config. Using identity.")
            matrix = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        return cls(matrix)


# ─────────────────────────────────────────────────────────────────────────────
# Heatmap Configuration & Generator
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HeatmapConfig:
    """Runtime heatmap generation parameters derived from zone_config.json."""
    frame_width: int = 1280
    frame_height: int = 720
    grid_scale_px: int = 20
    kde_sigma: float = 35.0
    normalization: str = "max_min"

    @property
    def grid_cols(self) -> int:
        return self.frame_width // self.grid_scale_px

    @property
    def grid_rows(self) -> int:
        return self.frame_height // self.grid_scale_px

    @classmethod
    def from_zone_config(cls, config: ZoneConfig) -> "HeatmapConfig":
        hc = config.heatmap_config
        return cls(
            frame_width=hc.get("frame_width", 1280),
            frame_height=hc.get("frame_height", 720),
            grid_scale_px=hc.get("grid_scale_px", 20),
            kde_sigma=hc.get("kde_sigma", 35.0),
            normalization=hc.get("normalization", "max_min"),
        )


def generate_weighted_heatmap(
    zone_dwell_counts: Dict[str, int],
    zone_map: Dict[str, ZoneDefinition],
    heatmap_cfg: HeatmapConfig,
) -> List[List[float]]:
    """
    Generates a normalised KDE heatmap grid from zone dwell observation counts.

    Each zone centroid is projected as a Gaussian kernel weighted by:
        - Number of dwell observations in that zone
        - Zone-level heatmap_weight from zone_config.json

    Args:
        zone_dwell_counts: {zone_id: total_dwell_events}
        zone_map:          Zone definitions keyed by zone_id
        heatmap_cfg:       Grid and sigma parameters

    Returns:
        2D list[row][col] of normalised intensities in [0.0, 1.0]
    """
    rows = heatmap_cfg.grid_rows
    cols = heatmap_cfg.grid_cols
    sigma = heatmap_cfg.kde_sigma
    scale = heatmap_cfg.grid_scale_px
    grid = [[0.0] * cols for _ in range(rows)]

    # Build weighted coordinate list from zone centroids
    coord_weights: List[Tuple[float, float, float]] = []
    for zone_id, count in zone_dwell_counts.items():
        zone = zone_map.get(zone_id)
        if zone is None or count == 0:
            continue
        cx, cy = zone.centroid
        weight = zone.heatmap_weight * count
        coord_weights.append((cx, cy, weight))

    if not coord_weights:
        return grid

    max_intensity = 0.0
    for r in range(rows):
        grid_cy = r * scale + scale / 2.0
        for c in range(cols):
            grid_cx = c * scale + scale / 2.0
            density = 0.0
            for px, py, w in coord_weights:
                dist_sq = (grid_cx - px) ** 2 + (grid_cy - py) ** 2
                density += w * math.exp(-dist_sq / (2.0 * sigma ** 2))
            grid[r][c] = density
            if density > max_intensity:
                max_intensity = density

    if max_intensity > 0.0:
        for r in range(rows):
            for c in range(cols):
                grid[r][c] = round(grid[r][c] / max_intensity, 4)

    return grid


# ─────────────────────────────────────────────────────────────────────────────
# Shelf Engagement Calculator
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ShelfEngagementResult:
    zone_id: str
    zone_name: str
    zone_type: str
    brand: Optional[str]
    department: Optional[str]
    total_visits: int
    attractive_stops: int           # dwell >= 5s
    engaged_stops: int              # dwell >= 15s
    deep_engage_stops: int          # dwell >= 45s
    attractiveness_index_pct: float  # % of pass-bys that stopped
    hold_power_seconds: float        # avg dwell of attracted visitors
    avg_dwell_seconds: float
    max_dwell_seconds: float


def compute_shelf_engagement(
    dwell_logs: List[Dict],
    zone_map: Dict[str, ZoneDefinition],
    total_store_sessions: int,
    cfg: Dict,
) -> List[ShelfEngagementResult]:
    """
    Computes attractiveness and hold-power metrics per shelf zone.

    Args:
        dwell_logs:           Raw dwell records [{"zone_id", "duration_seconds"}]
        zone_map:             Zone definitions
        total_store_sessions: Total unique shopper sessions in period
        cfg:                  shelf_engagement_config from ZoneConfig

    Returns:
        List of ShelfEngagementResult ordered by attractiveness_index_pct descending
    """
    min_attractive = cfg.get("minimum_dwell_seconds_attractive", 5.0)
    min_engaged = cfg.get("minimum_dwell_seconds_engaged", 15.0)
    min_deep = cfg.get("minimum_dwell_seconds_deep_engage", 45.0)
    pass_by_coeff = cfg.get("pass_by_coefficient", 0.15)

    # Group dwell durations by zone
    zone_data: Dict[str, List[float]] = {}
    for log in dwell_logs:
        zid = log["zone_id"]
        if zid not in zone_data:
            zone_data[zid] = []
        zone_data[zid].append(log["duration_seconds"])

    results = []
    for zid, durations in zone_data.items():
        zone = zone_map.get(zid)
        if zone is None:
            continue

        n = len(durations)
        attractive = [d for d in durations if d >= min_attractive]
        engaged = [d for d in durations if d >= min_engaged]
        deep = [d for d in durations if d >= min_deep]
        pass_by_estimate = max(n + int(total_store_sessions * pass_by_coeff), 1)

        results.append(ShelfEngagementResult(
            zone_id=zid,
            zone_name=zone.zone_name,
            zone_type=zone.zone_type,
            brand=zone.brand,
            department=zone.department,
            total_visits=n,
            attractive_stops=len(attractive),
            engaged_stops=len(engaged),
            deep_engage_stops=len(deep),
            attractiveness_index_pct=round(
                (len(attractive) / pass_by_estimate) * 100.0, 2
            ),
            hold_power_seconds=round(
                sum(attractive) / len(attractive), 1
            ) if attractive else 0.0,
            avg_dwell_seconds=round(sum(durations) / n, 1),
            max_dwell_seconds=round(max(durations), 1),
        ))

    results.sort(key=lambda x: x.attractiveness_index_pct, reverse=True)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Zone Analytics Engine — Primary Service Class
# ─────────────────────────────────────────────────────────────────────────────

class ZoneAnalyticsEngine:
    """
    Unified zone analytics service integrating zone_config.json with
    StoreSession and DwellLog data from the PurpleInsight PostgreSQL database.

    Provides:
        - zone_dwell_summary()       — per-zone visit counts + avg dwell
        - shelf_engagement_report()  — attractiveness + hold power per shelf
        - heatmap()                  — weighted KDE grid for frontend rendering
        - brand_zone_ranking()       — rank brand zones by engagement
        - checkout_intelligence()    — queue depth + wait time analytics
        - session_journey_map()      — per-track zone traversal paths
        - full_report()              — composite JSON report for API
    """

    def __init__(
        self,
        db: Session,
        store_id: str,
        zone_config_path: str = None,
    ):
        self.db = db
        self.store_id = store_id
        self.zone_cfg = load_zone_config(zone_config_path)
        self.zone_map = self.zone_cfg.zone_map
        self.heatmap_cfg = HeatmapConfig.from_zone_config(self.zone_cfg)
        self.projector = HomographyProjector.from_zone_config(self.zone_cfg)
        logger.info(
            f"ZoneAnalyticsEngine initialized — store={store_id}, "
            f"zones={len(self.zone_map)}"
        )

    # ── Shared Query Helpers ─────────────────────────────────────────────────

    def _dwell_query(self, start_time: datetime, end_time: datetime):
        return self.db.query(DwellLog).filter(
            and_(
                DwellLog.store_id == self.store_id,
                DwellLog.entered_at >= start_time,
                DwellLog.entered_at <= end_time,
            )
        )

    def _session_count(self, start_time: datetime, end_time: datetime) -> int:
        return (
            self.db.query(StoreSession)
            .filter(
                and_(
                    StoreSession.store_id == self.store_id,
                    StoreSession.entered_at >= start_time,
                    StoreSession.entered_at <= end_time,
                )
            )
            .distinct(StoreSession.track_id)
            .count()
        )

    # ── Zone Dwell Summary ───────────────────────────────────────────────────

    def zone_dwell_summary(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict]:
        """
        Per-zone visit counts, unique visitors, avg/max dwell times.

        Integrates StoreLayoutZone names from the database with zone_config
        definitions for complete metadata enrichment.

        Returns:
            List of zone dwell dicts ordered by total_visits descending.
        """
        try:
            results = (
                self.db.query(
                    DwellLog.zone_id,
                    func.count(DwellLog.id).label("total_visits"),
                    func.count(func.distinct(DwellLog.track_id)).label("unique_visitors"),
                    func.avg(DwellLog.duration_seconds).label("avg_dwell"),
                    func.max(DwellLog.duration_seconds).label("max_dwell"),
                    func.sum(DwellLog.duration_seconds).label("total_dwell"),
                )
                .filter(
                    and_(
                        DwellLog.store_id == self.store_id,
                        DwellLog.entered_at >= start_time,
                        DwellLog.entered_at <= end_time,
                    )
                )
                .group_by(DwellLog.zone_id)
                .all()
            )

            output = []
            for r in results:
                zone = self.zone_map.get(r.zone_id)
                db_zone = (
                    self.db.query(StoreLayoutZone)
                    .filter(StoreLayoutZone.id == r.zone_id)
                    .first()
                )
                output.append({
                    "zone_id": r.zone_id,
                    "zone_name": zone.zone_name if zone else (db_zone.name if db_zone else r.zone_id),
                    "zone_type": zone.zone_type if zone else "unknown",
                    "zone_subtype": zone.zone_subtype if zone else "unknown",
                    "brand": zone.brand if zone else None,
                    "department": zone.department if zone else None,
                    "total_visits": int(r.total_visits or 0),
                    "unique_visitors": int(r.unique_visitors or 0),
                    "avg_dwell_seconds": round(float(r.avg_dwell or 0), 1),
                    "max_dwell_seconds": round(float(r.max_dwell or 0), 1),
                    "total_dwell_seconds": round(float(r.total_dwell or 0), 1),
                    "centroid": list(zone.centroid) if zone else None,
                })

            output.sort(key=lambda x: x["total_visits"], reverse=True)
            return output
        except Exception as e:
            logger.error(f"zone_dwell_summary error: {e}")
            return []

    # ── Shelf Engagement Report ──────────────────────────────────────────────

    def shelf_engagement_report(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict]:
        """
        Attractiveness Index and Hold Power for all shelf and brand zones.

        Only includes zones listed in shelf_engagement_config.shelf_zones.

        Returns:
            List of engagement dicts sorted by attractiveness_index_pct desc.
        """
        try:
            shelf_ids = self.zone_cfg.shelf_zone_ids
            dwells = (
                self._dwell_query(start_time, end_time)
                .filter(DwellLog.zone_id.in_(shelf_ids))
                .all()
            )
            dwell_list = [
                {"zone_id": d.zone_id, "duration_seconds": d.duration_seconds}
                for d in dwells
            ]
            total_sessions = self._session_count(start_time, end_time)
            results = compute_shelf_engagement(
                dwell_list,
                self.zone_map,
                total_sessions,
                self.zone_cfg.shelf_engagement_config,
            )
            return [
                {
                    "zone_id": r.zone_id,
                    "zone_name": r.zone_name,
                    "zone_type": r.zone_type,
                    "brand": r.brand,
                    "department": r.department,
                    "total_visits": r.total_visits,
                    "attractive_stops": r.attractive_stops,
                    "engaged_stops": r.engaged_stops,
                    "deep_engage_stops": r.deep_engage_stops,
                    "attractiveness_index_pct": r.attractiveness_index_pct,
                    "hold_power_seconds": r.hold_power_seconds,
                    "avg_dwell_seconds": r.avg_dwell_seconds,
                    "max_dwell_seconds": r.max_dwell_seconds,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"shelf_engagement_report error: {e}")
            return []

    # ── Heatmap Generation ───────────────────────────────────────────────────

    def heatmap(
        self, start_time: datetime, end_time: datetime
    ) -> Dict:
        """
        Generates a weighted KDE heatmap grid from DwellLog observations.

        Zone centroids are used as spatial anchors. Dwell count and
        heatmap_weight from zone_config multiply the Gaussian kernel.

        Returns:
            {grid: [[float]], rows: int, cols: int, scale_px: int,
             zone_intensities: {zone_id: float}}
        """
        try:
            results = (
                self.db.query(
                    DwellLog.zone_id,
                    func.count(DwellLog.id).label("dwell_count"),
                )
                .filter(
                    and_(
                        DwellLog.store_id == self.store_id,
                        DwellLog.entered_at >= start_time,
                        DwellLog.entered_at <= end_time,
                    )
                )
                .group_by(DwellLog.zone_id)
                .all()
            )

            zone_dwell_counts = {r.zone_id: int(r.dwell_count) for r in results}
            grid = generate_weighted_heatmap(
                zone_dwell_counts, self.zone_map, self.heatmap_cfg
            )
            # Per-zone intensity snapshot
            zone_intensities = {}
            for zone_id, count in zone_dwell_counts.items():
                zone = self.zone_map.get(zone_id)
                if zone:
                    zone_intensities[zone_id] = round(
                        min(1.0, (zone.heatmap_weight * count) / max(sum(zone_dwell_counts.values()), 1)), 3
                    )

            return {
                "grid": grid,
                "rows": self.heatmap_cfg.grid_rows,
                "cols": self.heatmap_cfg.grid_cols,
                "scale_px": self.heatmap_cfg.grid_scale_px,
                "frame_width": self.heatmap_cfg.frame_width,
                "frame_height": self.heatmap_cfg.frame_height,
                "zone_intensities": zone_intensities,
            }
        except Exception as e:
            logger.error(f"heatmap error: {e}")
            return {"grid": [], "rows": 0, "cols": 0}

    # ── Brand Zone Ranking ───────────────────────────────────────────────────

    def brand_zone_ranking(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict]:
        """
        Ranks brand zones by engagement index and hold power.

        Combines spatial engagement metrics with brand metadata from zone_config.

        Returns:
            Ranked list of brand zone performance metrics.
        """
        try:
            brand_ids = self.zone_cfg.brand_zone_ids
            results = (
                self.db.query(
                    DwellLog.zone_id,
                    func.count(DwellLog.id).label("visits"),
                    func.count(func.distinct(DwellLog.track_id)).label("unique_visitors"),
                    func.avg(DwellLog.duration_seconds).label("avg_dwell"),
                    func.sum(DwellLog.duration_seconds).label("total_engagement_seconds"),
                )
                .filter(
                    and_(
                        DwellLog.store_id == self.store_id,
                        DwellLog.entered_at >= start_time,
                        DwellLog.entered_at <= end_time,
                        DwellLog.zone_id.in_(brand_ids),
                    )
                )
                .group_by(DwellLog.zone_id)
                .all()
            )

            total_sessions = max(self._session_count(start_time, end_time), 1)
            output = []
            for r in results:
                zone = self.zone_map.get(r.zone_id)
                visits = int(r.visits or 0)
                avg_dwell = float(r.avg_dwell or 0)
                # Engagement score: weighted combination of reach + depth
                reach_pct = round((visits / total_sessions) * 100.0, 2)
                engagement_score = round(reach_pct * math.log1p(avg_dwell) / 10.0, 3)

                output.append({
                    "zone_id": r.zone_id,
                    "zone_name": zone.zone_name if zone else r.zone_id,
                    "brand": zone.brand if zone else None,
                    "department": zone.department if zone else None,
                    "total_visits": visits,
                    "unique_visitors": int(r.unique_visitors or 0),
                    "reach_percent": reach_pct,
                    "avg_dwell_seconds": round(avg_dwell, 1),
                    "total_engagement_seconds": round(float(r.total_engagement_seconds or 0), 1),
                    "engagement_score": engagement_score,
                })

            output.sort(key=lambda x: x["engagement_score"], reverse=True)
            for rank, item in enumerate(output, start=1):
                item["rank"] = rank

            return output
        except Exception as e:
            logger.error(f"brand_zone_ranking error: {e}")
            return []

    # ── Checkout Intelligence ────────────────────────────────────────────────

    def checkout_intelligence(
        self, start_time: datetime, end_time: datetime
    ) -> Dict:
        """
        Queue depth analysis and wait-time distribution for checkout zones.

        Analyzes DwellLog records in checkout_queue and checkout_counter
        to compute queue wait times, peak periods, and service rate estimates.

        Returns:
            {queue_stats, counter_stats, peak_queue_hour, service_rate_per_hour}
        """
        try:
            checkout_ids = list(self.zone_cfg.checkout_zone_ids)
            results = (
                self.db.query(
                    DwellLog.zone_id,
                    DwellLog.track_id,
                    DwellLog.entered_at,
                    DwellLog.exited_at,
                    DwellLog.duration_seconds,
                )
                .filter(
                    and_(
                        DwellLog.store_id == self.store_id,
                        DwellLog.entered_at >= start_time,
                        DwellLog.entered_at <= end_time,
                        DwellLog.zone_id.in_(checkout_ids),
                    )
                )
                .all()
            )

            zone_stats: Dict[str, Dict] = {z: {
                "visits": 0, "unique_visitors": set(),
                "durations": [], "hours": []
            } for z in checkout_ids}

            for r in results:
                if r.zone_id not in zone_stats:
                    continue
                s = zone_stats[r.zone_id]
                s["visits"] += 1
                s["unique_visitors"].add(r.track_id)
                s["durations"].append(r.duration_seconds)
                if r.entered_at:
                    s["hours"].append(r.entered_at.hour)

            def summarize(zid: str, label: str) -> Dict:
                s = zone_stats.get(zid, {})
                durations = s.get("durations", [])
                hours = s.get("hours", [])
                peak_hour = max(set(hours), key=hours.count) if hours else None
                return {
                    "zone_id": zid,
                    "label": label,
                    "total_visits": s.get("visits", 0),
                    "unique_visitors": len(s.get("unique_visitors", set())),
                    "avg_wait_seconds": round(sum(durations) / len(durations), 1) if durations else 0.0,
                    "max_wait_seconds": round(max(durations), 1) if durations else 0.0,
                    "min_wait_seconds": round(min(durations), 1) if durations else 0.0,
                    "peak_hour": f"{peak_hour}:00" if peak_hour is not None else None,
                }

            queue_stats = summarize("checkout_queue", "Checkout Waiting Queue")
            counter_stats = summarize("checkout_counter", "Cash Counter")

            # Estimated service rate: transactions per hour
            counter_visits = zone_stats.get("checkout_counter", {}).get("visits", 0)
            period_hours = max((end_time - start_time).total_seconds() / 3600.0, 0.01)
            service_rate = round(counter_visits / period_hours, 1)

            return {
                "queue_stats": queue_stats,
                "counter_stats": counter_stats,
                "estimated_service_rate_per_hour": service_rate,
            }
        except Exception as e:
            logger.error(f"checkout_intelligence error: {e}")
            return {}

    # ── Session Journey Map ──────────────────────────────────────────────────

    def session_journey_map(
        self, start_time: datetime, end_time: datetime, limit: int = 50
    ) -> List[Dict]:
        """
        Reconstructs zone traversal journeys per shopper track.

        Links DwellLog records back to StoreSession to create ordered
        zone sequences showing shopper path through the store.

        Args:
            limit: Maximum number of unique track journeys to return.

        Returns:
            List of {track_id, session_duration_seconds, zone_path, zones_visited}
        """
        try:
            sessions = (
                self.db.query(StoreSession)
                .filter(
                    and_(
                        StoreSession.store_id == self.store_id,
                        StoreSession.entered_at >= start_time,
                        StoreSession.entered_at <= end_time,
                        StoreSession.exited_at.isnot(None),
                    )
                )
                .limit(limit)
                .all()
            )

            journeys = []
            for session in sessions:
                dwells = (
                    self.db.query(DwellLog)
                    .filter(
                        and_(
                            DwellLog.store_id == self.store_id,
                            DwellLog.track_id == session.track_id,
                            DwellLog.entered_at >= session.entered_at,
                            DwellLog.entered_at <= (session.exited_at or end_time),
                        )
                    )
                    .order_by(DwellLog.entered_at.asc())
                    .all()
                )

                zone_path = []
                for d in dwells:
                    zone = self.zone_map.get(d.zone_id)
                    zone_path.append({
                        "zone_id": d.zone_id,
                        "zone_name": zone.zone_name if zone else d.zone_id,
                        "zone_type": zone.zone_type if zone else "unknown",
                        "dwell_seconds": round(d.duration_seconds, 1),
                        "entered_at": d.entered_at.isoformat() if d.entered_at else None,
                    })

                session_duration = (
                    (session.exited_at - session.entered_at).total_seconds()
                    if session.exited_at else None
                )

                journeys.append({
                    "track_id": session.track_id,
                    "entered_at": session.entered_at.isoformat(),
                    "exited_at": session.exited_at.isoformat() if session.exited_at else None,
                    "session_duration_seconds": round(session_duration, 1) if session_duration else None,
                    "zones_visited": len(zone_path),
                    "zone_path": zone_path,
                    "re_entry": session.re_entry,
                })

            return journeys
        except Exception as e:
            logger.error(f"session_journey_map error: {e}")
            return []

    # ── Full Composite Report ────────────────────────────────────────────────

    def full_report(
        self, start_time: datetime, end_time: datetime
    ) -> Dict:
        """
        Generates the complete zone intelligence report for the API.

        Combines all analytics methods into a single structured response
        suitable for the PurpleInsight dashboard /api/v1/analytics/zones endpoint.

        Returns:
            Full composite zone report dict.
        """
        logger.info(
            f"Generating full zone report for store={self.store_id} "
            f"period={start_time.isoformat()} → {end_time.isoformat()}"
        )
        total_sessions = self._session_count(start_time, end_time)

        return {
            "store_id": self.store_id,
            "store_name": self.zone_cfg.store_name,
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": round((end_time - start_time).total_seconds() / 3600, 2),
            },
            "total_shopper_sessions": total_sessions,
            "total_zones_monitored": len(self.zone_map),
            "zone_dwell_summary": self.zone_dwell_summary(start_time, end_time),
            "shelf_engagement": self.shelf_engagement_report(start_time, end_time),
            "brand_zone_ranking": self.brand_zone_ranking(start_time, end_time),
            "checkout_intelligence": self.checkout_intelligence(start_time, end_time),
            "heatmap": self.heatmap(start_time, end_time),
        }
