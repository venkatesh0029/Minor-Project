"""
train_yolo.py — Complete YOLOv8 Training Pipeline
AI Shelf Inventory Monitoring System

This script handles the FULL training workflow:
  1. Dataset download / preparation
  2. Data augmentation config
  3. YOLOv8 model training
  4. Model evaluation & export
  5. Test inference on sample images

Usage:
  python train_yolo.py --mode prepare   # Download & prep dataset
  python train_yolo.py --mode train     # Train the model
  python train_yolo.py --mode evaluate  # Run evaluation
  python train_yolo.py --mode export    # Export to ONNX for deployment
  python train_yolo.py --mode all       # Full pipeline

Requirements:
  pip install ultralytics roboflow opencv-python matplotlib PyYAML
"""

import argparse
import os
import sys
import shutil
import yaml
import random
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "dataset"
TRAIN_DIR  = DATA_DIR / "train"
VAL_DIR    = DATA_DIR / "val"
TEST_DIR   = DATA_DIR / "test"
MODEL_DIR  = BASE_DIR
RUNS_DIR   = BASE_DIR / "runs"

# Product classes — must match your annotation labels
CLASSES = [
    "coca_cola_500ml",
    "pepsi_500ml",
    "lays_classic",
    "britannia_biscuits",
    "amul_butter_500g",
    "parle_g",
    "maggi_noodles",
    "horlicks_500g",
    "dettol_soap",
    "colgate_200g",
    "surf_excel_1kg",
    "lifebuoy_soap",
]

TRAINING_CONFIG = {
    "model":       "yolov8n.pt",   # nano = fastest on CPU, use yolov8s.pt for better accuracy
    "epochs":      60,
    "imgsz":       640,
    "batch":       16,             # reduce to 8 if RAM is limited
    "device":      "cpu",          # use "0" if you have NVIDIA GPU
    "workers":     4,
    "patience":    15,             # early stopping
    "lr0":         0.01,
    "lrf":         0.001,
    "momentum":    0.937,
    "weight_decay":0.0005,
    # Augmentation
    "hsv_h":       0.015,
    "hsv_s":       0.7,
    "hsv_v":       0.4,
    "degrees":     5.0,
    "translate":   0.1,
    "scale":       0.5,
    "flipud":      0.0,
    "fliplr":      0.5,
    "mosaic":      1.0,
    "mixup":       0.1,
}


# ── STEP 1: Dataset Preparation ───────────────────────────────────────────────

def prepare_dataset():
    """
    Prepares the dataset for training.

    Option A (Recommended): Use Roboflow to download a pre-annotated shelf dataset
    Option B: Use your own images with auto-annotation helper
    Option C: Synthetic data generation for quick testing
    """
    print("\n" + "="*60)
    print("  STEP 1: Dataset Preparation")
    print("="*60)

    # Create directory structure
    for split in ["train", "val", "test"]:
        (DATA_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / split / "labels").mkdir(parents=True, exist_ok=True)

    print("✅ Directory structure created")

    # Check if Roboflow is available
    try:
        from roboflow import Roboflow
        download_roboflow_dataset()
    except ImportError:
        print("⚠️  Roboflow not installed. Generating synthetic dataset for testing...")
        print("    Install with: pip install roboflow")
        print("    Then add your API key and dataset URL to this script.")
        generate_synthetic_dataset()

    # Write dataset YAML
    write_dataset_yaml()
    print("\n✅ Dataset ready at:", DATA_DIR)


def download_roboflow_dataset():
    """
    Download a pre-annotated retail shelf dataset from Roboflow.

    TO USE THIS:
    1. Go to https://universe.roboflow.com
    2. Search "retail shelf products" or "supermarket products"
    3. Click "Download" → YOLOv8 format → get your API key
    4. Replace the values below
    """
    from roboflow import Roboflow

    # ─── REPLACE THESE ──────────────────────────────────────────────
    API_KEY      = "YOUR_ROBOFLOW_API_KEY"
    WORKSPACE    = "your-workspace"
    PROJECT_NAME = "retail-shelf-products"
    VERSION      = 1
    # ────────────────────────────────────────────────────────────────

    if API_KEY == "YOUR_ROBOFLOW_API_KEY":
        print("⚠️  Please set your Roboflow API key in train_yolo.py")
        print("    Recommended datasets:")
        print("    • https://universe.roboflow.com/object-detection-benchmarks-and-datasets/grocery-store-products")
        print("    • https://universe.roboflow.com/shreyash-mishra-jkbad/retail-shelf-inventory")
        raise ValueError("API key not set")

    rf = Roboflow(api_key=API_KEY)
    project = rf.workspace(WORKSPACE).project(PROJECT_NAME)
    dataset = project.version(VERSION).download("yolov8", location=str(DATA_DIR))
    print(f"✅ Downloaded {PROJECT_NAME} v{VERSION} from Roboflow")


