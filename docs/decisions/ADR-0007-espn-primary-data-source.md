# ADR-0007: ESPN as the primary data source

- Status: Accepted
- Date: 2026-08-23
- Owner: Bryan
- Supersedes: [ADR-0003](ADR-0003-fantasypros-primary-data-source.md)

## Context and Problem

ADR-0003 chose FantasyPros as the primary source. That decision was made from vendor documentation, before an API key existed. Testing against the live APIs contradicted it on two points that matter:

1. The FantasyPros free tier returns a hard **10 rows per endpoint** and is labeled non-production. Real data costs $8.99/mo.
2. FantasyPros has **no box-score endpoint at any tier** — confirmed by probing twelve candidate paths against a nonsense-path control. Phases 4 and 5 both depend on actual game production, so it could never have carried the project alone.

Before subscribing, I tested six alternatives. The results support a different architecture.

## Decision Drivers

- Coverage of what the roadmap actually needs
- A source for actual game production, which ADR-0003 left unresolved
- Availability of 2026-27 data before the October draft
- Cost

## Considered Options

1. ESPN primary, Yahoo alongside, Sleeper stopgap
2. FantasyPros Premium primary, plus a separate box-score source
3. Sleeper primary
4. A paid general provider (balldontlie, FantasyData)

## Decision

**ESPN is the primary source. Yahoo supplies league state. Sleeper supplies projections until ESPN publishes.**

ESPN alone covers category and points ranks, ADP with trend deltas, auction values, ownership, injury status, per-game and total projections with makes and attempts, **game-by-game box scores**, and the **full NBA schedule** — free, unauthenticated, and uncapped.

Yahoo is not a preference but a necessity: nothing else knows our roster, opponents, matchups, or free-agent pool.

Sleeper is the only provider publishing 2026-27 projections today, which removes the last thing blocking Phase 3.

Full comparison: [docs/api/data-providers.md](../api/data-providers.md).

## Consequences

- Positive: every roadmap phase is covered at **$0**.
- Positive: the box-score gap left open by ADR-0003 is closed.
- Positive: ESPN supplies the NBA schedule, so games-per-week needs no extra source.
- Positive: Phase 3 is unblocked now rather than in October.
- Negative: **ESPN's API is undocumented and unofficial.** It can break without notice, with no SLA and no support. Mitigated by raw-response archiving and a startup assertion on the numeric stat-ID mapping.
- Negative: **single source, no consensus dispersion.** ESPN is one opinion; FantasyPros' expert panel is the thing genuinely given up.
- Negative: **three providers instead of one**, and no two share an identifier. ESPN↔Yahoo has no direct bridge and needs name-and-team matching — the highest-risk part of the design, since it fails silently and corrupts downstream numbers without erroring.
- Negative: news commentary is unavailable. ESPN's news host is blocked from at least one environment tested.
- Follow-ups: an ADR for the ESPN↔Yahoo join strategy in Phase 2; reassess Sleeper once ESPN publishes 2026-27 projections; revisit FantasyPros in October for dispersion and news only.

## Pros and Cons of the Options

### Option 1 — ESPN + Yahoo + Sleeper
- Good: broadest coverage; free; closes the box-score gap; 2026-27 projections available now.
- Bad: undocumented primary; three integrations; no dispersion; cross-provider joins unsolved.

### Option 2 — FantasyPros Premium + a box-score source
- Good: expert consensus with dispersion; documented and supported; news with commentary.
- Bad: costs $8.99/mo and *still* needs a second source for box scores and a third for league state. Pays for less coverage than the free option.

### Option 3 — Sleeper primary
- Good: free; simple JSON; the only current 2026-27 projections.
- Bad: no schedule, no game logs, no projected games played; empty `yahoo_id`/`espn_id` make joins worse, not better.

### Option 4 — Paid general provider
- Good: documented, supported, reliable.
- Bad: balldontlie's free tier excludes box scores, and $9.99/mo buys stats without ranks, ADP, or league state. Strictly worse value than ESPN free.

## Links

- [docs/api/data-providers.md](../api/data-providers.md)
- Supersedes [ADR-0003](ADR-0003-fantasypros-primary-data-source.md)
