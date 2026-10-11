# `data/`

**Everything here except this file is gitignored.** All of it is rebuildable from the API; none of it belongs in version control.

```
data/
├── raw/{endpoint}/{YYYY-MM-DD}.json   verbatim API responses, archived before parsing
├── parquet/{table}/as_of_date=…/      typed snapshots, partitioned by date
├── fantasy.duckdb                     dimensions, views over Parquet, and marts
├── player_data/                       provider exports, their fits and the injury table
├── draft-board/                       the local board: snapshots, draft state, backups
│   └── pulls/                         pulls of the live sheet, for verify.py --local
└── exports/                           files generated for elsewhere, e.g. Yahoo rankings CSVs
```

`raw/` exists so a parser bug costs a re-parse rather than API quota, and so we keep an honest record of what the provider actually returned on a given day rather than our interpretation of it.

Partitions are **append-only**. A refresh adds one new dated directory and never rewrites an existing one ([ADR-0004](../docs/decisions/ADR-0004-daily-append-only-snapshots.md)).

Only `src/fantasy_bb/ingest/` writes to the pipeline directories — `raw/`,
`parquet/` and `fantasy.duckdb`. The draft-board workflow is the standing
exception: it reads its provider exports from `player_data/` and writes to
`exports/` and `draft-board/`, none of which the pipeline touches. `draft-board/`
is the local copy of the board: snapshots written by `build_data.py`, draft state
written by `board.py`, sheet pulls written by `pull_sheet.py`
([ADR-0022](../docs/decisions/ADR-0022-local-draft-board.md)). See
[docs/draft-board/build-and-maintenance.md](../docs/draft-board/build-and-maintenance.md).

Layout and rationale: [docs/database/schema.md](../docs/database/schema.md).
