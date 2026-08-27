# ADR-0003: FantasyPros as the primary player data source

- Status: Superseded by [ADR-0007](ADR-0007-espn-primary-data-source.md)
- Date: 2026-08-22
- Owner: Bryan

## Context and Problem

Every feature on the roadmap — draft assistant, digests, roster management — depends on player data: projections, rankings, injuries, news, and actual production. The source has to be chosen before the database schema can be designed, because the schema is largely a typed reflection of what the source returns.

FantasyPros was specified by the project owner. This record captures the decision, and more importantly documents the **coverage gaps discovered while researching it**, so they are dealt with as known risks in Phase 2 rather than as surprises.

## Decision Drivers

- Owner preference and existing familiarity
- Expert-consensus rankings, which are FantasyPros' distinctive product
- One API covering rankings, projections, injuries, and news
- Affordable personal-use tier

## Considered Options

1. FantasyPros as the primary source
2. A general sports-data provider (FantasyData, Sportradar) as primary
3. The public NBA stats API plus scraped rankings

## Decision

**FantasyPros is the primary source for projections, consensus rankings, injuries, and news**, accessed via `https://api.fantasypros.com/public/v2/json` with an `x-api-key` header on the Premium personal tier.

Its consensus-across-130+-experts aggregation is the thing that is genuinely hard to reproduce elsewhere, and it is exactly what a draft board should be built on. One API and one key covers four of the five data types we need.

## Consequences

- Positive: expert-consensus rankings and ADP, the strongest available basis for a draft board.
- Positive: rank dispersion across experts is available, which distinguishes safe picks from contested ones.
- Positive: one integration, one key, one auth model for most of our needs.

**Negative — two known coverage gaps, both requiring resolution in Phase 2:**

1. **No confirmed source of actual NBA production.** The `player-points` endpoint is NFL-only. The verified NBA endpoints supply expectations (projections, rankings) and status (injuries, news), but not confirmed box scores. Daily digests, breakout detection, and matchup tracking all need actuals. Resolve by inspecting the authenticated API once the key is issued; failing that, add a second source for box scores only.

2. **No league state.** FantasyPros knows players, not *our* league. Our roster, opponents, matchup scores, and the free-agent pool live in Yahoo and require a separate Yahoo Fantasy Sports API integration (OAuth2). Roster management is not possible on FantasyPros data alone.

- Negative: exact rate limits are unpublished, so the daily call budget must be measured rather than designed against.
- Negative: full parameter lists and response schemas are not public, so the schema is provisional until verified against live responses.
- Follow-ups: run the verification checklist in [fantasypros-endpoints.md](../api/fantasypros-endpoints.md#verification-checklist) before writing ingestion code; write a new ADR for each of the two gaps once resolved.

## Pros and Cons of the Options

### Option 1 — FantasyPros primary
- Good: unmatched expert-consensus data; one key covers most needs; cheap for personal use.
- Bad: the two coverage gaps above; opaque rate limits and schemas.

### Option 2 — General sports-data provider
- Good: comprehensive box scores and play-by-play; documented schemas and limits.
- Bad: no expert-consensus rankings, which is the piece we most want and least want to reproduce; commercial pricing; still no league state.

### Option 3 — Public NBA stats API plus scraping
- Good: free; authoritative actual statistics.
- Bad: scraping rankings is fragile and breaks silently at the worst time; no projections; substantially more code to maintain for a hobby project.

## Links

- Endpoint reference: [docs/api/fantasypros-endpoints.md](../api/fantasypros-endpoints.md).
- [FantasyPros API](https://www.fantasypros.com/api-data/)

## Superseded

Live API testing on 2026-08-23 contradicted this record on two points: the FantasyPros free tier
returns only 10 rows per endpoint, and the suspected box-score gap was **confirmed** — no such
endpoint exists at any tier. See [ADR-0007](ADR-0007-espn-primary-data-source.md) for the
replacement decision and [data-providers.md](../api/data-providers.md) for the evidence.

This record is left unedited above, as written when the decision was made.
