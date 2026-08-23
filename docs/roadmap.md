# Roadmap

**A living document.** This is the initial sketch, not a complete plan. Phases will be added, reordered, and rewritten as the season approaches.

Current position: **Phase 0 complete.** Nothing is built.

---

## Phase 0 — Project setup ✅

Documentation, folder structure, API reference, database design, and the founding ADRs. No code.

---

## Phase 1 — Pre-season context

Organized documentation of everything that happened in the off-season and pre-season: trades, signings, injuries, depth-chart changes, role changes, rookies, and coaching changes.

This is human and AI research, not engineering, and it is deliberately first. Projections encode last season plus an adjustment; they lag real situational change. A player whose usage is about to jump because a teammate was traded is the kind of edge a draft is won on, and no ranking will hand it to you.

Lands in [`docs/preseason/`](preseason/).

---

## Phase 2 — Database and API

The foundation everything else reads from.

1. Obtain a FantasyPros API key and run the [verification checklist](api/fantasypros-endpoints.md#verification-checklist). **Do this before writing ingestion code** — the schema is provisional until real responses confirm it.
2. Resolve the two open questions in [ADR-0003](decisions/ADR-0003-fantasypros-primary-data-source.md): the actual-production source, and the Yahoo league-state integration. Each gets an ADR.
3. Build ingestion (`src/fantasy_bb/ingest/`), one module per endpoint, with raw-response archiving.
4. Build the DuckDB layer (`src/fantasy_bb/db/`) per [schema.md](database/schema.md).
5. Build valuation (`src/fantasy_bb/analytics/`): 9-cat z-scores with volume-weighted percentage categories, replacement level, and punt-aware valuation.
6. Automate the daily refresh (`scripts/`).

Blocks everything downstream.

---

## Phase 3 — Draft Assistant

A dedicated, visually strong table with everything needed on draft day: consensus rank, ADP, projected line, per-category z-scores, tiers, positional scarcity, injury flags, and rank dispersion as a risk signal.

Requirements to settle before building:
- How draft state is tracked live (manual entry, import, or Yahoo sync) — needs an ADR.
- Punt-build support: excluding a category should re-rank the board.
- Roster-need awareness as picks accumulate.

Must work offline with no build step. A tool that fails during a live draft is worse than no tool.

---

## Phase 4 — Daily and weekly digests

AI-generated briefings.

- **Daily:** injuries and status changes, standout and poor performances, waiver-wire risers, lineup actions needed today.
- **Weekly:** matchup review by category, schedule outlook (games per week drives streaming), trends over rolling windows.

Depends on `fact_player_game`, which is blocked on the actual-production source. Depends on Yahoo integration for matchup context.

---

## Phase 5 — Roster management

Daily and weekly recommendations: adds, drops, lineup moves, and streaming plays, judged against our current category standing rather than against generic player value. Winning a matchup means winning categories, so the right add is the one that flips a category we are close in, not the highest-ranked free agent.

Depends on Phase 4 and full Yahoo integration.

---

## Not yet placed

Ideas without a phase:

- Trade evaluation against our category profile
- Season-long performance review — how our own decisions actually turned out
- Schedule-strength analysis for playoff weeks
- League-mate tendency tracking
