"""Crawler service boundary for scheduling future crawl work."""

from __future__ import annotations

from app.index_store import InMemoryIndexStore
from app.models import IndexRequest
from app.status import StatusService


class CrawlerService:
    """Accept indexing requests without implementing real crawling yet.

    Planned direction:
    - BFS traversal from the origin URL
    - worker pool with shared thread-safe state
    - bounded queue for simple back pressure
    """

    def __init__(
        self,
        store: InMemoryIndexStore,
        status_service: StatusService,
        max_queue_size: int = 128,
    ) -> None:
        """Store the lightweight dependencies needed by the crawler boundary."""

        self.store = store
        self.status_service = status_service
        self.max_queue_size = max_queue_size

    def index(self, origin: str, max_depth: int) -> IndexRequest:
        """Register a crawl request and update placeholder status only."""

        request = IndexRequest(origin_url=origin, max_depth=max_depth)
        self.status_service.start(
            origin=origin,
            max_depth=max_depth,
            max_queue_size=self.max_queue_size,
        )
        return request
