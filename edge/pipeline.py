"""
PurpleInsight — Multi-Camera CCTV Ingestion Pipeline
======================================================
Orchestrates YOLOv8 detection + ByteTrack tracking across all 5
Brigade Road cameras, routing all events to IngestService,
MetricsService, and AlertService in PostgreSQL.

Cameras:
    CAM 1  — Entrance & Exit lobby (gate crossing)
    CAM 2  — Top shelf brand row (EB Korean → Accessories)
    CAM 3  — Central FOH, Makeup Unit, Fragrance/Nail
    CAM 4  — Bottom shelf brand row (Maybelline → Streax)
    CAM 5  — Checkout counter & PMU

Usage:
    # Single camera run
    python -m edge.pipeline --config edge/config/cameras/cam1_entrance.yaml --show

    # Full store run (all 5 cams)
    python -m edge.pipeline --all-cameras --db-url postgresql://...

    # Run with annotated video output
    python -m edge.pipeline --config edge/config/cameras/cam_brigade_full_store.yaml \\
        --output-video edge/output/brigade_annotated.mp4
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from typing import Dict, List, Optional

import cv2
import numpy as np

# Edge-layer imports
from edge.src.config import load_config, PipelineConfig
from edge.src.detector import VideoStreamReader, TrackingPipeline
from edge.src.analytics import AnalyticsEngine
from edge.src.event_dispatcher import (
    BaseEvent,
    PersonEntryEvent,
    PersonExitEvent,
    ZoneDwellEvent,
    OccupancyUpdateEvent,
    QueueUpdateEvent,
    QueueAlertEvent,
    ConsoleDispatcher,
    FileDispatcher,
    APIDispatcher,
    CompositeDispatcher,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PurpleInsight.Pipeline")

# ─── Zone Color Palette ──────────────────────────────────────────────────────

ZONE_COLORS: Dict[str, tuple] = {
    "entrance":     (34,  197, 94),   # green
    "brand_zone":   (139, 92,  246),  # purple
    "product_shelf":(245, 158, 11),   # amber
    "checkout":     (239, 68,  68),   # red
    "circulation":  (59,  130, 246),  # blue
    "service_zone": (20,  184, 166),  # teal
    "display_zone": (107, 114, 128),  # grey
    "default":      (156, 163, 175),  # light grey
}


# ─── Frame Annotation ────────────────────────────────────────────────────────

def draw_annotations(
    frame: cv2.Mat,
    detections: List,
    engine: AnalyticsEngine,
    fps: float,
    cam_label: str = "CAM",
) -> cv2.Mat:
    """
    Renders the PurpleInsight premium HUD overlay on a single frame.

    Draws:
        - Zone polygon overlays (colour-coded by zone type)
        - Entry/exit gate line with direction arrow
        - Bounding boxes + track IDs + trajectory trails
        - Queue wait-time label under feet
        - Live analytics HUD panel (top-left)
        - Camera label + FPS counter
    """
    overlay = frame.copy()
    config = engine.config
    now = time.time()

    # ── 1. Zone Polygon Overlays ─────────────────────────────────────────────
    for zone in config.zones:
        pts = np.array(zone.polygon, np.int32).reshape((-1, 1, 2))
        zone_type = getattr(zone, "zone_type", "default") if hasattr(zone, "zone_type") else "default"
        color = ZONE_COLORS.get(zone_type, ZONE_COLORS["default"])

        # Translucent fill
        cv2.fillPoly(overlay, [pts], color)
        # Solid outline
        cv2.polylines(frame, [pts], True, color, 2)

        # Zone label at centroid
        M = cv2.moments(pts)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            cv2.putText(
                frame, zone.name[:22],
                (cx - 60, cy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA
            )

    # Blend overlay for translucent polygon fill (alpha=0.18)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    # ── 2. Entry Gate ────────────────────────────────────────────────────────
    gate = config.entrance_gate
    p1, p2 = tuple(gate.line_a), tuple(gate.line_b)
    cv2.line(frame, p1, p2, (168, 85, 247), 4)
    cv2.circle(frame, p1, 8, (168, 85, 247), -1)
    cv2.circle(frame, p2, 8, (168, 85, 247), -1)
    mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
    cv2.arrowedLine(frame, (mid[0], mid[1] + 30), (mid[0], mid[1] - 30), (59, 130, 246), 2, tipLength=0.3)
    cv2.putText(frame, "ENTRY", (mid[0] - 25, mid[1] - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (59, 130, 246), 1)

    # ── 3. Tracked Persons ───────────────────────────────────────────────────
    for track_id, bbox, conf in detections:
        x1, y1, x2, y2 = map(int, bbox)
        orig_id = engine.get_original_track_id(track_id)
        hist = engine.tracks.get(track_id)
        is_inside = hist.has_entered if hist else False
        color = (34, 197, 94) if is_inside else (156, 163, 175)

        # Bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        # Track label
        lbl = f"#{orig_id} ({conf:.2f})"
        cv2.putText(frame, lbl, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

        # Feet point
        feet = (int((x1 + x2) / 2), y2)
        cv2.circle(frame, feet, 5, (239, 68, 68), -1)

        # Trajectory trail
        if hist and len(hist.points) > 2:
            pts_trail = np.array(hist.points[-20:], np.int32)
            cv2.polylines(frame, [pts_trail], False, (245, 158, 11), 1)

        # Queue wait-time label
        if hist and "checkout_queue" in hist.active_dwells:
            wait = now - hist.active_dwells["checkout_queue"]["entered_at"]
            cv2.putText(
                frame, f"Wait:{int(wait)}s",
                (x1, y2 + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (29, 78, 216), 1, cv2.LINE_AA
            )

    # ── 4. HUD Panel ─────────────────────────────────────────────────────────
    hud = np.zeros((195, 300, 3), np.uint8)
    h, w = hud.shape[:2]
    roi = frame[10: 10 + h, 10: 10 + w]
    cv2.addWeighted(hud, 0.55, roi, 0.45, 0, roi)

    occupancy = sum(
        1 for tid in engine.active_in_store_tracks
        if tid in engine.tracks and engine.tracks[tid].last_seen >= now - 2.0
    )

    def hud_text(text, y, color=(255, 255, 255), scale=0.45):
        cv2.putText(frame, text, (18, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)

    hud_text("PURPLEINSIGHT", 32, (168, 85, 247), 0.55)
    cv2.line(frame, (18, 40), (305, 40), (60, 60, 60), 1)
    hud_text(f"{cam_label}", 60, (245, 158, 11), 0.42)
    hud_text(f"Occupancy : {occupancy}", 78)
    hud_text(f"Active Tracks: {len(engine.tracks)}", 96)

    y_off = 116
    for zone in config.zones[:3]:
        cnt = sum(
            1 for tr in engine.tracks.values()
            if tr.last_seen >= now - 2.0 and zone.id in tr.active_dwells
        )
        hud_text(f"  {zone.name[:18]}: {cnt}", y_off, (209, 213, 219), 0.38)
        y_off += 18

    hud_text(f"FPS: {fps:.1f}", 185, (59, 130, 246), 0.4)

    return frame


# ─── Single Camera Worker ────────────────────────────────────────────────────

class CameraWorker:
    """
    Self-contained processing thread for a single CCTV camera.

    Lifecycle:
        start() → frames read → YOLO detect → analytics → events dispatched
        stop()  → graceful shutdown, resources released
    """

    def __init__(
        self,
        config: PipelineConfig,
        dispatcher,
        cam_label: str = "CAM",
        show: bool = False,
        output_video: str = "",
        db_session_factory=None,
    ):
        self.config = config
        self.dispatcher = dispatcher
        self.cam_label = cam_label
        self.show = show
        self.output_video = output_video
        self.db_session_factory = db_session_factory

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"worker-{cam_label}")

        self.fps: float = 0.0
        self.frame_count: int = 0
        self.error: Optional[Exception] = None

    def start(self) -> "CameraWorker":
        self._thread.start()
        logger.info(f"[{self.cam_label}] Worker thread started.")
        return self

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=10.0)
        logger.info(f"[{self.cam_label}] Worker thread stopped.")

    def _run(self) -> None:
        """Main camera loop: ingest → detect → track → analyse → dispatch."""
        try:
            # ── Video reader ─────────────────────────────────────────────────
            reader = VideoStreamReader(self.config.video_source).start()

            # ── YOLO + ByteTrack pipeline ────────────────────────────────────
            pipeline = TrackingPipeline(self.config)

            # ── Analytics state engine ───────────────────────────────────────
            engine = AnalyticsEngine(self.config)

            # ── Optional video writer ────────────────────────────────────────
            writer = None
            if self.output_video:
                os.makedirs(os.path.dirname(os.path.abspath(self.output_video)), exist_ok=True)
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(
                    self.output_video, fourcc,
                    reader.fps, (reader.width, reader.height)
                )
                logger.info(f"[{self.cam_label}] Writing annotated output to: {self.output_video}")

            t_start = time.time()
            fps_tick = 0

            while not self._stop_event.is_set() and not reader.stopped:
                frame = reader.read()
                if frame is None:
                    break

                # ── Detection + Tracking ──────────────────────────────────
                detections = pipeline.track_frame(frame)

                # ── Analytics state update → Event generation ─────────────
                events: List[BaseEvent] = engine.process_tracks(detections)

                # ── Dispatch all events ────────────────────────────────────
                for event in events:
                    self.dispatcher.dispatch(event)

                # ── Direct DB routing ──────────────────────────────────────
                if self.db_session_factory:
                    try:
                        from backend.services.cv_event_bus import CVEventRouter, adapt_edge_event
                        with self.db_session_factory() as db:
                            router = CVEventRouter(db)
                            for event in events:
                                cv_event = adapt_edge_event(event)
                                if cv_event:
                                    router.route(cv_event)
                    except Exception as db_exc:
                        logger.error(f"[{self.cam_label}] Error in direct DB event routing: {db_exc}", exc_info=True)

                # ── FPS measurement ───────────────────────────────────────
                self.frame_count += 1
                fps_tick += 1
                if fps_tick >= 15:
                    elapsed = time.time() - t_start
                    self.fps = 15.0 / max(elapsed, 1e-6)
                    t_start = time.time()
                    fps_tick = 0

                # ── Optional rendering ─────────────────────────────────────
                if self.show or writer:
                    annotated = draw_annotations(frame, detections, engine, self.fps, self.cam_label)
                    if writer:
                        writer.write(annotated)
                    if self.show:
                        cv2.imshow(f"PurpleInsight — {self.cam_label}", annotated)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            logger.info(f"[{self.cam_label}] Manual stop via 'q' key.")
                            break

        except Exception as exc:
            logger.error(f"[{self.cam_label}] Fatal error in camera worker: {exc}", exc_info=True)
            self.error = exc
        finally:
            if "reader" in dir():
                reader.release()
            if "writer" in dir() and writer:
                writer.release()
            cv2.destroyAllWindows()


# ─── Multi-Camera Pipeline Orchestrator ─────────────────────────────────────

CAMERA_CONFIGS = {
    "cam1": "edge/config/cameras/cam1_entrance.yaml",
    "cam2": "edge/config/cameras/cam2_top_shelves.yaml",
    "cam3": "edge/config/cameras/cam3_foh_makeup.yaml",
    "cam4": "edge/config/cameras/cam4_bottom_shelves.yaml",
    "cam5": "edge/config/cameras/cam5_checkout.yaml",
}


class MultiCameraPipeline:
    """
    Orchestrates concurrent CameraWorker threads for all 5 Brigade Road cameras.

    Events from all cameras are multiplexed through a shared CompositeDispatcher
    and routed to the PurpleInsight FastAPI backend.
    """

    def __init__(
        self,
        api_base_url: str = "http://127.0.0.1:8000/api/v1/telemetry",
        show: bool = False,
        output_dir: str = "",
        camera_filter: Optional[List[str]] = None,
        db_session_factory=None,
    ):
        self.api_base_url = api_base_url
        self.show = show
        self.output_dir = output_dir
        self.camera_filter = camera_filter or list(CAMERA_CONFIGS.keys())
        self.db_session_factory = db_session_factory
        self.workers: List[CameraWorker] = []

    def _build_dispatcher(self) -> CompositeDispatcher:
        dispatchers = [
            ConsoleDispatcher(),
            FileDispatcher("edge/data/events.jsonl"),
            APIDispatcher(self.api_base_url),
        ]
        return CompositeDispatcher(dispatchers)

    def start(self) -> None:
        """Load configs and spin up all camera workers."""
        dispatcher = self._build_dispatcher()

        for cam_key in self.camera_filter:
            cfg_path = CAMERA_CONFIGS.get(cam_key)
            if not cfg_path or not os.path.exists(cfg_path):
                logger.warning(f"Config not found for {cam_key}: {cfg_path}. Skipping.")
                continue

            try:
                config = load_config(cfg_path)
            except Exception as e:
                logger.error(f"Failed to load config for {cam_key}: {e}")
                continue

            output_video = ""
            if self.output_dir:
                output_video = os.path.join(self.output_dir, f"{cam_key}_annotated.mp4")

            worker = CameraWorker(
                config=config,
                dispatcher=dispatcher,
                cam_label=cam_key.upper(),
                show=self.show,
                output_video=output_video,
                db_session_factory=self.db_session_factory,
            )
            worker.start()
            self.workers.append(worker)
            logger.info(f"Camera worker {cam_key.upper()} initialized.")

    def wait(self) -> None:
        """Block until all camera workers complete."""
        try:
            while any(w._thread.is_alive() for w in self.workers):
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt — shutting down all camera workers.")
            self.stop()

    def stop(self) -> None:
        for worker in self.workers:
            worker.stop()
        cv2.destroyAllWindows()
        logger.info("All camera workers stopped.")


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m edge.pipeline",
        description="PurpleInsight — Multi-Camera CCTV Ingestion Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single camera (entrance)
  python -m edge.pipeline --config edge/config/cameras/cam1_entrance.yaml --show

  # All 5 cameras
  python -m edge.pipeline --all-cameras

  # All cameras, save annotated video per camera
  python -m edge.pipeline --all-cameras --output-dir edge/output/

  # Target remote backend
  python -m edge.pipeline --all-cameras --api-url http://192.168.1.10:8000/api/v1/telemetry
        """,
    )
    p.add_argument("--config", type=str, default="", help="Path to a single camera YAML config.")
    p.add_argument("--all-cameras", action="store_true", help="Run all 5 Brigade Road cameras concurrently.")
    p.add_argument("--cameras", nargs="+", choices=list(CAMERA_CONFIGS.keys()),
                   help="Subset of cameras to run (e.g. --cameras cam1 cam5).")
    p.add_argument("--api-url", type=str, default="http://127.0.0.1:8000/api/v1/telemetry",
                   help="PurpleInsight backend telemetry API base URL.")
    p.add_argument("--db-url", type=str, default="",
                   help="Optional database connection URL for direct event routing (e.g. sqlite:///store_intelligence.db).")
    p.add_argument("--show", action="store_true", help="Display live annotated video window.")
    p.add_argument("--output-video", type=str, default="",
                   help="[Single-cam mode] Path to save annotated output video.")
    p.add_argument("--output-dir", type=str, default="",
                   help="[Multi-cam mode] Directory to save per-camera annotated video files.")
    p.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG-level logging.")
    return p


