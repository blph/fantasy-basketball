# `data/`

**Everything here except this file is gitignored.** All of it is rebuildable from the API; none of it belongs in version control.

```
data/
├── raw/{endpoint}/{YYYY-MM-DD}.json   verbatim API responses, archived before parsing
├── parquet/{table}/as_of_date=…/      typed snapshots, partitioned by date
└── fantasy.duckdb                     dimensions, views over Parquet, and marts
```

`raw/` exists so a parser bug costs a re-parse rather than API quota, and so we keep an honest record of what the provider actually returned on a given day rather than our interpretation of it.

Partitions are **append-only**. A refresh adds one new dated directory and never rewrites an existing one ([ADR-0004](../docs/decisions/ADR-0004-daily-append-only-snapshots.md)).

Only `src/fantasy_bb/ingest/` writes here.

Layout and rationale: [docs/database/schema.md](../docs/database/schema.md).
