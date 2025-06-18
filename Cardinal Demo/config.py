# config.py
import os

# --- YOLO Model Configuration ---
# Paths to your YOLO model files. Using environment variables for flexibility in deployment.
YOLO_CFG = os.getenv("YOLO_CFG", "yolov3.cfg")
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", "yolov3.weights")
COCO_NAMES = os.getenv("COCO_NAMES", "coco.names") # File containing class names (e.g., for COCO dataset)

# --- Detection Thresholds ---
# Confidence threshold: Minimum confidence to consider a detection valid.
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", 0.3)) # Adjust based on desired precision vs. recall
# Non-Maximum Suppression (NMS) threshold: Overlap threshold for filtering duplicate bounding boxes.
NMS_THRESHOLD = float(os.getenv("NMS_THRESHOLD", 0.22)) # Lower values mean more aggressive suppression

# --- Camera & Processing Settings ---
# Camera ID: 0 for default webcam, or specific device ID/path for other cameras.
CAMERA_ID = int(os.getenv("CAMERA_ID", 0)) 
# Input dimensions for the YOLO model. Must match model's expected input size.
INPUT_WIDTH = int(os.getenv("INPUT_WIDTH", 320)) 
INPUT_HEIGHT = int(os.getenv("INPUT_HEIGHT", 320)) 
# Number of frames for the "Smart Startup" initial inventory scan.
# This period allows the system to build a baseline of items already present.
INITIAL_SCAN_FRAMES = int(os.getenv("INITIAL_SCAN_FRAMES", 150)) # e.g., 150 frames = 5 seconds at 30 FPS

# --- Object Tracking Settings ---
# Maximum pixel distance an object can move between frames to still be considered the same object.
MAX_DISTANCE = int(os.getenv("MAX_DISTANCE", 70)) 
# Number of consecutive frames an object can be "missing" before it's no longer tracked.
MAX_MISSING_FRAMES = int(os.getenv("MAX_MISSING_FRAMES", 15)) 

# --- Location Identifier (Crucial for Multi-Camera/Multi-Site Support in DB) ---
# A unique identifier for the specific camera setup/location. This is used in the MySQL database.
LOCATION_ID = os.getenv("LOCATION_ID", "default_test_site") # Example: "massey_truck_A_bay_1", "warehouse_shelf_3B"

# --- Shelf ROIs (Regions of Interest) and Counting Lines Configuration ---
# This is a list of dictionaries, allowing you to define multiple distinct monitoring areas
# within a single camera's view. Each ROI has its own counting line.
#
# Each dictionary contains:
# - "id": A unique string identifier for this ROI.
# - "coords": [x_start, y_start, width, height] defining the top-left corner and dimensions of the ROI in pixels.
# - "counting_line": [line_start_x_offset, line_start_y_offset, line_end_x_offset, line_end_y_offset]
#   These line coordinates are OFFSETS RELATIVE to the top-left (x_start, y_start) of the ROI.
#   For example, [0, 150, 500, 150] in an ROI of [50, 100, 500, 300] means the line goes from
#   absolute (50+0, 100+150) to (50+500, 100+150).
SHELF_ROIS = [
    # Example 1: A main shelf area with a horizontal counting line in the middle
    {"id": "main_shelf_area", "coords": [50, 100, 500, 300], "counting_line": [0, 150, 500, 150]},
    
    # Example 2: A second distinct area within the same camera's view (e.g., another shelf, or a specific bin)
    # The coordinates here are for a hypothetical second ROI, adjusting to avoid overlap.
    # This example shows a vertical line within the second ROI.
    # {"id": "secondary_bin", "coords": [580, 50, 200, 400], "counting_line": [100, 0, 100, 400]}, 
]


# --- MySQL Database Configuration ---
# These parameters are used by db_module.py to establish connection to your MySQL database.
# It is highly recommended to use environment variables for sensitive data like passwords
# in a production environment, or a more secure configuration management system

DB_CONFIG = {
    'host': os.getenv("DB_HOST", "localhost"),
    'user': os.getenv("DB_USER", "root"),
    'password': os.getenv("DB_PASSWORD", "abc123"), # <<<<<<< IMPORTANT: CHANGE THIS IN PRODUCTION!
    'database': os.getenv("DB_NAME", "cardinal_inventory_db"),
    'port': int(os.getenv("DB_PORT", 3306))
}
