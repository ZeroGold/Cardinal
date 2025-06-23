import cv2
import numpy as np
import time
import sys

sys.path.append('/usr/local/lib/python3.13/site-packages')

# --- Configuration ---
CONF_THRESHOLD = 0.5  # Confidence threshold for object detection
NMS_THRESHOLD = 0.4   # Non-maximum suppression threshold
INPUT_WIDTH = 416     # Width of the input image for the neural network
INPUT_HEIGHT = 416    # Height of the input image for the neural network

# Path to the YOLO files
YOLO_CFG = "yolov3.cfg"
YOLO_WEIGHTS = "yolov3.weights"
COCO_NAMES = "coco.names"

# Shelf region of interest (ROI) - define this based on your camera view
# Example: [x_start, y_start, width, height]
# You'll need to adjust these values by trial and error based on your actual shelf position in the camera feed.
SHELF_ROI = [100, 200, 400, 150] # Example values: x=100, y=200, width=400, height=150

# --- Load YOLO Model ---
try:
    net = cv2.dnn.readNet(YOLO_WEIGHTS, YOLO_CFG)
    # Use CUDA if available for faster inference
    # net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
    # net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU) # Using CPU for broader compatibility
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
output_layers = [
    layer_name for layer_name in net.getUnconnectedOutLayersNames()
]

# --- Item Counting Logic Variables ---
previous_item_count = 0
current_item_count = 0
items_added_this_frame = 0

# A simple debounce mechanism to avoid counting the same item multiple times immediately
debounce_frame_count = 0
DEBOUNCE_THRESHOLD = 10 # Number of frames to wait before re-evaluating new items


# --- Main Function for Item Counting ---
def count_items_on_shelf():
    global previous_item_count, current_item_count, items_added_this_frame, debounce_frame_count

    cap = cv2.VideoCapture(0)  # 0 for default webcam, change if using another camera

    if not cap.isOpened():
        print("Error: Could not open video stream.")
        return

    print("Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Get frame dimensions
        height, width, _ = frame.shape

        # Define the shelf ROI
        x, y, w, h = SHELF_ROI
        # Ensure ROI is within frame boundaries
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))

        shelf_roi_frame = frame[y : y + h, x : x + w]

        # Prepare the ROI frame for YOLO
        blob = cv2.dnn.blobFromImage(
            shelf_roi_frame, 1 / 255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False
        )
        net.setInput(blob)
        outs = net.forward(output_layers)

        # Process the detections
        class_ids = []
        confidences = []
        boxes = []

        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]

                if confidence > CONF_THRESHOLD:
                    # Object detected
                    center_x = int(detection[0] * w)
                    center_y = int(detection[1] * h)
                    box_w = int(detection[2] * w)
                    box_h = int(detection[3] * h)

                    # Rectangle coordinates
                    x_box = int(center_x - box_w / 2)
                    y_box = int(center_y - box_h / 2)

                    boxes.append([x_box, y_box, box_w, box_h])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)

        # Apply Non-Maximum Suppression (NMS) to remove redundant overlapping boxes
        indexes = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESHOLD, NMS_THRESHOLD)
        
        # Reset current_item_count for this frame
        current_item_count = 0 

        if len(indexes) > 0:
            for i in indexes.flatten():
                box = boxes[i]
                x_b, y_b, w_b, h_b = box

                # Draw bounding box on the original frame (relative to shelf ROI)
                cv2.rectangle(
                    frame,
                    (x + x_b, y + y_b),
                    (x + x_b + w_b, y + y_b + h_b),
                    (0, 255, 0),
                    2,
                )
                label = str(classes[class_ids[i]])
                cv2.putText(
                    frame,
                    label,
                    (x + x_b, y + y_b - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    2,
                )
                current_item_count += 1

        # --- Counting Logic ---
        if debounce_frame_count == 0:
            if current_item_count > previous_item_count:
                items_added_this_frame = current_item_count - previous_item_count
                print(f"Detected {items_added_this_frame} new item(s) on the shelf!")
                # Reset debounce
                debounce_frame_count = DEBOUNCE_THRESHOLD
            elif current_item_count < previous_item_count:
                print(f"Detected {previous_item_count - current_item_count} item(s) removed from the shelf.")
        else:
            debounce_frame_count -= 1

        previous_item_count = current_item_count

        # Display current counts on the frame
        cv2.putText(
            frame,
            f"Items on Shelf: {current_item_count}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            f"Added This Frame: {items_added_this_frame}",
            (10, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 255),
            2,
        )

        # Draw the Shelf ROI rectangle
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(frame, "Shelf ROI", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)


        cv2.imshow("Cardinal Inventory - Item Counter", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    count_items_on_shelf()
