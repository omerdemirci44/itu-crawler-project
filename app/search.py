"""Search service boundary for the crawler project."""

from __future__ import annotations

from app.index_store import SQLiteIndexStore
from app.models import SearchResult


class SearchService:
    """Provide a thin interface for query processing and ranking."""

    def __init__(self, store: SQLiteIndexStore) -> None:
        """Keep the search layer decoupled from the storage details."""

        self.store = store

    def search(self, query: str) -> list[SearchResult]:
        """Return search results as `(relevant_url, origin_url, depth)` values."""

        return self.store.search(query)
