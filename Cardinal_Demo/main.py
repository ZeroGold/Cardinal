# =============================================================================
# Cardinal Inventory System - Main Application
# =============================================================================
# This script runs the main item counting and tracking loop using YOLOv8.
# It handles:
#   - Model loading
#   - ROI management
#   - Frame processing and object tracking
#   - Inventory state updates and DB logging
#   - Visualization and user interaction
# =============================================================================

import os
import subprocess, atexit, sys
import cv2
import time
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv
from ultralytics import YOLO

# -----------------------------------------------------------------------------
# 1. Environment & Configuration
# -----------------------------------------------------------------------------

# Load environment variables from .env file
load_dotenv()

# Import project configuration and constants
from config import (
    YOLO_MODEL, COCO_NAMES, CONF_THRESHOLD, NMS_THRESHOLD,
    CAMERA_ID, INPUT_WIDTH, INPUT_HEIGHT, INITIAL_SCAN_FRAMES,
    MAX_DISTANCE, MAX_MISSING_FRAMES, SHELF_ROIS, LOCATION_ID,
    DB_CONFIG
)

# -----------------------------------------------------------------------------
# 2. ROI Management (Dynamic Override)
# -----------------------------------------------------------------------------

# Try to override ROIs from a JSON file if specified
env_val = os.getenv("ROI_JSON", "").strip()
roi_json_path = None

if env_val:
    p = Path(env_val).expanduser()
    if p.is_file():
        roi_json_path = p
    elif p.is_dir():
        candidate = p / "shelf_rois.json"
        if candidate.is_file():
            roi_json_path = candidate
        else:
            logging.warning(f"ROI_JSON points to directory {p}; shelf_rois.json not found inside.")
    else:
        logging.warning(f"ROI_JSON path {p} does not exist.")

if roi_json_path is None:
    sibling = Path(__file__).with_name("shelf_rois.json")
    if sibling.is_file():
        roi_json_path = sibling

if roi_json_path:
    with roi_json_path.open("r", encoding="utf-8") as f:
        SHELF_ROIS = json.load(f)
    logging.info(f"Loaded ROI(s) from {roi_json_path}")
else:
    logging.warning("No shelf_rois.json found – using built-in ROI from config.py")

# -----------------------------------------------------------------------------
# 3. Logging Setup
# -----------------------------------------------------------------------------

