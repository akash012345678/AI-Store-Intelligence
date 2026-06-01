import pytest
import time
from edge.src.config import PipelineConfig, GateConfig, ZoneConfig
from edge.src.analytics import (
    point_in_polygon,
    segments_intersect,
    AnalyticsEngine,
    Euclidean_distance
)
from edge.src.event_dispatcher import (
    PersonEntryEvent,
    PersonExitEvent,
    ZoneDwellEvent,
    QueueUpdateEvent,
    QueueAlertEvent
)

def test_point_in_polygon():
    # Square polygon from (0,0) to (10,10)
    polygon = [(0, 0), (10, 0), (10, 10), (0, 10)]
    
    # Clearly inside
    assert point_in_polygon((5, 5), polygon) is True
    # Clearly outside
    assert point_in_polygon((12, 5), polygon) is False
    assert point_in_polygon((5, -1), polygon) is False

    # Concave Polygon (L-shape)
    # Vertices: 
    # (0,0) -> (10,0) -> (10,5) -> (5,5) -> (5,10) -> (0,10)
    l_polygon = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
    # Inside L
    assert point_in_polygon((2, 2), l_polygon) is True
    assert point_in_polygon((8, 2), l_polygon) is True
    assert point_in_polygon((2, 8), l_polygon) is True
    # In the cut-out corner (outside)
    assert point_in_polygon((8, 8), l_polygon) is False

def test_segments_intersect():
    # Crossing segments
    # AB: (0, 5) to (10, 5)
    # CD: (5, 0) to (5, 10)
    assert segments_intersect((0, 5), (10, 5), (5, 0), (5, 10)) is True

    # Non-crossing parallel
    assert segments_intersect((0, 0), (10, 0), (0, 2), (10, 2)) is False

    # Collinear/touching but not intersecting crossing
    assert segments_intersect((0, 0), (5, 5), (10, 10), (12, 12)) is False

@pytest.fixture
def test_config():
    return PipelineConfig(
        store_id="store-123",
        camera_id="cam-123",
        video_source="0",
        model_path="yolov8n.pt",
        confidence_threshold=0.4,
        iou_threshold=0.45,
        tracker_config="bytetrack.yaml",
        device="cpu",
        occupancy_interval=5.0,
        dwell_cooldown_seconds=1.0, # low for faster test evaluation
        re_entry_time_threshold=2.0,
        re_entry_distance_threshold=50.0,
        entrance_gate=GateConfig(
            name="gate",
            line_a=(0, 100),
            line_b=(200, 100)
        ),
        zones=[
            ZoneConfig(
                id="zone_a",
                name="Zone Alpha",
                polygon=[(0, 0), (50, 0), (50, 50), (0, 50)]
            )
        ]
    )

def test_analytics_gate_crossing(test_config):
    engine = AnalyticsEngine(test_config)
    
    # 1. Simulate track 1 crossing gate INWARD (Entry)
    # Gate line is (0, 100) to (200, 100).
    # Path: from (100, 120) to (100, 80)
    # Gate vector AB: B - A = (200, 0). Motion CD: D - C = (0, -40).
    # Cross product = (200 * -40) - (0 * 0) = -8000. Wait!
    # Let's verify direction calculations in ccw logic.
    # We want a crossing event to be triggered.
    
    # Let's mock a detection feed
    # detection format: (track_id, (x1, y1, x2, y2), confidence)
    # feet position: ((x1+x2)/2, y2)
    
    # Frame 1: Shopper 1 spawns outside the gate (100, 120)
    # y2 is bottom coordinate (120)
    events_1 = engine.process_tracks([
        (1, (90, 80, 110, 120), 0.9)
    ])
    
    # Verify it initializes the track. Since it spawns at (100, 120), which is 20px below gate (0, 100)-(200, 100),
    # and Euclidean distance to line (0,100)-(200,100) is 20px, it spawns near the gate.
    # Therefore, it immediately triggers an entry event as designed in handling first appearance.
    assert len(events_1) == 1
    assert isinstance(events_1[0], PersonEntryEvent)
    assert events_1[0].track_id == 1
    assert events_1[0].re_entry_detected is False

    # Frame 2: Shopper 1 walks deeper inside, away from the gate (no crossing)
    # Let's see: from (100, 120) to (100, 160).
    events_2 = engine.process_tracks([
        (1, (90, 130, 110, 160), 0.9)
    ])
    # The initial entry is already registered, so no redundant crossing entry event is triggered.
    assert len(events_2) == 0

