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
- a single localhost server for background indexing, status, app search, and quiz-compatible search
- letter-sharded raw search storage files in `data/storage/[letter].data`

### Current Delivery-Time Limitations

- same-host crawling is still enforced
- one background indexing job at a time
- search scoring is intentionally simple and deterministic
- resume / crash recovery is not fully implemented
- the localhost UI is intentionally lightweight

## Repository Layout

```text
app/
  main.py
  crawler.py
  parser.py
  index_store.py
  quiz.py
  search.py
  server.py
  status.py
  models.py
  static/
    styles.css
    app.js
data/
  fixture_site/
    index.html
    about.html
    guide.html
    faq.html
  storage/
    a.data
    c.data
    p.data
    ...
docs/
  product_prd.md
  recommendation.md
crawler.db
```

## Run

```bash
python -m app.main build-search-data
python -m app.main serve --host 127.0.0.1 --port 3600
```

Other CLI commands still work:

```bash
python -m app.main index https://example.com 1
python -m app.main search example
python -m app.main status
```

## Quiz Compatibility

The raw search storage lives under `data/storage/` and is sharded by first letter.
Examples:
- `a.data` contains `a...` words
- `c.data` contains `c...` words
- `p.data` contains `p...` words only

Each line follows the deterministic compatibility format:

```text
word url origin depth frequency
```

To rebuild the committed raw search storage honestly from a real crawl:

```bash
python -m app.main build-search-data
```

The committed fixture includes the word `page` on multiple URLs so `p.data` is
real, visible in GitHub, and directly usable in the compatibility flow.

## UI Routes

- `/`
- `/status-page`
- `/search-page`

## JSON / API Routes

- `/status`
- `/api/search?q=page`
- `/search?query=page&sortBy=relevance`

`/api/search` is the app's SQLite-backed JSON search route.
`/search` is the quiz-compatible JSON route that reads from the letter-sharded
raw search storage files.

## Local Demo

Main app:

```bash
python -m app.main build-search-data
python -m app.main serve --host 127.0.0.1 --port 3600
```

Example checks:

```text
http://127.0.0.1:3600/
http://127.0.0.1:3600/status-page
http://127.0.0.1:3600/search-page
http://127.0.0.1:3600/status
http://127.0.0.1:3600/api/search?q=page
http://127.0.0.1:3600/search?query=page&sortBy=relevance
```

## Architecture Summary

The project stays single-machine and standard-library oriented. The crawler uses
a bounded `queue.Queue` frontier, persists pages incrementally into SQLite, and
updates a persisted latest-run status snapshot.

The same main localhost server exposes the HTML dashboard pages, the app JSON
status and search endpoints, and the quiz-compatible search route. Search data
is exported after crawling into deterministic letter-sharded raw storage files so
the raw storage and compatibility route stay aligned.
