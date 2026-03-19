# Product / Engineering Specification

## Project Summary

Build a localhost-runnable Python application that can crawl a small portion of the web from a starting URL and then search the collected pages. The system is intended for a take-home exercise, so the design must stay simple, explainable, and realistic for a single developer to build in roughly 3-5 hours. The implementation should favor the Python standard library and avoid crawler frameworks or parser libraries that solve the exercise directly.

The core interfaces are:

- `index(origin, k)`: crawl from one origin URL up to depth `k` without processing the same page twice
- `search(query)`: return ranked results as `(relevant_url, origin_url, depth)`

This document defines the target behavior and architecture for the next implementation sprint. It is intentionally practical rather than aspirational.

## Goals

- Implement a working end-to-end crawl and search flow on a single machine.
- Keep the system small enough to explain clearly in a code review or demo.
- Use breadth-first traversal so depth is easy to reason about and expose.
- Guarantee per-run deduplication of normalized URLs.
- Expose progress and queue-related status during indexing.
- Structure the code so search can later run while indexing is active.
- Start with in-memory state and make SQLite an optional future enhancement, not a requirement.
- Provide a simple CLI as the primary user interface.

## Non-Goals

- Distributed crawling, multiple machines, or external brokers.
- Internet-scale performance or storage.
- Advanced ranking, semantic search, or machine learning.
- JavaScript rendering, browser automation, or dynamic site support.
- Full robots.txt, sitemap, or crawl politeness features beyond minimal timeouts and a user agent.
- Persistent resume after interruption in the first working version.
- A rich web UI in the first working version.
- Multi-tenant or multi-user behavior.

## Assumptions

- Python 3.10+ is available.
- Only `http` and `https` URLs are considered crawlable.
- The first working version may restrict traversal to the same host as the origin URL to keep scope bounded and predictable.
- Only HTML responses are indexed. Non-HTML responses may be skipped after content-type inspection.
- The crawler operates on relatively small demo sites or small slices of larger sites.
- One indexing run is active at a time.
- A new indexing run may replace the previous in-memory index for simplicity.
- The primary interface is a CLI. A localhost UI is optional and may be added later.
- Search quality only needs to be reasonable and explainable, not state of the art.

## Functional Requirements

### Indexing

- Accept `index(origin, k)` where `origin` is a URL string and `k` is a non-negative integer depth limit.
- Normalize the origin URL before starting the crawl.
- Start at depth `0` for the origin page.
- Traverse in BFS order so pages at lower depth are processed before deeper pages.
- Never process the same normalized URL twice within a single indexing run.
- Avoid duplicate queue entries by marking URLs as seen when they are enqueued, not only when fetched.
- Skip child links whose computed depth would exceed `k`.
- Fetch page content with standard-library HTTP tooling.
- Parse successful HTML pages to extract:
  - normalized page URL
  - origin URL for the run
  - crawl depth
  - optional title
  - extracted body text suitable for simple keyword matching
  - outgoing links for further crawl expansion
- Continue crawling after individual fetch or parse failures.
- Record enough information to report status and produce search results.

### Search

- Accept `search(query)` where `query` is a free-text string.
- Return results as triples `(relevant_url, origin_url, depth)`.
- Return results in ranked order using a simple deterministic heuristic.
- Return an empty list when there are no matches.
- Work against the current in-memory index.
- Be structured so search can later run against partially built state while indexing is active.

### Status

- Expose at least the following status fields during or after indexing:
  - current origin URL
  - requested max depth
  - whether indexing is active
  - number of indexed pages
  - number of queued URLs
  - queue capacity
  - whether back pressure is active
  - a short last-message or phase string
- It is acceptable to add more counters such as failed pages, discovered URLs, or active workers if useful.

### CLI / User Interaction

- Provide a CLI as the first interface.
- Support these commands at minimum:
  - `index <origin> <depth>`
  - `search <query>`
  - `status`
- The CLI output should be human-readable and simple.
- Search command output should clearly show `(relevant_url, origin_url, depth)` for each result.

## Non-Functional Requirements

- Use Python and prefer the standard library.
- Keep the code understandable to a reviewer in one sitting.
- Keep the first implementation realistic for a 3-5 hour take-home.
- Keep module boundaries small and aligned with the current repository structure.
- Avoid hidden background services or infrastructure that make local execution harder.
- Favor deterministic behavior and clear tie-breaking rules in ranking.
- Fail gracefully on bad pages, timeouts, and malformed HTML.
- Use bounded in-memory structures where practical.
- Keep dependencies minimal; ideally zero third-party runtime dependencies.

## Architecture Overview

The system should remain a single Python process with clear service boundaries. The intended module responsibilities are:

