# FantasyPros API — Endpoint Reference

The data contract for the player database. Every ingestion module maps to one endpoint here.

**Status: not yet exercised.** No API key has been issued and no request has been made. Each fact below is labeled so nothing here is mistaken for tested behavior:

- **Verified** — confirmed against FantasyPros' public API documentation.
- **To confirm** — a reasonable expectation that must be checked against the live API before code depends on it. FantasyPros does not publish full parameter lists or response schemas outside the authenticated docs.

Run the [Verification checklist](#verification-checklist) the day the key arrives, then update this file in the same commit.

---

## Connection

| Item | Value | Status |
| --- | --- | --- |
| Base URL | `https://api.fantasypros.com/public/v2/json` | Verified |
| Auth | `x-api-key: <key>` request header | Verified |
| Format | JSON over HTTPS, `GET` only | Verified |
| Sport path segment | `nba` | Verified |
| Season path segment | Check whether the NBA season is `2026` or `2025-26` | To confirm |

The key lives in `.env` as `FANTASYPROS_API_KEY` and is read via `os.environ`. It is never inlined, logged, or written into a cached response file.

### Access tiers

| Tier | Cost | Notes |
| --- | --- | --- |
| Free | $0 | Prototyping, sample data, "generous daily call limits" |
| Premium | $8.99/mo, bundled with a Hall of Fame subscription | Personal, non-commercial use |
| Commercial | Custom | Commercial or high-volume |

Verified. Exact numeric rate limits are **not published** — treat the daily budget as unknown until measured. Personal use puts us on Premium.

---

## Endpoints

Verified endpoint set. `{season}` is the NBA season identifier.

| Endpoint | NBA | Purpose | Target table | Cadence |
| --- | --- | --- | --- | --- |
| `GET /nba/players` | yes | Player universe and external ID cross-reference | `dim_player` | Daily |
| `GET /nba/{season}/consensus-rankings` | yes | ECR and ADP, the draft board's spine | `fact_consensus_ranking` | Daily |
| `GET /nba/{season}/projections` | yes | Full stat-line projections, the z-score inputs | `fact_projection` | Daily |
| `GET /nba/injuries` | yes | Injury designations | `fact_injury_status` | Daily, plus pre-lock |
| `GET /nba/news` | yes | Breaking player news | `fact_news` | Daily |
| `GET /nba/{season}/rankings` | yes | Per-expert rankings behind the consensus | `fact_expert_ranking` | As needed |
| `GET /nba/{season}/rankings/experts` | yes | Expert metadata | `dim_expert` | Rarely |
| `GET /nba/compare-players` | yes | Head-to-head player comparison | none (on demand) | On demand |
| `GET /nfl/{season}/player-points` | **no** | NFL only — see Open question 1 | — | — |
| `GET /mlb/lineups` | **no** | MLB only | — | — |

---

### `GET /nba/players`

The anchor of the whole database. Everything else joins through it.

- **Purpose:** the player universe plus metadata and, critically, **external ID cross-references** — FantasyPros' own ID alongside other providers' IDs.
- **Why it matters most:** the Yahoo integration (Open question 2) and any box-score source (Open question 1) both have to join back to this table. If FantasyPros exposes a Yahoo ID here, that join is free; if not, we fall back to fuzzy name-plus-team matching, which is a meaningful source of silent error. **Check this first.**
- **Parameters:** none known. *To confirm:* whether the response is the full player universe or requires a filter.
- **Target:** `dim_player`. Assign our own surrogate `player_key`; never key facts on a provider ID directly.

### `GET /nba/{season}/consensus-rankings`

- **Purpose:** expert consensus rankings (ECR) and ADP, aggregated across FantasyPros' expert panel. The primary sort for the Draft Assistant board.
- **Parameters:** *all to confirm.* The NFL equivalent takes position, scoring format, and week; the NBA analogues are likely a position filter and a scoring/category format. **Our league is 9-cat H2H**, so if a format parameter exists it must be set to the categories variant, not points. Getting this wrong yields a plausible-looking but wrong board.
- **Fields expected:** consensus rank, average rank, best/worst rank, standard deviation, tier, ADP. *To confirm* which of these NBA actually returns.
- **Target:** `fact_consensus_ranking`, one row per player per `as_of_date`.

### `GET /nba/{season}/projections`

- **Purpose:** projected stat lines. These feed every derived valuation we compute.
- **Needed categories:** FG% (with makes and attempts), FT% (with makes and attempts), 3PM, PTS, REB, AST, STL, BLK, TO — plus games played and minutes.
- **Critical check:** percentage categories are worthless as bare percentages. A 90% free-throw shooter taking one attempt a game is not the same asset as one taking nine. **We need makes and attempts, not just the rate.** If the endpoint returns only rates, we must source attempt volume elsewhere before FG%/FT% valuation means anything. Verify on day one.
- **Parameters:** *to confirm* — expect a projection horizon (rest-of-season vs. weekly) and possibly a position filter. Documentation confirms weekly and rest-of-season projections exist for NBA.
- **Target:** `fact_projection`, keyed by player, `as_of_date`, and horizon.

### `GET /nba/injuries`

- **Purpose:** current injury designations. Drives digest flags and start/sit warnings.
- **Parameters:** none known.
- **Cadence:** daily with the main refresh. Injury news breaks close to tip-off, so a second pre-lock pull is worth evaluating once we know the rate limit.
- **Target:** `fact_injury_status`, append-only, so status transitions are queryable as history rather than a single overwritten current value.

### `GET /nba/news`

- **Purpose:** breaking player news, the narrative layer for digests.
- **Parameters:** *to confirm* — expect a limit and possibly a since/date filter. A since-filter matters: without one we re-pull and re-deduplicate the same feed daily.
- **Target:** `fact_news`. Deduplicate on the provider's news ID if present, otherwise on a hash of headline plus timestamp.

### `GET /nba/{season}/rankings` and `/rankings/experts`

- **Purpose:** individual expert rankings behind the consensus, plus expert metadata.
- **Why we want it:** disagreement is signal. A player ranked 20th by consensus with a spread from 8th to 60th is a genuinely contested asset, which is different information from a consensus 20 everyone agrees on. Useful for draft-day risk framing.
- **Cadence:** lower priority than the consensus feed; pull as needed rather than daily until the rate limit is known.

### `GET /nba/compare-players`

- **Purpose:** direct player-vs-player comparison, a natural fit for add/drop decisions.
- **Cadence:** on demand, not stored. Our own z-score marts will likely answer this better because they can be tuned to our exact category weights; treat this endpoint as a cross-check, not a dependency.

---

## Open questions

Two coverage gaps that shape Phase 2. Both need resolving before the digests or roster manager can work, and each gets its own ADR when decided.

### 1. No confirmed source of actual NBA production

`player-points` is NFL-only. The verified NBA endpoints supply **projections, rankings, injuries, and news** — what players are expected to do. None of them clearly supplies **what a player actually did last night**.

Nearly every roadmap item needs actuals:

- Daily digest: who went off, who cratered
- Waiver decisions: a breakout is a change in real production, not in projection
- Category tracking: our standing in a weekly matchup is measured in actual stats

Resolution paths, in order of preference:

1. Inspect the live API once the key is issued. A box-score or game-log endpoint may exist for NBA without being listed publicly.
2. Add a second source (the public NBA stats API, or a provider like FantasyData) for box scores only, joined to `dim_player` on the external IDs from `/nba/players`.

Until this is settled, `fact_player_game` in the schema is a **planned** table with no confirmed feed.

### 2. FantasyPros holds no league state

FantasyPros knows about players, not about *our* league. It cannot tell us our roster, our opponent, the current matchup score, who is on waivers, or what our league-mates are doing.

That requires the **Yahoo Fantasy Sports API** (OAuth2, three-legged, with a refresh-token flow). Placeholders are already in `.env.example`. This is a separate integration with its own auth model and its own ADR; the two data sources join through `dim_player`, which is why the external-ID check in `/nba/players` is the first thing to verify.

---

## Ingestion conventions

Rules the ingestion layer follows. These exist so a bad day of API responses can never corrupt good historical data.

**Archive the raw response before parsing.** Every fetch writes verbatim JSON to:

```
data/raw/{endpoint}/{YYYY-MM-DD}.json
```

Cheap insurance. If a parser has a bug, we re-parse from disk instead of re-spending API quota, and we keep a real record of what the provider actually said on a given day rather than our interpretation of it.

**One fetch per endpoint per day.** The database is a daily-snapshot model (ADR-0004). If a dated raw file already exists, reuse it rather than re-requesting, unless explicitly forced.

**Never mutate a past snapshot.** A refresh appends a new `as_of_date` partition. Corrections arrive as new snapshots.

**Fail loudly and atomically.** A failed or partial refresh must leave the previous day's data fully intact and queryable. Never half-write a partition.

**Backoff:** exponential with jitter on `429` and `5xx`, capped retries, and a hard stop that fails the run rather than hammering the API. Since the numeric rate limit is unpublished, log every response's rate-limit headers from the first request so we learn the real budget.

---

## Verification checklist

Run this the day the API key is issued, before writing any ingestion code. Update this document with the findings in the same commit.

- [ ] Authenticate: a `GET /nba/players` with the `x-api-key` header returns `200`.
- [ ] Record the exact season path segment format (`2026` vs. `2025-26`).
- [ ] **Capture rate-limit headers** from the first response; record the real daily budget here.
- [ ] `/nba/players` — does it return Yahoo, ESPN, and NBA IDs? This determines whether the Yahoo join is exact or fuzzy.
- [ ] `/nba/{season}/projections` — **does it return FG/FT makes and attempts, or only percentages?**
- [ ] `/nba/{season}/projections` — what horizons are available (rest-of-season, weekly, daily)?
- [ ] `/nba/{season}/consensus-rankings` — is there a scoring-format parameter, and does it have a 9-cat/categories value?
- [ ] `/nba/news` — is there a since/date parameter, or must we pull and deduplicate?
- [ ] Search the authenticated docs for **any NBA box-score, game-log, or actual-stats endpoint** (Open question 1).
- [ ] Record the real response schema of each endpoint we depend on, and reconcile `docs/database/schema.md` against it.
- [ ] Note any endpoint that returns sample rather than live data on our tier.

---

## Sources

- [FantasyPros API — Rankings, Projections, News & More](https://www.fantasypros.com/api-data/)
- [FantasyPros v2 Public Documentation](https://api.fantasypros.com/public/v2/docs)
- [How do I request access to the FantasyPros API?](https://support.fantasypros.com/hc/en-us/articles/49749297704475-How-do-I-request-access-to-the-FantasyPros-API)