def generate_synthetic_dataset(n_train=200, n_val=40):
    """
    Generates a synthetic YOLO dataset with bounding box annotations.
    Used for testing the training pipeline when real data isn't available.
    Creates placeholder images + valid YOLO label files.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("⚠️  OpenCV not available. Creating text placeholder dataset.")
        _create_text_placeholders(n_train, n_val)
        return

    print(f"🔧 Generating synthetic dataset ({n_train} train, {n_val} val images)...")

    # Product colors for visualization
    colors = [
        (220, 50, 50),   (50, 80, 200),  (240, 200, 50),
        (200, 120, 30),  (80, 200, 120), (240, 180, 40),
        (220, 100, 30),  (240, 160, 30), (50, 160, 80),
        (50, 160, 160),  (80, 100, 160), (200, 80, 80),
    ]

    def create_sample(split, idx):
        img_h, img_w = 640, 640
        # Dark shelf background
        img = np.ones((img_h, img_w, 3), dtype=np.uint8) * 25
        # Draw shelf lines
        for shelf_y in [160, 320, 480]:
            img[shelf_y-5:shelf_y, :] = (60, 50, 40)

        labels = []
        n_products = random.randint(3, 8)

        for _ in range(n_products):
            cls_id = random.randint(0, len(CLASSES)-1)
            # Random position on a shelf row
            shelf_row = random.choice([0, 1, 2])
            y_base = shelf_row * 160 + random.randint(20, 100)
            x_base = random.randint(20, img_w - 100)
            w = random.randint(50, 90)
            h = random.randint(80, 140)
            x_base = min(x_base, img_w - w - 5)
            y_base = min(y_base, img_h - h - 5)

            # Draw product rectangle
            color = colors[cls_id]
            cv2.rectangle(img, (x_base, y_base), (x_base+w, y_base+h), color, -1)
            cv2.rectangle(img, (x_base, y_base), (x_base+w, y_base+h), (255,255,255), 1)
            cv2.putText(img, CLASSES[cls_id][:6], (x_base+3, y_base+15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255,255,255), 1)

            # YOLO format: class cx cy w h (normalized)
            cx = (x_base + w/2) / img_w
            cy = (y_base + h/2) / img_h
            nw = w / img_w
            nh = h / img_h
            labels.append(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        img_path = DATA_DIR / split / "images" / f"{split}_{idx:04d}.jpg"
        lbl_path = DATA_DIR / split / "labels" / f"{split}_{idx:04d}.txt"
        cv2.imwrite(str(img_path), img)
        with open(lbl_path, "w") as f:
            f.write("\n".join(labels))

    for i in range(n_train):
        create_sample("train", i)
        if i % 50 == 0:
            print(f"  Generated {i}/{n_train} training images...")

    for i in range(n_val):
        create_sample("val", i)

    print(f"✅ Synthetic dataset ready: {n_train} train, {n_val} val images")


def _create_text_placeholders(n_train, n_val):
    """Fallback: create empty label files so YAML is valid."""
    for split, n in [("train", n_train), ("val", n_val)]:
        for i in range(n):
            (DATA_DIR / split / "labels" / f"{split}_{i:04d}.txt").write_text("")
    print(f"✅ Placeholder dataset created (no real images — add your own to dataset/train/images/)")


def write_dataset_yaml():
    """Write the dataset configuration YAML file required by YOLOv8."""
    config = {
        "path": str(DATA_DIR.resolve()),
        "train": "train/images",
        "val":   "val/images",
        "test":  "test/images",
        "nc":    len(CLASSES),
        "names": CLASSES,
    }
    yaml_path = DATA_DIR / "dataset.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"✅ Dataset YAML written to: {yaml_path}")
    return yaml_path


# ── STEP 2: Model Training ─────────────────────────────────────────────────────

def train_model():
    """Train YOLOv8 on the prepared dataset."""
    print("\n" + "="*60)
    print("  STEP 2: Model Training")
    print("="*60)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics not installed!")
        print("   Run: pip install ultralytics")
        sys.exit(1)

    yaml_path = DATA_DIR / "dataset.yaml"
    if not yaml_path.exists():
        print("❌ Dataset not prepared. Run: python train_yolo.py --mode prepare")
        sys.exit(1)

    print(f"🚀 Starting training:")
    print(f"   Model:   {TRAINING_CONFIG['model']}")
    print(f"   Epochs:  {TRAINING_CONFIG['epochs']}")
    print(f"   Image:   {TRAINING_CONFIG['imgsz']}px")
    print(f"   Device:  {TRAINING_CONFIG['device']}")
    print(f"   Classes: {len(CLASSES)}")
    print()

    # Load base model
    model = YOLO(TRAINING_CONFIG["model"])

    # Start training
    results = model.train(
        data      = str(yaml_path),
        epochs    = TRAINING_CONFIG["epochs"],
        imgsz     = TRAINING_CONFIG["imgsz"],
        batch     = TRAINING_CONFIG["batch"],
        device    = TRAINING_CONFIG["device"],
        workers   = TRAINING_CONFIG["workers"],
        patience  = TRAINING_CONFIG["patience"],
        project   = str(RUNS_DIR),
        name      = "shelf_inventory",
        exist_ok  = True,
        # Optimizer
        lr0       = TRAINING_CONFIG["lr0"],
        lrf       = TRAINING_CONFIG["lrf"],
        momentum  = TRAINING_CONFIG["momentum"],
        weight_decay = TRAINING_CONFIG["weight_decay"],
        # Augmentation
        hsv_h     = TRAINING_CONFIG["hsv_h"],
        hsv_s     = TRAINING_CONFIG["hsv_s"],
        hsv_v     = TRAINING_CONFIG["hsv_v"],
        degrees   = TRAINING_CONFIG["degrees"],
        translate = TRAINING_CONFIG["translate"],
        scale     = TRAINING_CONFIG["scale"],
        fliplr    = TRAINING_CONFIG["fliplr"],
        mosaic    = TRAINING_CONFIG["mosaic"],
        mixup     = TRAINING_CONFIG["mixup"],
        # Logging
        save      = True,
        save_period = 10,
        plots     = True,
        verbose   = True,
    )

    # Copy best model to models/
    best_path = RUNS_DIR / "shelf_inventory" / "weights" / "best.pt"
    if best_path.exists():
        dest = MODEL_DIR / "shelf_yolo.pt"
        shutil.copy(best_path, dest)
        print(f"\n✅ Best model saved to: {dest}")
    else:
        print("⚠️  Training complete but best.pt not found. Check runs/shelf_inventory/weights/")

    print("\n📊 Training Results:")
    print(f"   Results saved to: {RUNS_DIR / 'shelf_inventory'}")
    print(f"   View charts:      {RUNS_DIR / 'shelf_inventory' / 'results.png'}")

    return results


# ── STEP 3: Evaluation ────────────────────────────────────────────────────────

def evaluate_model():
    """Run validation and print mAP, precision, recall metrics."""
    print("\n" + "="*60)
    print("  STEP 3: Model Evaluation")
    print("="*60)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics not installed")
        return

    model_path = MODEL_DIR / "shelf_yolo.pt"
    if not model_path.exists():
        print(f"❌ Model not found at {model_path}")
        print("   Train first: python train_yolo.py --mode train")
        return

    model = YOLO(str(model_path))
    yaml_path = DATA_DIR / "dataset.yaml"

    print(f"🔍 Evaluating model: {model_path}")
    metrics = model.val(data=str(yaml_path), verbose=True)

    print("\n📊 Evaluation Results:")
    print(f"   mAP50:      {metrics.box.map50:.4f}")
    print(f"   mAP50-95:   {metrics.box.map:.4f}")
    print(f"   Precision:  {metrics.box.mp:.4f}")
    print(f"   Recall:     {metrics.box.mr:.4f}")

    # Per-class results
    print("\n📋 Per-class AP:")
    for i, (cls, ap) in enumerate(zip(CLASSES, metrics.box.ap50)):
        bar = "█" * int(ap * 20)
        print(f"   {cls:<25} {bar:<20} {ap:.3f}")


# ── STEP 4: Export ────────────────────────────────────────────────────────────

def export_model():
    """Export trained model to ONNX and TFLite for deployment."""
    print("\n" + "="*60)
    print("  STEP 4: Model Export")
    print("="*60)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics not installed")
        return

    model_path = MODEL_DIR / "shelf_yolo.pt"
    if not model_path.exists():
        print(f"❌ Model not found: {model_path}")
        return

    model = YOLO(str(model_path))

    # Export to ONNX (for CPU deployment, edge devices)
    print("📦 Exporting to ONNX...")
    model.export(format="onnx", imgsz=640, simplify=True)
    print(f"✅ ONNX model: {MODEL_DIR / 'shelf_yolo.onnx'}")

    # Export to TFLite (for Raspberry Pi / mobile)
    print("📦 Exporting to TFLite (for Raspberry Pi)...")
    try:
        model.export(format="tflite", imgsz=640)
        print(f"✅ TFLite model exported")
    except Exception as e:
        print(f"⚠️  TFLite export failed (TensorFlow required): {e}")

    print("\n✅ Exported models ready for deployment:")
    print("   • shelf_yolo.onnx  → CPU / Edge deployment")
    print("   • shelf_yolo.pt    → PyTorch / GPU deployment")


# ── STEP 5: Test Inference ────────────────────────────────────────────────────

def test_inference():
    """
    Test the trained model on webcam or sample images.
    Press 'q' to quit the webcam window.
    """
    print("\n" + "="*60)
    print("  TEST: Live Inference")
    print("="*60)

    try:
        from ultralytics import YOLO
        import cv2
    except ImportError:
        print("❌ ultralytics or opencv-python not installed")
        return

    model_path = MODEL_DIR / "shelf_yolo.pt"
    if not model_path.exists():
        # Fall back to base YOLOv8 for demo
        print("⚠️  Custom model not found. Using base YOLOv8n for demo.")
        model_path = "yolov8n.pt"

    print(f"🤖 Loading model: {model_path}")
    model = YOLO(str(model_path))

    print("📷 Opening webcam... Press 'q' to quit, 's' to save frame")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("❌ Cannot open webcam. Check camera connection.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    frame_count = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        fps = frame_count / (time.time() - start_time)

        # Run inference
        results = model(frame, conf=0.45, verbose=False)

        # Draw results
        annotated = results[0].plot()

        # Add FPS overlay
        cv2.putText(annotated, f"FPS: {fps:.1f}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 212, 255), 2)
        cv2.putText(annotated, f"Detections: {len(results[0].boxes)}", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 157), 2)

        # Print detections to console
        for box in results[0].boxes:
            cls_name = model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            print(f"  Detected: {cls_name} ({conf:.2f})", end="\r")

        cv2.imshow("ShelfAI — Live Detection (q=quit, s=save)", annotated)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            save_path = f"detection_{int(time.time())}.jpg"
            cv2.imwrite(save_path, annotated)
            print(f"\n💾 Saved: {save_path}")

    cap.release()
    cv2.destroyAllWindows()
    print("\n✅ Inference test complete")


# ── Annotation Helper ─────────────────────────────────────────────────────────

def print_annotation_guide():
    """Print instructions for annotating your own product images."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           ANNOTATION GUIDE — Adding Your Own Products       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  OPTION 1: Roboflow (Easiest — free tier available)         ║
