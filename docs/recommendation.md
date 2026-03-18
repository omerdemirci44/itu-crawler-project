# Recommendation

## Recommended Direction

Use a small single-process Python application with:
- BFS crawling
- a worker pool with shared thread-safe state
- a bounded queue for back pressure
- in-memory storage first
- a CLI first and optional localhost UI later

## Why This Fits The Exercise

Explain why this approach is easy to build, demo, and defend in a take-home.

## Proposed Components

- `crawler.py`: accepts crawl requests and manages traversal later
- `parser.py`: normalizes URLs and extracts links/text later
- `index_store.py`: stores page records and search state
- `search.py`: exposes the search interface
- `status.py`: exposes progress and queue information
- `models.py`: keeps shared data contracts small
- `main.py`: provides a minimal CLI entry point

## Storage Recommendation

Start with in-memory structures. Consider SQLite only if persistence or resume
becomes important after the first working version.

## Concurrency Recommendation

Start with one process and a small worker pool. Keep shared state simple and use
locks only where they are clearly needed.

## Back Pressure Recommendation

Use a bounded queue first. Add rate limiting only if queue pressure alone is not
enough for a clean demo.

## Suggested Sprint Sequence

1. Implement HTTP fetch plus link extraction.
2. Add BFS traversal with visited tracking and queue bounds.
3. Add simple search indexing and query lookup.
4. Surface live status in the CLI.

## Tradeoffs

List the main tradeoffs you want to mention in the take-home write-up.
