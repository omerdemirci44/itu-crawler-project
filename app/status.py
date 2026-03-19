"""Status tracking for indexing progress and back pressure visibility."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from threading import Lock

from app.models import StatusSnapshot


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "crawler.db"


class StatusService:
    """Track the latest crawl status and persist it in SQLite."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Load the latest persisted status snapshot or an idle default."""

        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self._lock = Lock()
        self._initialize()
        self._snapshot = self._load_snapshot()

    def start(self, origin: str, max_depth: int, max_queue_size: int) -> None:
        """Record that an indexing run has started."""

        with self._lock:
            self._snapshot = StatusSnapshot(
                origin_url=origin,
                max_depth=max_depth,
                indexed_pages=0,
                queued_urls=0,
                max_queue_size=max_queue_size,
                back_pressure_active=False,
                is_indexing=True,
                last_message="crawl starting",
            )
            self._persist_snapshot()

    def set_queue_depth(self, queued_urls: int) -> None:
        """Update the visible number of queued URLs."""

        with self._lock:
            self._snapshot.queued_urls = max(queued_urls, 0)
            self._snapshot.back_pressure_active = (
                self._snapshot.max_queue_size > 0
                and self._snapshot.queued_urls >= self._snapshot.max_queue_size
            )
            self._persist_snapshot()

    def increment_indexed_pages(self) -> None:
        """Increase the count of successfully stored HTML pages."""

        with self._lock:
            self._snapshot.indexed_pages += 1
            self._persist_snapshot()

    def set_message(self, message: str) -> None:
        """Set a short status message describing current crawl progress."""

        with self._lock:
            self._snapshot.last_message = message
            self._persist_snapshot()

    def finish(self, message: str = "crawl complete") -> None:
        """Mark the indexing run as complete."""

        with self._lock:
            self._snapshot.is_indexing = False
            self._snapshot.queued_urls = 0
            self._snapshot.back_pressure_active = False
            self._snapshot.last_message = message
            self._persist_snapshot()

    def snapshot(self) -> StatusSnapshot:
        """Return the latest known status information."""

        with self._lock:
            return replace(self._snapshot)

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection for the status database."""

        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        """Create the status table if it does not already exist."""

        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    origin_url TEXT NOT NULL DEFAULT '',
                    max_depth INTEGER NOT NULL DEFAULT 0,
                    indexed_pages INTEGER NOT NULL DEFAULT 0,
                    queued_urls INTEGER NOT NULL DEFAULT 0,
                    max_queue_size INTEGER NOT NULL DEFAULT 0,
                    back_pressure_active INTEGER NOT NULL DEFAULT 0,
                    is_indexing INTEGER NOT NULL DEFAULT 0,
                    last_message TEXT NOT NULL DEFAULT 'idle'
                )
                """
            )

    def _load_snapshot(self) -> StatusSnapshot:
        """Load the latest persisted status row or return an idle snapshot."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM crawl_status WHERE id = 1"
            ).fetchone()

        if row is None:
            return StatusSnapshot()

        return StatusSnapshot(
            origin_url=row["origin_url"],
            max_depth=row["max_depth"],
            indexed_pages=row["indexed_pages"],
            queued_urls=row["queued_urls"],
            max_queue_size=row["max_queue_size"],
            back_pressure_active=bool(row["back_pressure_active"]),
            is_indexing=bool(row["is_indexing"]),
            last_message=row["last_message"],
        )

    def _persist_snapshot(self) -> None:
        """Persist the in-memory snapshot as the latest crawl status."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO crawl_status (
                    id,
                    origin_url,
                    max_depth,
                    indexed_pages,
                    queued_urls,
                    max_queue_size,
                    back_pressure_active,
                    is_indexing,
                    last_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    origin_url = excluded.origin_url,
                    max_depth = excluded.max_depth,
                    indexed_pages = excluded.indexed_pages,
                    queued_urls = excluded.queued_urls,
                    max_queue_size = excluded.max_queue_size,
                    back_pressure_active = excluded.back_pressure_active,
                    is_indexing = excluded.is_indexing,
                    last_message = excluded.last_message
                """,
                (
                    1,
                    self._snapshot.origin_url,
                    self._snapshot.max_depth,
                    self._snapshot.indexed_pages,
                    self._snapshot.queued_urls,
                    self._snapshot.max_queue_size,
                    int(self._snapshot.back_pressure_active),
                    int(self._snapshot.is_indexing),
                    self._snapshot.last_message,
                ),
            )
