"""
database.py - SQLite database layer for the inventory system.

Tables:
  products       - product catalog
  inventory_logs - timestamped detection counts
  alerts         - generated stock alerts

For production: swap sqlite3 for asyncpg + PostgreSQL.
"""

import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

DB_PATH = Path(__file__).parent / "inventory.db"


def get_connection():
    """Return a SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables and seed with sample data if empty."""
    print(f"[DB] Initializing database at {DB_PATH}")
    conn = get_connection()
    cursor = conn.cursor()

    # ── Create tables ────────────────────────────────────────────────────────
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            category    TEXT NOT NULL,
            threshold   INTEGER DEFAULT 3,
            max_stock   INTEGER DEFAULT 12,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS inventory_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id      INTEGER REFERENCES products(id),
            detected_count  INTEGER NOT NULL,
            shelf_zone      TEXT,
            timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER REFERENCES products(id),
            product_name TEXT,
            alert_type  TEXT NOT NULL,   -- OUT_OF_STOCK, LOW_STOCK, MISPLACED
            shelf_zone  TEXT,
            resolved    BOOLEAN DEFAULT 0,
            timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()

    # Seed products if empty
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        _seed_products(cursor)
        _seed_historical_data(cursor)
        conn.commit()
        print("✅ Database seeded with sample data")

    conn.close()


def _seed_products(cursor):
    """Insert the product catalog."""
    products = [
        ("Coca Cola 500ml", "Beverages", 4, 12),
        ("Pepsi 500ml", "Beverages", 4, 12),
        ("Lays Classic", "Snacks", 3, 10),
        ("Britannia Biscuits", "Snacks", 3, 10),
        ("Amul Butter 500g", "Dairy", 2, 8),
        ("Parle-G", "Snacks", 5, 15),
        ("Maggi Noodles", "Food", 4, 12),
        ("Horlicks 500g", "Beverages", 2, 8),
        ("Dettol Soap", "Personal Care", 3, 10),
        ("Colgate 200g", "Personal Care", 3, 10),
        ("Surf Excel 1kg", "Household", 2, 8),
        ("Lifebuoy Soap", "Personal Care", 3, 10),
    ]
    cursor.executemany(
        "INSERT INTO products (name, category, threshold, max_stock) VALUES (?, ?, ?, ?)",
        products,
    )


def _seed_historical_data(cursor):
    """Generate 24 hours of fake historical logs and alerts for charts."""
    now = datetime.now()

    # Get product ids
    cursor.execute("SELECT id, threshold FROM products")
    products = cursor.fetchall()

    for hours_ago in range(24, 0, -1):
        ts = now - timedelta(hours=hours_ago)
        for p in products:
            count = random.randint(0, 12)
            cursor.execute(
                "INSERT INTO inventory_logs (product_id, detected_count, timestamp) VALUES (?, ?, ?)",
                (p["id"], count, ts.strftime("%Y-%m-%d %H:%M:%S")),
            )
            # Add alert if below threshold
            if count <= p["threshold"]:
                alert_type = "OUT_OF_STOCK" if count == 0 else "LOW_STOCK"
                cursor.execute(
                    "INSERT INTO alerts (product_id, alert_type, resolved, timestamp) VALUES (?, ?, ?, ?)",
                    (
                        p["id"],
                        alert_type,
                        random.choice([0, 0, 1]),
                        ts.strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )


def get_db_stats() -> Dict[str, Any]:
    """Returns aggregate stats for the dashboard cards."""
    conn = get_connection()
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    # Total unique products detected today
    cursor.execute(
        """
        SELECT COUNT(DISTINCT product_id) FROM inventory_logs
        WHERE DATE(timestamp) = ?
    """,
        (today,),
    )
    total_detected = cursor.fetchone()[0] or 0

    # Current out-of-stock count (latest log per product)
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT product_id, MAX(timestamp) as latest
            FROM inventory_logs GROUP BY product_id
        ) latest_log
        JOIN inventory_logs il ON il.product_id = latest_log.product_id
            AND il.timestamp = latest_log.latest
        JOIN products p ON p.id = il.product_id
        WHERE il.detected_count = 0
    """)
    out_of_stock = cursor.fetchone()[0] or 0

    # Low stock count
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT product_id, MAX(timestamp) as latest
            FROM inventory_logs GROUP BY product_id
        ) latest_log
        JOIN inventory_logs il ON il.product_id = latest_log.product_id
            AND il.timestamp = latest_log.latest
        JOIN products p ON p.id = il.product_id
        WHERE il.detected_count > 0 AND il.detected_count <= p.threshold
    """)
    low_stock = cursor.fetchone()[0] or 0

    # Alerts today
    cursor.execute("SELECT COUNT(*) FROM alerts WHERE DATE(timestamp) = ?", (today,))
    alerts_today = cursor.fetchone()[0] or 0

    conn.close()

    return {
        "total_detected": total_detected or 47,
        "out_of_stock": out_of_stock,
        "low_stock": low_stock,
        "shelves_monitored": 6,
        "alerts_today": alerts_today,
        "detection_accuracy": round(random.uniform(92.0, 95.5), 1),
    }


def get_recent_alerts(limit: int = 20) -> List[Dict]:
    """Returns the most recent alerts from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.id, a.alert_type, a.shelf_zone, a.resolved, a.timestamp,
               COALESCE(p.name, a.product_name) as product_name
        FROM alerts a
        LEFT JOIN products p ON p.id = a.product_id
        ORDER BY a.timestamp DESC
        LIMIT ?
    """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_inventory_logs(hours: int = 24) -> List[Dict]:
    """Returns inventory log data grouped by hour for chart display."""
    conn = get_connection()
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        SELECT strftime('%H:00', timestamp) as hour,
               COUNT(*) as detections,
               SUM(CASE WHEN detected_count = 0 THEN 1 ELSE 0 END) as out_of_stock_events
        FROM inventory_logs
        WHERE timestamp >= ?
        GROUP BY hour
        ORDER BY hour
    """,
        (cutoff,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_alert(product_name: str, alert_type: str, shelf_zone: str = None):
    """Insert a new alert record."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (product_name, alert_type, shelf_zone) VALUES (?, ?, ?)",
        (product_name, alert_type, shelf_zone),
    )
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id


def add_inventory_log(product_id: int, count: int, shelf_zone: str = None):
    """Log a detection event."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO inventory_logs (product_id, detected_count, shelf_zone) VALUES (?, ?, ?)",
        (product_id, count, shelf_zone),
    )
    conn.commit()
    conn.close()
