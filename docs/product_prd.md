# Product PRD

## Summary

Describe the take-home project in one paragraph.

## Problem Statement

Explain why a small localhost crawler and search tool is useful.

## Goals

- support `index(origin, k)`
- support `search(query)`
- expose indexing status
- keep the design simple and explainable

## Non-Goals

- distributed crawling
- production-grade ranking
- large-scale persistence
- advanced UI work in the first version

## Target User

Describe who will run the tool and how they will evaluate it.

## Functional Requirements

### Indexing

- start from one origin URL
- crawl recursively up to depth `k`
- never crawl the same page twice

### Search

- return `(relevant_url, origin_url, depth)` results
- support search while indexing is active in a later sprint

### Status

- show indexing progress
- show queue depth
- show back pressure state

## Non-Functional Requirements

- Python implementation
- standard library first
- single-machine design
- realistic scope for a 3?5 hour project

## Constraints

List explicit take-home constraints and package restrictions here.

## Acceptance Criteria

Describe the minimum demo that counts as complete.

## Risks

List the main technical and scope risks.

## Open Questions

List decisions that can wait until implementation.
