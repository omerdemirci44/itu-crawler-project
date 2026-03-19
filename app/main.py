"""Minimal CLI entry point for the crawler project."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.crawler import CrawlerService
from app.index_store import InMemoryIndexStore
from app.search import SearchService
from app.status import StatusService


def build_parser() -> argparse.ArgumentParser:
    """Build a small CLI surface for manual testing."""

    parser = argparse.ArgumentParser(
        description="Local web crawler and search prototype.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Queue an index request.")
    index_parser.add_argument("origin", help="Origin URL to start from.")
    index_parser.add_argument("depth", type=int, help="Maximum crawl depth.")

    search_parser = subparsers.add_parser(
        "search",
        help="Run a query against the placeholder index.",
    )
    search_parser.add_argument("query", help="Query text.")

    subparsers.add_parser("status", help="Print current status.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Wire the crawler services together for CLI usage."""

    parser = build_parser()
    args = parser.parse_args(argv)

    store = InMemoryIndexStore()
    status_service = StatusService()
    crawler = CrawlerService(store=store, status_service=status_service)
    search_service = SearchService(store=store)

    if args.command == "index":
        try:
            request = crawler.index(args.origin, args.depth)
        except ValueError as error:
            parser.error(str(error))

        snapshot = status_service.snapshot()
        print(f"Origin: {request.origin_url}")
        print(f"Max depth: {request.max_depth}")
        print(f"Indexed pages: {snapshot.indexed_pages}")

        sample_pages = store.list_pages(limit=5)
        if sample_pages:
            print("Stored URLs:")
            for page in sample_pages:
                print(f"- {page.url}")
        return 0

    if args.command == "search":
        results = search_service.search(args.query)
        print(results)
        return 0

    print(status_service.snapshot())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
