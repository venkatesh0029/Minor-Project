# 🔍 AI-Based Shelf-Level Inventory Monitoring System

> University Minor Project | Computer Vision + AI + Full-Stack

## 🎯 Project Overview

This system converts existing CCTV cameras into intelligent inventory monitors using:
- **YOLOv8** for real-time product detection
- **OpenCV** for video stream processing  
- **FastAPI** for high-performance REST API + WebSockets
- **React + Recharts** for a modern dashboard UI
- **SQLite / PostgreSQL** for inventory data persistence

---

## 📁 Project Structure

```
inventory-ai-system/
├── backend/                 # FastAPI backend
│   ├── main.py              # API + WebSocket server
│   ├── detection.py         # YOLO detection engine
│   ├── inventory_engine.py  # Stock analysis
│   ├── database.py          # Data persistence
│   ├── alerts.py            # Alert system
│   └── __init__.py
│
├── web/                     # React/Vite frontend
│   ├── src/
│   │   ├── App.jsx          # Main dashboard component
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── training/                # YOLO training scripts
│   └── train_yolo.py
│
├── data/                    # Datasets and configs
│   └── dataset.yaml
│
├── docs/                    # Documentation
│   └── README.md
│
└── run.bat                  # One-command launcher
```

## 🚀 Quick Start (One-Command Launch)

### Run Everything at Once

```bash
# Windows
run.bat

# Or manually:
# Terminal 1: python -m backend.main
# Terminal 2: cd web && npm run dev
```

- **Backend API**: http://localhost:8000
- **Frontend Dashboard**: http://localhost:5173

---

## 🔧 Full Stack Setup

### Step 1: Python Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run the API server
python main.py
```

### Step 2: React Frontend

```bash
cd web

# Install dependencies
npm install

# Start development server
npm run dev
```

Dashboard at: http://localhost:5173

---

## 🤖 AI Model Setup

### Option A: Use Pre-trained YOLOv8 (Quick)

YOLOv8 comes with a general object detector that works for testing:

```python
# In detection.py, set:
USE_REAL_MODEL = True

# Then modify the model path:
self.model = YOLO("yolov8n.pt")  # Downloads automatically (~6MB)
```

### Option B: Train Custom Shelf Model (Best Results)

1. Collect 500-1000 images of your target products on shelves
2. Annotate with [Roboflow](https://roboflow.com) or [LabelImg](https://github.com/heartexlabs/labelImg)
3. Train:

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")  # Start from pretrained
model.train(
    data="path/to/dataset.yaml",
    epochs=50,
    imgsz=640,
    batch=16,
    device="cpu"   # Use "0" for GPU
)
```

4. Copy `runs/detect/train/weights/best.pt` → `models/shelf_yolo.pt`

### Recommended Datasets

| Dataset | Products | Link |
|---------|----------|------|
| SKU110K | Retail shelves | [Papers with Code](https://paperswithcode.com/dataset/sku110k) |
| Grocery Store | 81 grocery items | [GitHub](https://github.com/marcusklasson/GroceryStoreDataset) |
| Open Images | General products | [Google](https://storage.googleapis.com/openimages/web/index.html) |
| Grozi-120 | 120 grocery products | [UC San Diego](http://grozi.calit2.net/) |

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/stats` | Overview metrics |
| GET | `/api/inventory` | Current stock levels |
| GET | `/api/alerts` | Recent stock alerts |
| GET | `/api/analytics/hourly` | 24h detection trend |
| GET | `/api/analytics/products` | Per-product analytics |
| GET | `/api/shelves` | Shelf occupancy data |
| POST | `/api/alerts/{id}/resolve` | Resolve an alert |
| WS | `/ws/monitor` | Live detection stream |

---

## 🗄️ Database Schema

```sql
-- Product catalog
CREATE TABLE products (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    threshold   INTEGER DEFAULT 3,   -- Alert when count <= threshold
    max_stock   INTEGER DEFAULT 12
);

-- Detection logs (timestamped)
CREATE TABLE inventory_logs (
    id              INTEGER PRIMARY KEY,
    product_id      INTEGER REFERENCES products(id),
    detected_count  INTEGER,
    shelf_zone      TEXT,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Alerts
CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER REFERENCES products(id),
    product_name TEXT,
    alert_type  TEXT,    -- OUT_OF_STOCK | LOW_STOCK | MISPLACED
    resolved    BOOLEAN DEFAULT 0,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🏗️ System Architecture

```
                    ┌─────────────────────┐
                    │   CCTV Camera Feed  │
                    │   (RTSP / Webcam)   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   OpenCV Frame      │
                    │   Capture & Resize  │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   YOLOv8 Detection  │
                    │   (Product + BBox)  │
                    └──────────┬──────────┘
                               │
              ┌────────────────▼────────────────┐
              │       Inventory Engine          │
              │  • Count products per shelf     │
              │  • Compare vs thresholds        │
              │  • Compute shelf health %       │
              └──────┬──────────────┬───────────┘
                     │              │
           ┌─────────▼──┐    ┌──────▼──────────┐
           │  Database  │    │  Alert Manager  │
           │  (SQLite)  │    │  (deduplication)│
           └─────────┬──┘    └──────┬──────────┘
                     │              │
              ┌──────▼──────────────▼──────────┐
              │     FastAPI Backend             │
              │  REST API + WebSocket Server    │
              └──────────────┬─────────────────┘
                             │  WebSocket (live)
              ┌──────────────▼─────────────────┐
              │     React Dashboard             │
              │  • Camera Feed View             │
              │  • Stock Status Cards           │
              │  • Alert Panel                  │
              │  • Analytics Charts             │
              │  • Shelf Heatmap                │
              └────────────────────────────────┘
```

---

## 💡 Innovation Features (Bonus Marks)

1. **Planogram Compliance Detection** — Compare shelf layout vs planogram image using OpenCV template matching
2. **Price Tag OCR** — Extract prices from shelf labels using Tesseract/EasyOCR
3. **Customer Interaction Tracking** — Detect hands picking up items to track real-time sales velocity
4. **Multi-camera Fusion** — Combine feeds from multiple cameras for full aisle coverage
5. **Automated Restock Orders** — Auto-generate purchase orders when stock drops below threshold
6. **Expiry Date Detection** — Detect visible expiry dates on products using OCR
7. **Mobile App Alerts** — Push notifications to store manager's phone via Firebase
8. **Edge Deployment** — Run inference on Raspberry Pi 4 with ONNX model for low-cost nodes

---

## 🧪 Testing Without Camera

1. **Demo mode** (default) — Open `frontend/demo.html`, everything simulated
2. **Video file** — Replace `cv2.VideoCapture(0)` with `cv2.VideoCapture("test_video.mp4")`
3. **Sample images** — Use `model.predict("shelf_image.jpg")` directly
4. **Test video sources**: Search "supermarket shelf stock video" on Pexels or Pixabay

---

## 📊 Performance (CPU Mode)

| Model | Size | Speed (CPU) | Accuracy |
|-------|------|-------------|----------|
| yolov8n.pt | 6MB | ~30fps | 80% mAP |
| yolov8s.pt | 22MB | ~15fps | 85% mAP |
| yolov8m.pt | 50MB | ~8fps  | 90% mAP |

Recommended for student laptop: **yolov8n.pt** (nano) for real-time performance.

---

## 👥 Team & Acknowledgements

- YOLOv8 by [Ultralytics](https://ultralytics.com)
- FastAPI by [Sebastián Ramírez](https://fastapi.tiangolo.com)
- React + Recharts for dashboard visualization
