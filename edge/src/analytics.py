import time
import logging
import math
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional, Set
from edge.src.config import PipelineConfig, ZoneConfig
from edge.src.event_dispatcher import (
    PersonEntryEvent,
    PersonExitEvent,
    ZoneDwellEvent,
    OccupancyUpdateEvent,
    QueueUpdateEvent,
    QueueAlertEvent,
    BaseEvent
)

logger = logging.getLogger("PurpleInsight.Analytics")
logger.setLevel(logging.INFO)

# --- Geometry Utilities ---

def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[int, int]]) -> bool:
    """Ray-casting algorithm in pure Python to check if a point is inside a polygon."""
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

def ccw(A: Tuple[float, float], B: Tuple[float, float], C: Tuple[float, float]) -> float:
    """Calculates orientation of triplet (A, B, C)."""
    return (C[1] - A[1]) * (B[0] - A[0]) - (B[1] - A[1]) * (C[0] - A[0])

def segments_intersect(A: Tuple[float, float], B: Tuple[float, float], 
                       C: Tuple[float, float], D: Tuple[float, float]) -> bool:
    """Checks if line segment AB and CD intersect."""
    def sign(x: float) -> int:
        return 1 if x > 0 else (-1 if x < 0 else 0)

    val1 = ccw(A, B, C)
    val2 = ccw(A, B, D)
    val3 = ccw(C, D, A)
    val4 = ccw(C, D, B)

    return (sign(val1) != sign(val2)) and (sign(val3) != sign(val4))

def Euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculates Euclidean distance between two points."""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


# --- Core Analytics State Engine ---

class TrackHistory:
    """Maintains the spatial-temporal history of a single tracking ID."""
    def __init__(self, track_id: int):
        self.track_id = track_id
        self.points: List[Tuple[float, float]] = []
        self.timestamps: List[float] = []
        self.last_seen: float = time.time()
        self.has_entered: bool = False
        
        # Dwell tracking by zone: {zone_id: {"entered_at": float, "last_seen_at": float}}
        self.active_dwells: Dict[str, Dict[str, float]] = {}

    def add_point(self, point: Tuple[float, float], timestamp: float) -> None:
        self.points.append(point)
        self.timestamps.append(timestamp)
        self.last_seen = timestamp
        if len(self.points) > 100:
            self.points.pop(0)
            self.timestamps.pop(0)

    @property
    def last_point(self) -> Optional[Tuple[float, float]]:
        return self.points[-1] if self.points else None

    @property
    def second_last_point(self) -> Optional[Tuple[float, float]]:
        return self.points[-2] if len(self.points) >= 2 else None


class AnalyticsEngine:
    """Stateful retail analytics engine processing trajectories frame-by-frame."""
    def __init__(self, config: PipelineConfig):
        self.config = config
        
        # Sessions and history state
        self.tracks: Dict[int, TrackHistory] = {}
        self.active_in_store_tracks: Set[int] = set()
        
        # Re-entry tracking
        self.recently_exited_tracks: Dict[int, Dict] = {}
        self.stitched_tracks: Dict[int, int] = {}
        
        # Queue Analytics specific tracking: {queue_zone_id: {track_id: entered_at}}
        self.queue_active_tracks: Dict[str, Dict[int, float]] = {
            zone.id: {} for zone in config.zones if "queue" in zone.id
        }
        self.last_queue_alert_time: Dict[str, float] = {
            zone.id: 0.0 for zone in config.zones if "queue" in zone.id
        }
        
        # Period schedulers
        self.last_occupancy_report_time: float = time.time()
        self.last_queue_report_time: float = time.time()

    def get_original_track_id(self, track_id: int) -> int:
        current_id = track_id
        while current_id in self.stitched_tracks:
            current_id = self.stitched_tracks[current_id]
        return current_id

    def process_tracks(self, active_detections: List[Tuple[int, Tuple[float, float, float, float], float]]) -> List[BaseEvent]:
        """Processes a frame's tracked persons and returns generated analytic events."""
        now = time.time()
        events: List[BaseEvent] = []
        currently_detected_ids: Set[int] = set()

        for track_id, bbox, conf in active_detections:
            currently_detected_ids.add(track_id)
            
            x1, y1, x2, y2 = bbox
            feet_point = ((x1 + x2) / 2.0, y2)

            if track_id not in self.tracks:
                self.tracks[track_id] = TrackHistory(track_id)
                self._handle_first_appearance(track_id, feet_point, now, conf, events)

            track_hist = self.tracks[track_id]
            track_hist.add_point(feet_point, now)

            # Evaluate Gates & Polygons
            self._evaluate_gate_crossing(track_hist, conf, events)
            self._evaluate_zones(track_hist, now, events)

        # Handle lost dropouts
        self._prune_lost_tracks(currently_detected_ids, now, events)

        # Periodic occupancy update
        if now - self.last_occupancy_report_time >= self.config.occupancy_interval:
            events.append(self._generate_occupancy_event())
            self.last_occupancy_report_time = now

        # Periodic queue update (evaluated every 5 seconds)
        if now - self.last_queue_report_time >= 5.0:
            self._evaluate_queues(now, events)
            self.last_queue_report_time = now

        return events

    def _handle_first_appearance(self, track_id: int, point: Tuple[float, float], 
                                  now: float, conf: float, events: List[BaseEvent]) -> None:
        gate = self.config.entrance_gate
        matched_previous_track_id: Optional[int] = None
        re_entry_detected = False

        # Trajectory stitching check
        best_match_id = None
        min_distance = float('inf')

        for old_id, exit_data in list(self.recently_exited_tracks.items()):
            time_delta = now - exit_data["exit_timestamp"]
            if time_delta > self.config.re_entry_time_threshold:
                self.recently_exited_tracks.pop(old_id)
                continue

            dist = Euclidean_distance(point, exit_data["exit_point"])
            if dist <= self.config.re_entry_distance_threshold and dist < min_distance:
                min_distance = dist
                best_match_id = old_id

        if best_match_id is not None:
            re_entry_detected = True
            matched_previous_track_id = self.get_original_track_id(best_match_id)
            self.stitched_tracks[track_id] = matched_previous_track_id
            self.recently_exited_tracks.pop(best_match_id)

        self.active_in_store_tracks.add(track_id)
        
        # In multi-camera retail tracking, any shopper seen for the first time
        # is dynamically initialized as a store entry to prevent spatial coordinate drift.
        spawned_near_gate = True

        if spawned_near_gate or re_entry_detected:
            self.tracks[track_id].has_entered = True
            events.append(PersonEntryEvent(
                store_id=self.config.store_id,
                camera_id=self.config.camera_id,
                track_id=self.get_original_track_id(track_id),
                confidence=conf,
                re_entry_detected=re_entry_detected,
                correlated_previous_track_id=matched_previous_track_id
            ))

    def _evaluate_gate_crossing(self, track_hist: TrackHistory, conf: float, events: List[BaseEvent]) -> None:
        p_curr = track_hist.last_point
        p_prev = track_hist.second_last_point

        if not p_curr or not p_prev:
            return

        gate = self.config.entrance_gate
        A = gate.line_a
        B = gate.line_b

        if segments_intersect(A, B, p_prev, p_curr):
            ab_x, ab_y = B[0] - A[0], B[1] - A[1]
            cd_x, cd_y = p_curr[0] - p_prev[0], p_curr[1] - p_prev[1]
            cross_product = (ab_x * cd_y) - (ab_y * cd_x)

            if cross_product > 0:
                if not track_hist.has_entered:
                    track_hist.has_entered = True
                    self.active_in_store_tracks.add(track_hist.track_id)
                    events.append(PersonEntryEvent(
                        store_id=self.config.store_id,
                        camera_id=self.config.camera_id,
                        track_id=self.get_original_track_id(track_hist.track_id),
                        confidence=conf,
                        re_entry_detected=False
                    ))
            else:
                if track_hist.has_entered:
                    track_hist.has_entered = False
                    self.active_in_store_tracks.discard(track_hist.track_id)
                    events.append(PersonExitEvent(
                        store_id=self.config.store_id,
                        camera_id=self.config.camera_id,
                        track_id=self.get_original_track_id(track_hist.track_id),
                        confidence=conf
                    ))
                    self.recently_exited_tracks[track_hist.track_id] = {
                        "exit_timestamp": time.time(),
                        "exit_point": p_curr
                    }

    def _evaluate_zones(self, track_hist: TrackHistory, now: float, events: List[BaseEvent]) -> None:
        p_curr = track_hist.last_point
        if not p_curr:
            return

        original_id = self.get_original_track_id(track_hist.track_id)

        for zone in self.config.zones:
            is_inside = point_in_polygon(p_curr, zone.polygon)
            zone_id = zone.id

            if is_inside:
                if zone_id not in track_hist.active_dwells:
                    track_hist.active_dwells[zone_id] = {
                        "entered_at": now,
                        "last_seen_at": now
                    }
                    # Add to queue analytics if it's a queue zone
                    if zone_id in self.queue_active_tracks:
                        self.queue_active_tracks[zone_id][track_hist.track_id] = now
                else:
                    track_hist.active_dwells[zone_id]["last_seen_at"] = now
            else:
                if zone_id in track_hist.active_dwells:
                    last_seen = track_hist.active_dwells[zone_id]["last_seen_at"]
                    time_outside = now - last_seen
                    
                    if time_outside >= self.config.dwell_cooldown_seconds:
                        # Finalize exit
                        dwell_data = track_hist.active_dwells.pop(zone_id)
                        entered_time = dwell_data["entered_at"]
                        dwell_duration = last_seen - entered_time

                        # Remove from active queue lists
                        if zone_id in self.queue_active_tracks:
                            self.queue_active_tracks[zone_id].pop(track_hist.track_id, None)

                        events.append(ZoneDwellEvent(
                            store_id=self.config.store_id,
                            camera_id=self.config.camera_id,
                            track_id=original_id,
                            zone_id=zone_id,
                            entered_at=datetime.fromtimestamp(entered_time, timezone.utc).isoformat(),
                            exited_at=datetime.fromtimestamp(last_seen, timezone.utc).isoformat(),
                            dwell_time_seconds=round(dwell_duration, 2)
                        ))

    def _prune_lost_tracks(self, currently_detected_ids: Set[int], now: float, events: List[BaseEvent]) -> None:
        lost_ids = set(self.tracks.keys()) - currently_detected_ids

        for lost_id in lost_ids:
            track_hist = self.tracks[lost_id]
            original_id = self.get_original_track_id(lost_id)

            for zone_id in list(track_hist.active_dwells.keys()):
                dwell_data = track_hist.active_dwells[zone_id]
                last_seen = dwell_data["last_seen_at"]
                
                if now - last_seen >= self.config.dwell_cooldown_seconds:
                    dwell_data = track_hist.active_dwells.pop(zone_id)
                    entered_time = dwell_data["entered_at"]
                    dwell_duration = last_seen - entered_time

                    if zone_id in self.queue_active_tracks:
                        self.queue_active_tracks[zone_id].pop(lost_id, None)

                    events.append(ZoneDwellEvent(
                        store_id=self.config.store_id,
                        camera_id=self.config.camera_id,
                        track_id=original_id,
                        zone_id=zone_id,
                        entered_at=datetime.fromtimestamp(entered_time, timezone.utc).isoformat(),
                        exited_at=datetime.fromtimestamp(last_seen, timezone.utc).isoformat(),
                        dwell_time_seconds=round(dwell_duration, 2)
                    ))

            # If the shopper is lost from the frame, we close their store session and emit a PEOPLE_EXIT event
            if track_hist.has_entered and now - track_hist.last_seen >= self.config.dwell_cooldown_seconds:
                track_hist.has_entered = False
                self.active_in_store_tracks.discard(lost_id)
                events.append(PersonExitEvent(
                    store_id=self.config.store_id,
                    camera_id=self.config.camera_id,
                    track_id=original_id,
                    confidence=0.90
                ))
                self.recently_exited_tracks[lost_id] = {
                    "exit_timestamp": now,
                    "exit_point": track_hist.last_point or (0.0, 0.0)
                }

            if now - track_hist.last_seen > 300.0:
                self.tracks.pop(lost_id)
                self.active_in_store_tracks.discard(lost_id)
                self.recently_exited_tracks.pop(lost_id, None)
                self.stitched_tracks.pop(lost_id, None)
                for qid in self.queue_active_tracks:
                    self.queue_active_tracks[qid].pop(lost_id, None)

    def _evaluate_queues(self, now: float, events: List[BaseEvent]) -> None:
        """Evaluates active checkout queues, calculating lengths, wait times, and triggers crowding alerts."""
        for queue_id, active_shoppers in self.queue_active_tracks.items():
            current_len = len(active_shoppers)
            
            if current_len == 0:
                # Emit empty queue updates
                events.append(QueueUpdateEvent(
                    store_id=self.config.store_id,
                    camera_id=self.config.camera_id,
                    queue_id=queue_id,
                    current_length=0,
                    avg_wait_seconds=0.0,
                    max_wait_seconds=0.0
                ))
                continue

            # Calculate individual wait times
            wait_times = [now - entered_at for entered_at in active_shoppers.values()]
            avg_wait = sum(wait_times) / len(wait_times)
            max_wait = max(wait_times)

            # 1. Periodic Queue Update
            events.append(QueueUpdateEvent(
                store_id=self.config.store_id,
                camera_id=self.config.camera_id,
                queue_id=queue_id,
                current_length=current_len,
                avg_wait_seconds=round(avg_wait, 1),
                max_wait_seconds=round(max_wait, 1)
            ))

            # 2. Queue Crowding Alert check
            # Thresholds: length > 4 people OR max wait > 120 seconds
            length_threshold = 4
            wait_threshold_seconds = 120.0
            
            if current_len >= length_threshold or max_wait >= wait_threshold_seconds:
                # Apply a 60-second alert debounce to prevent network flood
                last_alert = self.last_queue_alert_time.get(queue_id, 0.0)
                if now - last_alert >= 60.0:
                    severity = "HIGH" if current_len >= 6 or max_wait >= 180.0 else "MEDIUM"
                    message = (
                        f"Congestion alert inside checkout queue '{queue_id}': "
                        f"Active Length={current_len} (Limit={length_threshold}); "
                        f"Max Wait Time={max_wait:.1f}s (Limit={wait_threshold_seconds}s)."
                    )
                    
                    events.append(QueueAlertEvent(
                        store_id=self.config.store_id,
                        camera_id=self.config.camera_id,
                        queue_id=queue_id,
                        severity=severity,
                        message=message
                    ))
                    self.last_queue_alert_time[queue_id] = now
                    logger.warning(f"== [QUEUE WARNING ALERT DECLARED] == {message}")

    def _generate_occupancy_event(self) -> OccupancyUpdateEvent:
        zone_counts = {zone.id: 0 for zone in self.config.zones}
        now = time.time()
        
        for track in self.tracks.values():
            if now - track.last_seen <= 2.0:
                for zone_id in track.active_dwells:
                    if zone_id in zone_counts:
                        zone_counts[zone_id] += 1

        occupancy = len([tid for tid in self.active_in_store_tracks if tid in self.tracks and now - self.tracks[tid].last_seen <= 2.0])

        return OccupancyUpdateEvent(
            store_id=self.config.store_id,
            camera_id=self.config.camera_id,
            current_occupancy=occupancy,
            active_tracks_count=len(self.active_in_store_tracks),
            zone_occupancies=zone_counts
        )
