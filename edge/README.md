# PurpleInsight: Edge Detection & Tracking Module

This module leverages **YOLOv8** and **ByteTrack** to process real-time CCTV video streams, tracking customer footprints in 2D pixel space. It calculates entrance/exit line crossings, layout zone dwell times, store occupancy, and spatial-temporal re-entries.

---

## Folder Structure

```text
edge/
├── config/
│   └── pipeline_config.yaml      # Gate coordinates, layout zone polygons, model settings
├── src/
│   ├── __init__.py
│   ├── main.py                    # Main pipeline orchestrator & OpenCV HUD renderer
│   ├── config.py                  # YAML pipeline configuration validator (Pydantic v2)
│   ├── detector.py                # Multi-threaded Video Stream Reader & YOLOv8 tracker wrapper
│   ├── analytics.py               # Vector cross-product line crossings & ray-casting polygons
│   └── event_dispatcher.py        # Event schema specifications and JSONL logger
├── tests/
│   ├── __init__.py
│   ├── test_config.py             # Configuration validation unit tests
│   ├── test_analytics.py          # Polygon, line, and state-machine unit tests
│   └── test_dispatcher.py         # JSON serialization schema unit tests
└── requirements.txt               # Module python dependencies
```

---

## Core Algorithms & Math Systems

### 1. Line Crossing (Entry / Exit)
The entrance gate is represented as a directed segment $AB$. Customer movement is represented as segment $CD$ from frame $t-1$ to $t$.
*   **Intersection**: Checked using 2D orientation triplet checks:
    $$\text{ccw}(A, B, C) = (C_y - A_y) \cdot (B_x - A_x) - (B_y - A_y) \cdot (C_x - A_x)$$
    Two segments intersect if and only if $\text{ccw}(A,B,C)$ and $\text{ccw}(A,B,D)$ have different signs, AND $\text{ccw}(C,D,A)$ and $\text{ccw}(C,D,B)$ have different signs.
*   **Directionality**: Verified by evaluating the sign of the cross product of the gate vector $\vec{AB}$ and motion vector $\vec{CD}$. A positive sign represents an **Entry (Inbound)**, while a negative sign represents an **Exit (Outbound)**.

### 2. Dwell Area Containment
Layout zones are defined as multi-point polygons. Point containment is calculated using a high-efficiency **Ray-Casting Algorithm** in pure Python. A horizontal ray is cast from the customer's coordinate to the right. If it intersects an odd number of polygon boundaries, the coordinate lies inside the zone.

### 3. Trajectory Stitching & Re-entry
If a person exits the store (crosses the gate outbound) and a new track ID is spawned near the gate within `re_entry_distance_threshold` pixels and `re_entry_time_threshold` seconds, they are stitched back to their original session ID and marked as a `re_entry`.

---

## Installation & Setup

### 1. Install Dependencies
Ensure you have Python 3.9+ installed, then install the dependencies listed in `requirements.txt`:
```bash
pip install -r edge/requirements.txt
```

*Note: Ultralytics will automatically download the pre-trained weights (`yolov8n.pt`) to your local directory during the first execution.*

### 2. Configuration
You can configure cameras, entry/exit gates, and layout zones in [pipeline_config.yaml](file:///c:/Users/Maha%20Monisha/OneDrive/Desktop/purple/edge/config/pipeline_config.yaml). Coordinates are specified in pixels relative to your camera stream's resolution (e.g. 1280x720).

---

## Running the Pipeline

### 1. Execute Tracker (Live Console & Logging)
Run the main script, passing your config file. By default, it will write events to `edge/data/events.jsonl`:
```bash
python -m edge.src.main --config edge/config/pipeline_config.yaml
```

### 2. Visual Demonstration HUD
To view the real-time annotated feed (featuring bounding boxes, trails, gate segments, semi-transparent zone polygons, and a real-time analytics overlay), pass the `--show` argument:
```bash
python -m edge.src.main --config edge/config/pipeline_config.yaml --show
```

### 3. Record Annotated Footage
To save the annotated video rendering directly to a file:
```bash
python -m edge.src.main --config edge/config/pipeline_config.yaml --output-video output.mp4
```

---

## Testing

To run the full suite of mathematical and schema validation unit tests:
```bash
pytest edge/tests/
```
