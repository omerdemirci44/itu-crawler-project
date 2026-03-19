"""Minimal localhost server for background indexing, search, and status."""

from __future__ import annotations

import json
from dataclasses import asdict
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import parse_qs, urlencode, urlparse

from app.crawler import CrawlerService
from app.index_store import SQLiteIndexStore
from app.parser import normalize_url
from app.search import SearchService
from app.status import StatusService


class BackgroundIndexManager:
    """Run one indexing job at a time in a background thread."""

    def __init__(self, crawler: CrawlerService, status_service: StatusService) -> None:
        self.crawler = crawler
        self.status_service = status_service
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self, origin: str, max_depth: int) -> tuple[bool, str]:
        """Start a background indexing run if one is not already active."""

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
        """Return whether a background indexing thread is still active."""

        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def _run(self, origin: str, max_depth: int) -> None:
        """Execute the crawl and persist a failure status on unexpected errors."""

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
    """Serve a tiny localhost UI plus JSON endpoints."""

    server: CrawlerHTTPServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_home(parsed)
            return
        if parsed.path == "/status":
            self._serve_status_json()
            return
        if parsed.path == "/search":
            self._serve_search_json(parsed)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/start-index":
            self._handle_start_index()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default request logging to keep the demo output clean."""

        return

    def _handle_start_index(self) -> None:
        """Start background indexing from a simple HTML form submission."""

        body = self._read_form_body()
        origin = body.get("origin", [""])[0]
        depth_text = body.get("depth", ["0"])[0]

        try:
            depth = int(depth_text)
        except ValueError:
            self._redirect("/?message=Depth+must+be+an+integer.")
            return

        _, message = self.server.app.index_manager.start(origin, depth)
        self._redirect(f"/?{urlencode({'message': message})}")

    def _serve_home(self, parsed) -> None:
        """Render a tiny HTML page for local demo use."""

        params = parse_qs(parsed.query)
        query = params.get("q", [""])[0]
        message = params.get("message", [""])[0]
        snapshot = self.server.app.status_service.snapshot()
        results = self.server.app.search_service.search(query) if query else []
        auto_refresh = (
            '<meta http-equiv="refresh" content="2">'
            if self.server.app.index_manager.is_running()
            else ""
        )

        status_rows = "".join(
            f"<li><strong>{escape(label)}:</strong> {escape(str(value))}</li>"
            for label, value in [
                ("Origin", snapshot.origin_url),
                ("Max depth", snapshot.max_depth),
                ("Indexed pages", snapshot.indexed_pages),
                ("Queued URLs", snapshot.queued_urls),
                ("Max queue size", snapshot.max_queue_size),
                ("Back pressure active", snapshot.back_pressure_active),
                ("Indexing active", snapshot.is_indexing),
                ("Last message", snapshot.last_message),
            ]
        )

        result_items = ""
        for result in results:
            result_items += (
                "<li>"
                f"<code>{escape(result.relevant_url)}</code> "
                f"(origin: <code>{escape(result.origin_url)}</code>, depth: {result.depth})"
                "</li>"
            )
        if query and not result_items:
            result_items = "<li>No results.</li>"

        message_html = f"<p>{escape(message)}</p>" if message else ""
        response = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>itu-crawler-project</title>
  {auto_refresh}
</head>
<body>
  <h1>itu-crawler-project</h1>
  {message_html}

  <h2>Start Indexing</h2>
  <form method="post" action="/start-index">
    <label>Origin URL <input type="url" name="origin" size="50" required></label>
    <label>Depth <input type="number" name="depth" min="0" value="1" required></label>
    <button type="submit">Start</button>
  </form>

  <h2>Status</h2>
  <ul>{status_rows}</ul>
  <p><a href="/status">JSON status</a></p>

  <h2>Search</h2>
  <form method="get" action="/">
    <label>Query <input type="text" name="q" value="{escape(query)}"></label>
    <button type="submit">Search</button>
  </form>
  <ul>{result_items}</ul>
  <p><a href="/search?{urlencode({'q': query})}">JSON search</a></p>
</body>
</html>
"""
        self._send_text(response, content_type="text/html; charset=utf-8")

    def _serve_status_json(self) -> None:
        """Return the latest status snapshot as JSON."""

        payload = asdict(self.server.app.status_service.snapshot())
        payload["server_indexing_active"] = self.server.app.index_manager.is_running()
        self._send_json(payload)

    def _serve_search_json(self, parsed) -> None:
        """Return search results as JSON for the provided query."""

        query = parse_qs(parsed.query).get("q", [""])[0]
        results = [asdict(result) for result in self.server.app.search_service.search(query)]
        self._send_json({"query": query, "results": results})

    def _read_form_body(self) -> dict[str, list[str]]:
        """Read form-encoded POST data from the request body."""

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        return parse_qs(raw_body)

    def _redirect(self, location: str) -> None:
        """Send a simple HTTP redirect."""

        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _send_json(self, payload: object) -> None:
        """Serialize and send a JSON response."""

        body = json.dumps(payload, indent=2)
        self._send_text(body, content_type="application/json; charset=utf-8")

    def _send_text(self, body: str, content_type: str) -> None:
        """Send a UTF-8 encoded text response."""

        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host: str = "127.0.0.1", port: int = 8000, max_queue_size: int = 128) -> None:
    """Start the localhost server and serve requests until interrupted."""

    app = LocalCrawlerApplication(max_queue_size=max_queue_size)
    server = CrawlerHTTPServer((host, port), app)
    print(f"Serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
