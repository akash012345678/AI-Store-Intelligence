import argparse
import cv2
import time
import os
import logging
import numpy as np
from edge.src.config import load_config
from edge.src.event_dispatcher import ConsoleDispatcher, FileDispatcher, CompositeDispatcher, APIDispatcher
from edge.src.analytics import AnalyticsEngine
from edge.src.detector import VideoStreamReader, TrackingPipeline

# Setup root logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("PurpleInsight.Main")

def draw_annotations(frame: cv2.Mat, detections, analytics_engine: AnalyticsEngine, fps: float) -> cv2.Mat:
    """Draws a premium HUD visualization on the frames, including gates, zones, trails, and stats."""
    overlay = frame.copy()
    config = analytics_engine.config

    # 1. Draw Zones (Polygons) with translucent filling
    for zone in config.zones:
        pts = np.array(zone.polygon, np.int32)
        pts = pts.reshape((-1, 1, 2))
        
        # Color palettes based on zone type
        color = (139, 92, 246) # Purple for promotional/snacks
        if "checkout" in zone.id:
            color = (239, 68, 68) # Red for checkout queue
        elif "fresh" in zone.id:
            color = (34, 197, 94) # Green for fresh produce
            
        # Draw translucent polygon
        cv2.fillPoly(overlay, [pts], color)
        
        # Draw outline
        cv2.polylines(frame, [pts], True, color, 2)
        
        # Label zone
        moments = cv2.moments(pts)
        if moments["m00"] != 0:
            cx = int(moments["m10"] / moments["m00"])
            cy = int(moments["m01"] / moments["m00"])
            cv2.putText(frame, zone.name, (cx - 60, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    # Blend overlay with original frame for opacity
    alpha = 0.18
    frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

    # 2. Draw Entrance Gate (Directed line)
    gate = config.entrance_gate
    p1 = tuple(gate.line_a)
    p2 = tuple(gate.line_b)
    # Bright purple/violet line
    cv2.line(frame, p1, p2, (168, 85, 247), 4)
    cv2.circle(frame, p1, 8, (168, 85, 247), -1)
    cv2.circle(frame, p2, 8, (168, 85, 247), -1)
    
    # Draw simple direction indicator arrows
    mid_x = (p1[0] + p2[0]) // 2
    mid_y = (p1[1] + p2[1]) // 2
    cv2.arrowedLine(frame, (mid_x, mid_y + 30), (mid_x, mid_y - 30), (59, 130, 246), 2, tipLength=0.3)
    cv2.putText(frame, "ENTRY DIRECTION", (mid_x - 60, mid_y - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (59, 130, 246), 1)

    # 3. Draw Tracked Shoppers (Bounding Boxes & Trails)
    for track_id, bbox, conf in detections:
        x1, y1, x2, y2 = map(int, bbox)
        original_id = analytics_engine.get_original_track_id(track_id)
        
        # Determine color based on whether track has crossed/entered the store
        track_hist = analytics_engine.tracks.get(track_id)
        is_inside = track_hist.has_entered if track_hist else False
        box_color = (34, 197, 94) if is_inside else (156, 163, 175) # Green if entered, Grey otherwise

        # Bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
        
        # Label with original ID
        label = f"Shopper #{original_id} ({conf:.2f})"
        cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)

        # Plot feet footprint point
        feet_point = (int((x1 + x2) / 2), int(y2))
        cv2.circle(frame, feet_point, 5, (239, 68, 68), -1)

        # Draw Trajectory trail
        if track_hist and len(track_hist.points) > 1:
            pts = np.array(track_hist.points, np.int32)
            cv2.polylines(frame, [pts], False, (245, 158, 11), 2)
            
        # Draw active checkout queue wait-time directly under feet
        if track_hist and "checkout_queue" in track_hist.active_dwells:
            wait_time = time.time() - track_hist.active_dwells["checkout_queue"]["entered_at"]
            wait_lbl = f"Wait: {int(wait_time)}s"
            # Draw distinct bold orange warning label under feet coordinate
            cv2.putText(frame, wait_lbl, (x1, y2 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (29, 78, 216), 2)

    # 4. Premium Analytics HUD Panel
    hud_bg = np.zeros((180, 320, 3), dtype=np.uint8)
    # Blend HUD panel onto upper left corner
    h_h, h_w = hud_bg.shape[:2]
    frame_hud_region = frame[10:10+h_h, 10:10+h_w]
    cv2.addWeighted(hud_bg, 0.6, frame_hud_region, 0.4, 0, frame_hud_region)
    
    # Overlay metrics
    occupancy = len([tid for tid in analytics_engine.active_in_store_tracks if tid in analytics_engine.tracks and analytics_engine.tracks[tid].last_seen >= time.time() - 2.0])
    
    cv2.putText(frame, "PURPLEINSIGHT HUD", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (168, 85, 247), 2)
    cv2.line(frame, (20, 38), (310, 38), (80, 80, 80), 1)
    
    cv2.putText(frame, f"Live Store Occupancy: {occupancy}", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cv2.putText(frame, f"Active Tracks: {len(analytics_engine.tracks)}", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    # Show counts for top 2 zones
    y_offset = 115
    for idx, zone in enumerate(config.zones[:2]):
        zone_count = 0
        for track in analytics_engine.tracks.values():
            if track.last_seen >= time.time() - 2.0 and zone.id in track.active_dwells:
                zone_count += 1
        cv2.putText(frame, f"  {zone.name}: {zone_count}", (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (209, 213, 219), 1)
        y_offset += 20

    cv2.putText(frame, f"System Throughput: {fps:.1f} FPS", (20, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (59, 130, 246), 1)

    return frame

def main():
    parser = argparse.ArgumentParser(description="PurpleInsight Edge Detection & Tracking Pipeline")
    parser.add_argument("--config", type=str, default="edge/config/pipeline_config.yaml", help="Path to config file")
    parser.add_argument("--show", action="store_true", help="Display visual video output window")
    parser.add_argument("--output-video", type=str, default="", help="Path to save annotated output video file")
    args = parser.parse_args()

    logger.info("Initializing PurpleInsight Edge Module...")
    
    # 1. Load configuration
    try:
        config = load_config(args.config)
        logger.info("Configuration parsed successfully.")
    except Exception as e:
        logger.error(f"Fatal error loading config: {e}")
        return

    # 2. Setup Dispatchers
    console_disp = ConsoleDispatcher()
    file_disp = FileDispatcher("edge/data/events.jsonl")
    api_disp = APIDispatcher("http://127.0.0.1:8000/api/v1/telemetry")
    dispatcher = CompositeDispatcher([console_disp, file_disp, api_disp])

    # 3. Initialize processing pipeline elements
    pipeline = TrackingPipeline(config)
    analytics = AnalyticsEngine(config)

    # 4. Initialize Stream Ingest
    try:
        # Convert video source to integer if it represents camera index
        reader = VideoStreamReader(config.video_source).start()
    except Exception as e:
        logger.error(f"Failed to initialize video capture stream: {e}")
        return

    # Setup Video Writer if requested
    writer = None
    if args.output_video:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_video)), exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(args.output_video, fourcc, reader.fps, (reader.width, reader.height))
        logger.info(f"Saving output rendering to: {args.output_video}")

    frame_count = 0
    t_start = time.time()
    fps = 0.0

    try:
        while not reader.stopped:
            frame = reader.read()
            if frame is None:
                # Video file finished
                break

            # Run detection and tracking
            detections = pipeline.track_frame(frame)
            
            # Feed tracking updates to analytics state engine
            events = analytics.process_tracks(detections)
            
            # Dispatch all yielded events down the line
            for event in events:
                dispatcher.dispatch(event)

            # Frame rate measurement
            frame_count += 1
            if frame_count % 15 == 0:
                t_now = time.time()
                fps = 15.0 / (t_now - t_start)
                t_start = t_now

            # Render annotations if displaying or saving
            if args.show or writer:
                annotated_frame = draw_annotations(frame, detections, analytics, fps)
                
                if writer:
                    writer.write(annotated_frame)
                
                if args.show:
                    cv2.imshow("PurpleInsight AI Store Intelligence Edge Pipeline", annotated_frame)
                    # Stop on key press 'q'
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        logger.info("Termination key 'q' pressed by operator.")
                        break

    except KeyboardInterrupt:
        logger.info("System execution interrupted by user signal.")
    finally:
        # Release resources gracefully
        reader.release()
        if writer:
            writer.release()
        cv2.destroyAllWindows()
        logger.info("Pipeline shut down successfully.")

if __name__ == "__main__":
    main()
