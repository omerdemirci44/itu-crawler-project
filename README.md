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
- a quiz-compatible raw storage export at `data/storage/p.data`
- a quiz-compatible HTTP API at `GET /search?query=<word>&sortBy=relevance`

### Current Delivery-Time Limitations

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
  quiz.py
  search.py
  server.py
  status.py
  models.py
data/
  fixture_site/
    index.html
    about.html
    guide.html
    faq.html
  storage/
    p.data
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
python -m app.main generate-quiz-data
python -m app.main serve-quiz --host 127.0.0.1 --port 3600
```

`index`, `search`, and `status` work as separate CLI commands. `serve` starts a
localhost process that can run indexing in the background while search and
status continue to work.

## Quiz Compatibility

The repository includes a real generated quiz storage file at:
- `data/storage/p.data`

That file is produced from actual crawled page content using the committed local
fixture site in `data/fixture_site/`.

To regenerate the fixture crawl data and rebuild `p.data`:

```bash
python -m app.main generate-quiz-data
```

To run the quiz-compatible API on the expected localhost port:

```bash
python -m app.main serve-quiz --host 127.0.0.1 --port 3600
```

Then test the expected route directly:

```text
GET http://localhost:3600/search?query=crawler&sortBy=relevance
```

The quiz API reads from the same generated `data/storage/p.data` file, so the
raw file and API results stay consistent.

## Localhost Interface

- `GET /` renders a minimal HTML page with forms for indexing and search.
- `POST /start-index` starts one background indexing run.
- `GET /status` returns JSON status.
- `GET /search?q=...` returns JSON results for the existing app server.

## Architecture Summary

The project stays single-machine and standard-library oriented. The crawler uses
a bounded `queue.Queue` frontier, persists pages incrementally into SQLite, and
updates a persisted latest-run status snapshot.

The localhost server keeps a single background indexing thread alive so search
and status can read the same SQLite database while indexing is still active.

For quiz compatibility, crawled pages are also converted into a deterministic
raw word-frequency file at `data/storage/p.data`, and a dedicated localhost API
serves exact quiz-compatible relevance scoring from that file.
