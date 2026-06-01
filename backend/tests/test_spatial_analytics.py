import pytest
from backend.services.spatial_analytics import (
    TrajectoryKalmanFilter,
    PlanarHomographyProjector,
    generate_kde_heatmap_grid,
    ShelfEngagementCalculator
)

def test_kalman_filter_smoothing():
    filter_x = TrajectoryKalmanFilter(dt=0.2, process_noise=0.1, measurement_noise=1.0)
    
    # Simulate coordinate sequence with tracking jitter (wobbling around a straight line y = 10)
    measurements = [(10, 10), (12, 9), (14, 11), (16, 10), (18, 10), (20, 9)]
    smoothed_path = []
    
    for pt in measurements:
        smoothed = filter_x.update(pt)
        smoothed_path.append(smoothed)
        
    assert len(smoothed_path) == len(measurements)
    # The filter must align positions, smoothing out the high frequency spikes
    # Check last point: should be close to the trajectory target (20, 10)
    assert abs(smoothed_path[-1][0] - 20) < 2.0
    assert abs(smoothed_path[-1][1] - 10) < 2.0

def test_planar_homography_projection():
    # Identity matrix projector (should return original points)
    projector = PlanarHomographyProjector()
    x, y = projector.project_point(150.0, 300.0)
    assert x == 150.0
    assert y == 300.0

    # Custom perspective matrix mapping pixel origin to ground coordinates
    H = [
        [1.5, 0.0, 10.0],
        [0.0, 1.2, 20.0],
        [0.0, 0.0, 1.0]
    ]
    projector_custom = PlanarHomographyProjector(H)
    # project point (100, 100) -> x = (1.5*100 + 10)/1 = 160, y = (1.2*100 + 20)/1 = 140
    x, y = projector_custom.project_point(100.0, 100.0)
    assert x == 160.0
    assert y == 140.0

def test_gaussian_kde_heatmap_grid():
    # 3 points located in a cluster
    coords = [(200, 200), (210, 205), (195, 198)]
    
    grid = generate_kde_heatmap_grid(coords, width=1200, height=600, grid_scale=20, sigma=30.0)
    
    # Grid proportions should be 60 cols by 30 rows
    assert len(grid) == 30
    assert len(grid[0]) == 60
    
    # Check that grid cell containing the cluster center (row 10, col 10: x=210, y=210) has high density (approx 1.0)
    assert grid[10][10] > 0.8
    # Cells far away should be close to 0.0
    assert grid[0][0] == 0.0
    assert grid[25][50] == 0.0

def test_shelf_engagement_metrics():
    # 5 dwells in aisle_1_fresh: 2s, 3s, 12s, 18s, 22s (3 stops are attractive >= 5s)
    # Total store sessions = 10
    # Estimated pass-by traffic: stays count (5) + fallback (1) = 6
    # Attractiveness index: 3 / 6 = 50.0%
    # Hold power: (12 + 18 + 22) / 3 = 17.3s
    dwell_logs = [
        {"zone_id": "aisle_1_fresh", "name": "Fresh Produce", "duration_seconds": 2.0},
        {"zone_id": "aisle_1_fresh", "name": "Fresh Produce", "duration_seconds": 3.0},
        {"zone_id": "aisle_1_fresh", "name": "Fresh Produce", "duration_seconds": 12.0},
        {"zone_id": "aisle_1_fresh", "name": "Fresh Produce", "duration_seconds": 18.0},
        {"zone_id": "aisle_1_fresh", "name": "Fresh Produce", "duration_seconds": 22.0}
    ]
    
    metrics = ShelfEngagementCalculator.calculate_metrics(dwell_logs, total_store_sessions=10)
    
    assert len(metrics) == 1
    m = metrics[0]
    assert m["zone_id"] == "aisle_1_fresh"
    assert m["total_stops"] == 5
    assert m["attractive_stops"] == 3
    assert m["attractiveness_index_pct"] == 50.0
    assert m["hold_power_seconds"] == 17.3
