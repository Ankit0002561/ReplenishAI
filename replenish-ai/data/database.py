"""
Database module for ReplenishAI.
Initializes SQLite database and tables for products, suppliers, and daily sales logs.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any

DATA_DIR = Path(__file__).resolve().parent
DB_PATH = DATA_DIR / "replenish.db"
MOCK_DATA_JSON = DATA_DIR / "mock_data.json"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or DB_PATH
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None, force_reset: bool = False) -> None:
    target_path = db_path or DB_PATH
    if force_reset and target_path.exists():
        target_path.unlink()

    conn = get_connection(target_path)
    cursor = conn.cursor()

    # 1. Products Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            available_stock REAL NOT NULL,
            unit_cost REAL NOT NULL,
            reorder_point REAL NOT NULL,
            warehouse_location TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Suppliers Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY,
            supplier_name TEXT NOT NULL,
            sku TEXT NOT NULL,
            strategy_type TEXT NOT NULL, -- 'Alpha' (Cost-Optimized) or 'Beta' (Expedited)
            lead_time_days INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            shipping_cost REAL NOT NULL,
            moq INTEGER NOT NULL DEFAULT 1,
            reliability_score REAL NOT NULL DEFAULT 95.0,
            contact_email TEXT,
            FOREIGN KEY (sku) REFERENCES products(sku)
        );
    """)

    # 3. Daily Sales Demand Log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_demand_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            day_offset INTEGER NOT NULL, -- Day 1 to 30
            units_sold REAL NOT NULL,
            log_date DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (sku) REFERENCES products(sku)
        );
    """)

    conn.commit()

    # Seed initial data if tables are empty
    cursor.execute("SELECT COUNT(*) FROM products;")
    if cursor.fetchone()[0] == 0:
        seed_data(conn)

    conn.close()


def seed_data(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    if not MOCK_DATA_JSON.exists():
        raise FileNotFoundError(f"Mock data seed file missing at {MOCK_DATA_JSON}")

    with open(MOCK_DATA_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Insert products
    for p in data["products"]:
        cursor.execute("""
            INSERT OR REPLACE INTO products (sku, name, category, available_stock, unit_cost, reorder_point, warehouse_location)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (p["sku"], p["name"], p["category"], p["available_stock"], p["unit_cost"], p["reorder_point"], p["warehouse_location"]))

    # Insert suppliers
    for s in data["suppliers"]:
        cursor.execute("""
            INSERT OR REPLACE INTO suppliers (supplier_id, supplier_name, sku, strategy_type, lead_time_days, unit_price, shipping_cost, moq, reliability_score, contact_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (s["supplier_id"], s["supplier_name"], s["sku"], s["strategy_type"], s["lead_time_days"], s["unit_price"], s["shipping_cost"], s["moq"], s["reliability_score"], s.get("contact_email", "")))

    # Insert daily sales logs
    for log_item in data["daily_sales_logs"]:
        sku = log_item["sku"]
        history = log_item["history"]
        for day_idx, sold in enumerate(history, start=1):
            cursor.execute("""
                INSERT INTO sales_demand_log (sku, day_offset, units_sold)
                VALUES (?, ?, ?);
            """, (sku, day_idx, sold))

    conn.commit()


def get_all_products(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY sku ASC;")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_product(sku: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE sku = ?;", (sku,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_suppliers_for_sku(sku: str, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers WHERE sku = ? ORDER BY strategy_type ASC;", (sku,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_sales_log_for_sku(sku: str, days: int = 30, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT day_offset, units_sold FROM sales_demand_log 
        WHERE sku = ? 
        ORDER BY day_offset DESC 
        LIMIT ?;
    """, (sku, days))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    # return chronological (oldest to newest)
    return list(reversed(rows))


if __name__ == "__main__":
    init_db(force_reset=True)
    products = get_all_products()
    print(f"Initialized SQLite database at {DB_PATH} with {len(products)} products.")
