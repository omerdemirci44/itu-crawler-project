<<<<<<< HEAD
# itu-crawler-project

Sprint 0 scaffold for a localhost-runnable web crawler and search system.

## Goal

Build a small, explainable Python system that can eventually:
- index from an origin URL up to depth `k`
- avoid crawling the same page twice
- search while indexing is still active
- expose indexing status and back pressure

## Sprint 0 Scope

This sprint sets up the repository, module boundaries, and project documents.
It does not implement real crawling, parsing, ranking, or concurrency yet.

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

## Architecture Summary

The first real version should stay single-machine and simple. A CLI will call a
crawler service, a search service, and a status service. The crawler will likely
use BFS so depth is easy to reason about. A small worker pool can pull URLs from
a bounded queue, which gives basic back pressure. Shared in-memory state is the
starting point, and SQLite can be added later if persistence becomes useful.

## Planned Interfaces

- `index(origin, k)` schedules a crawl from one origin URL.
- `search(query)` returns `(relevant_url, origin_url, depth)` results.
- `status` exposes progress, queue depth, and back pressure state.

## Running the Scaffold

```bash
python -m app.main status
python -m app.main index https://example.com 1
python -m app.main search example
```

## Next Sprint

- fetch pages with the Python standard library
- normalize and filter URLs
- implement BFS traversal with a visited set
- add a basic inverted index
- report live status during indexing
=======
# itu-crawler-project
>>>>>>> 819948b556967eab12e20d6b8dda188ee7385624
