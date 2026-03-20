"""
AI Shelf Inventory Monitoring System - FastAPI Backend
Main entry point for the REST API and WebSocket server.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import uvicorn
from datetime import datetime
from pathlib import Path
from typing import List

from .database import (
    init_db,
    get_db_stats,
    get_recent_alerts,
    get_inventory_logs,
)
from .detection import ShelfDetector
from .inventory_engine import InventoryEngine
from .alerts import AlertManager

app = FastAPI(
    title="AI Shelf Inventory Monitoring API",
    description="Real-time shelf monitoring using YOLOv8 and computer vision",
    version="1.0.0",
)

# Serve the web dashboard (static HTML/JS)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=str(WEB_DIR), html=True), name="static")


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/static/index.html")


# Allow browser frontend (same origin) to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
detector = ShelfDetector()
inventory_engine = InventoryEngine()
alert_manager = AlertManager()


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send message to all connected WebSocket clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections.remove(conn)


manager = ConnectionManager()


# ─── REST ENDPOINTS ───────────────────────────────────────────────────────────


@app.get("/api", include_in_schema=False)
async def api_root():
    return {"message": "AI Shelf Inventory API is running", "version": "1.0.0"}


@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Returns key metrics for the dashboard overview cards."""
    stats = get_db_stats()
    return {
        "total_products_detected": stats["total_detected"],
        "out_of_stock_count": stats["out_of_stock"],
        "low_stock_count": stats["low_stock"],
        "shelves_monitored": stats["shelves_monitored"],
        "alerts_today": stats["alerts_today"],
        "detection_accuracy": stats["detection_accuracy"],
        "last_updated": datetime.now().isoformat(),
    }


@app.get("/api/alerts")
async def get_alerts(limit: int = 20):
    """Returns recent stock alerts."""
    alerts = get_recent_alerts(limit)
    return {"alerts": alerts, "total": len(alerts)}


@app.get("/api/inventory")
async def get_inventory():
    """Returns current shelf inventory status."""
    return inventory_engine.get_current_inventory()


@app.get("/api/analytics/hourly")
async def get_hourly_analytics():
    """Returns detections per hour for the past 24 hours."""
    logs = get_inventory_logs(hours=24)
    return {"data": logs, "generated_at": datetime.now().isoformat()}


@app.get("/api/analytics/products")
async def get_product_analytics():
    """Returns per-product stock statistics."""
    return inventory_engine.get_product_analytics()


@app.get("/api/shelves")
async def get_shelves():
    """Returns shelf layout and occupancy data for heatmap."""
    return inventory_engine.get_shelf_data()


@app.post("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int):
    """Mark an alert as resolved."""
    success = alert_manager.resolve_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert resolved", "alert_id": alert_id}


# ─── WEBSOCKET ENDPOINT ───────────────────────────────────────────────────────


@app.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    """
    WebSocket endpoint that streams live detection data to the dashboard.
    Sends updates every second with simulated/real camera detections.
    """
    await manager.connect(websocket)
    try:
        # Start streaming detection results
        while True:
            # Get latest detection frame data
            frame_data = detector.get_latest_frame_data()

            # Run inventory analysis
            inventory_status = inventory_engine.analyze(frame_data["detections"])

            # Check for new alerts
            new_alerts = alert_manager.check_and_generate(inventory_status)

            # Build payload for frontend
            payload = {
                "type": "frame_update",
                "timestamp": datetime.now().isoformat(),
                "camera_id": "CAM_001",
                "detections": frame_data["detections"],
                "inventory": inventory_status,
                "new_alerts": new_alerts,
                "fps": frame_data["fps"],
                "frame_count": frame_data["frame_count"],
            }

            await websocket.send_json(payload)
            await asyncio.sleep(1)  # Push update every second

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error: {e}")
        manager.disconnect(websocket)


# ─── STARTUP ──────────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup_event():
    print("[START] AI Shelf Monitoring System starting...")
    init_db()
    detector.initialize()
    print("[OK] All systems initialized")


if __name__ == "__main__":
    # When run as a script, reference the module path so uvicorn can import it correctly
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