║  ─────────────────────────────────────────────────────────  ║
║  1. Go to https://roboflow.com and create an account        ║
║  2. Create a new project → Object Detection                 ║
║  3. Upload your shelf photos                                ║
║  4. Draw bounding boxes around each product                 ║
║  5. Export as YOLOv8 format                                 ║
║  6. Download and place in dataset/ folder                   ║
║                                                             ║
║  OPTION 2: LabelImg (Desktop app, offline)                  ║
║  ─────────────────────────────────────────────────────────  ║
║  pip install labelImg                                       ║
║  labelImg                                                   ║
║  • Set format to YOLO                                       ║
║  • Open image folder                                        ║
║  • Draw boxes and assign class labels                       ║
║                                                             ║
║  OPTION 3: Label Studio (advanced, web UI)                  ║
║  pip install label-studio                                   ║
║  label-studio start                                         ║
║                                                             ║
║  IMAGE COLLECTION TIPS:                                     ║
║  • 100–500 images per product class for good accuracy       ║
║  • Vary lighting, angles, distances                         ║
║  • Include partial occlusions                               ║
║  • Mix empty/full shelf scenarios                           ║
║                                                             ║
╚══════════════════════════════════════════════════════════════╝
""")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="YOLOv8 Training Pipeline — AI Shelf Inventory System"
    )
    parser.add_argument("--mode", choices=["prepare","train","evaluate","export","test","guide","all"],
                        default="all", help="Pipeline step to run")
    args = parser.parse_args()

    print("""
╔════════════════════════════════════════════════╗
║   YOLOv8 Shelf Inventory Training Pipeline    ║
║   AI-Based Inventory Monitoring System        ║
╚════════════════════════════════════════════════╝
""")

    if args.mode in ("prepare", "all"):
        prepare_dataset()
    if args.mode in ("train", "all"):
        train_model()
    if args.mode in ("evaluate", "all"):
        evaluate_model()
    if args.mode in ("export", "all"):
        export_model()
    if args.mode == "test":
        test_inference()
    if args.mode == "guide":
        print_annotation_guide()

    print("\n" + "="*60)
    print("  ✅ Pipeline complete!")
    print("="*60)
    print(f"""
Next steps:
  1. Place trained model at:  models/shelf_yolo.pt
  2. Enable real detection:   set USE_REAL_MODEL = True in backend/detection.py
  3. Start backend:           cd backend && python main.py
  4. Open dashboard:          frontend/demo_webcam.html
""")


if __name__ == "__main__":
    main()
