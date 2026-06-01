import os
import yaml
from typing import List, Tuple, Union
from pydantic import BaseModel, Field, field_validator

class GateConfig(BaseModel):
    name: str
    line_a: Tuple[int, int] = Field(..., description="Starting point (x, y) of the gate segment")
    line_b: Tuple[int, int] = Field(..., description="Ending point (x, y) of the gate segment")

    @field_validator("line_a", "line_b")
    @classmethod
    def validate_point(cls, v: Tuple[int, int]) -> Tuple[int, int]:
        if len(v) != 2:
            raise ValueError("Coordinates must be exactly 2 integers (x, y)")
        if v[0] < 0 or v[1] < 0:
            raise ValueError("Coordinates cannot be negative")
        return v

class ZoneConfig(BaseModel):
    id: str
    name: str
    polygon: List[Tuple[int, int]] = Field(..., description="List of vertices defining the zone boundary")

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, v: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        if len(v) < 3:
            raise ValueError("A polygon must have at least 3 vertices")
        for point in v:
            if len(point) != 2:
                raise ValueError("Polygon coordinates must be exactly 2 integers (x, y)")
            if point[0] < 0 or point[1] < 0:
                raise ValueError("Polygon coordinates cannot be negative")
        return v

class PipelineConfig(BaseModel):
    store_id: str
    camera_id: str
    video_source: Union[str, int]
    model_path: str = "yolov8n.pt"
    confidence_threshold: float = Field(0.4, ge=0.0, le=1.0)
    iou_threshold: float = Field(0.45, ge=0.0, le=1.0)
    tracker_config: str = "bytetrack.yaml"
    device: str = "cpu"
    
    occupancy_interval: float = Field(5.0, gt=0.0)
    dwell_cooldown_seconds: float = Field(3.0, ge=0.0)
    re_entry_time_threshold: float = Field(15.0, ge=0.0)
    re_entry_distance_threshold: float = Field(80.0, ge=0.0)

    entrance_gate: GateConfig
    zones: List[ZoneConfig] = Field(default_factory=list)

    @field_validator("video_source")
    @classmethod
    def validate_source(cls, v: Union[str, int]) -> Union[str, int]:
        # If it's a numeric string, convert to int for webcam index
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

def load_config(file_path: str) -> PipelineConfig:
    """Loads and validates a pipeline configuration from a YAML file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    
    with open(file_path, "r") as f:
        config_data = yaml.safe_load(f)
    
    return PipelineConfig(**config_data)
