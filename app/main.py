"""Minimal CLI entry point for the crawler project."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.crawler import CrawlerService
from app.index_store import SQLiteIndexStore
from app.search import SearchService
from app.server import run_server
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
        help="Run a query against the persisted index.",
    )
    search_parser.add_argument("query", help="Query text.")

    subparsers.add_parser("status", help="Print current persisted status.")

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run the localhost server for background indexing, status, and quiz search.",
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    serve_parser.add_argument("--port", type=int, default=3600, help="Port to bind.")

    serve_quiz_parser = subparsers.add_parser(
        "serve-quiz",
        help=argparse.SUPPRESS,
    )
    serve_quiz_parser.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)
    serve_quiz_parser.add_argument("--port", type=int, default=3600, help=argparse.SUPPRESS)

    generate_parser = subparsers.add_parser(
        "generate-quiz-data",
        help="Crawl the committed fixture site and regenerate letter-sharded storage.",
    )
    generate_parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="Maximum crawl depth for the committed fixture site.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Wire the crawler services together for CLI usage."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {"serve", "serve-quiz"}:
        run_server(host=args.host, port=args.port)
        return 0

    if args.command == "generate-quiz-data":
        from app.quiz import generate_fixture_crawl_data

        summary = generate_fixture_crawl_data(max_depth=args.depth)
        print(f"Origin: {summary['origin']}")
        print(f"Storage dir: {summary['storage_dir']}")
        print(f"Shard count: {summary['shard_count']}")
        return 0

    store = SQLiteIndexStore()
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
        if not results:
            print("No results.")
            return 0

        for result in results:
            print(
                f"({result.relevant_url}, {result.origin_url}, {result.depth})"
            )
        return 0

    snapshot = status_service.snapshot()
    print(f"Origin: {snapshot.origin_url}")
    print(f"Max depth: {snapshot.max_depth}")
    print(f"Indexed pages: {snapshot.indexed_pages}")
    print(f"Queued URLs: {snapshot.queued_urls}")
    print(f"Max queue size: {snapshot.max_queue_size}")
    print(f"Back pressure active: {snapshot.back_pressure_active}")
    print(f"Indexing active: {snapshot.is_indexing}")
    print(f"Last message: {snapshot.last_message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
