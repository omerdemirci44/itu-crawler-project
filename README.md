# itu-crawler-project

Small localhost-runnable web crawler and search project for a take-home exercise.

## Goal

Build a simple Python system that can:
- index from an origin URL up to depth `k`
- avoid crawling the same page twice
- return search results as `(relevant_url, origin_url, depth)`
- expose indexing status and back pressure-related state

## Implemented Scope

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
- deterministic SQLite-backed search
- a small localhost server for background indexing, search, and status

Current delivery-time limitations:
- same-host crawling is still enforced
- one background indexing job at a time
- search scoring is intentionally simple and deterministic
- resume / crash recovery is not fully implemented
- the localhost UI is intentionally minimal

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

`index`, `search`, and `status` work as separate CLI commands. `serve` starts a
localhost process that can run indexing in the background while search and
status continue to work.

## Localhost Interface

- `GET /` renders a minimal HTML page with forms for indexing and search.
- `POST /start-index` starts one background indexing run.
- `GET /status` returns JSON status.
- `GET /search?q=...` returns JSON results.

## Architecture Summary

The project stays single-machine and standard-library oriented. The crawler uses
a bounded `queue.Queue` frontier, persists pages incrementally into SQLite, and
updates a persisted latest-run status snapshot. The localhost server keeps a
single background indexing thread alive so search and status can read the same
SQLite database while indexing is still active.
