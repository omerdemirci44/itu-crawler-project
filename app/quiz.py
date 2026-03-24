"""Quiz-compatible storage and HTTP helpers."""

from __future__ import annotations

import json
import re
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

from app.models import PageRecord


REPO_ROOT = Path(__file__).resolve().parent.parent
QUIZ_STORAGE_PATH = REPO_ROOT / "data" / "storage" / "p.data"
FIXTURE_SITE_DIR = REPO_ROOT / "data" / "fixture_site"
FIXTURE_HOST = "127.0.0.1"
FIXTURE_PORT = 3610
FIXTURE_ORIGIN_URL = f"http://{FIXTURE_HOST}:{FIXTURE_PORT}/index.html"
QUIZ_DEFAULT_HOST = "127.0.0.1"
QUIZ_DEFAULT_PORT = 3600
_WORD_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class QuizEntry:
    """Represent one quiz-compatible `(word, url)` storage row."""

    word: str
    url: str
    origin: str
    depth: int
    frequency: int


def tokenize_words(text: str) -> list[str]:
    """Return lowercase normalized word tokens from title/body text."""

    return _WORD_PATTERN.findall(text.lower())


def normalize_query_word(query: str) -> str:
    """Normalize a quiz query into the first lowercase word token."""

    tokens = tokenize_words(query)
    return tokens[0] if tokens else ""


def build_quiz_entries(pages: list[PageRecord]) -> list[QuizEntry]:
    """Build deterministic quiz-compatible rows from crawled pages."""

    entries: list[QuizEntry] = []
    for page in sorted(pages, key=lambda item: (item.url, item.origin_url, item.depth)):
        combined_text = " ".join(part for part in [page.title, page.body_text] if part)
        word_counts = Counter(tokenize_words(combined_text))
        for word in sorted(word_counts):
            entries.append(
                QuizEntry(
                    word=word,
                    url=page.url,
                    origin=page.origin_url,
                    depth=page.depth,
                    frequency=word_counts[word],
                )
            )

    entries.sort(key=lambda item: (item.word, item.url, item.origin, item.depth))
    return entries


def write_quiz_storage(
    entries: list[QuizEntry],
    path: str | Path | None = None,
) -> Path:
    """Write quiz-compatible storage rows to `data/storage/p.data`."""

    output_path = Path(path) if path is not None else QUIZ_STORAGE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{entry.word} {entry.url} {entry.origin} {entry.depth} {entry.frequency}"
        for entry in entries
    ]
    content = "\n".join(lines)
    if lines:
        content += "\n"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def generate_storage_from_pages(
    pages: list[PageRecord],
    path: str | Path | None = None,
) -> Path:
    """Generate quiz-compatible storage directly from crawled pages."""

    return write_quiz_storage(build_quiz_entries(pages), path=path)


def load_quiz_entries(path: str | Path | None = None) -> list[QuizEntry]:
    """Load quiz-compatible entries from the raw storage file."""

    storage_path = Path(path) if path is not None else QUIZ_STORAGE_PATH
    if not storage_path.exists():
        return []

    entries: list[QuizEntry] = []
    for raw_line in storage_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid quiz storage line: {line}")

        word, url, origin, depth_text, frequency_text = parts
        entries.append(
            QuizEntry(
                word=word,
                url=url,
                origin=origin,
                depth=int(depth_text),
                frequency=int(frequency_text),
            )
        )

    return entries


def compute_relevance_score(entry: QuizEntry) -> int:
    """Apply the exact quiz relevance formula."""

    return (entry.frequency * 10) + 1000 - (entry.depth * 5)


def search_quiz_storage(
    query: str,
    sort_by: str | None = None,
    path: str | Path | None = None,
) -> dict[str, object]:
    """Search quiz-compatible storage with the exact scoring rule."""

    normalized_query = normalize_query_word(query)
    effective_sort = sort_by or "relevance"
    matched_entries = [
        entry for entry in load_quiz_entries(path=path) if entry.word == normalized_query
    ]

    results = [
        {
            "word": entry.word,
            "url": entry.url,
            "origin": entry.origin,
            "depth": entry.depth,
            "frequency": entry.frequency,
            "relevance_score": compute_relevance_score(entry),
        }
        for entry in matched_entries
    ]
    results.sort(
        key=lambda item: (-item["relevance_score"], item["depth"], item["url"])
    )
    return {
        "query": normalized_query,
        "sortBy": effective_sort if effective_sort == "relevance" else "relevance",
        "results": results,
    }


class _FixtureRequestHandler(SimpleHTTPRequestHandler):
    """Serve the local fixture site without noisy request logs."""

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def fixture_site_server() -> None:
    """Run a temporary local HTTP server for the committed fixture site."""

    handler = partial(_FixtureRequestHandler, directory=str(FIXTURE_SITE_DIR))
    server = ThreadingHTTPServer((FIXTURE_HOST, FIXTURE_PORT), handler)
    thread = Thread(target=server.serve_forever, daemon=True, name="fixture-site")
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def generate_fixture_crawl_data(max_depth: int = 1) -> dict[str, object]:
    """Crawl the committed fixture site and regenerate `data/storage/p.data`."""

    from app.crawler import CrawlerService
    from app.index_store import SQLiteIndexStore
    from app.status import StatusService

    if not FIXTURE_SITE_DIR.exists():
        raise FileNotFoundError(f"Fixture site not found: {FIXTURE_SITE_DIR}")

    with fixture_site_server():
        store = SQLiteIndexStore()
        status_service = StatusService()
        crawler = CrawlerService(
            store=store,
            status_service=status_service,
            max_queue_size=32,
            request_timeout=5.0,
            worker_count=1,
        )
        crawler.index(FIXTURE_ORIGIN_URL, max_depth)

    return {
        "origin": FIXTURE_ORIGIN_URL,
        "storage_path": str(QUIZ_STORAGE_PATH),
        "entry_count": len(load_quiz_entries()),
    }


class QuizRequestHandler(BaseHTTPRequestHandler):
    """Serve the quiz-compatible `/search` HTTP API."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/search":
            self._serve_search(parsed)
            return
        if parsed.path == "/":
            self._send_text(
                "itu-crawler-project quiz API\n"
                "Use GET /search?query=<word>&sortBy=relevance\n",
                content_type="text/plain; charset=utf-8",
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _serve_search(self, parsed) -> None:
        params = parse_qs(parsed.query)
        query = params.get("query", [""])[0]
        sort_by = params.get("sortBy", ["relevance"])[0] or "relevance"
        payload = search_quiz_storage(query=query, sort_by=sort_by)
        self._send_json(payload)

    def _send_json(self, payload: object) -> None:
        body = json.dumps(payload, indent=2)
        self._send_text(body, content_type="application/json; charset=utf-8")

    def _send_text(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_quiz_server(host: str = QUIZ_DEFAULT_HOST, port: int = QUIZ_DEFAULT_PORT) -> None:
    """Run the localhost quiz-compatible API server."""

    server = ThreadingHTTPServer((host, port), QuizRequestHandler)
    print(f"Quiz API serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
