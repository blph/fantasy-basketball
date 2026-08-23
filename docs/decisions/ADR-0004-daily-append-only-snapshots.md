# ADR-0004: Daily refresh with append-only dated snapshots

- Status: Accepted
- Date: 2026-08-22
- Owner: Bryan

## Context and Problem

The player database refreshes from the API once a day; the owner confirmed no faster cadence is needed. That leaves the question of what a refresh *does* to existing data: overwrite the current state, or append a new dated snapshot alongside it?

This is a schema-shaping decision that becomes expensive to reverse. Overwrite-in-place cannot be retrofitted into history — once yesterday's values are gone, they are gone, and no later decision recovers them.

Several roadmap features turn out to need history rather than current state:

- Digests report *changes*: who moved from questionable to out, whose projection jumped.
- Waiver decisions rest on trends: production rising over two weeks, not a single day's line.
- Post-season review needs to know what we believed at the time, not what turned out to be true.

## Decision Drivers

- Trend and change detection are core features, not extras
- Failed refreshes must not corrupt good data
- Storage is negligible at our scale
- Reversibility: history can be discarded later, but never reconstructed

## Considered Options

1. Append-only dated snapshots
2. Overwrite-in-place current state
3. Current-state tables plus separate change-log tables

## Decision

**Every fact table is append-only and keyed by `as_of_date`. A refresh writes a new dated Parquet partition and never modifies an existing one.**

Corrections arrive as new snapshots, not as edits to old ones. Current state is a view — the rows at `max(as_of_date)` — rather than a physical table.

The exception is `fact_player_game`: a completed box score does not change, so its grain is player-game, keyed by game date rather than snapshot date.

## Consequences

- Positive: change and trend detection are simple `as_of_date` comparisons, needing no extra machinery.
- Positive: a failed refresh is harmless. It publishes nothing, and yesterday's data stays complete and queryable. Stale-but-correct beats fresh-but-broken for a system informing time-pressured decisions.
- Positive: refresh cost stays flat over the season — one new partition per day, never a rewrite of history.
- Positive: we can always reconstruct what we knew at any past point, which makes honest post-season review of our own decisions possible.
- Negative: every query needs an `as_of_date` filter. Omitting one scans the whole season and is the most likely performance mistake in this system. Mitigated by exposing current-state views and by naming the trap in [schema.md](../database/schema.md#what-would-make-this-slow).
- Negative: storage grows linearly. Negligible — a few hundred players over a season is well under a gigabyte.
- Negative: a bad day of API data is preserved rather than corrected in place. Acceptable, and arguably correct: it is a truthful record of what the provider said.
- Follow-ups: ingestion must write partitions atomically, never leaving a partial partition behind.

## Pros and Cons of the Options

### Option 1 — Append-only dated snapshots
- Good: history for free; failure isolation; flat refresh cost; trend queries are trivial.
- Bad: every query needs a date filter; storage grows.

### Option 2 — Overwrite-in-place
- Good: smallest storage; simplest queries; no date filter to forget.
- Bad: destroys the data that half the roadmap depends on. A failed mid-write refresh can leave the database in a partially updated state with no clean recovery. Irreversible in the way that matters most.

### Option 3 — Current state plus change logs
- Good: fast current-state reads with some history retained.
- Bad: two write paths to keep consistent, and the change log inevitably captures only the fields someone thought to log. All the complexity of history with only some of the benefit.

## Links

- Schema design: [docs/database/schema.md](../database/schema.md).
- Related: [ADR-0002](ADR-0002-duckdb-parquet-player-database.md) — Parquet partitioning is what makes this cheap.
