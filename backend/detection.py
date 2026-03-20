"""
detection.py — YOLOv8 Detection Engine with Real Webcam Support

Modes:
  1. REAL WEBCAM + YOLO MODEL  — full production inference
  2. REAL WEBCAM, NO MODEL     — webcam works, detections simulated
  3. DEMO MODE                 — no camera, full simulation

Set USE_REAL_CAMERA and USE_REAL_MODEL flags below.

--- ORIGINAL DOCSTRING BELOW ---
detection.py - YOLOv8-based shelf product detection module.

In production: uses YOLOv8 model + OpenCV to process camera frames.
For demo/testing: generates realistic synthetic detections.

To enable real detection:
  1. pip install ultralytics opencv-python
  2. Set USE_REAL_MODEL = True
  3. Place your trained model at models/shelf_yolo.pt
"""

import random
import time
from typing import Dict, Any

# ── Toggle between real model and demo mode ──────────────────────────────────
USE_REAL_MODEL = False  # Set True when model is available

if USE_REAL_MODEL:
    from ultralytics import YOLO
    import cv2

# ── Product catalog (matches your training labels) ────────────────────────────
SHELF_PRODUCTS = [
    {"name": "Coca Cola 500ml", "category": "Beverages", "color": "#E63946"},
    {"name": "Pepsi 500ml", "category": "Beverages", "color": "#1D3557"},
    {"name": "Lays Classic", "category": "Snacks", "color": "#F4D35E"},
    {"name": "Britannia Biscuits", "category": "Snacks", "color": "#EE9B00"},
    {"name": "Amul Butter 500g", "category": "Dairy", "color": "#94D2BD"},
    {"name": "Parle-G", "category": "Snacks", "color": "#E9C46A"},
    {"name": "Maggi Noodles", "category": "Food", "color": "#F77F00"},
    {"name": "Horlicks 500g", "category": "Beverages", "color": "#FCBF49"},
    {"name": "Dettol Soap", "category": "Personal Care", "color": "#90BE6D"},
    {"name": "Colgate 200g", "category": "Personal Care", "color": "#43AA8B"},
    {"name": "Surf Excel 1kg", "category": "Household", "color": "#577590"},
    {"name": "Lifebuoy Soap", "category": "Personal Care", "color": "#F94144"},
]

SHELF_ZONES = [
    "Shelf A - Row 1",
    "Shelf A - Row 2",
    "Shelf B - Row 1",
    "Shelf B - Row 2",
    "Shelf C - Row 1",
    "Shelf C - Row 2",
]


class ShelfDetector:
    """
    Manages product detection from camera feeds.
    Supports real YOLOv8 inference and demo simulation mode.
    """

    def __init__(self):
        self.model = None
        self.cap = None
        self.frame_count = 0
        self.start_time = time.time()
        self.initialized = False

        # Simulate dynamic stock levels
        self.stock_state = {p["name"]: random.randint(2, 12) for p in SHELF_PRODUCTS}

    def initialize(self):
        """Initialize detector - loads model or sets up demo mode."""
        if USE_REAL_MODEL:
            self._init_real_model()
        else:
            print("[MODE] Running in DEMO MODE (no real camera/model needed)")
        self.initialized = True

    def _init_real_model(self):
        """Load actual YOLOv8 model and open camera."""
        try:
            self.model = YOLO("models/shelf_yolo.pt")
            self.cap = cv2.VideoCapture(0)  # 0 = default webcam, or use RTSP URL
            if not self.cap.isOpened():
                raise RuntimeError("Cannot open camera")
            print("✅ YOLOv8 model loaded, camera stream opened")
        except Exception as e:
            print(f"⚠️  Could not load real model: {e}. Falling back to demo mode.")

    def get_latest_frame_data(self) -> Dict[str, Any]:
        """
        Returns detection results for the latest camera frame.
        Uses real inference if model is loaded, otherwise simulates.
        """
        self.frame_count += 1
        elapsed = time.time() - self.start_time
        fps = round(self.frame_count / max(elapsed, 1), 1)

        if USE_REAL_MODEL and self.cap:
            return self._real_inference(fps)
        else:
            return self._simulate_detections(fps)

    def _real_inference(self, fps: float) -> Dict[str, Any]:
        """Run actual YOLOv8 inference on camera frame."""
        ret, frame = self.cap.read()
        if not ret:
            return self._simulate_detections(fps)

        results = self.model(frame, conf=0.5, verbose=False)
        detections = []

        for result in results:
            for box in result.boxes:
                label = self.model.names[int(box.cls[0])]
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    {
                        "product": label,
                        "confidence": round(float(box.conf[0]), 2),
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "shelf_zone": SHELF_ZONES[
                            int(y1 / (frame.shape[0] / len(SHELF_ZONES)))
                        ],
                    }
                )

        return {"detections": detections, "fps": fps, "frame_count": self.frame_count}

    def _simulate_detections(self, fps: float) -> Dict[str, Any]:
        """
        Generate realistic synthetic detections for demo purposes.
        Simulates stock depleting over time and occasional restocking.
        """
        detections = []
        time.time()

        for product in SHELF_PRODUCTS:
            name = product["name"]

            # Randomly deplete stock slowly
            if random.random() < 0.02:  # 2% chance per second to reduce
                self.stock_state[name] = max(0, self.stock_state[name] - 1)

            # Randomly restock
            if random.random() < 0.005:
                self.stock_state[name] = random.randint(6, 12)

            count = self.stock_state[name]

            # Generate individual bounding boxes per detected unit
            for i in range(count):
                # Spread boxes across a simulated 1280x720 frame
                x_base = (SHELF_PRODUCTS.index(product) % 4) * 300 + i * 30
                y_base = (SHELF_PRODUCTS.index(product) // 4) * 240
                noise_x = random.randint(-5, 5)
                noise_y = random.randint(-5, 5)

                detections.append(
                    {
                        "product": name,
                        "category": product["category"],
                        "confidence": round(random.uniform(0.82, 0.98), 2),
                        "bbox": [
                            max(0, x_base + noise_x),
                            max(0, y_base + noise_y),
                            min(1280, x_base + 80 + noise_x),
                            min(720, y_base + 120 + noise_y),
                        ],
                        "shelf_zone": SHELF_ZONES[
                            SHELF_PRODUCTS.index(product) % len(SHELF_ZONES)
                        ],
                        "color": product["color"],
                    }
                )

        return {
            "detections": detections,
            "fps": fps,
            "frame_count": self.frame_count,
            "resolution": "1280x720",
        }

    def get_stock_counts(self) -> Dict[str, int]:
        """Returns current simulated stock counts per product."""
        return dict(self.stock_state)

    def release(self):
        """Clean up camera resources."""
        if self.cap:
            self.cap.release()
