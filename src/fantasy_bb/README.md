# `fantasy_bb`

Python package. Empty until Phase 2 — these are the intended module boundaries.

Data flows one way. No module writes back to an earlier stage.

| Package | Owns | Rule |
| --- | --- | --- |
| `ingest/` | FantasyPros API calls, raw archiving, Parquet snapshot writes | **The only place allowed to make API calls or write to `data/`.** One module per endpoint. |
| `db/` | DuckDB connection, DDL, views, mart builds | Reads Parquet, writes marts. Never calls the API. |
| `analytics/` | z-scores, replacement level, punt-aware valuation, trends | Pure functions over frames. No I/O, so it stays testable without fixtures. |
| `digests/` | Daily and weekly briefing generation | Reads marts only. |
| `common/` | Config loading, logging, HTTP with backoff, ID resolution | Shared utilities. Depends on nothing else here. |

The `analytics/` no-I/O rule is the one worth holding to: the valuation math is where a subtle error is most likely and hardest to notice, and keeping it pure means it can be tested against hand-computed cases.

See [AGENTS.md](../../AGENTS.md) for the full boundary list.
