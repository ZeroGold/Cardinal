import cv2
import numpy as np
import time
from collections import defaultdict

# --- Configuration ---
CONF_THRESHOLD = 0.5  # Confidence threshold for object detection
NMS_THRESHOLD = 0.4   # Non-maximum suppression threshold
INPUT_WIDTH = 416     # Width of the input image for the neural network
INPUT_HEIGHT = 416    # Height of the input image for the neural network

# Path to the YOLO files (ensure these are in the same directory)
YOLO_CFG = "yolov3.cfg"
YOLO_WEIGHTS = "yolov3.weights"
COCO_NAMES = "coco.names"

# Shelf region of interest (ROI) - Adjust these based on your camera view
# [x_start, y_start, width, height]
SHELF_ROI = [100, 200, 400, 150] # Example values for demonstration

# For tracking: Maximum Euclidean distance between centroids to consider them the same object
MAX_DISTANCE = 50
# For tracking: How many frames an object can be "missing" before it's considered gone
MAX_MISSING_FRAMES = 10

# --- Load YOLO Model ---
try:
    net = cv2.dnn.readNet(YOLO_WEIGHTS, YOLO_CFG)
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    print("YOLO model loaded successfully.")
except cv2.error as e:
    print(f"Error loading YOLO model: {e}")
    print("Please ensure yolov3.weights and yolov3.cfg are in the same directory.")
    exit()

# Load COCO class names
classes = []
with open(COCO_NAMES, "r") as f:
    classes = [line.strip() for line in f.readlines()]

# Get output layer names
output_layers = net.getUnconnectedOutLayersNames()

# --- Global Inventory State ---
# This will hold the "universal truth" of items on the shelf
# Format: { 'item_type': count, 'another_item': count }
current_inventory_state = defaultdict(int)

# --- Object Tracking Variables ---
# A dictionary to store tracked objects:
# { object_id: { 'centroid': (x, y), 'class_name': 'item_type', 'missing_frames': 0, 'last_seen_frame': frame_number } }
tracked_objects = {}
next_object_id = 0
frame_count = 0

# --- Helper Function for Centroid Distance ---
def euclidean_distance(p1, p2):
    return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