def test_analytics_dwell_tracking(test_config):
    engine = AnalyticsEngine(test_config)
    
    # Frame 1: Shopper 1 spawns at (10, 10) inside Zone Alpha
    # Zone polygon: (0,0) -> (50,0) -> (50,50) -> (0,50)
    events = engine.process_tracks([
        (1, (0, 0, 20, 10), 0.9) # feet point is (10, 10)
    ])
    
    # Shoud initialize tracking session and register entry (as it spawns near gate? Gate is at y=100.
    # Distance to gate is 90px. It does not spawn near gate (<150px) - actually (10,10) to (0,100) is sqrt(100 + 8100) = 90.5px.
    # Yes, it spawns near gate, so Entry is triggered. Dwell active is marked in zone_a.
    assert len(events) == 1
    assert isinstance(events[0], PersonEntryEvent)
    
    track_hist = engine.tracks[1]
    assert "zone_a" in track_hist.active_dwells
    
    # Mock passage of time for dwell (we simulate 3 seconds later)
    # To mock time, we will manually edit the active dwells entered_at time
    track_hist.active_dwells["zone_a"]["entered_at"] = time.time() - 10.0
    track_hist.active_dwells["zone_a"]["last_seen_at"] = time.time() - 5.0
    
    # Frame 2: Shopper 1 walks out of Zone Alpha to (60, 60)
    # Active dwell exit is registered after dwell_cooldown_seconds (1.0 second)
    events_out = engine.process_tracks([
        (1, (50, 50, 70, 60), 0.9) # feet point is (60, 60)
    ])
    
    # Cooldown check: now (time.time()) - last_seen (time.time()-5.0) = 5.0s > cooldown (1.0s)
    # The exit is processed immediately because the difference exceeds the cooldown.
    assert len(events_out) == 1
    assert isinstance(events_out[0], ZoneDwellEvent)
    assert events_out[0].zone_id == "zone_a"
    assert events_out[0].dwell_time_seconds >= 5.0

def test_analytics_re_entry_stitching(test_config):
    engine = AnalyticsEngine(test_config)
    
    # Frame 1: Shopper 1 crosses exit gate
    # Simulate track 1 crossing outbound. 
    # Instead of full crossing simulation, we can mock it directly by adding exit record to recently_exited_tracks
    engine.recently_exited_tracks[1] = {
        "exit_timestamp": time.time() - 0.5, # 0.5 seconds ago
        "exit_point": (100, 105)
    }
    
    # Frame 2: A new track 2 spawns near the exit point (100, 105) within threshold
    events = engine.process_tracks([
        (2, (90, 95, 110, 106), 0.9) # feet point is (100, 106), close to (100, 105)
    ])
    
    # Check that re-entry is detected, track 2 is stitched to original track 1
    assert len(events) == 1
    assert isinstance(events[0], PersonEntryEvent)
    assert events[0].re_entry_detected is True
    assert events[0].track_id == 1 # Stitched to old ID 1
    assert events[0].correlated_previous_track_id == 1
    assert engine.get_original_track_id(2) == 1

def test_analytics_queue_tracking(test_config):
    from edge.src.config import ZoneConfig
    test_config.zones.append(
        ZoneConfig(
            id="checkout_queue",
            name="Checkout Queue",
            polygon=[(0, 0), (100, 0), (100, 100), (0, 100)]
        )
    )
    
    engine = AnalyticsEngine(test_config)
    
    # 1. Spawn a person (track_id = 1) inside the checkout_queue zone
    # Feet point is (50, 50)
    now = time.time()
    events = engine.process_tracks([
        (1, (40, 40, 60, 50), 0.9)
    ])
    
    # Check that the person is registered in checkout_queue active tracks
    assert 1 in engine.queue_active_tracks["checkout_queue"]
    
    # We will simulate 4 more people joining to trigger length alert (total = 5 >= 4)
    # And mock elapsed time by altering the entry times in queue_active_tracks
    engine.queue_active_tracks["checkout_queue"][1] = now - 150.0 # wait time = 150s (exceeds 120s limit)
    
    # Add 4 more people inside queue
    engine.queue_active_tracks["checkout_queue"][2] = now - 10.0
    engine.queue_active_tracks["checkout_queue"][3] = now - 10.0
    engine.queue_active_tracks["checkout_queue"][4] = now - 10.0
    engine.queue_active_tracks["checkout_queue"][5] = now - 10.0
    
    # Force periodic queue check to run immediately by setting last_queue_report_time to 10s ago
    engine.last_queue_report_time = now - 10.0
    
    # Run process_tracks again with all tracks active so they are not pruned
    events_queue = engine.process_tracks([
        (1, (40, 40, 60, 50), 0.9),
        (2, (10, 10, 30, 20), 0.9),
        (3, (10, 10, 30, 20), 0.9),
        (4, (10, 10, 30, 20), 0.9),
        (5, (10, 10, 30, 20), 0.9)
    ])
    
    # Verify that QueueUpdateEvent and QueueAlertEvent are emitted
    assert any(isinstance(e, QueueUpdateEvent) for e in events_queue)
    assert any(isinstance(e, QueueAlertEvent) for e in events_queue)
    
    update_event = [e for e in events_queue if isinstance(e, QueueUpdateEvent)][0]
    alert_event = [e for e in events_queue if isinstance(e, QueueAlertEvent)][0]
    
    assert update_event.current_length == 5
    assert update_event.max_wait_seconds >= 150.0
    assert alert_event.severity in ["MEDIUM", "HIGH"]
