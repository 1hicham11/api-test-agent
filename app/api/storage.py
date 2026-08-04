"""SQLite persistence for analysis reports.

A fresh connection per operation keeps the module trivially thread-safe
(FastAPI sync endpoints and background tasks run in a threadpool).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models.report import Report

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    target_url TEXT NOT NULL,
    report_json TEXT,
    error TEXT
)
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.reports_db)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Create the reports table if it does not exist."""
    with _connect() as connection:
        connection.execute(_SCHEMA)


def create_report(report_id: str, target_url: str) -> None:
    """Register a new run with status ``running``."""
    with _connect() as connection:
        connection.execute(
            "INSERT INTO reports (id, created_at, status, target_url) VALUES (?, ?, ?, ?)",
            (report_id, datetime.now(timezone.utc).isoformat(), "running", target_url),
        )


def save_report(report_id: str, report: Report) -> None:
    """Persist a finished (completed or failed) report."""
    with _connect() as connection:
        connection.execute(
            "UPDATE reports SET status = ?, report_json = ?, error = ? WHERE id = ?",
            (report.status, report.model_dump_json(), report.error, report_id),
        )


def mark_crashed(report_id: str, error: str) -> None:
    """Record an unexpected workflow crash."""
    with _connect() as connection:
        connection.execute(
            "UPDATE reports SET status = 'failed', error = ? WHERE id = ?",
            (error, report_id),
        )


def get_report(report_id: str) -> dict[str, Any] | None:
    """Fetch one report row; ``report`` is the parsed JSON or None."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
    if row is None:
        return None
    return {
        "report_id": row["id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "target_url": row["target_url"],
        "error": row["error"],
        "report": json.loads(row["report_json"]) if row["report_json"] else None,
    }


def list_reports(limit: int = 50) -> list[dict[str, Any]]:
    """Most-recent-first summaries of all runs."""
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id, created_at, status, target_url FROM reports "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "report_id": row["id"],
            "created_at": row["created_at"],
            "status": row["status"],
            "target_url": row["target_url"],
        }
        for row in rows
    ]
