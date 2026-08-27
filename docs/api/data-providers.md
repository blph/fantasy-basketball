# Data Providers

Which API supplies this project's data, and why. All figures were measured against the live APIs on 2026-08-23, not taken from vendor documentation. Claims I could not verify are labeled.

**Decision: ESPN primary, Yahoo alongside it, Sleeper as a stopgap. Total cost $0.** Reasoning at the bottom; recorded in [ADR-0007](../decisions/ADR-0007-espn-primary-data-source.md).

## Comparison

| | ESPN | Sleeper | Yahoo | FantasyPros |
| --- | --- | --- | --- | --- |
| Cost | Free | Free | Free | $8.99/mo |
| Auth | None | None | OAuth2 | API key |
| Row cap | None | None | None | **10 (free tier)** |
| Players | 3,175 | 1,818 active | full | 2,783 |
| Category ranks | 387 (ROTO) | — | own ranks | 332 (ECR) |
| Rank dispersion | — | — | — | **yes** |
| ADP | 1,095 | 1,797 | — | unverified |
| Auction values | 345 | — | salary ranks | — |
| **2026-27 projections** | **none yet** | **528** | none | **none yet** |
| Makes + attempts | yes | yes | n/a | yes |
| Box scores | **84 periods** | season agg. | yes | **none at any tier** |
| Schedule | **31 teams** | — | — | — |
| Injuries | all players | 106 | yes | 586 |
| Depth charts | — | 527 | — | — |
| News | blocked here | — | — | **yes, with `impact`** |
| Ownership % | yes | — | yes | — |
| **League state** | — | — | **only source** | — |

## Providers

### ESPN — primary

`lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}` · free, no key, no cap. Season year is the *ending* year, so `2027` is 2026-27.

The broadest single source. Category ranks (ROTO) and points ranks (STANDARD), ADP with trend deltas, auction values, ownership and start percentages, injury status on every player, per-game **and** season totals with makes and attempts, projected games played, **game-by-game box scores** across 84 scoring periods, and the **full NBA schedule** via `proTeamSchedules_wl`.

Lacks 2026-27 projections so far, and offers no consensus dispersion — it is one opinion, not a panel.

**Risk:** undocumented and unofficial. It can change without notice, has no SLA, and stat keys are bare numbers (`"29"` is points per game). Mitigated by archiving raw responses and asserting the stat-ID mapping at startup.

### Sleeper — projections stopgap

`api.sleeper.app/v1` · free, no key, no auth.

**The only provider publishing 2026-27 projections today**: 528 players, per-game, all nine categories plus FGM/FGA and FTM/FTA. Verified current — Giannis is listed on MIA. Also ADP on 1,797 players and depth-chart order on 527.

Two real gaps. It has **no projected games played** (`gp` is a placeholder), so availability has to come from elsewhere. And it carries no schedule and no game-level logs.

### Yahoo — required, non-substitutable

`OAuth2, free with a Yahoo account.`

The **only** source that knows our league exists: roster, opponents, weekly matchup scores, free agents, waivers, transaction counts, league settings. Also actual stats by season, week, and date range, plus its own ranks — including a Default Rank computed from our league's scoring settings.

No NBA projections. Yahoo documents projections for football and baseball only; there is no basketball equivalent, and the API exposes no projected coverage type. *This rests on documentation — I could not make a live call without OAuth credentials.*

### FantasyPros — optional

Free tier returns a hard 10 rows per endpoint (`"tier": "free"`, `"public_api_limited": true`), and `limit`/`offset` are ignored. Explicitly non-production. Real data needs Premium at $8.99/mo.

Two things it alone provides: **expert consensus dispersion** (`rank_ecr`, `rank_min`, `rank_max`, `rank_std`) across a 12-expert NBA panel, and a **news feed with an `impact` commentary field**. Neither blocks any phase.

Confirmed absent at every tier: box scores, game logs, schedule, depth charts. Probed twelve candidate paths; all returned API Gateway's unrouted-path 403, verified against a nonsense-path control.

### Hashtag Basketball — interim, and not an API