def main() -> None:
    args = build_parser().parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    db_session_factory = None
    if args.db_url:
        from backend.database.connection import init_db
        logger.info(f"Initializing database connection: {args.db_url}")
        init_db(args.db_url)
        from backend.database.connection import SessionLocal
        db_session_factory = SessionLocal

    # ── Multi-camera mode ────────────────────────────────────────────────────
    if args.all_cameras or args.cameras:
        cam_filter = args.cameras if args.cameras else list(CAMERA_CONFIGS.keys())
        pipeline = MultiCameraPipeline(
            api_base_url=args.api_url,
            show=args.show,
            output_dir=args.output_dir,
            camera_filter=cam_filter,
            db_session_factory=db_session_factory,
        )
        pipeline.start()
        pipeline.wait()
        return

    # ── Single-camera mode ───────────────────────────────────────────────────
    cfg_path = args.config or "edge/config/cameras/cam_brigade_full_store.yaml"
    if not os.path.exists(cfg_path):
        logger.error(f"Config file not found: {cfg_path}")
        sys.exit(1)

    try:
        config = load_config(cfg_path)
    except Exception as e:
        logger.error(f"Failed to load pipeline config: {e}")
        sys.exit(1)

    dispatcher = CompositeDispatcher([
        ConsoleDispatcher(),
        FileDispatcher("edge/data/events.jsonl"),
        APIDispatcher(args.api_url),
    ])

    worker = CameraWorker(
        config=config,
        dispatcher=dispatcher,
        cam_label=cfg_path.split("/")[-1].replace(".yaml", "").upper(),
        show=args.show,
        output_video=args.output_video,
        db_session_factory=db_session_factory,
    )
    worker.start()

    try:
        while worker._thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Interrupt received — stopping worker.")
        worker.stop()


if __name__ == "__main__":
    main()
