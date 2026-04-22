"""
SQLite-backed job application tracker.
Replaces the old applied_jobs.json with a proper DB.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS applied_jobs (
                id          TEXT NOT NULL,
                platform    TEXT NOT NULL,
                title       TEXT,
                company     TEXT,
                url         TEXT,
                applied_at  TEXT NOT NULL,
                PRIMARY KEY (id, platform)
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                date        TEXT NOT NULL,
                platform    TEXT NOT NULL,
                applied     INTEGER DEFAULT 0,
                PRIMARY KEY (date, platform)
            );
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_applied(job_id: str, platform: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM applied_jobs WHERE id=? AND platform=?",
            (job_id, platform),
        ).fetchone()
        return row is not None


def mark_applied(job_id: str, platform: str, title: str, company: str, url: str = ""):
    now = datetime.now().isoformat()
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO applied_jobs (id, platform, title, company, url, applied_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, platform, title, company, url, now),
        )
        conn.execute(
            "INSERT INTO daily_stats (date, platform, applied) VALUES (?, ?, 1) "
            "ON CONFLICT(date, platform) DO UPDATE SET applied = applied + 1",
            (today, platform),
        )


def get_stats(days: int = 7) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT date, platform, applied FROM daily_stats "
            "WHERE date >= date('now', ?) ORDER BY date DESC, applied DESC",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_jobs(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM applied_jobs ORDER BY applied_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def total_applied() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM applied_jobs").fetchone()[0]


def applied_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        return conn.execute(
            "SELECT COALESCE(SUM(applied), 0) FROM daily_stats WHERE date=?",
            (today,),
        ).fetchone()[0]
