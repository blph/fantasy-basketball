# Player Database — Schema Design

The planned DuckDB model. **Design only — no DDL has been executed and no database exists yet.** Column lists are intentions to reconcile against real API responses (see the verification checklist in [fantasypros-endpoints.md](../api/fantasypros-endpoints.md)) before anything is built.

Engine choice and refresh model are recorded in [ADR-0002](../decisions/ADR-0002-duckdb-parquet-player-database.md) and [ADR-0004](../decisions/ADR-0004-daily-append-only-snapshots.md).

---

## The workload this is shaped for

Design follows from what we actually do with the data:

- **Write once a day, read constantly.** One batch refresh; then hundreds of ad-hoc analytical queries.
- **Reads are wide aggregations, not row lookups.** "Rank every player by 9-cat z-score" touches every row and a dozen columns. It is not "fetch player 4821."
- **History matters.** "Whose usage is trending up over three weeks" needs yesterday's data as much as today's.
- **Single user, no concurrency.** No transactions, no multi-writer locking, no connection pool.

That is a columnar analytical workload, which is why it is DuckDB and not SQLite or Postgres.

---

## Layers

Data flows one way. Nothing downstream writes back upstream.

```
ESPN API  ·  Yahoo API  ·  Sleeper API
      │
      ▼
data/raw/{endpoint}/{date}.json      raw archive, verbatim, never parsed in place
      │
      ▼
data/parquet/{table}/as_of_date=…/   typed columnar snapshots, partitioned by date
      │
      ▼
fantasy.duckdb                       dimensions + facts, views over Parquet
      │
      ▼
mart_*                               precomputed nightly, what the apps read
      │
      ▼
Draft Assistant · Digests · Roster Manager
```

Apps query marts. Apps never call the API and never recompute z-scores at page load.

---

## Dimensions

Slow-changing reference data. Current-state, upserted daily.

### `dim_player`

The join table for the entire system.

| Column | Type | Note |
| --- | --- | --- |
| `player_key` | BIGINT | **Our** surrogate key, stable forever |
| `espn_player_id` | VARCHAR | Primary provider ID per [ADR-0007](../decisions/ADR-0007-espn-primary-data-source.md) |
| `yahoo_player_id` | VARCHAR | For the Yahoo join — no direct bridge from ESPN, needs name-and-team matching |
| `sleeper_player_id` | VARCHAR | Projections stopgap until ESPN publishes |
| `nba_player_id` | VARCHAR | For a box-score source — unconfirmed |
| `full_name` | VARCHAR | |
| `team_key` | VARCHAR | FK to `dim_team` |
| `positions` | VARCHAR[] | Multi-position eligibility; a list, not a string |
| `birth_date` | DATE | For age curves |
| `is_active` | BOOLEAN | |
| `first_seen` / `last_seen` | DATE | Detects players entering and leaving the universe |

**Facts key on `player_key`, never on a provider ID.** Providers renumber, and a second data source will not share their numbering. One surrogate key means adding Yahoo or an NBA stats feed is a new column here, not a migration of every fact table.

`positions` as a list rather than `"PG/SG"` matters — multi-position eligibility is a real draft consideration and string-splitting it at query time is both slow and error-prone.

### `dim_team`

`team_key`, abbreviation, full name, conference, division. Small and static.

### `dim_date`

`date_key`, calendar date, season, **fantasy week** (Yahoo weeks start Monday), and `is_regular_season`.

Worth a real table rather than computing on the fly. Weekly digests, matchup boundaries, and games-per-week streaming math all pivot on fantasy week, and that is league-configured, not derivable from the calendar alone.

### `dim_expert`

`expert_key`, name, affiliation.

**Blocked, and possibly permanently.** This table and `fact_expert_ranking` were designed around FantasyPros' expert panel, which [ADR-0007](../decisions/ADR-0007-espn-primary-data-source.md) gave up: ESPN publishes one opinion, not a panel, and no consensus dispersion. Build these only if a second ranking source is ever added. Nothing else in the schema depends on them.

---

## Facts

**Append-only, every one keyed by `as_of_date`.** A refresh adds rows; it never updates or deletes them. Details in [ADR-0004](../decisions/ADR-0004-daily-append-only-snapshots.md).

### `fact_projection`

Grain: one row per player, per `as_of_date`, per horizon.

