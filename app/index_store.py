"""SQLite-backed storage for indexed pages and search state."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from app.models import PageRecord, SearchResult


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "crawler.db"
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class SQLiteIndexStore:
    """Persist crawled pages in a small local SQLite database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize the SQLite store and create tables if needed."""

        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self._initialize()

    def clear(self) -> None:
        """Remove all stored page records for a fresh indexing run."""

        with self._connect() as connection:
            connection.execute("DELETE FROM pages")

    def has_page(self, url: str) -> bool:
        """Return whether the given URL is already known to the store."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM pages WHERE url = ? LIMIT 1",
                (url,),
            ).fetchone()
        return row is not None

    def upsert_page(self, page: PageRecord) -> None:
        """Insert or replace a crawled page record."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pages (url, origin_url, depth, title, body_text)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    origin_url = excluded.origin_url,
                    depth = excluded.depth,
                    title = excluded.title,
                    body_text = excluded.body_text
                """,
                (
                    page.url,
                    page.origin_url,
                    page.depth,
                    page.title,
                    page.body_text,
                ),
            )

    def search(self, query: str) -> list[SearchResult]:
        """Return ranked search results from the persisted page records."""

        normalized_query = " ".join(query.lower().split())
        tokens = sorted(set(_TOKEN_PATTERN.findall(normalized_query)))
        if not normalized_query or not tokens:
            return []

        ranked_matches: list[tuple[int, int, str, SearchResult]] = []
        for page in self.list_pages():
            score = self._score_page(page, normalized_query, tokens)
            if score <= 0:
                continue

            ranked_matches.append(
                (
                    score,
                    page.depth,
                    page.url,
                    SearchResult(
                        relevant_url=page.url,
                        origin_url=page.origin_url,
                        depth=page.depth,
                    ),
                )
            )

        ranked_matches.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [item[3] for item in ranked_matches]

    def page_count(self) -> int:
        """Return the number of stored pages."""

        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM pages").fetchone()
        return int(row[0])

    def list_pages(self, limit: int | None = None) -> list[PageRecord]:
        """Return stored pages for status, CLI output, or search."""

        query = (
            "SELECT url, origin_url, depth, title, body_text "
            "FROM pages ORDER BY depth ASC, url ASC"
        )
        parameters: tuple[object, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            parameters = (limit,)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_page(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with row access by column name."""

        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        """Create the minimal schema needed for persisted pages."""

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    url TEXT PRIMARY KEY,
                    origin_url TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    body_text TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def _row_to_page(self, row: sqlite3.Row) -> PageRecord:
        """Convert a SQLite row into a page record."""

        return PageRecord(
            url=row["url"],
            origin_url=row["origin_url"],
            depth=row["depth"],
            title=row["title"],
            body_text=row["body_text"],
        )

    def _score_page(
        self,
        page: PageRecord,
        normalized_query: str,
        tokens: list[str],
    ) -> int:
        """Apply the simple PRD-aligned ranking heuristic to one page."""

        title_text = page.title.lower()
        url_text = page.url.lower()
        body_text = page.body_text.lower()
        score = 0

        if normalized_query in title_text:
            score += 6
        if normalized_query in url_text:
            score += 4

        for token in tokens:
            if token in title_text:
                score += 3
            if token in url_text:
                score += 2
            if token in body_text:
                score += 1

        return score


InMemoryIndexStore = SQLiteIndexStore
