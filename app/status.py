"""Status tracking for indexing progress and back pressure visibility."""

from __future__ import annotations

from app.models import StatusSnapshot


class StatusService:
    """Track the small status surface needed by CLI and future UI callers."""

    def __init__(self) -> None:
        """Start with an idle status snapshot."""

        self._snapshot = StatusSnapshot()

    def start(self, origin: str, max_depth: int, max_queue_size: int) -> None:
        """Record that an indexing run has started."""

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

    def set_queue_depth(self, queued_urls: int) -> None:
        """Update the visible number of queued URLs."""

        self._snapshot.queued_urls = max(queued_urls, 0)
        self._snapshot.back_pressure_active = (
            self._snapshot.max_queue_size > 0
            and self._snapshot.queued_urls >= self._snapshot.max_queue_size
        )

    def increment_indexed_pages(self) -> None:
        """Increase the count of successfully stored HTML pages."""

        self._snapshot.indexed_pages += 1

    def set_message(self, message: str) -> None:
        """Set a short status message describing current crawl progress."""

        self._snapshot.last_message = message

    def finish(self, message: str = "crawl complete") -> None:
        """Mark the indexing run as complete."""

        self._snapshot.is_indexing = False
        self._snapshot.queued_urls = 0
        self._snapshot.back_pressure_active = False
        self._snapshot.last_message = message

    def snapshot(self) -> StatusSnapshot:
        """Return the latest known status information."""

        return self._snapshot
