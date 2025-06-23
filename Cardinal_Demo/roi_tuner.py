# Making a file to tune the ROI for the shelf area so we don't have to hardcode it in the config.py file
"""
roi_tuner.py  – click-and-drag ROI calibrator
  • Left-click + drag = draw rectangle
  • ENTER            = accept & save as  shelf_rois.json
  • r                = reset / redraw
  • q                = quit without saving
"""
import json, cv2, os, pathlib, time

CAMERA_ID = 0
WINDOW    = "ROI Calibrator"
json_file = pathlib.Path(__file__).with_name("shelf_rois.json")

drawing   = False
ix = iy   = 0
roi       = None

def mouse(evt, x, y, flags, _):
    global drawing, ix, iy, roi
    if evt == cv2.EVENT_LBUTTONDOWN:
        drawing, ix, iy = True, x, y
    elif evt == cv2.EVENT_MOUSEMOVE and drawing:
        roi = (ix, iy, x - ix, y - iy)
    elif evt == cv2.EVENT_LBUTTONUP:
        drawing = False
        roi = (min(ix, x), min(iy, y), abs(x - ix), abs(y - iy))

cap = cv2.VideoCapture(CAMERA_ID)
if not cap.isOpened():
    raise SystemExit(f"Camera {CAMERA_ID} failed to open.")

cv2.namedWindow(WINDOW)
cv2.setMouseCallback(WINDOW, mouse)

print("[ROI-Tuner] Draw rectangle, press ENTER to save, r to reset, q to quit.")

while True:
    ret, frame = cap.read()
    if not ret:
        time.sleep(0.1)
        continue

    if roi:
        x, y, w, h = roi
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    cv2.imshow(WINDOW, frame)
    key = cv2.waitKey(1) & 0xFF

    if key in (13, 10) and roi:             # ENTER
        data = [{"id": "main_shelf_area", "coords": roi}]
        json_file.write_text(json.dumps(data, indent=2))
        print(f"[ROI-Tuner] Saved to {json_file.resolve()}")
        break
    elif key == ord('r'):
        roi = None
    elif key == ord('q'):
        print("[ROI-Tuner] Quit without saving.")
        break

cap.release()
cv2.destroyAllWindows()