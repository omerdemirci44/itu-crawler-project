"""HTML parsing helpers for the first working crawler core."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit


SUPPORTED_SCHEMES = {"http", "https"}


class _DocumentParser(HTMLParser):
    """Extract links, title text, and body text with standard-library parsing."""

    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[str] = []
        self._seen_links: set[str] = set()
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._in_title = False
        self._skip_text_depth = 0

    @property
    def title(self) -> str:
        """Return normalized page title text."""

        return _collapse_whitespace(" ".join(self._title_parts))

    @property
    def text(self) -> str:
        """Return normalized body text."""

        return _collapse_whitespace(" ".join(self._text_parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track title/script context and collect normalized links."""

        if tag == "title":
            self._in_title = True
            return

        if tag in {"script", "style"}:
            self._skip_text_depth += 1
            return

        if tag != "a":
            return

        href = dict(attrs).get("href")
        normalized = normalize_url(href or "", base_url=self.base_url)
        if normalized is None or normalized in self._seen_links:
            return

        self._seen_links.add(normalized)
        self.links.append(normalized)

    def handle_endtag(self, tag: str) -> None:
        """Track the end of title/script/style sections."""

        if tag == "title":
            self._in_title = False
            return

        if tag in {"script", "style"} and self._skip_text_depth > 0:
            self._skip_text_depth -= 1

    def handle_data(self, data: str) -> None:
        """Collect human-readable text while skipping script/style content."""

        text = _collapse_whitespace(data)
        if not text:
            return

        if self._in_title:
            self._title_parts.append(text)
            return

        if self._skip_text_depth > 0:
            return

        self._text_parts.append(text)


def normalize_url(url: str, base_url: str | None = None) -> str | None:
    """Return a normalized absolute HTTP(S) URL or ``None`` if unsupported."""

    if not url:
        return None

    candidate = url.strip()
    if not candidate:
        return None

    if base_url:
        candidate = urljoin(base_url, candidate)

    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in SUPPORTED_SCHEMES or not parts.netloc:
        return None

    path = parts.path or "/"
    netloc = parts.netloc.lower()
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def extract_title(html: str) -> str:
    """Extract a normalized title string from HTML."""

    return _parse_document(html).title


def extract_links(html: str, base_url: str) -> list[str]:
    """Return normalized outgoing HTTP(S) links discovered in a page."""

    return _parse_document(html, base_url=base_url).links


def extract_text(html: str) -> str:
    """Return normalized text content suitable for simple search matching."""

    return _parse_document(html).text


def _parse_document(html: str, base_url: str | None = None) -> _DocumentParser:
    """Parse an HTML document with the shared internal parser."""

    parser = _DocumentParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    return parser


def _collapse_whitespace(text: str) -> str:
    """Reduce repeated whitespace to single spaces and trim the result."""

    return " ".join(text.split())
