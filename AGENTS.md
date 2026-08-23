# AGENTS.md

Owner: Bryan

## Overview

A suite of assistants for one Yahoo 9-category head-to-head NBA fantasy league: draft assistant, daily and weekly digests, and roster management. All of it reads from a local player database refreshed once a day from the FantasyPros API.

Status: **Phase 0 — scaffolding only.** No ingestion, database, or app code exists yet. See [docs/roadmap.md](docs/roadmap.md).

## Priorities (when rules conflict)

1. Data correctness. A wrong number that looks right is worse than no number.
2. Preserve API quota. Never re-fetch what a dated snapshot already holds.
3. Minimal diff.

## Setup & Commands

Python 3.11+ (`tomllib` and modern typing are assumed).

- Create env: `python3 -m venv .venv && source .venv/bin/activate`
- Install: `pip install -e ".[dev]"`
- Test (all): `pytest`
- Test (single): `pytest tests/test_file.py::test_name`
- Lint: `ruff check .`
- Format: `ruff format .`

No dependencies are declared yet beyond dev tooling. Runtime dependencies land in Phase 2 and each needs an ADR.

## Testing

- Tests live in `tests/`.
- Never hit the live API in a test. Fixtures are archived JSON from `data/raw/`, copied into `tests/fixtures/` and committed.
- Run `pytest` and `ruff check .` before finishing a task; fix failures rather than reporting them as pre-existing without checking.

## Boundaries (do NOT)

- DO NOT call the FantasyPros API outside `src/fantasy_bb/ingest/`. Analytics and apps read the database.
- DO NOT write to `data/` from anything but ingestion.
- DO NOT modify an existing `as_of_date` partition. Facts are append-only ([ADR-0004](docs/decisions/ADR-0004-daily-append-only-snapshots.md)); corrections are new snapshots.
- DO NOT commit anything under `data/`, or any real API key.
- DO NOT add a runtime dependency without an ADR.
- DO NOT key a fact table on a provider's player ID. Use our `player_key` surrogate.
- DO NOT value FG%/FT% as bare rates. They are volume-weighted; without makes and attempts the math is silently wrong. See [schema.md](docs/database/schema.md#marts).

## Architecture (non-obvious only)

One-way flow, no step writes backward:

```
API → data/raw/{endpoint}/{date}.json → data/parquet/{table}/as_of_date=… → fantasy.duckdb → mart_* → apps
```

Apps read marts only. They never call the API and never recompute valuations at load time — draft day is when latency is least acceptable.

Deeper docs: [API endpoints](docs/api/fantasypros-endpoints.md) · [database schema](docs/database/schema.md) · [decisions](docs/decisions/decision-log.md)

## Security & Data Handling

- Treat this file as public.
- Secrets live in `.env` (gitignored), read via `os.environ`. Never inline, never log, never write into an archived response.
- `data/` and `.env` are gitignored. Verify with `git status` before committing.

## Repository Etiquette

- This is a **standalone git repo**. Run git from inside this directory, not the parent.
- Branch naming: `phase-N/<slug>` (e.g. `phase-2/duckdb-ingest`).
- Commit format: `type: summary` (`feat`, `fix`, `docs`, `chore`).
- Record a decision as an ADR in the **same commit** as the change it describes, and update `docs/decisions/decision-log.md`.
- Update this file in the same commit when commands, structure, or conventions change.

## When to Stop and Ask

- League rules are ambiguous, or a `TODO` in `config/league.yaml` is needed to proceed.
- An action would spend meaningful API quota, or the rate limit is still unmeasured.
- A schema change would affect data already collected.
- The API's real response contradicts what `docs/` claims. Fix the doc, do not code around it silently.

## Glossary

- **9-cat**: our scoring — FG%, FT%, 3PM, PTS, REB, AST, STL, BLK, TO. Turnovers count *against*.
- **H2H categories**: each week we beat one opponent category by category; the weekly result is a win-loss-tie tally, not a points total.
- **ECR**: Expert Consensus Ranking, FantasyPros' aggregate across its expert panel.
- **ADP**: Average Draft Position.
- **z-score**: a player's per-category value in standard deviations above the rostered-player mean. The basis of our valuation.
- **Punt build**: deliberately conceding a category to dominate the others. Changes which players are valuable, so valuation must be able to exclude a category.
- **Streaming**: cycling low-value players through a roster spot to maximize games played in a week.
- **as_of_date**: the snapshot date a fact row was collected. Nearly every query filters on it.
