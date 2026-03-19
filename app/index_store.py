"""Storage interface for indexed pages and future search state."""

from __future__ import annotations

from app.models import PageRecord, SearchResult


class InMemoryIndexStore:
    """Keep the first version of storage in memory with a narrow interface.

    The public methods are designed so the backing store can later move to
    SQLite without forcing the rest of the application to change shape.
    """

    def __init__(self) -> None:
        """Initialize the in-memory page map used by the scaffold."""

        self._pages: dict[str, PageRecord] = {}

    def clear(self) -> None:
        """Remove all stored page records for a fresh indexing run."""

        self._pages.clear()

    def has_page(self, url: str) -> bool:
        """Return whether the given URL is already known to the store."""

        return url in self._pages

    def upsert_page(self, page: PageRecord) -> None:
        """Insert or replace a page record.

        Search indexing and persistence are intentionally left for later sprints.
        """

        self._pages[page.url] = page

    def search(self, query: str) -> list[SearchResult]:
        """Return placeholder search results for the requested query."""

        _ = query
        return []

    def page_count(self) -> int:
        """Return the number of stored pages."""

        return len(self._pages)

    def list_pages(self, limit: int | None = None) -> list[PageRecord]:
        """Return stored pages in insertion order for status or CLI output."""

        pages = list(self._pages.values())
        if limit is None:
            return pages
        return pages[:limit]