`player_key`, `as_of_date`, `horizon` (`rest_of_season` | `weekly` | `daily`), `games_projected`, `minutes`, then the stat line:

`pts`, `reb`, `ast`, `stl`, `blk`, `tov`, `fg3m`, **`fgm`, `fga`, `ftm`, `fta`**.

The bolded four are not optional. Percentage categories are **volume-weighted**: a 90% free-throw shooter at one attempt a game is nearly irrelevant to a matchup, while a 78% shooter at nine attempts moves it decisively. Storing only `fg_pct` and `ft_pct` makes correct valuation impossible, and it is a silent failure — the numbers still compute, they are just wrong. If the API returns only rates, that is a blocker to resolve before building, not a detail to paper over.

### `fact_consensus_ranking`

Grain: one row per player, per `as_of_date`, per scoring format.

`player_key`, `as_of_date`, `scoring_format` (ours is `9cat`), `position_filter`, `rank_ecr`, `rank_avg`, `rank_best`, `rank_worst`, `rank_std_dev`, `tier`, `adp`.

`rank_std_dev` and the best/worst spread are the interesting columns, not just `rank_ecr` — they are how the Draft Assistant distinguishes a safe pick from a contested one.

### `fact_expert_ranking`

Grain: player × expert × `as_of_date`. The raw material behind consensus dispersion.

### `fact_injury_status`

Grain: player × `as_of_date`.

`player_key`, `as_of_date`, `status` (out / doubtful / questionable / probable / day-to-day), `injury_type`, `description`, `expected_return`.

Append-only, so status *transitions* are queryable. "Who moved from out to questionable today" is exactly a digest item, and it is only answerable if yesterday's row still exists.

### `fact_news`

`news_key`, `player_key`, `published_at`, `as_of_date`, `headline`, `body`, `source`, `content_hash`.

`content_hash` deduplicates if the API has no stable news ID or no since-filter.

### `fact_player_game` — planned, no confirmed feed

Grain: player × game date. Actual box-score production.

Same stat columns as `fact_projection`, plus `game_key`, `opponent_team_key`, `is_home`, `minutes_played`, `did_play`.

