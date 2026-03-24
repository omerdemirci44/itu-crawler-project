"""Crawler service for the first working BFS crawler core."""

from __future__ import annotations

from dataclasses import dataclass
from queue import Full, Queue
from threading import Thread
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from app.index_store import InMemoryIndexStore
from app.models import IndexRequest, PageRecord
from app.parser import extract_links, extract_text, extract_title, normalize_url
from app.status import StatusService


_STOP = object()


@dataclass(slots=True)
class _FrontierItem:
    """Represent one pending crawl item in the frontier."""

    url: str
    depth: int


@dataclass(slots=True)
class _CrawlResult:
    """Represent the output of one fetch-and-parse operation."""

    requested_url: str
    depth: int
    resolved_url: str | None = None
    page: PageRecord | None = None
    links: list[str] | None = None
    error_message: str = ""


class CrawlerService:
    """Perform a simple single-process BFS crawl and store HTML pages."""

    USER_AGENT = "itu-crawler-project/0.5"

    def __init__(
        self,
        store: InMemoryIndexStore,
        status_service: StatusService,
        max_queue_size: int = 128,
        request_timeout: float = 10.0,
        worker_count: int = 1,
    ) -> None:
        """Store the lightweight dependencies needed by the crawler boundary."""

        self.store = store
        self.status_service = status_service
        self.max_queue_size = max_queue_size
        self.request_timeout = request_timeout
        self.worker_count = max(1, worker_count)

    def index(self, origin: str, max_depth: int) -> IndexRequest:
        """Crawl HTML pages in BFS order from the normalized origin URL."""

        if max_depth < 0:
            raise ValueError("Maximum crawl depth must be zero or greater.")

        origin_url = normalize_url(origin)
        if origin_url is None:
            raise ValueError("Origin must be a valid http or https URL.")

        request = IndexRequest(origin_url=origin_url, max_depth=max_depth)
        origin_host = urlsplit(origin_url).netloc
        frontier: Queue[object] = Queue(maxsize=self.max_queue_size)
        results: Queue[_CrawlResult] = Queue()
        visited = {origin_url}

        self.store.clear()
        self.status_service.start(
            origin=origin_url,
            max_depth=max_depth,
            max_queue_size=self.max_queue_size,
        )
        self._enqueue_frontier(frontier, _FrontierItem(origin_url, 0))
        self.status_service.set_message("crawl running")

        pending_count = 1
        workers = [
            Thread(
                target=self._worker_loop,
                args=(frontier, results),
                daemon=True,
                name=f"crawler-worker-{index}",
            )
            for index in range(self.worker_count)
        ]
        for worker in workers:
            worker.start()

        while pending_count > 0:
            result = results.get()
            pending_count -= 1
            self.status_service.set_queue_depth(frontier.qsize())

            if result.error_message:
                self.status_service.set_message(result.error_message)
                continue

            if result.resolved_url is not None:
                visited.add(result.resolved_url)

            if result.page is not None:
                result.page.origin_url = origin_url
                self.store.upsert_page(result.page)
                self.status_service.increment_indexed_pages()
                self.status_service.set_message(f"indexed {result.page.url}")

            if result.depth >= max_depth or not result.links:
                continue

            for link in result.links:
                if urlsplit(link).netloc != origin_host:
                    continue
                if link in visited:
                    continue

                visited.add(link)
                self._enqueue_frontier(frontier, _FrontierItem(link, result.depth + 1))
                pending_count += 1

        for _ in workers:
            frontier.put(_STOP)
        for worker in workers:
            worker.join()

        try:
            from app.raw_search_storage import generate_storage_from_pages

            generate_storage_from_pages(self.store.list_pages())
        except Exception as error:
            self.status_service.finish(f"crawl export failed: {error}")
            raise

        self.status_service.finish(
            f"crawl complete: {self.store.page_count()} pages indexed"
        )
        return request

    def _worker_loop(
        self,
        frontier: Queue[object],
        results: Queue[_CrawlResult],
    ) -> None:
        """Fetch and parse frontier items until a stop sentinel is received."""

        while True:
            item = frontier.get()
            if item is _STOP:
                frontier.task_done()
                return

            assert isinstance(item, _FrontierItem)
            results.put(self._crawl_item(item))
            frontier.task_done()

    def _crawl_item(self, item: _FrontierItem) -> _CrawlResult:
        """Fetch and parse a single frontier item."""

        try:
            fetched = self._fetch_html(item.url)
            if fetched is None:
                return _CrawlResult(
                    requested_url=item.url,
                    depth=item.depth,
                    error_message=f"skipped non-html response: {item.url}",
                )

            html, resolved_url = fetched
            page = PageRecord(
                url=resolved_url,
                origin_url="",
                depth=item.depth,
                title=extract_title(html),
                body_text=extract_text(html),
            )
            links = extract_links(html, resolved_url)
            return _CrawlResult(
                requested_url=item.url,
                depth=item.depth,
                resolved_url=resolved_url,
                page=page,
                links=links,
            )
        except Exception as error:
            return _CrawlResult(
                requested_url=item.url,
                depth=item.depth,
                error_message=f"crawl failed for {item.url}: {error}",
            )

    def _enqueue_frontier(self, frontier: Queue[object], item: _FrontierItem) -> None:
        """Push one URL into the bounded frontier, waiting if the queue is full."""

        while True:
            try:
                frontier.put(item, timeout=0.2)
                self.status_service.set_queue_depth(frontier.qsize())
                return
            except Full:
                self.status_service.set_queue_depth(frontier.qsize())
                self.status_service.set_message(
                    f"waiting for queue space for {item.url}"
                )

    def _fetch_html(self, url: str) -> tuple[str, str] | None:
        """Fetch a URL and return decoded HTML plus the resolved final URL."""

        request = Request(url, headers={"User-Agent": self.USER_AGENT})
        with urlopen(request, timeout=self.request_timeout) as response:
            content_type = response.headers.get_content_type()
            if content_type != "text/html":
                return None

            final_url = normalize_url(response.geturl()) or url
            body = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            return self._decode_html(body, encoding), final_url

    def _decode_html(self, body: bytes, encoding: str) -> str:
        """Decode fetched HTML using the declared encoding with a safe fallback."""

        try:
            return body.decode(encoding, errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")
