# main.py

import cv2
import numpy as np
import time
import logging
from logging.handlers import RotatingFileHandler # For file logging

# --- 1. Import Configurations (from config.py) ---
from config import (
    YOLO_CFG, YOLO_WEIGHTS, COCO_NAMES, CONF_THRESHOLD, NMS_THRESHOLD,
    CAMERA_ID, INPUT_WIDTH, INPUT_HEIGHT, INITIAL_SCAN_FRAMES,
    MAX_DISTANCE, MAX_MISSING_FRAMES, SHELF_ROIS, LOCATION_ID,
    DB_CONFIG # Used implicitly by db_module
)

# --- 2. Import Database Module (from db_module.py) ---
from db_module import InventoryDB

# --- 3. Import Utilities (from utils.py) ---
from utils import euclidean_distance, intersect_line_segments

# --- Global Variables ---
# These will be modified by various functions, hence declared globally
next_object_id = 0
frame_count = 0
tracked_objects = {} # {id: {centroid, prev_centroid, class_name, missing_frames, last_seen_frame, counted_in, counted_out, initial_scan_counted, roi_id, confidence}}
current_inventory_state = {} # {item_type: count} (In-memory mirror of DB state for display/fast lookup)
db_instance = None # Will be initialized later

# --- 3. Robust Error Handling and Logging Setup ---
def setup_logging(log_file="system.log", level=logging.INFO, max_bytes=10*1024*1024, backup_count=5):
    """Configures the logging system."""
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes, # 10 MB
        backupCount=backup_count # Keep 5 backup log files
    )
    file_handler.setFormatter(log_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Add handlers only if not already present
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    logging.info("Logging configured successfully.")

# Call logging setup at the very beginning of the script execution
setup_logging()
logger = logging.getLogger(__name__) # Logger for this module

# --- Initialize DNN outside the main loop for efficiency ---
try:
    logger.info("Loading YOLO model...")
    net = cv2.dnn.readNetFromDarknet(YOLO_CFG, YOLO_WEIGHTS)
    # --- COMMENT OUT OR REMOVE THESE TWO LINES ---
    # net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA) # Use CUDA if available
    # net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA) # Use CUDA if available

    # --- INSTEAD, EXPLICITLY SET TO CPU ---
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV) # Or cv2.dnn.DNN_BACKEND_DEFAULT
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    output_layers = [net.getLayerNames()[i - 1] for i in net.getUnconnectedOutLayers()]
    with open(COCO_NAMES, "r") as f:
        classes = [line.strip() for line in f.readlines()]
    logger.info("YOLO model loaded successfully.")
except Exception as e:
    logger.critical(f"Failed to load YOLO model or class names: {e}. Exiting.", exc_info=True)
    exit() # Critical error, cannot proceed

