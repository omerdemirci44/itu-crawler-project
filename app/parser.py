"""HTML parsing helpers kept intentionally small for Sprint 0."""

from __future__ import annotations

from urllib.parse import urljoin


def normalize_url(url: str, base_url: str | None = None) -> str:
    """Return an absolute URL placeholder using only the standard library."""

    if base_url:
        return urljoin(base_url, url)
    return url.strip()


def extract_links(html: str, base_url: str) -> list[str]:
    """Return discovered links from a page.

    Real HTML parsing is intentionally deferred until the crawler is implemented.
    """

    _ = html, base_url
    return []


def extract_text(html: str) -> str:
    """Return plain text ready for future indexing work."""

    _ = html
    return ""
