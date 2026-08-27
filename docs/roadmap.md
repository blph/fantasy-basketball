# Roadmap

**A living document.** This is the initial sketch, not a complete plan. Phases will be added, reordered, and rewritten as the season approaches.

Current position: **Phase 0 complete.** The pipeline is not built. One thing is: the 2026-27 draft board, shipped ahead of the pipeline because the draft would not wait — see Phase 3 below and [ADR-0008](decisions/ADR-0008-google-sheet-draft-board.md).

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

1. Review [data-providers.md](api/data-providers.md). ESPN and Sleeper need no key; only Yahoo needs OAuth setup.
2. Settle the **ESPN↔Yahoo player-ID join** — they share no identifier. Highest-risk piece of the design; needs an ADR before ingestion.
3. Set up Yahoo OAuth2 for league state.
4. Build ingestion (`src/fantasy_bb/ingest/`), one module per provider endpoint, with raw-response archiving.
5. Build the DuckDB layer (`src/fantasy_bb/db/`) per [schema.md](database/schema.md).
6. Build valuation (`src/fantasy_bb/analytics/`): volume-weighted percentage categories, replacement level, punt-aware, games-per-week aware.
7. Automate the daily refresh (`scripts/`).

Blocks everything downstream.

---

## Phase 3 — Draft Assistant

A dedicated, visually strong table with everything needed on draft day: consensus rank, ADP, projected line, per-category z-scores, tiers, positional scarcity, injury flags, and rank dispersion as a risk signal.

Data is available now: ESPN supplies ROTO category ranks, ADP with trend deltas, and auction values; Sleeper supplies 2026-27 projections. ESPN's own projections publish later (expect late September to mid-October).

**Shipped in the interim:** a Google Sheet draft board built by [scripts/draft-board/](../scripts/draft-board/) from manual exports, implementing the [playbook](references/fantasy-basketball-draft-playbook.md) in full — z-scores on the 156-player pool, G-score multipliers, VOR, a games-played adjustment, tiering, six punt builds, and a live category tracker. It covers the 2026-27 draft; the requirements below still stand for the real assistant ([ADR-0008](decisions/ADR-0008-google-sheet-draft-board.md)). Operating manual in [docs/draft-board/](draft-board/build-and-maintenance.md).

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

No longer blocked: ESPN supplies game-by-game box scores and the NBA schedule (games per week drives streaming). Yahoo supplies matchup context.

---

## Phase 5 — Roster management

Daily and weekly recommendations: adds, drops, lineup moves, and streaming plays, judged against our current category standing rather than against generic player value. Winning a matchup means winning categories, so the right add is the one that flips a category we are close in, not the highest-ranked free agent.

Depends on Phase 4 and Yahoo integration. Yahoo is the only source of league state, so it is required, not optional.

---

## Not yet placed

Ideas without a phase:

- Trade evaluation against our category profile
- Season-long performance review — how our own decisions actually turned out
- Schedule-strength analysis for playoff weeks
- League-mate tendency tracking