# --- Main Function for Item Counting ---
def count_items_on_shelf():
    global next_object_id, frame_count, current_inventory_state, tracked_objects

    cap = cv2.VideoCapture(0)  # 0 for default webcam, change if using another camera

    if not cap.isOpened():
        print("Error: Could not open video stream.")
        return

    print("Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1

        # Get frame dimensions
        height, width, _ = frame.shape

        # Define the shelf ROI
        x_roi, y_roi, w_roi, h_roi = SHELF_ROI
        # Ensure ROI is within frame boundaries
        x_roi = max(0, min(x_roi, width - 1))
        y_roi = max(0, min(y_roi, height - 1))
        w_roi = max(1, min(w_roi, width - x_roi))
        h_roi = max(1, min(h_roi, height - y_roi))

        shelf_roi_frame = frame[y_roi : y_roi + h_roi, x_roi : x_roi + w_roi]

        # Prepare the ROI frame for YOLO
        blob = cv2.dnn.blobFromImage(
            shelf_roi_frame, 1 / 255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False
        )
        net.setInput(blob)
        outs = net.forward(output_layers)

        # Process the detections
        detections = [] # Store current frame's detections as [x, y, w, h, class_id, confidence, centroid_x, centroid_y]

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

                    x_box = int(center_x - box_w / 2)
                    y_box = int(center_y - box_h / 2)
                    
                    detections.append([x_box, y_box, box_w, box_h, class_id, float(confidence), center_x, center_y])
        
        # Apply NMS
        if len(detections) > 0:
            boxes = [d[:4] for d in detections]
            confidences = [d[5] for d in detections]
            class_ids = [d[4] for d in detections]

            indexes = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESHOLD, NMS_THRESHOLD)
            
            # Filter detections to only include those after NMS
            current_frame_detections = []
            if len(indexes) > 0:
                for i in indexes.flatten():
                    current_frame_detections.append(detections[i])
        else:
            current_frame_detections = []


        # --- Object Tracking and Inventory Update Logic ---
        
        # Mark all existing tracked objects as potentially missing
        for obj_id in tracked_objects:
            tracked_objects[obj_id]['missing_frames'] += 1

        # Match current detections with tracked objects
        for det in current_frame_detections:
            det_x, det_y, det_w, det_h, det_class_id, det_confidence, det_cx, det_cy = det
            det_centroid = (det_cx, det_cy)
            det_class_name = classes[det_class_id]

            matched_id = None
            min_dist = float('inf')

            for obj_id, obj_data in tracked_objects.items():
                distance = euclidean_distance(det_centroid, obj_data['centroid'])
                if distance < MAX_DISTANCE and distance < min_dist and obj_data['class_name'] == det_class_name:
                    min_dist = distance
                    matched_id = obj_id
            
            if matched_id is not None:
                # Update existing tracked object
                tracked_objects[matched_id]['centroid'] = det_centroid
                tracked_objects[matched_id]['missing_frames'] = 0
                tracked_objects[matched_id]['last_seen_frame'] = frame_count
            else:
                # New object detected and added to inventory
                new_object_id = next_object_id
                next_object_id += 1
                tracked_objects[new_object_id] = {
                    'centroid': det_centroid,
                    'class_name': det_class_name,
                    'missing_frames': 0,
                    'last_seen_frame': frame_count
                }
                current_inventory_state[det_class_name] += 1
                print(f"[Inventory Update] Added: {det_class_name}. New count: {current_inventory_state[det_class_name]}")

        # Remove objects that have been missing for too long (considered removed)
        objects_to_remove = []
        for obj_id, obj_data in tracked_objects.items():
            if obj_data['missing_frames'] > MAX_MISSING_FRAMES:
                objects_to_remove.append(obj_id)
                removed_class = obj_data['class_name']
                current_inventory_state[removed_class] -= 1
                if current_inventory_state[removed_class] < 0: # Should not happen, but for safety
                    current_inventory_state[removed_class] = 0 
                print(f"[Inventory Update] Removed: {removed_class}. New count: {current_inventory_state[removed_class]}")

        for obj_id in objects_to_remove:
            del tracked_objects[obj_id]


        # --- Visualization ---
        
        # Draw Shelf ROI
        cv2.rectangle(frame, (x_roi, y_roi), (x_roi + w_roi, y_roi + h_roi), (255, 0, 0), 2)
        cv2.putText(frame, "Shelf ROI", (x_roi, y_roi - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

        # Draw bounding boxes and centroids for currently tracked objects
        for obj_id, obj_data in tracked_objects.items():
            # Estimate approximate bounding box from centroid for visualization
            # This is a simplification; a more robust approach would store bbox directly
            cx, cy = obj_data['centroid']
            # Convert centroid from ROI-relative to frame-relative
            cx_abs = cx + x_roi
            cy_abs = cy + y_roi

            # Crude estimate of box for visualization - can be improved
            # assuming an average object size based on INPUT_WIDTH/HEIGHT
            vis_box_w = 50 # Example visual width
            vis_box_h = 50 # Example visual height
            x_vis = int(cx_abs - vis_box_w / 2)
            y_vis = int(cy_abs - vis_box_h / 2)

            cv2.rectangle(frame, (x_vis, y_vis), (x_vis + vis_box_w, y_vis + vis_box_h), (0, 255, 0), 2)
            cv2.circle(frame, (cx_abs, cy_abs), 5, (0, 0, 255), -1) # Draw centroid
            label = f"{obj_data['class_name']} ({obj_id})"
            cv2.putText(frame, label, (x_vis, y_vis - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        # Display current inventory state
        y_offset = 30
        cv2.putText(frame, "Inventory State:", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        y_offset += 30
        for item_type, count in current_inventory_state.items():
            cv2.putText(
                frame,
                f"{item_type}: {count}",
                (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
            )
            y_offset += 25

        cv2.imshow("Cardinal Inventory - Item Counter (Stateful)", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    count_items_on_shelf()