| Module | Responsibility |
| --- | --- |
| `app/main.py` | CLI entry point, argument parsing, command routing |
| `app/crawler.py` | Crawl coordinator, BFS frontier management, fetch scheduling, deduplication rules |
| `app/parser.py` | URL normalization, link extraction, title extraction, body-text extraction |
| `app/index_store.py` | In-memory storage for pages and searchable state |
| `app/search.py` | Query normalization, scoring, sorting, result formatting |
| `app/status.py` | Status snapshot updates and read access |
| `app/models.py` | Shared dataclasses for requests, page records, search results, and status |

### Runtime Shape

- One active crawl coordinator controls the lifecycle of an indexing run.
- A BFS frontier queue holds pending URLs together with their depth.
- A visited set prevents duplicate processing.
- The index store keeps page records in memory.
- The search service reads from the index store and returns ranked results.
- The status service exposes progress and queue state to the CLI.

This is intentionally not a service-oriented design. Everything lives in one process and communicates through direct Python objects.

## Data Model

### Public Models

| Model | Required fields | Purpose |
| --- | --- | --- |
| `IndexRequest` | `origin_url`, `max_depth` | Describe one crawl request |
| `PageRecord` | `url`, `origin_url`, `depth`, `title`, `body_text` | Store searchable page content |
| `SearchResult` | `relevant_url`, `origin_url`, `depth` | Return search output in the required shape |
| `StatusSnapshot` | `origin_url`, `max_depth`, `indexed_pages`, `queued_urls`, `max_queue_size`, `back_pressure_active`, `is_indexing`, `last_message` | Report crawl state |

### Planned Internal Runtime State

| Structure | Suggested shape | Purpose |
| --- | --- | --- |
| Visited URLs | `set[str]` | Prevent duplicate crawl work |
| Frontier queue | `queue.Queue[FrontierItem]` or equivalent | Hold pending BFS work |
| Frontier item | `url`, `depth`, `origin_url` | Represent one pending fetch |
| Page store | `dict[str, PageRecord]` | Fast lookup by normalized URL |
| Failure tracking | `dict[str, str]` or `list[tuple[str, str]]` | Record skipped or failed pages for status/debugging |

### Notes On Search Storage

The initial version does not need a full inverted index. For the expected project scale, scanning stored `PageRecord` values and scoring them directly is acceptable and simpler. If the project grows, token caches or an inverted index can be added later without changing the public `search(query)` interface.

## Indexing Flow

1. Validate input.
2. Normalize the origin URL.
3. Initialize a fresh run state:
   - clear or replace the previous in-memory index
   - reset status counters
   - create an empty visited set
   - create a bounded frontier queue
4. Enqueue the normalized origin URL at depth `0`.
5. Mark the origin URL as visited immediately.
6. While the frontier is not empty:
   - dequeue the next item in BFS order
   - fetch the URL with a timeout and a simple user agent
   - skip non-HTML responses
   - parse title, text, and outgoing links
   - store a `PageRecord`
   - update indexed-page counters and status
   - if current depth is less than `k`, normalize and filter child links
   - enqueue unseen child links at `depth + 1`
7. When the queue is exhausted, mark indexing as complete and publish a final status snapshot.

### URL Deduplication Rules

- Normalize URLs before visited checks.
- Deduplicate on normalized URL string.
- Mark URLs as visited at enqueue time.
- The same URL discovered from multiple parents should still appear only once in the crawl.

### URL Filtering Rules For The First Working Version

- Allow only `http` and `https` schemes.
- Ignore fragments when deduplicating.
- Same-host filtering is acceptable for the first working version.
- Skip obvious non-page links such as `mailto:` and `javascript:`.

### Error Handling Rules

- A failed fetch must not abort the whole crawl.
- A parse failure on one page must not abort the whole crawl.
- Errors should update status and optionally a failure log, then continue.
- Bad links or malformed URLs should be skipped.

## Search Flow

1. Normalize the query by lowercasing and tokenizing it into simple word tokens.
2. If the query is empty after normalization, return an empty result list.
3. Iterate through the stored page records.
4. For each page, compute a simple relevance score from the URL, title, and body text.
5. Keep only pages with a positive score.
6. Sort matches by score descending, then by depth ascending, then by URL ascending.
7. Convert matches to `SearchResult` values containing `(relevant_url, origin_url, depth)`.
8. Return the ranked list.

### Search Behavior Notes

- Exact substring matches are useful but not required for every field.
- Token-based matching is sufficient for the first version.
- Returning all matches is acceptable; a result limit can be added later if needed.

## Concurrency Plan

The architecture should support a worker-pool implementation, but the design should remain simple.

### Target Direction

- Use a single process.
- Use `queue.Queue(maxsize=N)` as the shared frontier.
- Use a small worker pool based on `threading.Thread`.
- Use a thread-safe status service and a thread-safe index store, protected with simple locks where needed.

