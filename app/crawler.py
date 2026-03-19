"""Crawler service for the first working BFS crawler core."""

from __future__ import annotations

from collections import deque
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app.index_store import InMemoryIndexStore
from app.models import IndexRequest, PageRecord
from app.parser import extract_links, extract_text, extract_title, normalize_url
from app.status import StatusService


class CrawlerService:
    """Perform a simple single-process BFS crawl and store HTML pages."""

    USER_AGENT = "itu-crawler-project/0.2"

    def __init__(
        self,
        store: InMemoryIndexStore,
        status_service: StatusService,
        max_queue_size: int = 128,
        request_timeout: float = 10.0,
    ) -> None:
        """Store the lightweight dependencies needed by the crawler boundary."""

        self.store = store
        self.status_service = status_service
        self.max_queue_size = max_queue_size
        self.request_timeout = request_timeout

    def index(self, origin: str, max_depth: int) -> IndexRequest:
        """Crawl HTML pages in BFS order from the normalized origin URL."""

        if max_depth < 0:
            raise ValueError("Maximum crawl depth must be zero or greater.")

        origin_url = normalize_url(origin)
        if origin_url is None:
            raise ValueError("Origin must be a valid http or https URL.")

        request = IndexRequest(origin_url=origin_url, max_depth=max_depth)
        origin_host = urlsplit(origin_url).netloc
        frontier: deque[tuple[str, int]] = deque([(origin_url, 0)])
        visited = {origin_url}

        self.store.clear()
        self.status_service.start(
            origin=origin_url,
            max_depth=max_depth,
            max_queue_size=self.max_queue_size,
        )
        self.status_service.set_queue_depth(len(frontier))
        self.status_service.set_message("crawl running")

        while frontier:
            current_url, depth = frontier.popleft()
            self.status_service.set_queue_depth(len(frontier))
            self.status_service.set_message(f"fetching {current_url}")

            fetched = self._fetch_html(current_url)
            if fetched is None:
                continue

            html, resolved_url = fetched
            visited.add(resolved_url)

            try:
                page = PageRecord(
                    url=resolved_url,
                    origin_url=origin_url,
                    depth=depth,
                    title=extract_title(html),
                    body_text=extract_text(html),
                )
                self.store.upsert_page(page)
                self.status_service.increment_indexed_pages()
            except Exception as error:
                self.status_service.set_message(
                    f"parse failed for {current_url}: {error}"
                )
                continue

            if depth >= max_depth:
                continue

            for link in extract_links(html, resolved_url):
                if urlsplit(link).netloc != origin_host:
                    continue
                if link in visited:
                    continue

                visited.add(link)
                frontier.append((link, depth + 1))

            self.status_service.set_queue_depth(len(frontier))

        self.status_service.finish(
            f"crawl complete: {self.store.page_count()} pages indexed"
        )
        return request

    def _fetch_html(self, url: str) -> tuple[str, str] | None:
        """Fetch a URL and return decoded HTML plus the resolved final URL."""

        request = Request(url, headers={"User-Agent": self.USER_AGENT})
        try:
            with urlopen(request, timeout=self.request_timeout) as response:
                content_type = response.headers.get_content_type()
                if content_type != "text/html":
                    self.status_service.set_message(
                        f"skipped non-html response: {url}"
                    )
                    return None

                final_url = normalize_url(response.geturl()) or url
                body = response.read()
                encoding = response.headers.get_content_charset() or "utf-8"
                return self._decode_html(body, encoding), final_url
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            self.status_service.set_message(f"fetch failed for {url}: {error}")
            return None

    def _decode_html(self, body: bytes, encoding: str) -> str:
        """Decode fetched HTML using the declared encoding with a safe fallback."""

        try:
            return body.decode(encoding, errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")
