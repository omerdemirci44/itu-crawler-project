"""Shared data models for the crawler, search, and status boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IndexRequest:
    """Describe a single indexing request submitted by the CLI or UI."""

    origin_url: str
    max_depth: int


@dataclass(slots=True)
class PageRecord:
    """Represent one crawled page stored by the index layer."""

    url: str
    origin_url: str
    depth: int
    title: str = ""
    body_text: str = ""


@dataclass(slots=True)
class SearchResult:
    """Represent the required `(relevant_url, origin_url, depth)` search tuple."""

    relevant_url: str
    origin_url: str
    depth: int


@dataclass(slots=True)
class StatusSnapshot:
    """Capture the small status surface needed by a CLI or minimal UI."""

    origin_url: str = ""
    max_depth: int = 0
    indexed_pages: int = 0
    queued_urls: int = 0
    max_queue_size: int = 0
    back_pressure_active: bool = False
    is_indexing: bool = False
    last_message: str = "idle"