### Practical Implementation Order

- Step 1: get the full crawl loop working with the same queue interface and one worker.
- Step 2: increase workers to a small fixed number such as `2` to `4`.
- Step 3: add careful locking around shared state if live search during indexing is enabled.

### Search While Indexing

The system should be designed so this is possible later, but full simultaneous search and indexing may be deferred until there is a long-lived process or local UI. A one-shot CLI process cannot easily search an in-memory crawl that is owned by another short-lived process.

The important requirement for the implementation sprint is architectural compatibility:

- do not design the store in a way that assumes indexing must fully finish before any reads are possible
- keep store updates small and consistent
- keep status reads cheap

## Back Pressure Plan

Back pressure should be explicit and simple.

- Use a bounded frontier queue as the primary back-pressure mechanism.
- Start with a small default queue size such as `128`.
- If the queue is full, producers should block briefly or wait until workers consume items.
- Expose queue depth and queue capacity in status.
- Set `back_pressure_active` when the queue is full or when enqueue operations must wait for space.
- Do not add separate rate limiting unless the bounded queue proves insufficient.

This keeps the mechanism explainable: the crawler cannot discover work faster than it can buffer and consume it.

## Relevance / Ranking Heuristic

The ranking heuristic should be simple, deterministic, and easy to explain.

### Suggested Scoring Rules

For each page:

- add `6` if the full normalized query appears in the title
- add `4` if the full normalized query appears in the URL
- add `3` for each distinct query token found in the title
- add `2` for each distinct query token found in the URL
- add `1` for each distinct query token found in the body text

Then sort by:

1. total score descending
2. crawl depth ascending
3. URL ascending

### Why This Is Good Enough

- It rewards exact matches in high-signal fields.
- It is easy to implement with plain string and token operations.
- It is deterministic and easy to defend in a review.
- It avoids premature complexity.

## CLI Or UI Scope

### Required For The First Working Version

- CLI only.
- Example commands:
  - `python -m app.main index https://example.com 2`
  - `python -m app.main search example`
  - `python -m app.main status`

### Expected CLI Behavior

- `index` should print at least a start message and a final summary.
- `search` should print one result per line in a readable triple-like format.
- `status` should print the current status snapshot.

### Explicitly Deferred

- A browser-based localhost UI.
- Streaming progress in a separate dashboard.
- Cross-process coordination between multiple CLI invocations.

## Acceptance Criteria

The next implementation sprint should be considered successful when all of the following are true:

- Running `index(origin, k)` on a small HTML site visits the origin at depth `0` and discovers child pages up to depth `k`.
- The crawl uses BFS semantics.
- No normalized URL is processed twice in one run.
- Successfully fetched HTML pages are stored as `PageRecord` values.
- `search(query)` returns ranked `(relevant_url, origin_url, depth)` results from the stored pages.
- `status` reports indexing state, queue depth, queue capacity, and back-pressure state.
- Individual fetch and parse failures do not crash the full run.
- The implementation remains single-machine, Python-based, and standard-library oriented.
- The code structure still maps cleanly to the existing modules in `app/`.

### Nice-To-Have But Not Required For The Next Sprint

- Search against a partially built index while indexing is still running.
- SQLite-backed persistence.
- Resume after interruption.
- Localhost UI.

## Known Risks

- URL normalization has many edge cases; an overly naive implementation can cause duplicate crawls or incorrect skipping.
- Standard-library HTML parsing is less convenient than dedicated libraries, so malformed HTML may reduce extraction quality.
- Same-host restriction may exclude some relevant pages, but it keeps the crawl bounded and explainable.
- In-memory search by scanning all stored pages is simple but will not scale far beyond small demos.
- True concurrent search during active indexing introduces locking tradeoffs and may be awkward with a one-shot CLI.
- The public web is unpredictable; timeouts, redirects, and bad markup must be handled defensively.

## Intentionally Deferred To Later Sprints

- Search from a separate long-lived interface while indexing is actively mutating shared state.
- A richer ranking system with stemming, phrase search, snippets, or inverted-index optimization.
- SQLite persistence, resumable crawls, and crash recovery.
- Domain politeness controls beyond bounded queue pressure and reasonable HTTP timeouts.
- Support for JavaScript-rendered pages.
- Multi-origin crawl management.
- A localhost web UI.

## Future Improvements

- Add optional SQLite storage behind the same `index_store` interface.
- Add a minimal localhost UI that can show status and search results from a persistent process.
- Add token caching or an inverted index if page counts grow enough to justify it.
- Add result snippets and match highlighting.
- Add per-domain policies, crawl delay, or request budgeting if broader crawling becomes necessary.
- Add export or import of crawl snapshots for repeatable demos.
