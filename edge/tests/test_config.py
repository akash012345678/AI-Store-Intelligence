import pytest
import os
import yaml
from pydantic import ValidationError
from edge.src.config import PipelineConfig, load_config, GateConfig, ZoneConfig

def test_gate_config_validation():
    # Valid gate configuration
    valid_gate = GateConfig(name="main_gate", line_a=(100, 200), line_b=(300, 400))
    assert valid_gate.name == "main_gate"
    assert valid_gate.line_a == (100, 200)

    # Invalid coordinates size
    with pytest.raises(ValidationError):
        GateConfig(name="bad_gate", line_a=(100,), line_b=(200, 300))

    # Negative coordinates
    with pytest.raises(ValidationError):
        GateConfig(name="bad_gate", line_a=(-100, 200), line_b=(200, 300))

def test_zone_config_validation():
    # Valid zone configuration
    valid_zone = ZoneConfig(id="z1", name="Zone 1", polygon=[(1, 1), (5, 1), (5, 5), (1, 5)])
    assert len(valid_zone.polygon) == 4

    # Polygon with fewer than 3 vertices (not a polygon)
    with pytest.raises(ValidationError):
        ZoneConfig(id="z2", name="Zone 2", polygon=[(1, 1), (5, 1)])

    # Negative coordinates
    with pytest.raises(ValidationError):
        ZoneConfig(id="z3", name="Zone 3", polygon=[(1, 1), (-5, 1), (1, 5)])

def test_pipeline_config_parsing(tmp_path):
    config_yaml = """
store_id: "test-store"
camera_id: "test-cam"
video_source: "data/sample.mp4"
model_path: "yolov8n.pt"
confidence_threshold: 0.5
iou_threshold: 0.45
tracker_config: "bytetrack.yaml"
device: "cpu"
occupancy_interval: 10.0
dwell_cooldown_seconds: 5.0
re_entry_time_threshold: 10.0
re_entry_distance_threshold: 50.0
entrance_gate:
  name: "entrance"
  line_a: [100, 500]
  line_b: [500, 500]
zones:
  - id: "zone_1"
    name: "Zone A"
    polygon:
      - [0, 0]
      - [100, 0]
      - [100, 100]
      - [0, 100]
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_yaml)
    
    config = load_config(str(config_file))
    
    assert config.store_id == "test-store"
    assert config.camera_id == "test-cam"
    assert config.video_source == "data/sample.mp4"
    assert config.confidence_threshold == 0.5
    assert len(config.zones) == 1
    assert config.zones[0].id == "zone_1"
    assert config.entrance_gate.name == "entrance"
