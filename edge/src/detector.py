import cv2
import threading
import time
import logging
from queue import Queue
from typing import List, Tuple, Optional
from ultralytics import YOLO
from edge.src.config import PipelineConfig

logger = logging.getLogger("PurpleInsight.Detector")
logger.setLevel(logging.INFO)

class VideoStreamReader:
    """Multi-threaded frame reader designed to ingest CCTV frames without lag or buffering."""
    def __init__(self, source: str | int):
        self.source = source
        self.cap = cv2.VideoCapture(source)
        
        if not self.cap.isOpened():
            raise ValueError(f"Could not open video source: {source}")

        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0

        self.stopped = False
        self.frame_queue = Queue(maxsize=2) # Keep buffer extremely small to enforce live processing
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._grab_frames, daemon=True)

    def start(self) -> "VideoStreamReader":
        self.thread.start()
        logger.info(f"Started video capture thread for source: {self.source} ({self.width}x{self.height} @ {self.fps} FPS)")
        return self

    def _grab_frames(self) -> None:
        while not self.stopped:
            ret, frame = self.cap.read()
            if not ret:
                logger.info("Video stream reached end of file or was disconnected.")
                self.stopped = True
                break

            # If queue is full, evict the oldest frame to guarantee real-time feed processing
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except Exception:
                    pass

            self.frame_queue.put(frame)

    def read(self) -> Optional[cv2.Mat]:
        """Returns the latest frame, or None if stream is stopped."""
        if self.stopped and self.frame_queue.empty():
            return None
        try:
            return self.frame_queue.get(timeout=0.5)
        except Exception:
            return None

    def release(self) -> None:
        self.stopped = True
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.cap.release()
        logger.info("Released video capture resource.")


class TrackingPipeline:
    """Orchestrates person detection and ByteTrack tracking using YOLOv8."""
    def __init__(self, config: PipelineConfig):
        self.config = config
        
        logger.info(f"Loading YOLOv8 model: {config.model_path} on device: {config.device}")
        self.model = YOLO(config.model_path)
        
        # Warmup model with a dummy image to compile kernels
        dummy_frame = cv2.imread(config.model_path) # YOLO supports passing model string as dummy to build structure, or just pass a zero array
        import numpy as np
        dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(dummy_img, verbose=False, device=self.config.device)
        logger.info("YOLOv8 tracking pipeline initialized successfully.")

    def track_frame(self, frame: cv2.Mat) -> List[Tuple[int, Tuple[float, float, float, float], float]]:
        """Processes a single frame and returns a list of tracked people: (track_id, bounding_box, confidence)."""
        # Run YOLOv8 built-in tracking loop
        results = self.model.track(
            source=frame,
            persist=True,
            tracker=self.config.tracker_config,
            conf=self.config.confidence_threshold,
            iou=self.config.iou_threshold,
            device=self.config.device,
            verbose=False
        )

        detections = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            for box in boxes:
                # We only want targets that have a successfully associated track ID
                if box.id is None:
                    continue

                # Filter target classes: COCO class 0 is 'person'
                cls_id = int(box.cls[0].item())
                if cls_id != 0:
                    continue

                track_id = int(box.id[0].item())
                conf = float(box.conf[0].item())
                xyxy = box.xyxy[0].tolist() # [x1, y1, x2, y2] bounding box vertices
                
                detections.append((track_id, xyxy, conf))

        return detections
