# itu-crawler-project

Small localhost-runnable web crawler and search project for a take-home exercise.

## Goal

Build a simple Python system that can:
- index from an origin URL up to depth `k`
- avoid crawling the same page twice
- return search results as `(relevant_url, origin_url, depth)`
- expose indexing status and back pressure-related state

## Current Scope

The current implementation includes:
- URL normalization
- HTML fetch with the Python standard library
- link extraction
- basic title and body-text extraction
- bounded frontier queue with visible queue depth
- BFS-oriented crawling with visited tracking
- max-depth enforcement
- SQLite-backed page persistence in `crawler.db`
- persisted status for the latest crawl run
- basic deterministic search over persisted pages
- a small localhost server for background indexing, search, and status

Still intentionally deferred:
- advanced concurrency
- resume support
- richer UI

## Repository Layout

```text
app/
  main.py
  crawler.py
  parser.py
  index_store.py
  search.py
  server.py
  status.py
  models.py
docs/
  product_prd.md
  recommendation.md
crawler.db
```

## CLI Usage

```bash
python -m app.main index https://example.com 1
python -m app.main search example
python -m app.main status
python -m app.main serve --host 127.0.0.1 --port 8000
```

`index`, `search`, and `status` still work as separate CLI commands. `serve`
starts a localhost process that can run indexing in the background while search
and status requests continue to work.

## Localhost Interface

- `GET /` renders a minimal HTML page with forms for indexing and search.
- `GET /status` returns JSON status.
- `GET /search?q=...` returns JSON results.
- `POST /start-index` starts a background indexing run.

## Architecture Summary

The project stays single-machine and standard-library oriented. The crawler now
uses a bounded `queue.Queue` frontier and a small background worker model so the
localhost server stays responsive during indexing. Pages are persisted into
SQLite incrementally, search reads from the same database, and status is stored
as the latest crawl snapshot so both the CLI and the server can inspect it while
indexing is still active.