**This table has no confirmed data source.** See Open question 1 in the [endpoint reference](../api/fantasypros-endpoints.md#1-no-confirmed-source-of-actual-nba-production). Digests and roster management both depend on it, so resolving the source is the first Phase 2 task.

Unlike the others this table is **immutable by game date rather than snapshot date** — a completed game's box score does not change, so there is one row per player-game, not one per player-game-per-day.

---

## Marts

Precomputed nightly at the end of each refresh. This is where the query cost is paid once instead of on every page load.

### `mart_player_zscores`

Per-player, per-`as_of_date` z-score for each of the 9 categories, plus a composite total.

Three things the naive version gets wrong:

- **Percentage categories use impact, not rate.** FG% value is `(player_fga / pool_avg_fga) × (player_fg_pct − pool_fg_pct)`, divided by the standard deviation of that impact column across the pool. A player's shooting matters in proportion to how much they shoot. This is the single most common fantasy-basketball valuation error.
- **The pool rate is the aggregate**, `SUM(fgm) / SUM(fga)` across the pool — not the average of the individual percentages, which would count a 3-shot night the same as an 18-shot one. This is load-bearing beyond correctness of the mean: using the aggregate makes the impact column sum to exactly zero across the pool, which is why no mean subtraction is needed before dividing by its SD.
- **Turnovers invert.** Negative weight, not positive.

The choice of that SD is a known open question: Rosenof's Table 5(b) defines it over the raw rate rather than the impact column. The spreadsheet prints both and their ratio. **Whatever Phase 2 does here, it must match whatever the sheet is doing at the time, and say so in this file** — a silent divergence between the two implementations is exactly the failure ADR-0008's cross-check exists to catch.

Z-scores are computed against the **rostered player pool** — `team_count × (starters + bench)` from `config/league.yaml`, which is 156 for this league — not the full league. A replacement-level player should sit near zero, and including 500 deep-bench players drags the mean down and inflates everyone's value. Injured-list slots are excluded from that product.

### `mart_player_gscores`

Per-player, per-`as_of_date` **G-score**: each z-score multiplied by that category's week-to-week volatility discount, plus a composite `g_total`. Multipliers come from `config/league.yaml`, not hardcoded, and the file records their vintage.

**This, not `mart_player_zscores`, is the valuation.** The playbook, ADR-0008, and the shipped draft board all treat z-score as an intermediate and G-score as the answer, because an edge in a volatile category converts to head-to-head wins less often than the same edge in a stable one. An earlier version of this document specified z-scores only, which would have had Phase 2 rebuild the wrong metric and silently discard the one edge this project has over a free ranking site.

`scripts/draft-board/valuation.py` is the reference implementation to test against.

### `mart_player_value`

Composite value, tier, and value over replacement, built from `g_total`. Joins with injury status and games projected.

Value over replacement is scaled by projected availability, `vor × games / divisor`, and that scaling is **switched off where VOR is negative** — otherwise a fraction moves a negative value toward zero, ranking the less available of two equal players higher.

### `mart_replacement_level`

The league-wide baseline: the `Q`-th best `g_total`, given team count and roster slots from `config/league.yaml`. What makes "value over replacement" mean anything specific to our league rather than a generic one.

Deliberately **not per-position.** Rosenof addresses this directly (§4.1.3) and judges the omission tolerable because flex spots are plentiful, players carry multiple eligibilities, and value is spread fairly evenly across positions; computing z-scores within position groups is a known fantasy-baseball mistake. Positional scarcity belongs in the draft-day *tiebreak* — how many at this position remain in the live tier — not in the valuation. Where a per-build punt ranking is needed, each build gets its own replacement level.

### `mart_category_trend`

Rolling 7-, 14-, and 30-day actual production per category per player. The breakout and slump detector that drives waiver recommendations. **Blocked on `fact_player_game`.**

---

## Performance

The workload is small by database standards — a few hundred players times a season of days. The performance work is about keeping queries simple and scans narrow, not about scale.

**Typed columns, never JSON blobs.** Storing an API response as JSON and extracting at query time forfeits every advantage of a columnar engine. Parse once at ingestion.

**Partition Parquet by `as_of_date`:**

```
data/parquet/fact_projection/as_of_date=2026-08-22/data.parquet
```

A daily refresh writes exactly one new directory. It never rewrites history, so refresh cost stays flat as the season grows. DuckDB prunes partitions from a `WHERE as_of_date = …` clause without reading the others, so "today's board" reads one file regardless of how many days are stored.

**Let the columnar format do its job.** A query selecting 4 of 20 columns reads 4 columns' worth of bytes. Prefer narrow explicit column lists over `SELECT *`.

**Sort within partitions by `player_key`** so joins to `dim_player` stay merge-friendly.

**Compute marts once nightly.** The Draft Assistant should be reading precomputed rows, not recomputing z-scores across the player pool on every keystroke. This is the main thing keeping the draft-day experience fast, and draft day is exactly when latency is least acceptable.

**Keep `dim_player` in DuckDB proper; keep facts in Parquet** exposed as views. Dimensions are small and upserted; facts are large and appended.

### What would make this slow

Named so we do not do them:

- Querying without an `as_of_date` filter, which scans every partition ever written
- `SELECT *` across wide fact tables
- Recomputing z-scores per request instead of reading a mart
- Row-by-row Python loops over players where one SQL aggregate would do
- Storing raw JSON in a column and extracting at query time

---

## Daily refresh contract

1. Fetch each endpoint once; archive verbatim JSON to `data/raw/{endpoint}/{date}.json`.
2. Parse into typed frames; validate row counts and required columns.
3. Write a new `as_of_date` partition per fact table. **Never touch an existing partition.**
4. Upsert dimensions.
5. Rebuild marts.
6. On any failure, abort without publishing a partial partition.

**A failed run leaves yesterday's database fully intact and queryable.** Stale-but-correct beats fresh-but-broken, particularly for a system meant to inform decisions with a deadline.

---

## Open items before building

- Reconcile every column above against real API responses.
- Confirm FG/FT **makes and attempts** are available.
- Confirm whether `/nba/players` supplies a Yahoo ID.
- Resolve the actual-production source for `fact_player_game`.
- Fill in the remaining `TODO` fields in `config/league.yaml`. Team count, roster slots and scoring format are now recorded, so `Q = 156` is grounded; `draft_date` is still open.
