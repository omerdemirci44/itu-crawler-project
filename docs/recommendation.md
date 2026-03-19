# Recommendation

## Recommended Delivery Position

The current implementation is already in a good delivery shape for the take-home
assignment. It stays single-machine, Python-only, standard-library oriented, and
keeps the core ideas easy to explain in a review.

## Implemented Direction

The project now uses:
- BFS-oriented crawling with same-host restriction
- a bounded frontier queue for simple back pressure
- SQLite for persisted pages and latest status
- deterministic search scored in Python
- a CLI for `index`, `search`, and `status`
- a minimal localhost server for background indexing, live status, and live search

## Why This Fits The Exercise

- The architecture is small enough to explain end-to-end.
- The crawler, storage, search, and server layers are all easy to inspect.
- The system demonstrates the assignment's important behaviors without adding
  unnecessary infrastructure.
- SQLite keeps the design local and practical while enabling separate CLI runs
  and live reads during background indexing.

## Current Module Roles

- `crawler.py`: crawl coordination, bounded frontier, fetch worker flow
- `parser.py`: URL normalization plus title/text/link extraction
- `index_store.py`: SQLite-backed page persistence and search retrieval
- `search.py`: thin search service over the store
- `status.py`: persisted latest-run status snapshot
- `server.py`: localhost UI / HTTP endpoints and background indexing manager
- `main.py`: CLI entry point

## Tradeoffs Worth Mentioning In The Presentation

- Search ranking is intentionally simple and deterministic.
- Same-host crawling keeps the demo bounded and predictable.
- Only one background indexing job is allowed at a time.
- Resume-after-crash is still out of scope.
- The localhost UI is functional but intentionally minimal.

## If More Time Were Available

- add richer snippets or match highlighting in search results
- allow a small configurable worker count greater than one
- improve crawl politeness controls and observability
- add stronger recovery/resume behavior
- polish the localhost UI
