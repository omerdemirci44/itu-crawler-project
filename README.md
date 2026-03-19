# itu-crawler-project

Small localhost-runnable web crawler and search project for a take-home exercise.

## Goal

Build a simple Python system that can:
- index from an origin URL up to depth `k`
- avoid crawling the same page twice
- eventually support search results as `(relevant_url, origin_url, depth)`
- expose indexing status and back pressure-related state

## Current Scope

The current implementation includes the first working crawler core:
- URL normalization
- HTML fetch with the Python standard library
- link extraction
- basic title and body-text extraction
- BFS traversal with visited tracking
- max-depth enforcement
- in-memory storage of crawled pages

Still intentionally deferred:
- search implementation
- concurrency / worker pool
- SQLite
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
```

## CLI Usage

```bash
python -m app.main index https://example.com 1
python -m app.main status
python -m app.main search example
```

`index` currently performs a real crawl and prints a short summary. `search`
still uses the placeholder store interface and will be expanded in a later
sprint.

## Architecture Summary

The project stays single-machine and standard-library oriented. The crawler uses
a simple BFS queue, normalizes URLs before deduplication, skips non-HTML pages,
and stores successful pages in memory. Status is tracked separately so CLI
output can report crawl progress and final counts.
