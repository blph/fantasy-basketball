# `data/`

**Everything here except this file is gitignored.** All of it is rebuildable from the API; none of it belongs in version control.

```
data/
├── raw/{endpoint}/{YYYY-MM-DD}.json   verbatim API responses, archived before parsing
├── parquet/{table}/as_of_date=…/      typed snapshots, partitioned by date
├── fantasy.duckdb                     dimensions, views over Parquet, and marts
├── player_data/player_data_MMDD.md    manual provider exports that feed the draft board
└── exports/                           files generated for elsewhere, e.g. Yahoo rankings CSVs
```

`raw/` exists so a parser bug costs a re-parse rather than API quota, and so we keep an honest record of what the provider actually returned on a given day rather than our interpretation of it.

Partitions are **append-only**. A refresh adds one new dated directory and never rewrites an existing one ([ADR-0004](../docs/decisions/ADR-0004-daily-append-only-snapshots.md)).

Only `src/fantasy_bb/ingest/` writes to the pipeline directories — `raw/`,
`parquet/` and `fantasy.duckdb`. The draft-board workflow is the standing
exception: it reads its provider exports from `player_data/` and writes to
`exports/`, neither of which the pipeline touches. See
[docs/draft-board/build-and-maintenance.md](../docs/draft-board/build-and-maintenance.md).

Layout and rationale: [docs/database/schema.md](../docs/database/schema.md).
