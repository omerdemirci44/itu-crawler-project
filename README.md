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
- BFS traversal with visited tracking
- max-depth enforcement
- SQLite-backed page persistence in `crawler.db`
- persisted status for the latest crawl run
- basic deterministic search over persisted pages

Still intentionally deferred:
- concurrency / worker pool
- live search while indexing
- resume support
- localhost UI

## Repository Layout

```text
app/
  main.py
  crawler.py
  parser.py
  index_store.py
  search.py
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
```

`index` crawls pages and persists them into `crawler.db`. `search` and `status`
can be run later in separate CLI invocations against the persisted data.

## Architecture Summary

The project stays single-machine and standard-library oriented. The crawler uses
a simple BFS queue, normalizes URLs before deduplication, skips non-HTML pages,
and stores successful pages in SQLite. Search loads persisted page records and
applies a small deterministic ranking heuristic in Python. Status is stored as
the latest crawl snapshot so CLI output stays useful across separate runs.
