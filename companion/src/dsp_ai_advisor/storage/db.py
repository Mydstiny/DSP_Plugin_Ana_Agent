"""SQLite persistence for scan results, task history, and agent memory."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


class AdvisorDB:
    """Async SQLite database for persistent storage."""

    def __init__(self, db_path: str = "data/advisor.db") -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and initialize schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._init_schema()
        logger.info("Database connected: %s", self._db_path.absolute())

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS scan_results (
                id TEXT PRIMARY KEY,
                timestamp_unix INTEGER NOT NULL,
                data_json TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS task_history (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                priority TEXT NOT NULL,
                category TEXT NOT NULL,
                planet TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS agent_sessions (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                rounds INTEGER DEFAULT 0,
                tasks_generated INTEGER DEFAULT 0,
                started_at TEXT DEFAULT (datetime('now')),
                finished_at TEXT
            );
        """)
        await self._conn.commit()

    async def save_scan(self, scan_id: str, timestamp: int, data: dict) -> None:
        """Save a galaxy scan result."""
        if not self._conn:
            return
        await self._conn.execute(
            "INSERT OR REPLACE INTO scan_results (id, timestamp_unix, data_json) VALUES (?, ?, ?)",
            (scan_id, timestamp, json.dumps(data)),
        )
        await self._conn.commit()

    async def save_tasks(self, tasks: list[dict]) -> None:
        """Batch save task items."""
        if not self._conn:
            return
        for t in tasks:
            await self._conn.execute(
                """INSERT OR REPLACE INTO task_history
                   (id, title, priority, category, planet, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    t.get("id"),
                    t.get("title"),
                    t.get("priority"),
                    t.get("category"),
                    t.get("planet"),
                    t.get("status", "new"),
                ),
            )
        await self._conn.commit()
