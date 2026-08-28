# Decision Log

One record per significant decision, MADR-style. Records are **immutable**: when a decision changes, write a new ADR and mark the old one `Superseded by ADR-0YYY` rather than editing it.

Write an ADR when architecture, data model, dependencies, external integrations, core strategy, security posture, or a committed workflow changes in a way that is hard to reverse or likely to be questioned later. Skip it for formatting, renames, and refactors with no behavioral change. When unsure, the test is reversibility, not size.

Record the decision in the **same commit** as the change it describes.

| ID | Title | Status | Date | Owner | Supersedes |
| --- | --- | --- | --- | --- | --- |
| [ADR-0001](ADR-0001-python-and-static-html-stack.md) | Python plus static HTML as the project stack | Accepted | 2026-08-22 | Bryan | |
| [ADR-0002](ADR-0002-duckdb-parquet-player-database.md) | DuckDB plus Parquet as the player database | Accepted | 2026-08-22 | Bryan | |
| [ADR-0003](ADR-0003-fantasypros-primary-data-source.md) | FantasyPros as the primary player data source | Superseded by ADR-0007 | 2026-08-22 | Bryan | |
| [ADR-0004](ADR-0004-daily-append-only-snapshots.md) | Daily refresh with append-only dated snapshots | Accepted | 2026-08-22 | Bryan | |
| [ADR-0005](ADR-0005-public-repository-mit-license.md) | Public repository under the MIT license | Accepted | 2026-08-23 | Bryan | |
| [ADR-0006](ADR-0006-no-provider-data-redistribution.md) | Publish no provider data, and enforce it mechanically | Accepted | 2026-08-23 | Bryan | |
| [ADR-0007](ADR-0007-espn-primary-data-source.md) | ESPN as the primary data source | Accepted | 2026-08-23 | Bryan | ADR-0003 |
| [ADR-0008](ADR-0008-google-sheet-draft-board.md) | A Google Sheet draft board, fed by manual exports, for the 2026-27 draft | Accepted | 2026-08-27 | Bryan | |
| [ADR-0009](ADR-0009-soft-punt-weighting.md) | Punted categories keep a fraction of their weight, not zero | Accepted | 2026-08-27 | Bryan | |
| [ADR-0010](ADR-0010-punt-build-set.md) | Which punt builds the board ships | Accepted | 2026-08-27 | Bryan | |
| [ADR-0011](ADR-0011-min-gp-pool-gate.md) | Pool membership also requires a minimum projected games played | Accepted | 2026-08-27 | Bryan | |
| [ADR-0012](ADR-0012-tier-multiplier-and-percentage-denominator.md) | Tier multiplier of 2.0, and closing the percentage-denominator question | Accepted | 2026-08-28 | Bryan | |

## Decisions expected next

Known open questions that will each need a record once resolved. Listed here so they are not lost, not because they are decided.

- **A second projection source.** One provider means no consensus dispersion, so "everyone agrees he is 40th" and "opinions range 22nd to 71st" look identical. Named as a known negative in ADR-0007 and unaddressed.
- **ESPN↔Yahoo player-ID join strategy.** No shared identifier exists between them. Crosswalk table or normalized name-and-team matching. Highest-risk piece of the design; decide in Phase 2.
- **AI digest generation approach.** Model, prompt structure, and how digests are delivered.
- **Draft Assistant interaction model.** Live draft-day input: manual entry, import, or Yahoo sync.