def setup_logging(log_file="system.log", level=logging.INFO, max_bytes=10*1024*1024, backup_count=5):
    """Configures the logging system for both console and file output."""
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    file_handler.setFormatter(log_formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
    logging.info("Logging configured successfully.")

setup_logging()
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 4. Model & Class Names Loading
# -----------------------------------------------------------------------------

try:
    logger.info("Loading YOLO model...")
    yolo_model = YOLO(YOLO_MODEL)
    with open(COCO_NAMES, "r") as f:
        classes = [line.strip() for line in f.readlines()]
    logger.info("YOLO model loaded successfully.")
except Exception as e:
    logger.critical(f"Failed to load YOLO model or class names: {e}. Exiting.", exc_info=True)
    exit()

# -----------------------------------------------------------------------------
# 5. Database & Utilities
# -----------------------------------------------------------------------------

from db_module import InventoryDB
from utils import euclidean_distance, intersect_line_segments

# -----------------------------------------------------------------------------
# 6. Global State Variables
# -----------------------------------------------------------------------------

next_object_id = 0
frame_count = 0
tracked_objects = {}  # {id: {...}}
current_inventory_state = {}  # {item_type: count}
db_instance = None
WARMUP_FRAMES = 60
baseline_established = False

# -----------------------------------------------------------------------------
# 7. Core Frame Processing Function
# -----------------------------------------------------------------------------

def process_frame(frame, *, initial_scan_mode=False, warmup_mode=False):
    """
    Processes a single video frame:
      - Runs YOLO detection (bottles only)
      - Assigns detections to ROIs
      - Tracks objects and updates inventory state
      - Handles DB logging and visualization
    """
    global next_object_id, tracked_objects, current_inventory_state, db_instance, frame_count

    # --- 1. Run YOLOv8 Detection (bottles only) ---
    results = yolo_model.predict(
        frame,
        imgsz=INPUT_WIDTH,
        conf=CONF_THRESHOLD,
        half=True,
        device=0,
        verbose=False,
        classes=[39]  # Only bottles
    )[0]

    # --- 2. Parse Detections and Assign to ROIs ---
    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        box_w, box_h = x2 - x1, y2 - y1
        cx, cy = x1 + box_w // 2, y1 + box_h // 2
        class_id = int(box.cls[0])
        confidence = float(box.conf[0])
        roi_id = None
        for roi_cfg in SHELF_ROIS:
            rx, ry, rw, rh = roi_cfg["coords"]
            if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                roi_id = roi_cfg["id"]
                break
        detections.append([x1, y1, box_w, box_h, class_id, confidence, cx, cy, roi_id])

    # --- 3. Non-Max Suppression ---
    detections_nms = []
    if detections:
        boxes_for_nms = [[d[0], d[1], d[2], d[3]] for d in detections]
        confidences_for_nms = [d[5] for d in detections]
        idxs = cv2.dnn.NMSBoxes(boxes_for_nms, confidences_for_nms, CONF_THRESHOLD, NMS_THRESHOLD)
        if len(idxs) > 0:
            for i in idxs.flatten():
                detections_nms.append(detections[i])

    # --- 4. Update Tracked Objects ---
    for obj in tracked_objects.values():
        obj["missing_frames"] += 1

    unmatched = []
    for det in detections_nms:
        det_cx, det_cy = det[6], det[7]
        det_class_name = classes[det[4]]
        det_roi_id = det[8]
        best_id, best_d = None, 1e9
        for obj_id, obj in tracked_objects.items():
            if obj["class_name"] != det_class_name:
                continue
            d = euclidean_distance((det_cx, det_cy), obj["centroid"])
            if d < best_d and d <= MAX_DISTANCE:
                best_id, best_d = obj_id, d
        if best_id is not None:
            obj = tracked_objects[best_id]
            obj["prev_centroid"] = obj["centroid"]
            obj["centroid"] = (det_cx, det_cy)
            obj["roi_prev"] = obj["roi_curr"]
            obj["roi_curr"] = det_roi_id
            obj["confidence"] = det[5]
            obj["missing_frames"] = 0
            obj["last_seen_frame"] = frame_count
        else:
            unmatched.append(det)

    # --- 5. Add New Objects ---
    for det in unmatched:
        det_cx, det_cy = det[6], det[7]
        new_id = next_object_id
        next_object_id += 1
        tracked_objects[new_id] = {
            "centroid": (det_cx, det_cy),
            "prev_centroid": (det_cx, det_cy),
            "class_name": classes[det[4]],
            "roi_prev": None,
            "roi_curr": det[8],
            "missing_frames": 0,
            "last_seen_frame": frame_count,
            "counted_in": False,
            "counted_out": False,
            "confidence": det[5],
        }

    # --- 6. Inventory Logic: Zone Transitions ---
    for obj_id, obj in list(tracked_objects.items()):
        # if obj["missing_frames"] > MAX_MISSING_FRAMES:
        #     if obj["roi_curr"] and not obj["counted_out"]:
        if obj["missing_frames"] > MAX_MISSING_FRAMES:
            if (not warmup_mode) and obj["roi_curr"] and not obj["counted_out"]:    
                item = obj["class_name"]
                current_inventory_state[item] = max(0, current_inventory_state.get(item, 0) - 1)
                logger.info(f"[OUT] {item} (ID {obj_id}) vanished → {current_inventory_state[item]}")
                db_instance.update_inventory_count(item, -1, LOCATION_ID)
                db_instance.log_transaction(item, "OUT", 1, str(obj_id), obj["confidence"], LOCATION_ID)
            del tracked_objects[obj_id]
            continue

        entered_roi = obj["roi_prev"] is None and obj["roi_curr"] is not None
        exited_roi = obj["roi_prev"] is not None and obj["roi_curr"] is None

        if warmup_mode:
            # if obj["roi_curr"]:
            #     obj["counted_in"] = True
            continue

        if initial_scan_mode:
            if obj["roi_curr"] and not obj["counted_in"]:
                item = obj["class_name"]
                current_inventory_state[item] = current_inventory_state.get(item, 0) + 1
                obj["counted_in"] = True
        else:
            if entered_roi and not obj["counted_in"]:
                item = obj["class_name"]
                current_inventory_state[item] = current_inventory_state.get(item, 0) + 1
                obj["counted_in"] = True
                obj["counted_out"] = False
                logger.info(f"[IN]  {item} (ID {obj_id}) to {obj['roi_curr']}  →  {current_inventory_state[item]}")
                db_instance.update_inventory_count(item, 1, LOCATION_ID)
                db_instance.log_transaction(item, "IN", 1, str(obj_id), obj["confidence"], LOCATION_ID)
            if exited_roi and not obj["counted_out"]:
                item = obj["class_name"]
                current_inventory_state[item] = max(0, current_inventory_state.get(item, 0) - 1)
                obj["counted_out"] = True
                obj["counted_in"] = False
                logger.info(f"[OUT] {item} (ID {obj_id}) from {obj['roi_prev']} →  {current_inventory_state[item]}")
                db_instance.update_inventory_count(item, -1, LOCATION_ID)
                db_instance.log_transaction(item, "OUT", 1, str(obj_id), obj["confidence"], LOCATION_ID)

    # --- 7. Visualization: Draw ROIs, Objects, HUD ---
    for roi_cfg in SHELF_ROIS:
         x, y, w, h = roi_cfg["coords"]
         cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        # Dynamic counting line (20px from bottom)
        # line_y_abs = y + h - 20
        # cv2.line(frame, (x, line_y_abs), (x + w, line_y_abs), (0, 0, 255), 2)
        # cv2.putText(frame, f"ROI: {roi_cfg['id']}", (x + 5, y - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    for obj_id, obj in tracked_objects.items():
        cx, cy = obj["centroid"]
        cv2.circle(frame, (cx, cy), 4, (255, 0, 0), -1)
        cv2.putText(frame, f"{obj['class_name']}-{obj_id}", (cx - 40, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    # --- HUD: Mode & Inventory Counts ---
    mode_text = "INIT SCAN" if initial_scan_mode else "LIVE"
    cv2.putText(frame, f"MODE: {mode_text}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    y_off = 60
    for itm, cnt in current_inventory_state.items():
        cv2.putText(frame, f"{itm}: {cnt}", (10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y_off += 25

    return frame

# -----------------------------------------------------------------------------
# 8. Main Application Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
     # --- launch the Live-View GUI in a side process -----------------------
    gui_script = Path(__file__).with_name("inventory_gui.py")  # same folder
    gui_proc   = subprocess.Popen([sys.executable, str(gui_script)])

    # ensure the GUI dies when we exit (Ctrl-C or normal quit)
    atexit.register(lambda: gui_proc.poll() is None and gui_proc.terminate())

    cap = None
    try:
        cap = cv2.VideoCapture(CAMERA_ID)
        if not cap.isOpened():
            logger.critical(f"Camera ID {CAMERA_ID} failed to open. Exiting.")
            exit()

        logger.info("System starting. Press 'q' to quit.")

        db_instance = InventoryDB()
        db_instance.initialize_schema()
        current_inventory_state = db_instance.get_all_inventory_counts(LOCATION_ID)

        has_nonzero = any(cnt > 0 for cnt in current_inventory_state.values())
        baseline_established = has_nonzero
        initial_scan_required = not has_nonzero

        if current_inventory_state:
            initial_scan_required = False
            baseline_established = True
        else:
            initial_scan_required = True
            baseline_established = False

        prev_frame_time = 0
        new_frame_time = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Frame grab failed; attempting reconnect …")
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(CAMERA_ID)
                if not cap.isOpened():
                    logger.critical("Reconnection failed. Exiting.")
                    break
                continue

            frame_count += 1

            processed_frame = process_frame(
                frame.copy(),
                warmup_mode=frame_count < WARMUP_FRAMES,
                initial_scan_mode=initial_scan_required and WARMUP_FRAMES <= frame_count < WARMUP_FRAMES + INITIAL_SCAN_FRAMES
            )

            if frame_count == WARMUP_FRAMES:
                logger.info(f"Warm-up done. Inventory snapshot: {current_inventory_state}")

            if not baseline_established and frame_count >= WARMUP_FRAMES:
                baseline_established = True
                logger.info(f"Warm-up done. Inventory snapshot: {current_inventory_state}")

            if initial_scan_required and frame_count >= WARMUP_FRAMES + INITIAL_SCAN_FRAMES:
                initial_scan_required = False
                logger.info("--- Initial scan complete; switching to LIVE mode ---")
                for item, cnt in current_inventory_state.items():
                    db_instance.update_inventory_count(item, cnt, LOCATION_ID, absolute_set=True)

            # --- FPS Overlay ---
            new_frame_time = time.time()
            fps = 1 / (new_frame_time - prev_frame_time) if new_frame_time != prev_frame_time else 0
            prev_frame_time = new_frame_time
            cv2.putText(processed_frame, f"FPS: {int(fps)}",
                        (processed_frame.shape[1] - 100, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            cv2.imshow("Cardinal Inventory - Item Counter", processed_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                logger.info("Quit requested by user.")
                break

    except Exception as e:
        logger.critical(f"Unhandled critical error: {e}", exc_info=True)

    finally:
        if cap and cap.isOpened():
            cap.release()
            logger.info("Camera released.")
        cv2.destroyAllWindows()
        if db_instance:
            db_instance.close()
            logger.info("Database connection closed.")
