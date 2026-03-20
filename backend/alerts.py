"""
alerts.py - Alert generation and management.

Detects stock threshold violations and generates/deduplicates alerts.
"""

from datetime import datetime
from typing import List, Dict
from .database import add_alert, get_connection

# Cooldown: don't re-alert for the same product within N seconds
ALERT_COOLDOWN_SECONDS = 60


class AlertManager:
    """
    Monitors inventory status and generates alerts when stock is low.
    Includes deduplication to avoid alert spam.
    """

    def __init__(self):
        # Track last alert time per product to avoid duplicates
        self.last_alert_time: Dict[str, datetime] = {}

    def check_and_generate(self, inventory_status: Dict) -> List[Dict]:
        """
        Given inventory analysis output, check each product
        and generate alerts if thresholds are breached.

        Returns: list of new alerts generated this cycle
        """
        new_alerts = []
        products = inventory_status.get("products", [])

        for product in products:
            name = product["name"]
            status = product["status"]

            if status not in ("OUT_OF_STOCK", "LOW_STOCK"):
                continue

            # Cooldown check
            last_time = self.last_alert_time.get(name)
            now = datetime.now()
            if last_time and (now - last_time).seconds < ALERT_COOLDOWN_SECONDS:
                continue

            # Generate alert
            self.last_alert_time[name] = now
            alert = {
                "product_name": name,
                "alert_type": status,
                "shelf_zone": product.get("shelf_zone", "Unknown"),
                "timestamp": now.isoformat(),
                "message": self._format_message(
                    name, status, product["detected_count"]
                ),
                "severity": "critical" if status == "OUT_OF_STOCK" else "warning",
            }
            new_alerts.append(alert)

            # Persist to database
            add_alert(
                product_name=name, alert_type=status, shelf_zone=alert["shelf_zone"]
            )

        return new_alerts

    def _format_message(self, name: str, status: str, count: int) -> str:
        if status == "OUT_OF_STOCK":
            return f"🚨 OUT OF STOCK: {name} — Shelf is completely empty!"
        else:
            return f"⚠️ LOW STOCK: {name} — Only {count} unit(s) remaining"

    def resolve_alert(self, alert_id: int) -> bool:
        """Mark an alert as resolved in the database."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def get_active_alert_count(self) -> int:
        """Returns number of unresolved alerts."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE resolved = 0")
        count = cursor.fetchone()[0]
        conn.close()
        return count
