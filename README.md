# Cardinal

**Cardinal** is a computer-vision inventory management system. It watches a camera feed, detects items on a shelf (or in a truck bay, bin, or storage area), counts them as they move in and out across a virtual line, and stores every event in a MySQL database. A separate reporting tool turns that data into polished PDF reports with charts and trends.


https://github.com/user-attachments/assets/385b7121-fcd9-49f2-a753-d41b666a3bcb


It is designed for hands-free, continuous inventory tracking: point a camera at a defined area, and Cardinal keeps a running count without anyone scanning barcodes.

---

## How it works

```
Camera frame<img width="986" height="770" alt="databases_state" src="https://github.com/user-attachments/assets/4fc192de-2543-467d-8004-706eb57ec4ab" />

   │
   ▼
YOLO object detection (per Region of Interest)
   │
   ▼
Centroid tracking (match detections to existing objects across frames)
   │
   ├─ Smart startup scan ──► baseline count of items already present
   │
   ▼
Line-crossing logic ──► IN / OUT / DISCREPANCY events
   │
   ▼
MySQL  (current state + transaction log)
   │
   ▼
report_generator.py ──► PDF reports with charts
```

1. **Detection.** Each frame is cropped to one or more configured *Regions of Interest* (ROIs). YOLOv3 (via OpenCV's DNN module) detects objects in each ROI, filtered by a confidence threshold and de-duplicated with Non-Maximum Suppression.
2. **Tracking.** Detected objects are matched to previously tracked objects by Euclidean distance between centroids, so the same physical item keeps a stable ID across frames.
3. **Smart startup scan.** On first run for a location, Cardinal spends a configurable number of frames building a baseline of items already in view before it starts counting movement.
4. **Counting.** Each ROI has a *counting line*. When a tracked object crosses it, Cardinal records an `IN` or `OUT` event depending on direction. If an item disappears without ever crossing out, it is logged as a `DISCREPANCY`.
5. **Persistence.** All counts and events are written to MySQL and survive restarts — on startup Cardinal reloads the last known state for its location.
6. **Reporting.** `report_generator.py` reads the database and produces PDF reports (full inventory, per-item, or date-ranged) with charts and linear-regression trend lines.

---

## Features

- Real-time multi-object detection and counting from any camera (`CAMERA_ID`)
- Multiple independent monitoring zones per camera, each with its own counting line
- Smart startup scan to baseline existing stock
- Directional IN / OUT counting with discrepancy detection for items that vanish
- Persistent MySQL storage with per-location state and a full transaction log
- Automatic camera reconnection if the feed drops
- Rotating log files for diagnostics
- PDF report generation with charts (daily activity, most-active items, inventory level over time)
- Sample report generator that runs on dummy data — no database required

---

## Repository structure

```
Cardinal/
└── Cardinal Demo/
    ├── main.py                     # Live camera inventory counter (entry point)
    ├── config.py                   # All configuration (env-var driven)
    ├── db_module.py                # MySQL connection + schema + queries
    ├── utils.py                    # Geometry helpers (distance, line crossing)
    ├── report_generator.py         # PDF reports from the live database
    ├── sample_report_generator.py  # PDF reports from random dummy data (no DB)
    ├── coco.names                  # 80 COCO class labels
    ├── dependencies.txt            # Notes on required packages
    ├── models/
    │   └── yolov3-tiny.cfg         # YOLO model architecture
    ├── inventory_reports/          # Example generated reports
    └── extras/                     # Earlier demo scripts and sample PDFs
```

---

## Requirements

- Python 3.8+
- A running **MySQL** server (for `main.py` and `report_generator.py`)
- A webcam or other OpenCV-compatible camera
- **YOLO model files** — see the next section

Python packages:

```bash
pip install opencv-python numpy mysql-connector-python pandas fpdf matplotlib scipy
```

| Package | Used by |
| --- | --- |
| `opencv-python`, `numpy` | live detection & tracking (`main.py`) |
| `mysql-connector-python` | database (`main.py`, `report_generator.py`) |
| `pandas`, `fpdf`, `matplotlib`, `scipy` | PDF reports |

---

## Model files (required, not included)

The detection model is **not committed to the repo** and must be supplied separately. You need three files:

- a YOLO config (`.cfg`) — the repo ships `models/yolov3-tiny.cfg`
- the matching YOLO weights (`.weights`) — **not included; obtain these separately**
- a class-names file (`coco.names`) — included in the repo

> **Note:** `config.py` defaults to `yolov3.cfg` / `yolov3.weights`, but the file shipped in `models/` is `yolov3-tiny.cfg`. Either rename your files to match the defaults or override the paths with the `YOLO_CFG` / `YOLO_WEIGHTS` / `COCO_NAMES` environment variables (recommended). The config and weights must be from the **same** YOLO variant or the model will fail to load.

---

## Configuration

All settings live in `config.py` and can be overridden with environment variables — no code changes needed.

### Model & detection

| Variable | Default | Description |
| --- | --- | --- |
| `YOLO_CFG` | `yolov3.cfg` | Path to the YOLO `.cfg` file |
| `YOLO_WEIGHTS` | `yolov3.weights` | Path to the YOLO `.weights` file |
| `COCO_NAMES` | `coco.names` | Path to the class-names file |
| `CONF_THRESHOLD` | `0.3` | Minimum detection confidence |
| `NMS_THRESHOLD` | `0.22` | Overlap threshold for duplicate suppression |

### Camera & processing

| Variable | Default | Description |
| --- | --- | --- |
| `CAMERA_ID` | `0` | Camera index or device path |
| `INPUT_WIDTH` / `INPUT_HEIGHT` | `320` | Model input size (must match the model) |
| `INITIAL_SCAN_FRAMES` | `150` | Frames spent baselining existing stock (~5s at 30 FPS) |

### Tracking

| Variable | Default | Description |
| --- | --- | --- |
| `MAX_DISTANCE` | `70` | Max pixels an object can move between frames and still be the same object |
| `MAX_MISSING_FRAMES` | `15` | Frames an object can be missing before it is dropped |

### Location & database
<img width="986" height="770" alt="databases_state" src="https://github.com/user-attachments/assets/8765b755-7d7a-49d2-b513-7b935dbb9bd5" />

| Variable | Default | Description |
| --- | --- | --- |
| `LOCATION_ID` | `default_test_site` | Unique ID for this camera/site (used to separate data in the DB) |
| `DB_HOST` | `localhost` | MySQL host |
| `DB_USER` | `###` | MySQL user — **set this** |
| `DB_PASSWORD` | `###` | MySQL password — **set this** |
| `DB_NAME` | `cardinal_inventory_db` | Database name |
| `DB_PORT` | `3306` | MySQL port |

### Regions of Interest

`SHELF_ROIS` in `config.py` defines the monitored zones. Each entry is:

```python
{
    "id": "main_shelf_area",
    "coords": [50, 100, 500, 300],      # [x, y, width, height] of the zone, in pixels
    "counting_line": [0, 150, 500, 150] # line endpoints, as offsets from the zone's top-left corner
}
```

Add more dictionaries to monitor several zones in one camera view. The counting line in `[0, 150, 500, 150]` is horizontal; an object moving downward across it counts as `IN`, upward as `OUT`.

---

## Setup

1. **Clone and enter the project**
   ```bash
   git clone https://github.com/ZeroGold/Cardinal.git
   cd "Cardinal/Cardinal Demo"
   ```

2. **Install dependencies** (see Requirements above).

3. **Add your model files** and point the env vars at them (see Model files above).

4. **Set up MySQL.** Create the database and a user, then export credentials:
   ```bash
   export DB_HOST=localhost
   export DB_USER=your_user
   export DB_PASSWORD=your_password
   export DB_NAME=cardinal_inventory_db
   ```
   The required tables are created automatically on first run — you do not need to create them by hand.

5. **Configure your ROIs and counting lines** in `config.py` to match your camera's view.

---

## Usage

### Run the live counter

```bash
cd "Cardinal Demo"
python main.py
```

A window opens showing the camera feed with ROIs, counting lines, tracked objects, live counts, current mode (scan vs. monitoring), and FPS. Press **`q`** to quit. State is saved to MySQL throughout and restored next time you run against the same `LOCATION_ID`.

### Generate reports from real data

```bash
python report_generator.py
```

Reads the live database and writes PDF reports into a timestamped folder under `inventory_reports/` (e.g. a full report, a per-item report, and date-ranged reports).

### Preview reports without a database

```bash
python sample_report_generator.py
```

Generates the same report layout using randomly generated transactions — useful for previewing the format before any real data exists.

---

## Database schema

Two tables are created automatically:

**`inventory_current_state`** — the current count per item per location.

| Column | Type | Notes |
| --- | --- | --- |
| `item_type` | VARCHAR | part of primary key |
| `location_id` | VARCHAR | part of primary key |
| `count` | INT | current quantity |
| `last_updated` | DATETIME | auto-updated |

**`transaction_log`** — every counting event.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INT | auto-increment PK |
| `timestamp` | DATETIME | event time |
| `item_type` | VARCHAR | detected class name |
| `event_type` | ENUM | `IN`, `OUT`, `DISCREPANCY`, `SCALE_UPDATE`, `MANUAL_ADJUSTMENT` |
| `quantity_change` | INT | amount changed |
| `object_id` | VARCHAR | tracked-object ID |
| `confidence` | REAL | detection confidence |
| `location_id` | VARCHAR | site identifier |
| `description` | TEXT | free-text detail |

---

## Known limitations & notes

- **Line crossing is horizontal-only.** `intersect_line_segments` in `utils.py` is a simplified implementation tuned for horizontal counting lines. Arbitrary line orientations need a more general algorithm.
- **Detection classes come from COCO.** Out of the box the model recognizes the 80 standard COCO classes (person, laptop, bottle, etc.). Tracking specialized inventory items requires a custom-trained model and class-names file.
- **CPU by default.** `main.py` runs the network on CPU. The CUDA backend lines are commented out; enable them if you have a CUDA-capable OpenCV build.
- **Set real DB credentials.** The defaults are `###` placeholders and will fail to connect.
- **Sample report data.** Per `inventory_reports/NOTES ABOUT REPORT GENERATION.txt`, some short-range sample reports contain placeholder Monitor/Laptop items that are intended to be replaced with real data.

---

## Roadmap ideas

- General (non-horizontal) line-crossing geometry
- Custom-trained model for real inventory SKUs
- Optional GPU acceleration toggle in config
- Scale/sensor integration (the schema already reserves `SCALE_UPDATE` events)
- Web dashboard for live counts and report browsing