# --- Core Frame Processing Function (for modularity) ---
def process_frame(frame, initial_scan_mode=False):
    """
    Processes a single frame for object detection, tracking, and inventory updates.
    Handles both initial scan mode and normal line-crossing mode.
    """
    global next_object_id, tracked_objects, current_inventory_state, db_instance, frame_count

    # --- Object Detection ---
    all_current_frame_detections = [] # Detections across all ROIs
    for roi_cfg in SHELF_ROIS:
        x_roi, y_roi, w_roi, h_roi = roi_cfg["coords"]
        
        # Ensure ROI is within frame bounds (important for dynamic environments like trucks)
        x_roi = max(0, min(x_roi, frame.shape[1] - 1))
        y_roi = max(0, min(y_roi, frame.shape[0] - 1))
        w_roi = max(1, min(w_roi, frame.shape[1] - x_roi))
        h_roi = max(1, min(h_roi, frame.shape[0] - y_roi))
        
        shelf_roi_frame = frame[y_roi : y_roi + h_roi, x_roi : x_roi + w_roi]

        if shelf_roi_frame.size == 0 or shelf_roi_frame.shape[0] == 0 or shelf_roi_frame.shape[1] == 0:
            logger.warning(f"ROI '{roi_cfg['id']}' is invalid or empty ({w_roi}x{h_roi}). Skipping detection for this ROI.")
            continue # Skip detection for invalid ROI

        blob = cv2.dnn.blobFromImage(shelf_roi_frame, 1 / 255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False)
        net.setInput(blob)
        outs = net.forward(output_layers)

        detections_in_roi = [] # Raw detections for this ROI
        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                if confidence > CONF_THRESHOLD:
                    center_x = int(detection[0] * w_roi)
                    center_y = int(detection[1] * h_roi)
                    box_w = int(detection[2] * w_roi)
                    box_h = int(detection[3] * h_roi)
                    # Store absolute centroid and ROI ID
                    # Note: x_box, y_box are relative to ROI. d[0] and d[1] from detection are normalized to ROI.
                    x_box = int(center_x - box_w / 2) # X relative to ROI's top-left
                    y_box = int(center_y - box_h / 2) # Y relative to ROI's top-left
                    detections_in_roi.append([x_box, y_box, box_w, box_h, class_id, float(confidence), center_x + x_roi, center_y + y_roi, roi_cfg["id"]])

        # Apply NMS per ROI
        current_roi_detections_nms = []
        if len(detections_in_roi) > 0:
            # Boxes for NMS need to be in absolute frame coordinates
            boxes_for_nms = [[d[0] + x_roi, d[1] + y_roi, d[2], d[3]] for d in detections_in_roi]
            confidences_for_nms = [d[5] for d in detections_in_roi]
            indexes = cv2.dnn.NMSBoxes(boxes_for_nms, confidences_for_nms, CONF_THRESHOLD, NMS_THRESHOLD)
            if len(indexes) > 0:
                for i in indexes.flatten():
                    current_roi_detections_nms.append(detections_in_roi[i])
        
        all_current_frame_detections.extend(current_roi_detections_nms)

    # --- Object Tracking: Update missing frames for old objects ---
    for obj_id in tracked_objects:
        tracked_objects[obj_id]['missing_frames'] += 1

    # --- Object Tracking: Match current detections to tracked objects ---
    unmatched_detections = []
    for det in all_current_frame_detections:
        det_class_id = det[4]
        det_confidence = det[5]
        det_centroid_abs = (det[6], det[7])
        det_roi_id = det[8]
        det_class_name = classes[det_class_id]

        matched_id = None
        for obj_id, obj_data in tracked_objects.items():
            # Match based on proximity and class name within the same ROI
            distance = euclidean_distance(det_centroid_abs, obj_data['centroid'])
            if distance < MAX_DISTANCE and obj_data['class_name'] == det_class_name and obj_data['roi_id'] == det_roi_id:
                matched_id = obj_id
                break # Found a match

        if matched_id is not None:
            # Update existing tracked object's position and reset missing frames count
            tracked_objects[matched_id]['prev_centroid'] = tracked_objects[matched_id]['centroid']
            tracked_objects[matched_id]['centroid'] = det_centroid_abs
            tracked_objects[matched_id]['missing_frames'] = 0
            tracked_objects[matched_id]['last_seen_frame'] = frame_count
            tracked_objects[matched_id]['confidence'] = det_confidence # Update confidence
        else:
            # This is a new detection, to be added or processed by line crossing
            unmatched_detections.append(det)

    # --- Logic based on system state (Initial Scan vs. Normal Operation) ---
    if initial_scan_mode:
        # During initial scan, all new detections in ROIs are considered 'IN'
        for det in unmatched_detections:
            det_class_id = det[4]
            det_confidence = det[5]
            det_centroid_abs = (det[6], det[7])
            det_roi_id = det[8]
            det_class_name = classes[det_class_id]

            new_object_id = next_object_id
            next_object_id += 1
            tracked_objects[new_object_id] = {
                'centroid': det_centroid_abs,
                'prev_centroid': det_centroid_abs, # Prev and current are same initially
                'class_name': det_class_name,
                'missing_frames': 0,
                'last_seen_frame': frame_count,
                'counted_in': True,  # Mark as already 'counted in' by initial scan
                'counted_out': False,
                'initial_scan_counted': True, # Specific flag for initial scan objects
                'roi_id': det_roi_id,
                'confidence': det_confidence
            }
            # Update in-memory state. DB update for initial scan is done once transition.
            current_inventory_state[det_class_name] = current_inventory_state.get(det_class_name, 0) + 1
            logger.info(f"[Initial Scan] Detected {det_class_name} (ID: {new_object_id}) in {det_roi_id}. In-memory count: {current_inventory_state[det_class_name]}")

        # Remove objects that were part of initial scan but disappeared for too long during the scan
        objects_to_remove_from_scan = []
        for obj_id, obj_data in tracked_objects.items():
            if obj_data['missing_frames'] > MAX_MISSING_FRAMES and obj_data.get('initial_scan_counted', False):
                 objects_to_remove_from_scan.append(obj_id)
                 removed_class = obj_data['class_name']
                 current_inventory_state[removed_class] = max(0, current_inventory_state.get(removed_class, 0) - 1)
                 logger.info(f"[Initial Scan Clean-up] {removed_class} (ID: {obj_id}) disappeared from {obj_data['roi_id']} during scan. In-memory count: {current_inventory_state[removed_class]}")

        for obj_id in objects_to_remove_from_scan:
            del tracked_objects[obj_id]

    else: # Normal Operation: Line Crossing Logic
        # Process unmatched detections (potential new objects that need to cross)
        for det in unmatched_detections:
            det_class_id = det[4]
            det_confidence = det[5]
            det_centroid_abs = (det[6], det[7])
            det_roi_id = det[8]
            det_class_name = classes[det_class_id]
            
            # Add to tracked objects, but not counted_in yet (waiting for line crossing)
            new_object_id = next_object_id
            next_object_id += 1
            tracked_objects[new_object_id] = {
                'centroid': det_centroid_abs,
                'prev_centroid': det_centroid_abs,
                'class_name': det_class_name,
                'missing_frames': 0,
                'last_seen_frame': frame_count,
                'counted_in': False, # Not yet counted in
                'counted_out': False,
                'initial_scan_counted': False,
                'roi_id': det_roi_id,
                'confidence': det_confidence
            }

        # Process all tracked objects for line crossing and disappearance
        objects_to_remove_from_tracking = []
        for obj_id, obj_data in list(tracked_objects.items()): # Iterate on a copy
            if obj_data['missing_frames'] > MAX_MISSING_FRAMES:
                # Object has disappeared. If it was counted 'in' but not 'out', it's a discrepancy.
                if obj_data['counted_in'] and not obj_data['counted_out']:
                    logger.warning(f"[Discrepancy] {obj_data['class_name']} (ID: {obj_id}) disappeared from {obj_data['roi_id']} without 'OUT' event.")
                    # Log this discrepancy to DB
                    db_instance.log_transaction(obj_data['class_name'], "DISCREPANCY", 1, str(obj_id), obj_data['confidence'], LOCATION_ID, description="Item disappeared without explicit OUT event.")
                objects_to_remove_from_tracking.append(obj_id)
                continue # Skip further processing for removed object

            # --- Line Crossing Logic for Tracked Objects ---
            # Apply only if not already counted in/out (or if specific scenario resets flags)
            if not obj_data['counted_in'] or not obj_data['counted_out']:
                # Find the line associated with this object's ROI
                line_cfg = next((roi for roi in SHELF_ROIS if roi['id'] == obj_data['roi_id']), None)
                if line_cfg:
                    x_roi_abs, y_roi_abs, _, _ = line_cfg["coords"]
                    line_start_x = line_cfg["counting_line"][0] + x_roi_abs
                    line_start_y = line_cfg["counting_line"][1] + y_roi_abs
                    line_end_x = line_cfg["counting_line"][2] + x_roi_abs
                    line_end_y = line_cfg["counting_line"][3] + y_roi_abs
                    
                    line_start_abs = (line_start_x, line_start_y)
                    line_end_abs = (line_end_x, line_end_y)

                    prev_cx, prev_cy = obj_data['prev_centroid']
                    curr_cx, curr_cy = obj_data['centroid']

                    crossed = intersect_line_segments(
                        (prev_cx, prev_cy), (curr_cx, curr_cy),
                        line_start_abs, line_end_abs
                    )

                    if crossed:
                        # Assuming a horizontal line and 'IN' is crossing from above to below
                        if not obj_data['counted_in'] and prev_cy < line_start_y and curr_cy >= line_start_y:
                            current_inventory_state[obj_data['class_name']] = current_inventory_state.get(obj_data['class_name'], 0) + 1
                            tracked_objects[obj_id]['counted_in'] = True
                            tracked_objects[obj_id]['counted_out'] = False # Reset out flag if it was set
                            logger.info(f"[Inventory Update] IN: {obj_data['class_name']} (ID: {obj_id}) in {obj_data['roi_id']}. New count: {current_inventory_state[obj_data['class_name']]}")
                            db_instance.update_inventory_count(obj_data['class_name'], 1, LOCATION_ID)
                            db_instance.log_transaction(obj_data['class_name'], "IN", 1, str(obj_id), obj_data['confidence'], LOCATION_ID)

                        # Assuming a horizontal line and 'OUT' is crossing from below to above
                        elif not obj_data['counted_out'] and prev_cy > line_start_y and curr_cy <= line_start_y:
                            current_inventory_state[obj_data['class_name']] = max(0, current_inventory_state.get(obj_data['class_name'], 0) - 1)
                            tracked_objects[obj_id]['counted_out'] = True
                            tracked_objects[obj_id]['counted_in'] = False # Reset in flag if it was set
                            logger.info(f"[Inventory Update] OUT: {obj_data['class_name']} (ID: {obj_id}) from {obj_data['roi_id']}. New count: {current_inventory_state[obj_data['class_name']]}")
                            db_instance.update_inventory_count(obj_data['class_name'], -1, LOCATION_ID)
                            db_instance.log_transaction(obj_data['class_name'], "OUT", 1, str(obj_id), obj_data['confidence'], LOCATION_ID)
                        # An object that crosses should probably have its flags reset so it can be counted again if it leaves and re-enters.
                        # For simple IN/OUT, if it's "counted_out", you might remove it from tracked_objects immediately,
                        # or only when its missing_frames count goes too high. This design implies objects stay tracked
                        # for a while after an OUT event to prevent double OUTs.
                        # For now, if it crosses OUT, it's considered "done" for this cycle.
            
        for obj_id in objects_to_remove_from_tracking:
            del tracked_objects[obj_id]

    # --- Visualization ---
    # Draw ROIs and Counting Lines
    for roi_cfg in SHELF_ROIS:
        x_roi, y_roi, w_roi, h_roi = roi_cfg["coords"]
        cv2.rectangle(frame, (x_roi, y_roi), (x_roi + w_roi, y_roi + h_roi), (0, 255, 0), 2) # Green for ROI
        
        line_start_x = roi_cfg["counting_line"][0] + x_roi
        line_start_y = roi_cfg["counting_line"][1] + y_roi
        line_end_x = roi_cfg["counting_line"][2] + x_roi
        line_end_y = roi_cfg["counting_line"][3] + y_roi
        cv2.line(frame, (line_start_x, line_start_y), (line_end_x, line_end_y), (0, 0, 255), 2) # Red for line
        
        cv2.putText(frame, f"ROI: {roi_cfg['id']}", (x_roi + 5, y_roi + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Draw tracked objects
    for obj_id, obj_data in tracked_objects.items():
        cx, cy = obj_data['centroid']
        cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1) # Blue dot for centroid
        
        # Color code based on state
        text_color = (0, 255, 0) # Green for counted IN (normal operation)
        if obj_data.get('initial_scan_counted', False):
            text_color = (255, 165, 0) # Orange for objects initially scanned in (during startup)
        elif not obj_data['counted_in'] and not obj_data['counted_out']:
            text_color = (0, 165, 255) # Yellow/Orange for objects not yet counted IN (waiting to cross)
        elif obj_data['counted_out']:
            text_color = (0, 0, 255) # Red for objects counted OUT

        cv2.putText(frame, f"{obj_data['class_name']}-{obj_id}", (cx - 50, cy - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 2)
        cv2.putText(frame, f"Conf: {obj_data['confidence']:.2f}", (cx - 50, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)


    # --- User Feedback and Configuration Display ---
    # Display Current Mode
    mode_text = "INITIAL SCAN" if initial_scan_mode else "LIVE MONITORING"
    cv2.putText(frame, f"MODE: {mode_text}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

    if initial_scan_mode:
        cv2.putText(frame, f"SCAN PROGRESS: {frame_count}/{INITIAL_SCAN_FRAMES}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    # Display per-item inventory counts
    y_offset = 100 # Start lower to not overlap mode/progress text
    cv2.putText(frame, "Current Inventory:", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    y_offset += 30
    for item, count in current_inventory_state.items():
        cv2.putText(frame, f"{item}: {count}", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        y_offset += 25

    return frame # Return processed frame for display


# --- Main Application Entry Point ---
if __name__ == "__main__":
    cap = None # Declare cap here to ensure it's in scope for finally
    try:
        cap = cv2.VideoCapture(CAMERA_ID)
        if not cap.isOpened():
            logger.critical(f"Failed to open video stream from camera ID {CAMERA_ID}. Check camera connection and ID.")
            exit() # Exit if camera cannot be opened initially

        logger.info("System starting. Press 'q' to quit.")

        db_instance = InventoryDB()
        db_instance.initialize_schema() # Ensure tables exist
        
        # Attempt to load previous state for this location from DB
        loaded_db_state = db_instance.get_all_inventory_counts(LOCATION_ID)
        if loaded_db_state:
            current_inventory_state = loaded_db_state # Initialize in-memory state from DB
            initial_scan_complete = True # Skip initial scan if we have a state
            logger.info(f"Loaded previous inventory state from DB for {LOCATION_ID}: {current_inventory_state}")
            # TODO: If loading from DB, you might need to 'seed' tracked_objects
            # based on the database count, especially for existing items.
            # For simplicity now, if initial_scan_complete is True, new objects will
            # only be counted via line-crossing.
        else:
            logger.info(f"No previous inventory state found for {LOCATION_ID}. Starting initial scan.")
            initial_scan_complete = False

        prev_frame_time = 0
        new_frame_time = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to grab frame. Attempting to reconnect camera...")
                cap.release() # Release current capture object
                time.sleep(2) # Wait a bit before retrying
                cap = cv2.VideoCapture(CAMERA_ID)
                if not cap.isOpened():
                    logger.critical("Camera reconnection failed after retry. Exiting application.")
                    break # Break out of loop if camera truly fails
                else:
                    logger.info("Camera reconnected successfully.")
                    continue # Continue to next frame
            
            frame_count += 1
            
            # --- Call the core processing function ---
            try:
                processed_frame = process_frame(frame.copy(), initial_scan_mode=not initial_scan_complete)
            except Exception as e:
                logger.error(f"Error during frame processing at frame {frame_count}: {e}", exc_info=True)
                processed_frame = frame # Fallback to original frame for display if processing fails

            # --- Handle Transition from Initial Scan to Normal Operation ---
            if not initial_scan_complete and frame_count >= INITIAL_SCAN_FRAMES:
                initial_scan_complete = True
                logger.info("\n--- Initial Scan Complete. Switching to Line Crossing Mode ---")
                # Persist the final state of the initial scan to DB
                for item_type, count in current_inventory_state.items():
                    db_instance.update_inventory_count(item_type, count, LOCATION_ID, absolute_set=True) # Set exact count

                # After initial scan, reset missing frames for all tracked objects
                # so only new disappearances count later.
                for obj_id in tracked_objects:
                    tracked_objects[obj_id]['missing_frames'] = 0 
                    tracked_objects[obj_id]['initial_scan_counted'] = False # No longer an initial scan object

            # --- 5. Performance Optimization: Display FPS ---
            new_frame_time = time.time()
            fps = 1/(new_frame_time-prev_frame_time) if (new_frame_time - prev_frame_time) > 0 else 0.0 # Avoid ZeroDivisionError
            prev_frame_time = new_frame_time
            cv2.putText(processed_frame, f"FPS: {int(fps)}", (processed_frame.shape[1] - 120, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            cv2.imshow("Cardinal Inventory - Item Counter", processed_frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                logger.info("Quit requested by user.")
                break

    except Exception as e:
        logger.critical(f"Unhandled critical error in main application loop: {e}", exc_info=True)
    finally:
        # --- Resource Release and Database Shutdown ---
        if cap and cap.isOpened():
            cap.release()
            logger.info("Camera released.")
        cv2.destroyAllWindows()
        if db_instance:
            db_instance.close()
            logger.info("Database connection closed gracefully.")