**The provider actually feeding the only shipped artefact.** It appears here because
`data-providers.md` is where someone will look to find that out, and until now the
answer lived only in ADR-0008 and a docstring.

Not an API and not automated: a **manual markdown export**, saved by hand into
gitignored `data/player_data/` and parsed by
[`gen_data.py`](../../scripts/draft-board/gen_data.py). It supplies per-game
projections for 200 players **with makes and attempts** (as `0.573(10.5/18.3)`,
which is what makes volume-weighted FG%/FT% possible), its own rank — used as the
draft board's pool seed — and its own ADP.

Two limitations worth costing:

- **The ADP is Hashtag's aggregate, not Yahoo's.** The playbook is emphatic that ADP
  is platform-specific and that the only one that matters is the room you are
  drafting in. ESPN publishes ADP on 1,095 players free and unauthenticated, which is
  closer to a real draft room than a ranking site's aggregate, and Yahoo's own would
  need the OAuth integration Phase 2 needs anyway. Until then the board labels the
  source on its Settings tab so the GAP column cannot be misread.
- **One opinion, no dispersion.** Same weakness ADR-0007 names for ESPN.

Interim per [ADR-0008](../decisions/ADR-0008-google-sheet-draft-board.md), and
retired when Phase 2 ingestion lands. Its data is provider data and is gitignored in
full, `Data.gs` included.

### Ruled out

- **stats.nba.com** — timed out from this environment. Official box scores and advanced stats; may work from a home network. Unofficial and needs header spoofing.
- **balldontlie** — free tier is 5 req/min covering teams, players, and games only. **No box scores** without $9.99/mo.
- **ESPN site API** (news, scoreboard) — Akamai `Access Denied` here, likely datacenter-IP blocking. Worth retesting elsewhere; it would close the news gap for free.

## Roadmap coverage

| Phase | Needs | Source | Status |
| --- | --- | --- | --- |
| 1 · Pre-season | research | none | ready |
| 2 · Database | players, stats, schedule | ESPN + Yahoo | ready |
| 3 · Draft assistant | ranks, ADP, projections | ESPN + **Sleeper** | ready |
| 4 · Digests | box scores, injuries, matchups | ESPN + Yahoo | ready |
| 5 · Roster mgmt | league state, schedule | Yahoo + ESPN | ready |

Every phase is covered at zero cost. News commentary is the one soft gap; FantasyPros fills it if wanted.

## Open problem: cross-provider joins

No two providers share an identifier cleanly.

| Provider | IDs offered |
| --- | --- |
| ESPN | ESPN id only |
| Yahoo | `yahoo_id` |
| Sleeper | `sportradar_id`, `rotowire_id` — `yahoo_id` and `espn_id` are present in the schema but **empty for all 1,818 players** (verified) |
| FantasyPros | `player_yahoo_id` **and** `player_nbacom_id` together |

So **ESPN↔Yahoo has no direct bridge** and needs name-and-team matching. That is the highest-risk part of the design: it fails silently on suffixes, accents, and traded players, and a mismatch corrupts every downstream number without raising an error.

Two options, to settle in Phase 2 with its own ADR: build a one-time crosswalk (assembled once, reviewed by hand, committed as project data rather than provider data), or match on normalized name plus team with an assertion that every rostered player resolves to exactly one match.

## Why ESPN

**Breadth.** It covers ranks, ADP, box scores, schedule, injuries, and ownership in one place. Every alternative covers a subset.

**It closes the gap nothing else could.** Box scores are what Phases 4 and 5 run on, and FantasyPros has none at any price.

**Cost is not the argument, coverage is.** ESPN being free is convenient; ESPN having more of what this project needs than the paid option is the actual reason.

**Yahoo is not a choice.** Nothing else knows our league.

**Sleeper is temporary.** It solves one dated problem — projections that ESPN has not published yet. Reassess when ESPN publishes, expected late September to mid-October.

**FantasyPros stays on the table.** Worth $8.99 for one month in October if consensus dispersion and news commentary prove useful on draft day. It blocks nothing, so the decision can wait.
