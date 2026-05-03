"""
database.py — SQLite-backed deduplication store.

Tracks every item (by URL) that has been fetched, so we never
send the same regulatory update twice regardless of how often
the tracker runs.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


# ── Internal helpers ──────────────────────────────────────────────────────────

def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Public API ────────────────────────────────────────────────────────────────

def init_db(db_path: Path) -> None:
    """Create tables if they don't exist yet."""
    with _conn(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_items (
                url          TEXT PRIMARY KEY,
                title        TEXT,
                source_name  TEXT,
                category     TEXT,
                jurisdiction TEXT,
                first_seen   TEXT NOT NULL,
                emailed      INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at     TEXT NOT NULL,
                new_items  INTEGER,
                emailed    INTEGER,
                status     TEXT DEFAULT 'ok'
            )
        """)
        conn.commit()


def is_new(db_path: Path, url: str) -> bool:
    """Return True if this URL has never been seen before."""
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE url = ?", (url,)
        ).fetchone()
    return row is None


def mark_seen(
    db_path: Path,
    url: str,
    title: str,
    source_name: str,
    category: str = "",
    jurisdiction: str = "",
) -> None:
    """Insert a new item; silently ignore if URL already exists."""
    with _conn(db_path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO seen_items
               (url, title, source_name, category, jurisdiction, first_seen)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                url, title, source_name, category, jurisdiction,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def mark_emailed(db_path: Path, urls: list[str]) -> None:
    """Flag a list of URLs as having been included in an emailed digest."""
    with _conn(db_path) as conn:
        conn.executemany(
            "UPDATE seen_items SET emailed = 1 WHERE url = ?",
            [(u,) for u in urls],
        )
        conn.commit()


def log_run(db_path: Path, new_items: int, emailed: int, status: str = "ok") -> None:
    """Append a run record for auditing."""
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT INTO run_log (run_at, new_items, emailed, status) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), new_items, emailed, status),
        )
        conn.commit()


def recent_runs(db_path: Path, n: int = 10) -> list[sqlite3.Row]:
    """Return the N most recent run log entries (newest first)."""
    with _conn(db_path) as conn:
        return conn.execute(
            "SELECT * FROM run_log ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
