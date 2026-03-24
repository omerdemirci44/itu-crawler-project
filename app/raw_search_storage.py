"""Raw search storage helpers for the letter-sharded compatibility flow."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from app.models import PageRecord


REPO_ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = REPO_ROOT / "data" / "storage"
FIXTURE_SITE_DIR = REPO_ROOT / "data" / "fixture_site"
FIXTURE_HOST = "127.0.0.1"
FIXTURE_PORT = 3610
FIXTURE_ORIGIN_URL = f"http://{FIXTURE_HOST}:{FIXTURE_PORT}/index.html"
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


def write_letter_sharded_storage(entries: list[QuizEntry]) -> Path:
    """Write deterministic `[letter].data` quiz storage files."""

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    for existing in STORAGE_DIR.glob("*.data"):
        existing.unlink()

    buckets: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        if not entry.word:
            continue
        first = entry.word[0].lower()
        if not first.isalpha():
            continue
        buckets[first].append(
            f"{entry.word} {entry.url} {entry.origin} {entry.depth} {entry.frequency}"
        )

    for letter in sorted(buckets):
        lines = sorted(buckets[letter])
        (STORAGE_DIR / f"{letter}.data").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    return STORAGE_DIR


def generate_storage_from_pages(pages: list[PageRecord]) -> Path:
    """Generate letter-sharded quiz storage directly from crawled pages."""

    return write_letter_sharded_storage(build_quiz_entries(pages))


def score_entry(frequency: int, depth: int) -> int:
    """Apply the exact quiz relevance formula."""

    return (frequency * 10) + 1000 - (depth * 5)


def search_letter_storage(query: str, sort_by: str | None = None) -> dict[str, object]:
    """Search the appropriate `[letter].data` file for a single word query."""

    normalized_query = normalize_query_word(query)
    effective_sort = sort_by or "relevance"
    if not normalized_query:
        return {"query": "", "sortBy": "relevance", "results": []}

    shard = STORAGE_DIR / f"{normalized_query[0]}.data"
    if not shard.exists():
        return {
            "query": normalized_query,
            "sortBy": "relevance" if effective_sort != "relevance" else effective_sort,
            "results": [],
        }

    results: list[dict[str, object]] = []
    for raw_line in shard.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            continue

        word, url, origin, depth_text, frequency_text = parts
        if word != normalized_query:
            continue

        depth = int(depth_text)
        frequency = int(frequency_text)
        results.append(
            {
                "word": word,
                "url": url,
                "origin": origin,
                "depth": depth,
                "frequency": frequency,
                "relevance_score": score_entry(frequency, depth),
            }
        )

    results.sort(key=lambda item: (-item["relevance_score"], item["depth"], item["url"]))
    return {
        "query": normalized_query,
        "sortBy": "relevance" if effective_sort != "relevance" else effective_sort,
        "results": results,
    }


class _FixtureRequestHandler(SimpleHTTPRequestHandler):
    """Serve the committed local site without noisy request logs."""

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def fixture_site_server() -> None:
    """Run a local HTTP server for the committed site files."""

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
    """Crawl the committed local site and regenerate letter-sharded storage."""

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
        "storage_dir": str(STORAGE_DIR),
        "shard_count": len(list(STORAGE_DIR.glob("*.data"))),
    }
