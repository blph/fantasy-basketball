# ADR-0002: DuckDB plus Parquet as the player database

- Status: Accepted
- Date: 2026-08-22
- Owner: Bryan

## Context and Problem

Every app in this project reads from one player database, refreshed daily from the FantasyPros API. The stated requirements are that daily freshness is sufficient (no need for faster), the structure must be well organized, and performance must support quick calculations and fast extraction for several different consuming apps.

The workload has a specific shape, and the engine should follow from it:

- **Writes:** one batch per day, appending a snapshot of a few hundred players.
- **Reads:** wide analytical aggregations — rank the whole pool by composite z-score, compute rolling category trends, compare across snapshot dates. These touch every row and many columns.
- **History:** retained for the full season, since trend detection is a core feature.
- **Concurrency:** none. One user, one machine.

Total data is small: a few hundred players times ~180 days times a handful of fact tables. Well under a gigabyte for a season. The requirement is analytical throughput on a small dataset, not scale.

## Decision Drivers

- Aggregation speed across the full player pool
- Zero operational overhead (no server to run or maintain between seasons)
- Clean handling of daily snapshot history
- Direct Python integration

## Considered Options

1. DuckDB with Parquet storage
2. SQLite
3. Postgres

## Decision

**DuckDB as the query engine, with fact tables stored as Parquet partitioned by `as_of_date`.**

DuckDB is columnar and in-process: a query reading 4 of 20 columns reads only those 4 columns' bytes, and aggregations across the pool are vectorized. That is precisely our read pattern. It is also a single file with no server, so there is nothing to start, secure, or maintain — and nothing to re-provision after an eight-month offseason.

Parquet partitioning is what makes the daily refresh cheap and history safe. Each run writes one new dated directory and never rewrites what came before, so refresh cost stays flat as the season accumulates, and DuckDB prunes irrelevant partitions from an `as_of_date` filter without reading them.

## Consequences

- Positive: fast aggregation, which is the dominant query pattern; no server or ops burden; excellent Python integration; append-only history is structurally natural rather than bolted on.
- Positive: Parquet files stay readable by other tools, so we are not locked into DuckDB.
- Negative: weak at high-frequency single-row writes. Irrelevant here — we write in one daily batch.
- Negative: not built for concurrent writers. Irrelevant for a single user, but it rules out ever pointing a shared web service at this file directly.
- Negative: DuckDB enforces constraints more loosely than Postgres, so referential integrity has to be validated in the ingestion layer instead of by the database.
- Follow-ups: ingestion must validate row counts and required columns before publishing a partition, since the engine will not catch that for us.

## Pros and Cons of the Options

### Option 1 — DuckDB plus Parquet
- Good: columnar scans matched to our read pattern; serverless; native Parquet; strong Python API; snapshot partitioning is a first-class idiom.
- Bad: poor concurrent-write story; looser constraint enforcement.

### Option 2 — SQLite
- Good: ubiquitous, zero-config, extremely stable, in the standard library.
- Bad: row-oriented, so a wide aggregation reads every column of every row it touches. Fine for "fetch this player," measurably worse for "rank the entire pool across nine categories," which is what we actually do. No native Parquet.

### Option 3 — Postgres
- Good: strongest constraints, real concurrency, richest feature set.
- Bad: a server to run, back up, and maintain for a single-user daily batch job. Also row-oriented, so it does not even buy the analytical speed that would justify the operational cost. Overkill on the axis we do not need and unremarkable on the one we do.

## Links

- Schema design: [docs/database/schema.md](../database/schema.md).
- Related: [ADR-0004](ADR-0004-daily-append-only-snapshots.md) on the refresh model.
