import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import DB_PATH, NTFY_TOPIC


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                target_price REAL NOT NULL,
                current_price REAL,
                lowest_price REAL,
                highest_price REAL,
                last_checked TEXT,
                last_status TEXT DEFAULT 'pending',
                last_error TEXT,
                last_notified_price REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                price REAL NOT NULL,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        # Inicializar el tema ntfy desde config.py si no existe en la tabla settings
        cur = conn.execute("SELECT value FROM settings WHERE key = 'ntfy_topic'")
        if not cur.fetchone():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('ntfy_topic', ?)",
                (NTFY_TOPIC,),
            )
        conn.commit()


def get_ntfy_topic() -> str:
    with get_connection() as conn:
        cur = conn.execute("SELECT value FROM settings WHERE key = 'ntfy_topic'")
        row = cur.fetchone()
        return row["value"] if row else NTFY_TOPIC


def set_ntfy_topic(topic: str) -> str:
    clean_topic = topic.strip()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES ('ntfy_topic', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (clean_topic,),
        )
        conn.commit()
    return clean_topic


def create_item(name: str, url: str, target_price: float) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO items (name, url, target_price, last_status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (name.strip(), url.strip(), round(float(target_price), 2), now),
        )
        item_id = cur.lastrowid
        conn.commit()
        return get_item(item_id)


def get_item(item_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = cur.fetchone()
        if not row:
            return None
        item = dict(row)
        hist_cur = conn.execute(
            """
            SELECT price, recorded_at
            FROM price_history
            WHERE item_id = ?
            ORDER BY id DESC
            LIMIT 30
            """,
            (item_id,),
        )
        item["history"] = [dict(h) for h in hist_cur.fetchall()][::-1]
        return item


def list_items() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM items ORDER BY id DESC")
        rows = cur.fetchall()
        items = []
        for row in rows:
            item = dict(row)
            hist_cur = conn.execute(
                """
                SELECT price, recorded_at
                FROM price_history
                WHERE item_id = ?
                ORDER BY id DESC
                LIMIT 20
                """,
                (item["id"],),
            )
            item["history"] = [dict(h) for h in hist_cur.fetchall()][::-1]
            items.append(item)
        return items


def update_item_price(
    item_id: int,
    price: Optional[float],
    status: str = "ok",
    error: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        existing = cur.fetchone()
        if not existing:
            return None

        if price is not None:
            rounded_price = round(float(price), 2)
            lowest = existing["lowest_price"]
            highest = existing["highest_price"]
            new_lowest = (
                rounded_price if lowest is None else min(float(lowest), rounded_price)
            )
            new_highest = (
                rounded_price if highest is None else max(float(highest), rounded_price)
            )

            conn.execute(
                """
                UPDATE items
                SET current_price = ?,
                    lowest_price = ?,
                    highest_price = ?,
                    last_checked = ?,
                    last_status = ?,
                    last_error = NULL
                WHERE id = ?
                """,
                (rounded_price, new_lowest, new_highest, now, status, item_id),
            )
            conn.execute(
                """
                INSERT INTO price_history (item_id, price, recorded_at)
                VALUES (?, ?, ?)
                """,
                (item_id, rounded_price, now),
            )
        else:
            conn.execute(
                """
                UPDATE items
                SET last_checked = ?,
                    last_status = ?,
                    last_error = ?
                WHERE id = ?
                """,
                (now, status, error, item_id),
            )
        conn.commit()
    return get_item(item_id)


def mark_item_notified(item_id: int, notified_price: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE items SET last_notified_price = ? WHERE id = ?",
            (round(float(notified_price), 2), item_id),
        )
        conn.commit()


def delete_item(item_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        return cur.rowcount > 0
