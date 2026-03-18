"""Status tracking for indexing progress and back pressure visibility."""

from __future__ import annotations

from app.models import StatusSnapshot


class StatusService:
    """Track the small status surface needed by CLI and future UI callers."""

    def __init__(self) -> None:
        """Start with an idle status snapshot."""

        self._snapshot = StatusSnapshot()

    def start(self, origin: str, max_depth: int, max_queue_size: int) -> None:
        """Record that an indexing request has been accepted."""

        self._snapshot = StatusSnapshot(
            origin_url=origin,
            max_depth=max_depth,
            indexed_pages=0,
            queued_urls=1,
            max_queue_size=max_queue_size,
            back_pressure_active=False,
            is_indexing=True,
            last_message="accepted placeholder index request",
        )

    def snapshot(self) -> StatusSnapshot:
        """Return the latest known status information."""

        return self._snapshot
