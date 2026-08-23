# ADR-0001: Python plus static HTML as the project stack

- Status: Accepted
- Date: 2026-08-22
- Owner: Bryan

## Context and Problem

The project spans two very different kinds of work: a daily data pipeline (API ingestion, a player database, statistical valuation, AI-generated digests) and a set of user-facing surfaces (a Draft Assistant board, a roster manager). A single stack decision governs the folder layout, the tooling, and the commands recorded in `AGENTS.md`, so it has to be made before scaffolding.

The constraints are unusual for a software project and worth stating, because they invert the normal defaults:

- One user. No auth, no multi-tenancy, no concurrency.
- The compute is statistical: z-scores across a player pool, rolling averages, category valuation.
- The Draft Assistant's peak demand is a single live event where latency is highly visible and a build failure is unrecoverable in the moment.
- This is a hobby project maintained in spare time between NBA seasons.

## Decision Drivers

- Strength of the data and statistics ecosystem
- Low ceremony; time goes into analysis, not build tooling
- Reliability on draft day specifically
- Long maintenance gaps between seasons

## Considered Options

1. Python for data, static HTML/CSS/JS for the apps
2. TypeScript/Node end to end
3. Python backend with a React frontend

## Decision

**Python for ingestion, database, analytics, and digests; plain static HTML/CSS/JS for the apps.**

Python owns the half of the project that is genuinely hard — DuckDB has a first-class Python API, and the valuation math is exactly what this ecosystem is for. The apps are a data-dense table and some panels over a locally generated dataset, which needs no framework.

The static choice is mostly about draft day. A page that opens with a double-click, with no dev server and no build step, cannot fail in a way that costs a pick. It also survives an eight-month offseason without a dependency-upgrade session before it will run again, which a Node front end reliably would not.

## Consequences

- Positive: best-available tooling for the analytical work; near-zero front-end build surface; apps open directly from the filesystem; nothing to re-provision between seasons.
- Positive: the two halves stay decoupled — Python writes data, HTML reads it.
- Negative: complex interactive UI is more laborious in vanilla JS than in React. Accepted, because the Draft Assistant is fundamentally a sortable, filterable table.
- Negative: two languages instead of one.
- Follow-ups: if an app's interactivity outgrows vanilla JS, revisit with a new ADR rather than quietly introducing a framework.

## Pros and Cons of the Options

### Option 1 — Python plus static HTML
- Good: strongest data/stats ecosystem; no front-end build; robust across long idle periods; trivially fast page loads over precomputed data.
- Bad: two languages; hand-written interactivity.

### Option 2 — TypeScript/Node end to end
- Good: one language; strong tooling for the UI half.
- Bad: markedly weaker for statistical work; DuckDB's Node bindings are less mature than its Python API; the ingestion and valuation code would be the harder half written in the less suitable language.

### Option 3 — Python backend plus React
- Good: most capable UI; scales to genuinely complex interfaces.
- Bad: a build pipeline and dependency tree to maintain for a table; a stale toolchain each new season; a build step in the critical path on draft day.

## Links

- Implemented by the Phase 0 project setup.
- Related: [ADR-0002](ADR-0002-duckdb-parquet-player-database.md).
