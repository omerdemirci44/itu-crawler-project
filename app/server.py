"""Minimal localhost server for background indexing, search, and status."""

from __future__ import annotations

import json
import mimetypes
import re
from dataclasses import asdict
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import parse_qs, urlencode, urlparse

from app.crawler import CrawlerService
from app.index_store import SQLiteIndexStore
from app.parser import normalize_url
from app.quiz import search_letter_storage
from app.search import SearchService
from app.status import StatusService


STATIC_ROOT = Path(__file__).resolve().parent / "static"
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class BackgroundIndexManager:
    """Run one indexing job at a time in a background thread."""

    def __init__(self, crawler: CrawlerService, status_service: StatusService) -> None:
        self.crawler = crawler
        self.status_service = status_service
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self, origin: str, max_depth: int) -> tuple[bool, str]:
        if max_depth < 0:
            return False, "Depth must be zero or greater."
        if normalize_url(origin) is None:
            return False, "Origin must be a valid http or https URL."

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False, "Indexing is already running."
            self._thread = Thread(
                target=self._run,
                args=(origin, max_depth),
                daemon=True,
                name="background-indexer",
            )
            self._thread.start()
        return True, "Indexing started."

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def _run(self, origin: str, max_depth: int) -> None:
        try:
            self.crawler.index(origin, max_depth)
        except Exception as error:
            self.status_service.finish(f"index failed: {error}")


class LocalCrawlerApplication:
    """Bundle the server-facing services into one small app container."""

    def __init__(self, max_queue_size: int = 128) -> None:
        self.store = SQLiteIndexStore()
        self.status_service = StatusService()
        self.search_service = SearchService(self.store)
        self.crawler = CrawlerService(
            store=self.store,
            status_service=self.status_service,
            max_queue_size=max_queue_size,
            worker_count=1,
        )
        self.index_manager = BackgroundIndexManager(self.crawler, self.status_service)


class CrawlerHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server with a shared application container."""

    def __init__(self, server_address: tuple[str, int], app: LocalCrawlerApplication):
        super().__init__(server_address, CrawlerRequestHandler)
        self.app = app


class CrawlerRequestHandler(BaseHTTPRequestHandler):
    """Serve dashboard pages plus the existing JSON endpoints."""

    server: CrawlerHTTPServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/static/"):
            self._serve_static(parsed.path)
            return
        if parsed.path == "/":
            self._serve_home(parsed)
            return
        if parsed.path == "/status-page":
            self._serve_status_page(parsed)
            return
        if parsed.path == "/search-page":
            self._serve_search_page(parsed)
            return
        if parsed.path == "/status":
            self._serve_status_json()
            return
        if parsed.path == "/api/search":
            self._serve_search_json(parsed)
            return
        if parsed.path == "/search":
            self._serve_quiz_search_json(parsed)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        if urlparse(self.path).path == "/start-index":
            self._handle_start_index()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_start_index(self) -> None:
        body = self._read_form_body()
        origin = body.get("origin", [""])[0]
        depth_text = body.get("depth", ["0"])[0]
        try:
            depth = int(depth_text)
        except ValueError:
            self._redirect(f"/status-page?{urlencode({'message': 'Depth must be an integer.', 'tone': 'danger'})}")
            return

        success, message = self.server.app.index_manager.start(origin, depth)
        tone = "success" if success else "warning"
        self._redirect(f"/status-page?{urlencode({'message': message, 'tone': tone})}")

    def _serve_home(self, parsed) -> None:
        params = parse_qs(parsed.query)
        message = params.get("message", [""])[0]
        tone = params.get("tone", ["info"])[0]
        snapshot = self.server.app.status_service.snapshot()
        running = self.server.app.index_manager.is_running()
        state_text, state_class = self._status_state(snapshot, running)
        queue_limit = snapshot.max_queue_size or self.server.app.crawler.max_queue_size
        sample_pages = self.server.app.store.list_pages(limit=5)

        message_html = self._render_message(message, tone) if message else ""
        rows = "".join(
            f"<tr><td><a class='table-link' href='{escape(page.url, quote=True)}' target='_blank' rel='noreferrer'>{escape(page.url)}</a></td><td>{page.depth}</td><td><code>{escape(page.origin_url)}</code></td></tr>"
            for page in sample_pages
        )
        sample_html = (
            "<div class='table-wrap'><table class='data-table'><thead><tr><th>Stored URL</th><th>Depth</th><th>Origin</th></tr></thead><tbody>"
            + rows
            + "</tbody></table></div>"
            if sample_pages
            else self._render_empty_state(
                "No crawled pages yet.",
                "Start a crawl to populate SQLite and see recent pages here.",
            )
        )

        body_html = f"""
        <section class="hero card hero-card">
          <div>
            <p class="eyebrow">Crawler workspace</p>
            <h1>Run a crawl, track queue pressure, and inspect results cleanly.</h1>
            <p class="lead">The backend stays exactly the same. This page simply turns the localhost tools into a clearer demo dashboard.</p>
            <div class="hero-actions">
              <a class="button button-secondary" href="/status-page">Open Status</a>
              <a class="button button-secondary" href="/search-page">Open Search</a>
            </div>
          </div>
          <div class="hero-panel">
            {self._render_badge(state_text, state_class)}
            <div class="hero-metric"><span>Indexed pages</span><strong>{snapshot.indexed_pages}</strong></div>
            <div class="hero-metric"><span>Queue depth</span><strong>{snapshot.queued_urls}</strong></div>
            <div class="hero-metric"><span>Queue cap</span><strong>{queue_limit}</strong></div>
          </div>
        </section>

        {message_html}

        <section class="grid two-col">
          <article class="card section-card">
            <div class="section-head">
              <div>
                <p class="eyebrow">Start crawl</p>
                <h2>Launch a new indexing job</h2>
              </div>
              {self._render_badge('Bounded queue', 'badge-muted')}
            </div>
            <p class="muted">Same-host crawling, SQLite persistence, and the raw quiz-compatible storage export stay enabled.</p>
            <form method="post" action="/start-index" class="crawl-form" data-loading-form>
              <label class="field">
                <span>Origin URL</span>
                <input type="url" name="origin" placeholder="https://example.com" required>
                <small>The starting page for BFS crawling.</small>
              </label>
              <label class="field field-narrow">
                <span>Max depth</span>
                <input type="number" name="depth" min="0" value="1" required>
                <small>Depth `0` means only the origin page.</small>
              </label>
              <div class="field field-full settings-box">
                <span>Runtime settings</span>
                <div class="pill-row">
                  <span class="pill">Same-host only</span>
                  <span class="pill">SQLite</span>
                  <span class="pill">Queue {queue_limit}</span>
                  <span class="pill">Worker 1</span>
                </div>
              </div>
              <div class="field field-full action-row">
                <button type="submit" class="button button-primary" data-submit-button>Start Crawl</button>
                <p class="helper">You will be redirected to the status dashboard after submitting.</p>
              </div>
            </form>
          </article>

          <article class="card section-card">
            <div class="section-head">
              <div>
                <p class="eyebrow">Latest crawl</p>
                <h2>Current snapshot</h2>
              </div>
              {self._render_badge(state_text, state_class)}
            </div>
            <div class="mini-grid">
              <div class="mini-card"><span>Origin</span><strong>{escape(snapshot.origin_url) if snapshot.origin_url else 'No run yet'}</strong></div>
              <div class="mini-card"><span>Max depth</span><strong>{snapshot.max_depth}</strong></div>
              <div class="mini-card"><span>Indexed pages</span><strong>{snapshot.indexed_pages}</strong></div>
              <div class="mini-card"><span>Last message</span><strong>{escape(snapshot.last_message)}</strong></div>
            </div>
          </article>
        </section>

        <section class="section-stack">
          <div class="section-head wide">
            <div>
              <p class="eyebrow">Recent crawler jobs</p>
              <h2>Latest stored page sample</h2>
            </div>
            <p class="muted compact">Only the latest run is persisted, so this table reflects the current crawl state.</p>
          </div>
          <article class="card table-card">{sample_html}</article>
        </section>
        """
        self._send_text(
            self._render_page("Crawler", "crawler", body_html, auto_refresh=running),
            "text/html; charset=utf-8",
        )

    def _serve_status_page(self, parsed) -> None:
        params = parse_qs(parsed.query)
        message = params.get("message", [""])[0]
        tone = params.get("tone", ["info"])[0]
        snapshot = self.server.app.status_service.snapshot()
        running = self.server.app.index_manager.is_running()
        state_text, state_class = self._status_state(snapshot, running)
        refresh_note = (
            "Auto-refreshing every 2 seconds while indexing is active."
            if running
            else "Auto-refresh is paused because the crawler is idle."
        )

        body_html = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">Crawler status</p>
            <h1>Monitor indexing progress and queue health.</h1>
            <p class="lead muted">The latest status snapshot is persisted, so this page stays useful across separate runs.</p>
          </div>
          <div class="page-head-side">
            {self._render_badge(state_text, state_class)}
            <span class="refresh-note{' refresh-live' if running else ''}">{escape(refresh_note)}</span>
          </div>
        </section>
        {self._render_message(message, tone) if message else ''}
        <section class="metrics-grid">
          {self._metric_card('Origin', escape(snapshot.origin_url) if snapshot.origin_url else 'No active origin')}
          {self._metric_card('Max depth', str(snapshot.max_depth))}
          {self._metric_card('Indexed pages', str(snapshot.indexed_pages))}
          {self._metric_card('Queued URLs', str(snapshot.queued_urls))}
          {self._metric_card('Max queue size', str(snapshot.max_queue_size))}
          {self._metric_card('Back pressure', self._render_badge('Yes' if snapshot.back_pressure_active else 'No', 'badge-warning' if snapshot.back_pressure_active else 'badge-success'))}
          {self._metric_card('Is indexing', self._render_badge('Active' if running or snapshot.is_indexing else 'Idle', 'badge-live' if running or snapshot.is_indexing else 'badge-muted'))}
          {self._metric_card('Last message', escape(snapshot.last_message))}
        </section>
        <section class="grid two-col">
          <article class="card section-card">
            <div class="section-head"><div><p class="eyebrow">Message log</p><h2>Latest runtime note</h2></div><a class="text-link" href="/status">JSON status</a></div>
            <div class="log-box"><pre>{escape(snapshot.last_message)}</pre></div>
          </article>
          <article class="card section-card">
            <div class="section-head"><div><p class="eyebrow">Reading guide</p><h2>Demo talking points</h2></div>{self._render_badge('Live dashboard', 'badge-muted')}</div>
            <ul class="note-list">
              <li>Queue depth shows how much frontier work is waiting.</li>
              <li>Back pressure becomes visible when the bounded queue fills up.</li>
              <li>Indexed pages grows as pages are persisted into SQLite.</li>
              <li>The last message gives the latest crawl milestone or failure.</li>
            </ul>
          </article>
        </section>
        """
        self._send_text(
            self._render_page("Status", "status", body_html, auto_refresh=running),
            "text/html; charset=utf-8",
        )

    def _serve_search_page(self, parsed) -> None:
        query = parse_qs(parsed.query).get("q", [""])[0]
        running = self.server.app.index_manager.is_running()
        results = self._build_search_view_results(query) if query else []
        cards = "".join(
            f"""
            <article class="card result-card">
              <div class="result-top"><span class="result-rank">#{index}</span>{self._render_badge(f"Score {result['relevance_score']}", 'badge-live')}</div>
              <a class="result-url" href="{escape(result['url'], quote=True)}" target="_blank" rel="noreferrer">{escape(result['url'])}</a>
              <div class="pill-row">
                <span class="pill">Depth {result['depth']}</span>
                <span class="pill">Origin {escape(result['origin'])}</span>
              </div>
              <div class="result-actions">
                <button type="button" class="button button-ghost" data-copy-text="{escape(result['url'], quote=True)}">Copy URL</button>
                <a class="text-link" href="/api/search?{urlencode({'q': query})}">JSON search</a>
              </div>
            </article>
            """
            for index, result in enumerate(results, start=1)
        )
        if not query:
            cards = self._render_empty_state(
                "Search the current index.",
                "Enter a keyword to scan the SQLite-backed crawl results.",
            )
        elif not cards:
            cards = self._render_empty_state(
                "No matching pages found.",
                "Try a broader keyword or start a new crawl first.",
            )

        body_html = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">Search the crawl</p>
            <h1>Browse indexed pages quickly.</h1>
            <p class="lead muted">Results stay compatible with the existing backend search while the presentation becomes easier to scan in a demo.</p>
          </div>
          <div class="page-head-side">
            <span class="refresh-note{' refresh-live' if running and query else ''}">{'Live results refresh while indexing is active.' if running and query else 'Results stay static until you search again.'}</span>
          </div>
        </section>
        <section class="card section-card search-panel">
          <form method="get" action="/search-page" class="search-form" data-loading-form>
            <label class="search-field">
              <span class="sr-only">Search query</span>
              <input type="text" name="q" value="{escape(query)}" placeholder="Search indexed pages">
            </label>
            <button type="submit" class="button button-primary" data-submit-button>Search</button>
          </form>
          <p class="helper">Matches are shown with URL, origin, depth, and a UI-only relevance display for readability.</p>
        </section>
        <section class="section-stack">
          <div class="section-head wide"><div><p class="eyebrow">Results</p><h2>{escape(query) if query else 'Ready to search'}</h2></div><p class="muted compact">{len(results)} result(s)</p></div>
          <div class="result-list">{cards}</div>
        </section>
        """
        self._send_text(
            self._render_page("Search", "search", body_html, auto_refresh=running and bool(query)),
            "text/html; charset=utf-8",
        )

    def _serve_status_json(self) -> None:
        payload = asdict(self.server.app.status_service.snapshot())
        payload["server_indexing_active"] = self.server.app.index_manager.is_running()
        self._send_json(payload)

    def _serve_search_json(self, parsed) -> None:
        query = parse_qs(parsed.query).get("q", [""])[0]
        results = [asdict(result) for result in self.server.app.search_service.search(query)]
        self._send_json({"query": query, "results": results})

    def _serve_quiz_search_json(self, parsed) -> None:
        params = parse_qs(parsed.query)
        query = params.get("query", [""])[0]
        sort_by = params.get("sortBy", ["relevance"])[0] or "relevance"
        self._send_json(search_letter_storage(query, sort_by=sort_by))

    def _build_search_view_results(self, query: str) -> list[dict[str, object]]:
        normalized_query = " ".join(query.lower().split())
        tokens = sorted(set(_TOKEN_PATTERN.findall(normalized_query)))
        if not normalized_query or not tokens:
            return []

        matches: list[dict[str, object]] = []
        for page in self.server.app.store.list_pages():
            score = self.server.app.store._score_page(page, normalized_query, tokens)
            if score > 0:
                matches.append(
                    {
                        "url": page.url,
                        "origin": page.origin_url,
                        "depth": page.depth,
                        "relevance_score": score,
                    }
                )
        matches.sort(key=lambda item: (-item["relevance_score"], item["depth"], item["url"]))
        return matches

    def _serve_static(self, path: str) -> None:
        requested = (STATIC_ROOT / path.removeprefix("/static/")).resolve()
        try:
            requested.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        self._send_bytes(requested.read_bytes(), content_type)

    def _status_state(self, snapshot, running: bool) -> tuple[str, str]:
        if snapshot.back_pressure_active:
            return "Throttled", "badge-warning"
        if running or snapshot.is_indexing:
            return "Active", "badge-live"
        if snapshot.origin_url:
            return "Done", "badge-success"
        return "Idle", "badge-muted"

    def _render_page(self, title: str, active_nav: str, body_html: str, auto_refresh: bool = False) -> str:
        refresh = '<meta http-equiv="refresh" content="2">' if auto_refresh else ''
        return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} | itu-crawler-project</title>
  {refresh}
  <link rel="stylesheet" href="/static/styles.css">
  <script defer src="/static/app.js"></script>
</head>
<body>
  <div class="site-shell">
    <header class="topbar">
      <div class="topbar-inner">
        <a class="brand" href="/"><span class="brand-mark">IC</span><span class="brand-copy"><strong>itu-crawler-project</strong><small>localhost crawler dashboard</small></span></a>
        <nav class="nav-links" aria-label="Primary navigation">
          {self._nav_link('Crawler', '/', active_nav == 'crawler')}
          {self._nav_link('Status', '/status-page', active_nav == 'status')}
          {self._nav_link('Search', '/search-page', active_nav == 'search')}
        </nav>
      </div>
    </header>
    <main class="page-shell">{body_html}</main>
    <footer class="site-footer"><p>Single-machine crawler, SQLite persistence, bounded queue, and a lightweight localhost UI.</p></footer>
  </div>
</body>
</html>
        """

    def _nav_link(self, label: str, href: str, active: bool) -> str:
        active_class = " nav-link-active" if active else ""
        return f'<a class="nav-link{active_class}" href="{href}">{escape(label)}</a>'

    def _render_badge(self, text: str, css_class: str) -> str:
        return f'<span class="badge {css_class}">{escape(text)}</span>'

    def _render_message(self, text: str, tone: str) -> str:
        safe_tone = tone if tone in {'info', 'success', 'warning', 'danger'} else 'info'
        return f'<div class="message message-{safe_tone}">{escape(text)}</div>'

    def _metric_card(self, label: str, value: str) -> str:
        return f'<article class="metric-card"><span>{escape(label)}</span><strong>{value}</strong></article>'

    def _render_empty_state(self, title: str, copy: str) -> str:
        return f'<div class="empty-state"><h3>{escape(title)}</h3><p>{escape(copy)}</p></div>'

    def _read_form_body(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        return parse_qs(raw_body)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _send_json(self, payload: object) -> None:
        self._send_text(json.dumps(payload, indent=2), "application/json; charset=utf-8")

    def _send_text(self, body: str, content_type: str) -> None:
        self._send_bytes(body.encode("utf-8"), content_type)

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 3600, max_queue_size: int = 128) -> None:
    app = LocalCrawlerApplication(max_queue_size=max_queue_size)
    server = CrawlerHTTPServer((host, port), app)
    print(f"Serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
