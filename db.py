"""
db.py - everything to do with connecting to the SQLite database.

Flask handles one browser request at a time per thread. For each request we
open ONE connection, keep it in Flask's `g` object (a per-request storage
box), and close it automatically when the request finishes.
"""
import sqlite3
from datetime import datetime

from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    """Return the database connection for the current request (open it if needed)."""
    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config["DATABASE"],
            # isolation_level=None puts Python's sqlite3 in "autocommit" mode.
            # Single statements save immediately, and WE decide where a
            # multi-step transaction starts and ends with BEGIN / COMMIT /
            # ROLLBACK - exactly like the pseudocode in Part 1, Section 5.
            isolation_level=None,
            timeout=10,  # wait up to 10s if another till is writing
        )
        conn.row_factory = sqlite3.Row            # lets us write row["product_name"]
        conn.execute("PRAGMA foreign_keys = ON")  # SQLite needs this switched on per connection
        g.db = conn
    return g.db


def close_db(e=None):
    """Close the connection at the end of the request (registered in app.py)."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now():
    """Current local date-time as text, e.g. '2026-11-16 14:05:33'.

    We store local time (not UTC) because reports are read by South African
    staff and 'today's sales' must mean today in South Africa.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db(default_password="Manager@123"):
    """Create all tables from schema.sql and the default Store Manager (FR-01)."""
    conn = get_db()
    with current_app.open_resource("schema.sql") as f:
        conn.executescript(f.read().decode("utf8"))
    conn.execute(
        "INSERT INTO User (username, password_hash, role) VALUES (?, ?, 'MANAGER')",
        ("manager", generate_password_hash(default_password, method="pbkdf2:sha256")),
    )
