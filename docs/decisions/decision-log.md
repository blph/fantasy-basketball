# Decision Log

One record per significant decision, MADR-style. Records are **immutable**: when a decision changes, write a new ADR and mark the old one `Superseded by ADR-0YYY` rather than editing it.

Write an ADR when architecture, data model, dependencies, external integrations, core strategy, security posture, or a committed workflow changes in a way that is hard to reverse or likely to be questioned later. Skip it for formatting, renames, and refactors with no behavioral change. When unsure, the test is reversibility, not size.

Record the decision in the **same commit** as the change it describes.

| ID | Title | Status | Date | Owner | Supersedes |
| --- | --- | --- | --- | --- | --- |
| [ADR-0001](ADR-0001-python-and-static-html-stack.md) | Python plus static HTML as the project stack | Accepted | 2026-08-22 | Bryan | |
| [ADR-0002](ADR-0002-duckdb-parquet-player-database.md) | DuckDB plus Parquet as the player database | Accepted | 2026-08-22 | Bryan | |
| [ADR-0003](ADR-0003-fantasypros-primary-data-source.md) | FantasyPros as the primary player data source | Accepted | 2026-08-22 | Bryan | |
| [ADR-0004](ADR-0004-daily-append-only-snapshots.md) | Daily refresh with append-only dated snapshots | Accepted | 2026-08-22 | Bryan | |
| [ADR-0005](ADR-0005-public-repository-mit-license.md) | Public repository under the MIT license | Accepted | 2026-08-23 | Bryan | |
| [ADR-0006](ADR-0006-no-provider-data-redistribution.md) | Publish no provider data, and enforce it mechanically | Accepted | 2026-08-23 | Bryan | |

## Decisions expected next

Known open questions that will each need a record once resolved. Listed here so they are not lost, not because they are decided.

- **Source of actual NBA production.** FantasyPros has no confirmed NBA box-score endpoint. Blocks digests and trend detection. See [ADR-0003](ADR-0003-fantasypros-primary-data-source.md) consequences.
- **Yahoo Fantasy Sports API integration.** Required for league state (roster, opponents, matchups, free agents). OAuth2, separate auth model.
- **AI digest generation approach.** Model, prompt structure, and how digests are delivered.
- **Draft Assistant interaction model.** Live draft-day input: manual entry, import, or Yahoo sync.
