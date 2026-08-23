# Fantasy Basketball

**Personal project.** I built this to manage my own fantasy league. It is public for reference, not maintained as a product — no support, no stability guarantees, and the league settings in [config/league.yaml](config/league.yaml) are mine. [MIT licensed](LICENSE) if you want to borrow from it.

Tools for a Yahoo 9-category head-to-head NBA fantasy league: a draft assistant, daily and weekly digests, and roster management, all built on a player database refreshed daily from the FantasyPros API.

**Status: Phase 0 — project setup.** Documentation and structure only; nothing is built yet.

## Where things are

| Path | What |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Agent and contributor context: commands, conventions, boundaries |
| [docs/roadmap.md](docs/roadmap.md) | The five phases and what blocks what |
| [docs/api/fantasypros-endpoints.md](docs/api/fantasypros-endpoints.md) | API reference, plus the checklist to run when the key arrives |
| [docs/database/schema.md](docs/database/schema.md) | Planned DuckDB schema and performance rationale |
| [docs/decisions/decision-log.md](docs/decisions/decision-log.md) | Decision records |
| [docs/preseason/](docs/preseason/) | Pre-season research (Phase 1) |
| [config/league.yaml](config/league.yaml) | League settings — **has TODOs to fill in** |
| `src/fantasy_bb/` | Python: ingestion, database, analytics, digests |
| `apps/` | Static HTML apps |
| `data/` | Local database and snapshots (gitignored, rebuilt from the API) |

## Stack

Python for the data pipeline; plain static HTML/CSS/JS for the apps. DuckDB with Parquet snapshots for storage. Reasoning in [ADR-0001](docs/decisions/ADR-0001-python-and-static-html-stack.md) and [ADR-0002](docs/decisions/ADR-0002-duckdb-parquet-player-database.md).

## Getting started

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then add your FantasyPros API key
```

Nothing to run yet. The daily refresh and the apps arrive in Phase 2 and Phase 3.

## Next steps

1. Fill in the `TODO` fields in [config/league.yaml](config/league.yaml).
2. Request a FantasyPros API key and run the [verification checklist](docs/api/fantasypros-endpoints.md#verification-checklist).
3. Start Phase 1 pre-season research in [docs/preseason/](docs/preseason/).

Two known gaps to resolve before Phase 2 can be fully specified: FantasyPros has no confirmed NBA box-score endpoint, and it holds no league state (that needs the Yahoo API). Both are documented in [ADR-0003](docs/decisions/ADR-0003-fantasypros-primary-data-source.md).
