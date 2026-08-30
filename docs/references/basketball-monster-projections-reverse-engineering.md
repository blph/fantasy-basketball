# Reverse-engineering the Basketball Monster projection export

An instruction manual. Everything below was measured on the 2026-08-30 export, and every
claim carries the number that backs it. Follow it end to end and you will reproduce
Basketball Monster's published value columns to display precision.

Written 2026-08-30 on branch `durant-actual`. Nothing in this document changes the draft
board; it is a record of how somebody else's numbers are built.

**This is a reproduction manual, not a survey.** Every section that gives a procedure is meant to
be followed literally and to produce Basketball Monster's published numbers. Sections that record
a *finding* rather than a procedure — §7's non-reproducible columns, §9's open gaps — say so in
their headings.

**Every number here is quoted with the input path that produced it**, because the same
calculation scored against a rounded input and a raw one gives different answers, and a figure
without its path is not checkable. Where two figures appear side by side they were produced the
same way; where they were not, the text says so.

> **This repository is public.** Under
> [ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md) it publishes no
> provider data, so no player appears here attached to a stat line and no export rows are
> reproduced. The worked example uses an invented player. The pool constants in §4 are
> aggregate statistics we derived, not Basketball Monster's projections.

---

## The short version

Basketball Monster's `Value` column is a **plain nine-category z-score average**, computed
per game against a pool of roughly the top 156 players — twelve teams times thirteen roster
spots, the same `Q` our own board uses.

1. Convert each player's projected season totals to per-game rates.
2. For each of the seven counting categories, z-score against the pool. Negate turnovers.
3. For the two percentage categories, z-score a **volume-weighted impact**, not the raw rate.
4. `Value` is the arithmetic **mean** of those nine numbers.
5. `Rank` is descending `Value`. `Round` is `ceil(Rank / 12)`.

That is the whole valuation. There is no transform, no weighting, no availability term, and
no punt logic. Everything interesting beyond that lives in DURANT (§10).

### The standard export is not DURANT

Worth stating first, because the original export was pulled expecting otherwise. DURANT is a
separate set of columns that has to be switched on; §10 covers it, and it *is* solved.

DURANT applies a Yeo-Johnson power transformation to each category before standardising. If
one had been applied here, each published category column would be a *non-linear* function of
the underlying per-game stat. It is not. Regressing each published column on its raw per-game
stat gives:

| Column | R², straight line | Best R² over the whole Yeo-Johnson family | Best λ |
|---|---|---|---|
| `pV` | 0.999989 | 0.999989 | **+1.0** |
| `3V` | 0.999976 | 0.999976 | **+1.0** |
| `rV` | 0.999983 | 0.999983 | **+1.0** |
| `aV` | 0.999988 | 0.999988 | **+1.0** |
| `sV` | 0.999807 | 0.999807 | **+1.0** |
| `bV` | 0.999918 | 0.999918 | **+1.0** |
| `toV` | 0.999965 | 0.999965 | **+1.0** |

λ = 1 *is* the identity transform. Searching the full family from λ = −1.0 to +3.0 in steps
of 0.1, every category lands on the identity, and the straight line is never beaten. The
residual that remains is smaller than the display rounding.

So the default export is Basketball Monster's **standard z-score view**. DURANT is a separate
column set on `projections.aspx`, pulled on 2026-08-30 and reverse-engineered in §10: it *is* a
Yeo-Johnson layer, its lambdas are recovered, and its minus-one rule is confirmed exactly.

The two metrics therefore split cleanly, and this document does too. **§§1–9 are the standard
`Value` layer. §10 is DURANT.** They share the per-game inputs of §3 and nothing else. §11 covers
the two projection sources, and §12 the punt weights.

---

## 1. Inputs

You need two exports, taken in the same session and **from the same projection source**:

| Export | What it is | How to get it |
|---|---|---|
| **The totals export** | Projected **season totals**, every player (569 under Josh, 584 under Bonus). The input to the valuation. | `projections.aspx` → `Stats Display Format` = **Total Stats**, `Filters` = **All Players** → `Export to CSV` |
| **The rendered table** | The same page in its normal state, carrying the *outputs* — `Value`, `Rank`, the nine category columns. | `projections.aspx` → `Stats Display Format` = **Per Game Stats** → `Export to CSV` |

The totals export alone cannot verify anything, because it holds no values. The rendered table
alone gives you inputs already rounded to one decimal, which caps the accuracy you can reach on
steals and blocks. **Feed the totals into §3 and check the result against the rendered table.**

Use `projections.aspx`, not the Player Rankings page: rankings serves *actuals*, so for a season
that has not started it returns "There are no results to display."

### Both exports are per-source — this is the trap

`projections.aspx` carries **two projection sources**, `Josh Projections` and `Bonus
Projections`, and *every* export follows whichever is selected. A totals file from one source and
a rendered table from the other will not reconcile: across the 564 players common to both, only
**123** share a games total, and projected minutes differ by an average of 194.

**Set `Projection Source` first, take both exports, then record which source you used.** §11
covers both and reproduces each.

> If you already have a file called `Projections.csv` from Basketball Monster's standalone
> projections download — 569 players, 22 columns of integer season totals, headed
> `player_id,last_name,first_name,games,minutes,…` — it is a **Josh** file. It is interchangeable
> with the Total Stats export for Josh: every total agrees within one unit, and games and minutes
> match exactly. There is no equivalent standalone download for Bonus, which is why the Total
> Stats route above is the one this document uses.

### Joining the two exports

Join on **player id**, never on name — the rule in [AGENTS.md](../../CLAUDE.md) applies to this
provider too. In the rendered table the id is the `i=` parameter of each player link
(`playerinfo.aspx?i=NNNN`); in the standalone CSV it is the `player_id` column. On the 2026-08-30
Josh exports the join is **234 of 234**.

### Parsing traps

**The table repeats its header.** A 234-player export arrives as 254 delimited rows: one header,
one separator, **19 repeated header rows**, and the players. Parse naively and you get 253 rows
and a crash on the first `int()`. Filter on `Rank` matching `^\d+$`.

**Totals are comma-formatted.** The Total Stats export writes `2,108.0` for minutes. Strip commas
before parsing or every large total silently becomes unparseable.

**The Total Stats export gives percentages, not makes.** It carries `fg%` and `fga` but no `fgm`,
so makes must be reconstructed as `fg% × fga`. That is a three-decimal percentage times a total,
carrying roughly half a make of rounding error — the same order as everything else here.

**Every export quantises.** Basketball Monster's internal projections are fractional and all
exports round them. This is the floor on how exactly you can reproduce anything, and §8
quantifies it. The evidence: take a displayed percentage and multiply by the exported attempts to
recover the makes it implies — the gap against the exported makes has median 0.29 for FG% and
0.30 for FT%, maximum 1.12, exactly the budget from rounding makes, attempts and the percentage.

In this repo the exports live under `data/player_data/`, which is gitignored — deliberately, and
required.

---

## 2. Column inventory

All 47 columns of the rendered table, sorted by whether you can reproduce them.

### Exactly reproducible from the CSV

| Column | What it is |
|---|---|
| `g` | Projected games. CSV `games`, matching 234/234. |
| `m/g` `p/g` `3/g` `r/g` `a/g` `s/g` `b/g` `to/g` `fga/g` `fta/g` | Per-game rates. Total ÷ games. |
| `fg%` `ft%` | Makes ÷ attempts. |
| `pV` `3V` `rV` `aV` `sV` `bV` `fg%V` `ft%V` `toV` | The nine category values. §4. |
| `Value` | Mean of the nine. §5. |
| `Rank` | Descending `Value`. Zero mismatches across 234. |
| `Round` | `ceil(Rank / 12)`. Exact — it reads league size off the account. |

### Reproducible with one extra input

| Column | Missing input |
|---|---|
| `USG` | Team-level totals across every player on the roster, not just the 234 shown. |
| `b2b` | The 2026-27 NBA schedule. |

### Not reproducible — judgement, or built on data this export does not carry

`FrV`, `Conf`, `Tier`, `Role`, `Inj`, `Inj Risk`, `1W+-`. §7 gives the evidence for each,
including the negative results.

### Empty in this export

`Own`, `Adv ADP`, `Adv%`, `Adv+-`, `Note`, `Status`, `Josh`, `Kyle`, `Matt`, `Analysts`.
These are user-populated or draft-session columns. `Josh`, `Kyle` and `Matt` are the
Basketball Monster analysts' own rankings, sold as a separate view.

---

## 3. Step one — per-game rates

Every rate is a season total divided by projected games. **Exclude players with `games = 0`** —
the 2026-08-30 Josh set has 60 of them, leaving 509; the Bonus set leaves 521.

The two exports of §1 carry different columns, so the arithmetic differs. Use whichever row of
the table matches the file you have.

| Quantity | From the **Total Stats** export | From the standalone **`Projections.csv`** |
|---|---|---|
| Points | `pts` — given directly | `2 × field_goals + threes + free_throws` |
| Rebounds | `reb` — given directly | `offensive_rebounds + defensive_rebounds` |
| Threes, assists, steals, blocks, turnovers | given directly | given directly |
| FG attempts | `fga` | `field_goals_attempted` |
| FG makes | `fg% × fga` — **not given** | `field_goals` |
| FT attempts | `fta` | `free_throws_attempted` |
| FT makes | `ft% × fta` — **not given** | `free_throws` |
| Minutes | `min` | `minutes` |

Then divide every one by games.

**Two traps, one per file.**

*Using `Projections.csv`:* **`field_goals` already includes three-pointers.** This is the single
most likely first-attempt error, and it is silent — every made three is worth three points,
counted as a two-point field goal plus one. Get it wrong and every high-volume shooter shifts
down and every non-shooter up, and the result still looks plausible.

*Using the Total Stats export:* it gives **percentages, not makes**, so makes must be
reconstructed. It is also comma-formatted, so strip commas first (§1).

**The two files do not agree exactly**, and that is expected: Basketball Monster's internal
projections are fractional and each export rounds them differently. Compared player by player on
Josh, every total agrees within one unit, and games and minutes match exactly — except points,
which reaches a difference of 2 because the `Projections.csv` route derives it from three
separately-rounded components while the Total Stats export publishes it directly. **Where they
differ, the Total Stats export is the better input**, since it is one rounding step closer to the
source.

---

## 4. Step two — the nine category values

### The pool

Every value is standardised against a pool, not against the whole league. The pool is the
**top 156 players by `Value`** — `12 teams x 13 roster spots`, the count of players who get
drafted.

The pool definition is circular: you need values to pick the pool, and the pool to compute the
values. Resolve it by iterating. Seed with the top 156 of any reasonable ranking, compute the
pool's means and standard deviations, revalue every player, take the new top 156, repeat. It
converges in **two iterations**, and the fixed point contains no player outside the 234 shown.

Two independent lines of evidence put the pool at 156:

- Sweeping the pool size and scoring the resulting values against the published columns
  minimises at N between 156 and 159.
- The published columns themselves have mean ≈ 0 and standard deviation ≈ 0.99 over the top
  156, drifting away in both directions. A z-score layer is only centred on its own pool.

Use the **population** standard deviation, dividing by *n*, not *n−1*.

### The seven counting categories

```
value = (player_per_game - pool_mean) / pool_sd
```

applied to points, threes, rebounds, assists, steals, blocks and turnovers, with **turnovers
negated** so that more turnovers means a worse number. Nothing else is inverted.

### The two percentage categories

Percentages are **not** z-scored as rates. A player shooting 90% on two attempts and one
shooting 90% on twelve are not the same asset, and standardising the bare rate calls them
equal. Basketball Monster scores the volume-weighted impact:

```
fg_impact = FGM_per_game - FGA_per_game x pool_FG%
ft_impact = FTM_per_game - FTA_per_game x pool_FT%
```

where `pool_FG%` is the pool's **attempt-weighted** mean — `sum(FGM) / sum(FGA)` over the
pool, not the average of the players' percentages. On this pool the attempt-weighted FG% is
.4899 against .4969 for the simple average — seven-tenths of a point, which is enough to move
players.

Read the impact directly: it is *makes above what a pool-average shooter would have made on the
same attempts*, in makes per game. A player who shoots exactly pool average scores zero however
many shots they take. Volume then amplifies whichever direction they deviate.

Each impact column is then z-scored against the pool exactly like a counting category.

This is the same construction our own board uses under
[ADR-0012](../decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md). It is
independently confirmed here: solving for the pool percentage from the published columns alone
returns **.798766** for FT%, against **.79930** computed directly as the pool's attempt-weighted
mean. The two agree to three decimal places from completely different directions.

### The constants

Because the published columns are exactly linear in the raw per-game stats, the mean and
standard deviation Basketball Monster used can be solved for directly rather than inferred
from a pool. Regress each published column on its per-game stat: the slope is `1/sd` and the
intercept is `-mean/sd`. For the percentages, regress on makes and attempts together — the
coefficients give `1/sd`, `-pool_pct/sd` and `-impact_mean/sd`.

The constants recovered from the 2026-08-30 export:

| Category | Mean | SD | Fit R² |
|---|---|---|---|
| Points | 17.01484 | 5.51789 | 0.9999887 |
| Threes | 1.70472 | 1.04527 | 0.9999756 |
| Rebounds | 5.98620 | 2.55316 | 0.9999828 |
| Assists | 3.89834 | 2.12316 | 0.9999881 |
| Steals | 1.00745 | 0.31981 | 0.9998073 |
| Blocks | 0.70573 | 0.52317 | 0.9999184 |
| Turnovers | 1.86440 | 0.77879 | 0.9999653 |

| Percentage | Pool rate | Impact mean | Impact SD | Fit R² |
|---|---|---|---|---|
| FG% | 0.491810 | −0.000887 | 0.653027 | 0.9999249 |
| FT% | 0.798766 | +0.002772 | 0.321948 | 0.9995835 |

These are specific to this snapshot. Re-derive them from any new export using the regression
above; it takes one pass and needs no assumption about who is in the pool.

---

## 5. Step three — `Value`, `Rank`, `Round`

**`Value` is the arithmetic mean of the nine category columns**, not their sum. Verified across
all 234 players: the largest deviation is 0.0056, which is what rounding nine two-decimal
numbers produces.

Worth flagging against our own board, which sums. A uniform ÷9 reorders nothing, but it means
every Basketball Monster magnitude is one ninth of the comparable figure in our `G TOTAL`, and
their per-category columns sit on the same footing as our `z` block.

**`Rank`** is descending `Value`, with zero mismatches across the 234.

**`Round`** is `ceil(Rank / 12)`, exact for all 234. It is reading the league size straight off
the account, which is a useful confirmation that 12 is the number the pool arithmetic should use.

---

## 6. Worked example

An invented player, with the constants from §4. Season projection: 70 games, 32.0 minutes,
and the per-game line below.

Per-game inputs: 22.4 pts · 2.1 3PM · 7.5 reb · 4.8 ast · 1.2 stl · 0.9 blk · 2.6 TO ·
8.2 FGM on 17.4 FGA (.471) · 3.9 FTM on 4.6 FTA (.848).

Points check: `2 x 8.2 + 2.1 + 3.9 = 22.4`.

```
pV   = (22.40 - 17.01484) / 5.51789      = +0.97595  ->  +0.98
3V   = ( 2.10 -  1.70472) / 1.04527      = +0.37816  ->  +0.38
rV   = ( 7.50 -  5.98620) / 2.55316      = +0.59291  ->  +0.59
aV   = ( 4.80 -  3.89834) / 2.12316      = +0.42468  ->  +0.42
sV   = ( 1.20 -  1.00745) / 0.31981      = +0.60208  ->  +0.60
bV   = ( 0.90 -  0.70573) / 0.52317      = +0.37133  ->  +0.37
toV  = -( 2.60 - 1.86440) / 0.77879      = -0.94454  ->  -0.94

fg%V  impact = 8.20 - 17.40 x 0.491810   = -0.35749
      z      = (-0.35749 - -0.000887) / 0.653027 = -0.54608  ->  -0.55
ft%V  impact = 3.90 -  4.60 x 0.798766   = +0.22568
      z      = (+0.22568 - +0.002772) / 0.321948 = +0.69236  ->  +0.69

sum   = +2.54684
Value = 2.54684 / 9 = +0.28298  ->  +0.28
```

Note the two percentage lines. This player shoots .471 from the field, below the pool's .4918,
on high volume — and is punished for it, −0.55. He shoots .848 from the line, well above the
pool's .7988, but on only 4.6 attempts, so the reward is +0.69 rather than the +2 a raw-rate
z-score would have handed him. That asymmetry is the whole point of the volume weighting.

---

## 7. The other columns — findings, not procedures

### `USG` — the standard possession formula

```
USG% = 100 x (FGA + 0.44 x FTA + TO) x (TeamMinutes / 5)
           / (Minutes x (TeamFGA + 0.44 x TeamFTA + TeamTO))
```

The structure is confirmed, decisively. Everything after the player's own
`(FGA + 0.44 x FTA + TO) / Minutes` is a single team-level constant, and it behaves like one:
across the 234 players its standard deviation **within** a team is 0.00065, against 0.00882
**between** teams — a factor of thirteen. Usage is that possession rate scaled by the player's
own team's pace, and nothing else.

Reproducing it to the decimal needs team totals over every player on each roster. The 234-row
view holds only the fantasy-relevant ones, so every team denominator comes out short and the
result lands about 6% low. Closing it means mapping all 569 CSV rows to teams — the rendered
table supplies team only for the 234 it shows, so the mapping has to come from elsewhere.

### `b2b` — a schedule count

Constant within all 30 teams, ranging 13 to 16. It is the count of back-to-back sets on that
team's 2026-27 schedule and has nothing to do with the player. Reproduce it from any published
schedule.

### `g` — an availability judgement, not a calculation

Only 19 distinct values across 234 players, and they ladder against `Inj Risk`:

| `Inj Risk` | n | `g` values assigned |
|---|---|---|
| low | 3 | 77, 81 |
| med | 123 | 58, 62, 66, 73 |
| high | 99 | 44 – 68 |

A projection of 82 games appears nowhere. Games are being set from a small menu keyed to a
risk grade, then the box-score totals are built on top. This is a forecast, not a formula, and
it cannot be reverse-engineered — only observed.

It also matters more than it looks. `g` is the denominator of every per-game rate in §3, so
the injury grade propagates into all nine category values even though the valuation itself has
no availability term.

### `FrV` — Frustration Value, not reproducible

Standardised like a value column: mean +0.05, standard deviation 1.05, range −3.76 to +1.90.
It tracks availability and nothing else in the export:

| Predictor | Correlation with `FrV` |
|---|---|
| Projected games | +0.40 |
| `fta/g` | −0.20 |
| `to/g` | −0.19 |
| `m/g` | −0.17 |
| `USG` | −0.14 |
| `Value` | −0.12 |
| Spread of the player's own nine values | −0.07 |

Grouped by injury grade it separates cleanly — low +1.37, medium +0.39, high −0.34.

The decisive test: a cross-validated linear model over **54 features** (5-fold, seeded) scores
**in-sample R² +0.565 but out-of-sample only +0.106.** So there is a little real signal — roughly
a tenth of the variance, and what survives is the availability information above — but nine
tenths of `FrV` is not recoverable from anything the export publishes.

That fits what the column is supposed to be. Whatever the rest measures is built from data this
export does not carry, almost certainly game-level logs: a season projection has no game-to-game
variance in it to measure. Treat `FrV` as an input you can read but not rebuild.

(An earlier version of this document quoted R² = 0.31 here. That was an in-sample fit; see the
method note under `Conf` below.)

### `Tier`, `Role`, `Conf` — curated

`Tier` is filled for 87 of 234 and formatted `POS<tier>#<rank-in-tier>`. It is not computed
from `Value`: in **18 of 34** tier groups the within-tier numbering disagrees with the value
order, so a `#2` outranks its own `#1`. Someone is placing these by hand.

`Role` is a depth-chart call — `ST` starter, `mST` marginal starter, `BN` bench, with the
position. 57 of 234 are bench.

### `Conf` — drafting confidence, and a genuine negative result

An integer 1–10 spread across the whole range. The natural hypothesis is that it measures how
much the metrics disagree about a player: if Josh, Bonus, DURANT and DURANT H2H all say the same
thing, be confident. **That is not what it is, and neither is anything else in the export.**

Three approaches were tried, in increasing order of flexibility.

**1. The disagreement hypothesis, directly.**

| Feature | Correlation with `Conf` |
|---|---|
| `Value` level, as a control | **+0.223** |
| \|Value − DUR\| | +0.162 |
| \|Josh rank − Bonus rank\| | −0.131 |
| spread of Josh / Bonus / DUR / DUR H2H | +0.118 |
| \|Josh Value − Bonus Value\| | **−0.074** |
| \|DUR − DUR H2H\| | +0.023 |

The disagreement measures are the *weakest* entries. The most direct one — how far the two
projection sources' values differ — is −0.074, indistinguishable from nothing, and several carry
the wrong sign, with more disagreement going alongside slightly *higher* confidence. The plain
level of `Value` beats every one of them.

**2. Categorical structure.** Measured as η², the share of variance explained by grouping:

| Grouping | η² |
|---|---|
| `Role` | 0.120 |
| `Inj Risk` | 0.048 |
| Has NBA history | 0.018 |
| Position | 0.005 |
| `Status` | 0.000 |

Conditioning on all three of (`Inj Risk`, role class, history) gives 18 cells, only **4** of them
single-valued, and leaves a within-cell standard deviation of **2.11** against an overall 2.36.
Almost nothing is explained.

**3. Arbitrary non-linear interactions.** A regression tree over 54 features — including every
disagreement measure above, both projection sources, all nine category values, and the
minute-gap features — scored by 5-fold cross-validation:

| Tree depth | In-sample R² | Out-of-sample R² |
|---|---|---|
| 2 | +0.218 | **+0.027** |
| 3 | +0.319 | −0.013 |
| 4 | +0.405 | −0.118 |
| 5 | +0.489 | −0.180 |

A cross-validated linear model over the same 54 features scores **in-sample +0.378, out-of-sample
−0.391.**

Out-of-sample performance is at best a rounding error above zero and mostly *worse than
predicting the mean*, while in-sample fit climbs steadily with capacity. That pattern is
memorisation, not signal.

**`Conf` is exogenous.** It is an analyst's grade for how sure they are about a player's role and
health, and it carries information no exported column does. Read it as an input; do not try to
rebuild it.

> **A note on method, because an earlier version of this document got it wrong.** It reported
> "R² = 0.148 on 25 numeric columns" for `Conf` and 0.31 for `FrV`. Both were *in-sample* fits of
> a many-parameter model to roughly two hundred rows — a number that only rises as features are
> added and cannot separate signal from memorisation. The cross-validated figures above replace
> them. They make the conclusion stronger, not weaker, but the original method could not have
> supported either claim.
>
> **The protocol, so the figures can be checked rather than taken on trust.** 5-fold
> cross-validation over a fixed permutation seeded with `numpy.default_rng(0)`; ridge regression
> at λ = 1e-3 for the linear model; a CART regression tree with a minimum leaf of 8 for the
> non-linear one. Out-of-sample R² is computed as `1 − SSE/(n·var(y))` pooled across held-out
> folds, so it is comparable to the in-sample figure beside it. 54 features, `n` = 204 for `Conf`
> and 212 for `FrV`. A negative value means the model does worse than predicting the mean.

`1W+-` is the one-week change in `Value`, spanning −0.21 to +0.72. Reproducing it needs last
week's export, so archive each pull if you want the series.

---

## 8. Verification protocol

Score a reconstruction. Do not assert one.

For each of the nine columns, report mean absolute error against the published value, the
maximum, and the share within ±0.05. Then compare the reconstructed ranking to the published
one by Spearman correlation and by how many ranks players move.

**State the input path with every number you report.** A figure scored against the rendered
table's one-decimal columns is not comparable to one scored against a totals export, and a Tier 1
figure is not comparable to a Tier 2 one. Both mistakes have been made in earlier drafts of this
document, in §11 — both times producing a comparison that looked like a result and was not.

There are two levels, and they are worth keeping separate because they answer different
questions.

### Tier 1 — use the recovered constants

Take the constants from §4 and apply them. This tests whether the *formula* is right,
independent of the pool question.

| Column | MAE | Max | ≤0.01 | ≤0.05 |
|---|---|---|---|---|
| `pV` | 0.0029 | 0.0081 | 100% | 100% |
| `3V` | 0.0037 | 0.0115 | 97.9% | 100% |
| `rV` | 0.0032 | 0.0099 | 100% | 100% |
| `aV` | 0.0027 | 0.0077 | 100% | 100% |
| `sV` | 0.0117 | 0.0558 | 45.7% | 99.6% |
| `bV` | 0.0069 | 0.0242 | 76.5% | 100% |
| `fg%V` | 0.0067 | 0.0185 | 78.2% | 100% |
| `ft%V` | 0.0146 | 0.0367 | 40.2% | 100% |
| `toV` | 0.0049 | 0.0156 | 92.3% | 100% |
| **mean** | **0.0064** | | | |

`Value`: MAE 0.0034, maximum 0.0112, 99.6% within 0.01.
`Rank`: Spearman **0.999814**, 118 of 234 exactly right, no player off by more than **7**.

This is a solved problem. The residual is the integer quantisation of §1 plus two-decimal
display rounding, and it is largest exactly where it should be — steals and free-throw makes,
the smallest season totals, where losing half a unit costs the most in relative terms.

**Acceptance: mean MAE ≤ 0.010 across the nine, every column at least 99.5% within ±0.05,
Spearman ≥ 0.9995, and no player moving more than 10 places.** Anything worse means a bug, not
a limit.

The ±0.05 bar is 99.5% and not 100% for one reason: `sV` has a single player at 0.0558. Steals
carry the smallest season totals of any category, so integer quantisation costs the most there
in relative terms, and one player lands just outside. Demanding 100% would be demanding the
export be more precise than it is.

### Tier 2 — rebuild the pool yourself

Iterate to the top-156 fixed point and derive the constants from it. This tests the pool
hypothesis as well as the formula, and it is what you must do on an export whose published
columns you do not have.

Mean MAE **0.0319**; Spearman **0.999515**; 79 of 234 ranks exact; mean displacement 1.40
places, maximum 8. Rebounds, assists and FT% land 100% within ±0.05; steals is the weak
column at 17.5%.

**Acceptance: mean MAE ≤ 0.040, Spearman ≥ 0.999, no player moving more than 10 places.**

---

## 9. Open gaps — findings, not procedures

### The pool's spread does not match any top-N

The one thing not closed. The means recovered in §4 agree with the top-156 pool to within
0.5%, but the standard deviations run consistently **wider**:

| Category | Top-156 pool SD | Recovered SD | Ratio |
|---|---|---|---|
| Steals | 0.31116 | 0.31981 | 1.028 |
| Points | 5.41398 | 5.51789 | 1.019 |
| Turnovers | 0.76562 | 0.77879 | 1.017 |
| Threes | 1.03110 | 1.04527 | 1.014 |
| Assists | 2.10652 | 2.12316 | 1.008 |
| Blocks | 0.51915 | 0.52317 | 1.008 |
| Rebounds | 2.56444 | 2.55316 | 0.996 |

This is not a pool-size problem, and it is not measurement error. What has been ruled out:

- **A larger or smaller top-N.** No nested pool fits both moments. Points wants N ≈ 159 for
  its mean and N ≈ 179 for its spread; steals wants 177 and 233; assists wants 158 and 135.
- **Filtered-out players.** Iterating the pool over all 509 CSV players with games returns a
  fixed point containing nobody outside the 234 shown.
- **A different selection basis.** Pools ranked by total value, by minutes, and by minutes per
  game all score three to four times worse than the top-156 by per-game value.
- **Sample vs population SD.** `n−1` accounts for 0.3% of a gap that reaches 2.8%.
- **CSV quantisation.** Errors-in-variables attenuation from integer totals inflates the
  recovered SD by about 0.02%, two orders of magnitude too small.
- **Any 156-player subset at all.** A local search over 6,000 swaps cut the joint moment error
  from 0.214 to 0.065 and got the spreads right — by pulling the means off. No subset of these
  projections satisfies both.

**The standing hypothesis** is that the constants come from a wider distribution than the
current projection set: realised production rather than projections. Projections are regressed
toward the mean, so they are narrower than the outcomes they predict, and the size of the gap
per category tracks how predictable that category is. Steals — the noisiest, most heavily
shrunk stat — shows the largest gap at 1.028. Rebounds, the most persistent, shows none at
0.996. That ordering is what shrinkage predicts, and it is unlikely to be coincidence.

**The experiment that settles it:** export a prior season's *actual* per-game statistics from
Basketball Monster, take the top 156 by that season's value, and compare its moments to the
recovered constants. If they match, the pool question is closed.

None of this blocks reproduction. The Tier 1 constants are recoverable from any export by
regression, and they reproduce every published number to display precision regardless of how
Basketball Monster derived them.

### Smaller open questions

- What `FrV` measures, and on what data. Pulling it as a member column (it is one) changes
  nothing: the values are identical to those in the default export, and the R² of 0.31 stands.
  `Conf` is now tested and closed the same way — see §7; it is judgement, not arithmetic.
- Whether `Tier` is analyst-set or clustered by some rule not visible in the export.
- `USG`, pending a complete player-to-team mapping.
- DURANT's percentage categories — the one part of §10 not reproduced. `BalV` (Balance Value)
  was pulled at the same time and is not analysed here.

---

## 10. DURANT, reverse-engineered

Solved on 2026-08-30 against a live member export. This section replaces the protocol that
stood here before, and supersedes several claims that circulate about DURANT — including two
recorded on branch `bbm`.

### Where it lives

**DURANT is a column, not a value type.** The `Value Type` dropdown offers only *Total Games
Value*, *Per Game Value* and *Per 36 Value* — that is the denominator, not the metric. And the
Player Rankings page is the wrong page for a season that has not started: it serves actuals, so
for 26-27 it returns "There are no results to display." **Projections live on
`projections.aspx`**, which carries its own independent column selection.

There, `Edit Display and Value Columns` offers six DURANT entries — `DURANT`, `DURANT Category
Values`, `DURANT Dollars`, and the same three for `DURANT H2H`. Type `durant` into the picker's
`Find a column…` box to isolate them. Enable the four non-Dollars ones, plus **`Minus 1 Value`**
and **`Balance Value`**. All are membership-gated.

Two practical notes. The picker has both **`Save`** and **`Apply`**: `Apply` redraws the table
for this visit only, and the selection is lost on reload — `Save` persists it. And the page has
its own **`Export to CSV`** button, which is a better source than scraping the DOM.

**There is no DURANT-based projection.** The `Projection Source` dropdown offers only *Josh
Projections* and *Bonus Projections*. DURANT is a valuation applied on top of whichever of those
is selected — the same games, minutes and box-score totals, scored a different way. Nothing in
the projection itself changes when you switch DURANT on; only the value columns appear.

### The columns, and the gift hidden in them

The aggregate columns are composite strings, not plain numbers:

```
DUR        ->  1.18#2to      value 1.18, DURANT rank 2, category dropped: turnovers
DUR H2H    ->  0.99#23       value 0.99, rank 2,        category dropped: threes
Minus1V    ->  1.66+0.22to   value 1.66, gain of 0.22,  category dropped: turnovers
```

**Basketball Monster names the dropped category itself.** That converts the hardest part of the
reconstruction from an inference into a read.

The category token for three-pointers is the bare digit `3`, which runs straight into the rank
and makes the string genuinely ambiguous: `0.99#23` is *rank 2, threes*, not *rank 23*. On screen
it renders as `0.99 #23 3` and reads even more like rank 23. Parse with
`^(-?[\d.]+)#(\d+?)(pts|3|reb|ast|stl|blk|fg%|ft%|to)?$` — the **non-greedy** rank group is
what resolves it, and a greedy one turns `#47` plus a threes token into rank 473.

Verify the parse rather than trusting it. Across both columns the recovered ranks are 234
distinct values with **zero value-versus-rank inversions**, which the wrong split does not
produce.

The per-category columns are `DpV D3V DrV DaV DsV DbV Dfg%V Dft%V DtoV` and, for the H2H
variant, the same with a `DH` prefix.

### The algorithm

Both metrics share the first three steps and diverge after that.

```
Shared:
  1. Per-game rate for each category, exactly as in §3.
  2. Yeo-Johnson transform each category with its own lambda.
  3. Standardise the transformed column against the pool.  -> the D*V columns

DURANT:
  4. Drop each player's single lowest D*V.
  5. DURANT = the arithmetic mean of the eight survivors.  (all nine equally weighted)

DURANT H2H:
  4. Multiply each D*V by a fixed category weight.         -> the DH*V columns
     Turnovers carry weight 0, which is how they are "removed".
  5. Drop the lowest of the remaining eight weighted values.
  6. DURANT H2H = the arithmetic mean of the seven survivors.
```

**The two metrics do not share their category columns.** `DH*V` is `D*V` scaled by a fixed
per-category weight — only points passes through unchanged. This is the difference that matters
and the one an earlier draft of this document got wrong; see *Where the category weights are*
below.

### Confirmed, exactly

| Claim | Result |
|---|---|
| The named category is that player's minimum `D*V` | **234 / 234** |
| `DUR` = unweighted mean of the eight survivors | MAE **0.0025**, max 0.0063 |
| `DUR H2H` drops turnovers for everyone | **0 of 234** name turnovers |
| `DUR H2H` = unweighted mean of the seven survivors | MAE **0.0024**, max 0.0071 |
| Its named category is the minimum of the remaining eight | **234 / 234** |

Those MAEs are the rounding floor: averaging eight values published to two decimals cannot do
better.

### The lambdas

**Fitted on the Josh source.** The lambdas below, and every DURANT figure in this section, come
from the Josh projections and their pool. They are not claimed to transfer to Bonus: a
Yeo-Johnson lambda is fitted to a particular distribution, and §11 shows the two sources put
players in materially different places. Re-fit before using them on Bonus, by the same procedure.

Recovered by golden-section search on the R² of each published column regressed on
`YeoJohnson(raw per-game stat, lambda)`. Turnovers are fitted on the negated column, keeping the
inversion of §4.

| Category | λ | mean of YJ(x) | SD of YJ(x) | fit R² |
|---|---|---|---|---|
| Points | +0.4151 | 5.51802 | 0.98572 | 0.9999887 |
| Threes | +1.0166 | 1.74286 | 1.05071 | 0.9999751 |
| Rebounds | −0.4381 | 1.26670 | 0.15419 | 0.9999782 |
| Assists | +0.0065 | 1.51402 | 0.42332 | 0.9999842 |
| Steals | −0.3513 | 0.61416 | 0.11872 | 0.9997738 |
| Blocks | −1.6863 | 0.30644 | 0.11144 | 0.9997575 |
| Turnovers | −0.1778 | 0.93094 | 0.21651 | 0.9999492 |
| FG% impact | +0.1727 | −0.15608 | 0.60352 | 0.9978992 |
| FT% impact | +1.5038 | 0.02685 | 0.30813 | 0.9983610 |

Read the λ column as a ranking of how badly each category needed fixing, and it lands exactly
where Lloyd's argument says it should:

- **Blocks, −1.69** — by far the most aggressive compression. Blocks are the most right-skewed
  category in the pool, and this is the transform doing the thing DURANT was built to do.
- **Rebounds −0.44, steals −0.35, turnovers −0.18** — moderate right-tail compression.
- **Assists +0.0065** — indistinguishable from a **log transform**, which is λ = 0 exactly.
- **Threes +1.0166** — indistinguishable from **the identity**. Threes are already near-normal,
  and DURANT leaves them alone. A useful sanity check on the whole fit: the method finds "do
  nothing" when nothing needs doing.
- **FT% impact +1.50** — the only λ above 1, *expanding* rather than compressing, because FT%
  impact is the one category skewed **left**.

### Where the category weights are

The most-repeated claim about DURANT is that it applies fixed, unpublished category weights.
The truth is split, and both halves matter.

**Plain `DURANT` has none.** Two independent lines of evidence:

- An unweighted mean of the survivors reproduces `DUR` to the rounding floor. Any non-equal
  weighting would leave a systematic residual, and there is none.
- The weights are not hiding inside the `D*V` columns either. Over the top ~150 by `DUR`, every
  one of the nine has SD between 0.96 and 1.04 and mean within 0.08 of zero. They are plain
  unit-variance z-scores.

**`DURANT H2H` has them, and they are recoverable exactly.** Regressing each `DH*V` column on
its `D*V` counterpart gives a clean proportional relationship with no intercept:

| Category | Fitted slope | Weight | R² |
|---|---|---|---|
| Points | 1.00000 | **1.00** | 1.0000000 |
| Rebounds | 0.93997 | **0.94** | 0.9999833 |
| Assists | 0.75037 | **0.75** | 0.9999772 |
| Threes | 0.59959 | **0.60** | 0.9999643 |
| Steals | 0.60024 | **0.60** | 0.9999741 |
| Blocks | 0.60006 | **0.60** | 0.9999674 |
| FG% | 0.60011 | **0.60** | 0.9999713 |
| FT% | 0.60015 | **0.60** | 0.9999617 |
| Turnovers | 0.00000 | **0.00** | — |

Every intercept is below 0.0005 and every maximum residual below 0.0093, which is two-decimal
display rounding. `DHtoV` is literally `0.00` for all 234 players: turnovers are removed by
carrying weight zero, not by a special case in the drop logic.

Read the vector plainly. Points are the reference at 1.00; rebounds nearly match them; assists
count three-quarters; and threes, steals, blocks and both percentages all count **0.60**. So a
point of steals edge is worth 60% of a point of scoring edge before the drop rule does anything.

Lloyd's pre-DURANT manual method weighted threes, steals and blocks at 0.8 and punted turnovers.
The shape survives — those three are still the discounted ones and turnovers are still gone —
but the values do not, and FG%/FT% have joined the discounted group.

**A correction to an earlier version of this document.** It claimed DURANT applied no category
weights at all, generalising a result that only held for `DUR`. The error came from a test with
a blind spot: the aggregation check consumed the *published* `DH*V` columns, so it validated the
arithmetic given those columns and structurally could not detect that they differed from `D*V`.
The end-to-end reconstruction from raw stats — run for `DUR` but not, at the time, for
`DUR H2H` — would have caught it immediately. It is now run for both.

### Full reconstruction accuracy

Built end to end from the raw projections CSV — per-game rates, transform, standardise, drop the
minimum, average:

| Column | MAE | Max | ≤0.05 |
|---|---|---|---|
| `DpV` | 0.0032 | 0.0109 | 100% |
| `D3V` | 0.0038 | 0.0113 | 100% |
| `DrV` | 0.0038 | 0.0157 | 100% |
| `DaV` | 0.0036 | 0.0092 | 100% |
| `DsV` | 0.0133 | 0.0546 | 99.6% |
| `DbV` | 0.0109 | 0.0821 | 99.1% |
| `DtoV` | 0.0063 | 0.0268 | 100% |
| `Dfg%V` | 0.0345 | 0.1632 | 79.1% |
| `Dft%V` | 0.0273 | 0.1517 | 88.9% |

Aggregates, both built end to end from the raw CSV:

| Metric | MAE | Max | Spearman | Mean rank move |
|---|---|---|---|---|
| `DUR` | **0.0048** | 0.0165 | **0.999657** | 2.63 |
| `DUR H2H` | **0.0038** | 0.0168 | **0.999846** | 3.59 |

`DUR H2H` reconstructs slightly *better* than `DUR`, because zeroing turnovers removes the
noisiest of the nine columns from the average.

**The control that matters.** Rebuilding `DUR H2H` with equal weights — the way an earlier
version of this document described it — gives **MAE 0.0963, max 0.3257**, about 38× worse. If a
reconstruction lands near 0.10 rather than 0.004, the weight vector is missing.

**Acceptance for a DURANT reconstruction: the seven counting columns at MAE ≤ 0.015 and ≥99%
within ±0.05, and each aggregate at MAE ≤ 0.010 with Spearman ≥ 0.9995.** Both metrics pass;
run the check for both, not just `DUR`.

### What is solved, and what is not

Worth stating precisely, because "the percentages are open" is easy to over-read as "DURANT is
not reproduced". It is reproduced. The gap is one layer down.

**Solved — both metrics, exactly.** Given Basketball Monster's published category columns, the
aggregation reproduces at the rounding floor: `DUR` MAE **0.0025**, `DUR H2H` MAE **0.0025**. The
drop rule, the weight vector and the averaging are fully known, and the dropped category matches
the player's minimum 234/234 for both.

**Solved — seven of the nine input columns**, rebuilt from the raw stat sheet through the
recovered lambdas:

| Column | MAE | | Column | MAE |
|---|---|---|---|---|
| `DpV` | 0.0032 | | `DaV` | 0.0036 |
| `D3V` | 0.0038 | | `DtoV` | 0.0063 |
| `DrV` | 0.0038 | | `DbV` | 0.0109 |
| | | | `DsV` | 0.0133 |

**Not solved — the two percentage input columns.** `Dfg%V` reaches only MAE 0.0345 and `Dft%V`
0.0273 against a Yeo-Johnson-on-impact model, at **Spearman 0.9977 and 0.9980** — and it is the
Spearman that gives it away. A monotone transform of the correct input would order players
*identically*, at 1.0. DURANT is transforming something slightly different from the §4
volume-weighted impact.

Ruled out: the raw percentage (R² 0.83 / 0.72) and impact scaled by the square root of attempts
(R² 0.96 / 0.93). Both are worse on every measure.

**Which situation are you in?**

- **Reading Basketball Monster's own numbers** — you have `D*V`, so both aggregates are exact and
  the gap does not touch you.
- **Rebuilding DURANT end to end from a stat sheet** — seven categories land at MAE ≤ 0.013 and
  two at ~0.03, which is why the full reconstruction comes in at MAE 0.0048 rather than 0.0025.
  Still comfortably inside the acceptance bar, but the two percentage columns are where the error
  lives.

This is also where Lloyd says the method is unfinished — *"Durant doesn't necessarily fix this
problem… I actually haven't found a way to do it yet"* — so the residual may not be a gap in the
reconstruction so much as a reflection of something ad hoc in the original.

### Corrections this section makes

- **"DURANT applies fixed category weights."** Half right, and the half matters. Plain `DURANT`
  applies none — the survivors are averaged equally and the `D*V` columns carry no embedded
  scaling. `DURANT H2H` applies them, and they are now recovered exactly: 1.00 points, 0.94
  rebounds, 0.75 assists, 0.60 for threes, steals, blocks, FG% and FT%, and 0.00 turnovers.
- **"You switch the value type to DURANT."** No — it is a column, on `projections.aspx`, and the
  `Value Type` dropdown is unrelated.
- **"The coefficients are unpublished, and nobody has replicated it."** The coefficients are
  still unpublished, but they are recoverable. The table above is a replication of everything
  except the percentage handling.

### What this does not settle

Reproducing DURANT is a measurement exercise. Adopting any of it is a separate decision needing
its own ADR, and the argument against is untouched by a successful fit: categories are won by
13-man team totals, and the central limit theorem makes those near-normal however skewed the
individual distributions are. Rosenof cites Lloyd for the non-normality premise and still
declines to transform, for exactly that reason.

Two further asymmetries are worth keeping in view. DURANT still has **no availability term** —
it is per-game throughout, and our `Adjusted Value` models something it does not. And its
punting is **automatic and per player**, deciding for you which category each player concedes,
where our board makes you choose a build and values everyone against it.

## 11. The two projection sources

`Projection Source` on `projections.aspx` offers **Josh Projections** and **Bonus Projections**.

**There is no difference in the math. None.** Same z-score construction, same 156-player pool,
same volume-weighted percentages, same arithmetic mean of nine, same `Rank` and `Round`.
Everything in §§3–5 applies to both, unchanged and with no substitutions.

What differs is the **input** — the projected games, minutes and box-score totals fed into that
identical machine. These are projection *sources*, not valuation methods.

### How to reproduce either one

The procedure is the same for both. Only step 1 changes.

```
1. On projections.aspx, set Projection Source to Josh or Bonus.
2. Set Stats Display Format = Total Stats, Filters = All Players.  Export to CSV.
      -> the totals export: 569 players under Josh, 584 under Bonus
3. Set Stats Display Format = Per Game Stats.                      Export to CSV.
      -> the rendered table: the published Value and category columns
4. Run sections 3, 4 and 5 exactly as written, using the step-2 totals as input.
5. Check against the step-3 table.
```

Step 2 needs the §1 handling: strip commas, and rebuild makes as `fg% × fga`.

Do not mix sources between steps 2 and 3. Both exports follow the selector, and a mismatched
pair will not reconcile — see the trap in §1.

### Both sources verified, by that procedure

Run end to end from each source's own Total Stats export against its own rendered table — the
same code, the same steps, the only difference being which source produced the files. Scored
against §8's **Tier 2** bar, which is the one this procedure is subject to, because it rebuilds
the pool rather than using recovered constants:

| Check | Tier 2 bar | Josh | Bonus |
|---|---|---|---|
| Each category value linear in its raw per-game stat | R² ≥ 0.9998 | 0.99981 – 0.99999 | 0.99983 – 0.99999 |
| `Value` = arithmetic mean of the nine | — | MAE 0.0075 | MAE **0.0043** |
| Rank correlation | Spearman ≥ 0.999 | 0.99942 | **0.99970** |
| Maximum rank displacement | ≤ 10 | 8 | **8** |
| Pool size where published columns reach unit variance | — | 156 | **156** |
| Those columns' SDs at N = 156 | — | 0.972 – 1.004 | 0.977 – 1.005 |

Both pass. Same construction, same pool, same aggregation — demonstrated from raw totals on both
sides rather than inferred, and Bonus is if anything the cleaner of the two.

Note that Josh's Spearman here (0.99942) is below the **Tier 1** bar of 0.9995 quoted in §8. That
is not a failure: Tier 1 uses constants recovered by regression and Tier 2 rebuilds the pool from
scratch, so Tier 2 is the harder path and carries the looser bar. Compare like with like.

> **A note on an earlier version of this section.** It reported R² of 0.9928–0.99996 for Bonus and
> attributed the softness to "display rounding on small per-game counts". The real cause was that
> no Bonus totals export had been found, so the check had quietly been run against the *rendered
> table's* one-decimal per-game columns — a different and weaker input path than §4 prescribes,
> and one the section did not disclose. It also set that figure beside Josh's Tier 1 numbers, so
> the two columns were not comparable in the first place. Both faults are the same mistake: a
> number is meaningless without the input path that produced it. §8 now says so explicitly.

### The choice moves players a lot

Comparing the same 212 players across both sources:

- Mean rank movement **about 20 places** (19.8–20.6 depending on tie-break), maximum 93–98.
- Roughly **130–140 of 212** move ten or more places.
- Mean absolute `Value` difference **0.078**, maximum 0.31.

The rank figures are ranges on purpose. `Value` is published to two decimals and 140 of 230
players share theirs with somebody, so exact rank counts shift with how ties are broken. The
ranges span 40 random tie-breaks plus the export's own order — and that order is itself sorted by
baseline rank, which preserves ties in place and so *understates* movement. Do not quote a single
figure. The `Value` differences, which need no ranking, are exact.

That is a bigger reshuffle than most methodology choices produce, and larger than DURANT's own
weighting decision. **Which projection source produced a number matters more than which valuation
produced it.** Establish the source before comparing any Basketball Monster figure against ours.

### Nothing here settles §9

An earlier draft suggested the Bonus pool sat noticeably closer to unit variance than Josh's, and
offered that as a lead on the §9 spread gap. Measured like-for-like from the totals exports, the
two are 0.972–1.004 and 0.977–1.005 — indistinguishable. The lead was an artefact of comparing a
rounded input path against a raw one. §9 stands exactly as written.

---

## 12. Punt weights

Basketball Monster's punt support is a **per-category weight**, not a binary punt — the same
shape as our own [ADR-0009](../decisions/ADR-0009-soft-punt-weighting.md) soft weighting.

### The control

`Punt Settings` on `projections.aspx` opens nine numeric inputs, one per category, `min=0`,
`step=0.01`, no maximum. They are named `PuntCategoriesControl_weight_N`, where N is Basketball
Monster's own category id — `1` pts, `2` threes, `3` reb, `4` ast, `5` stl, `6` blk, `7` fg%,
`8` ft%, `25` to. Those are the same ids that appear in the rendered table's sort links
(`SortC_1`, `SortV_25`), which is a useful cross-check.

Blank means "no punt". **A weight of `0` is read as blank and silently does nothing** — it will
not survive a refresh. Use a small non-zero value to model a hard punt.

### The mechanism

**Measured on the Josh source**, with both the punted and baseline exports taken from it. The
mechanism is structural rather than fitted, so it should hold under Bonus, but that has not been
checked.

Measured by setting one weight, exporting, and regressing every column against the unpunted
baseline. Two builds were tested — turnovers at 0.50, and FT% at 0.25 — to confirm the rule
generalises across a counting category and a percentage, and across two different weights.

```
1. Weight the category's standardised value:  V_punted = w x V
2. Re-derive the pool and re-standardise, because Value changed and so did who is in the top 156.
3. Value = the arithmetic mean of the nine columns.  The denominator stays 9.
```

| Build | Punted column slope vs baseline | Other eight | `Value` = mean of nine |
|---|---|---|---|
| `to` at 0.50 | 0.523 | 1.009 – 1.024 | MAE 0.0025 |
| `ft%` at 0.25 | 0.246 | 0.983 – 1.023 | MAE 0.0025 |

The punted column scales by the weight, as intended. The other eight drift by one to two percent
— not a rounding artefact but the pool re-standardising: under the turnovers punt, **six players
enter or leave the top 156**, which shifts every category's mean and SD slightly.

Two consequences worth stating plainly.

**The denominator does not change.** Value is the mean of nine even when a category is weighted
to a fraction, so punting *lowers* everyone's Value rather than redistributing it. It is not a
renormalised weighted average.

**Punting is not local to the punted category.** Because the pool re-derives, a punt moves
players who have nothing to do with the punted category. Under a half-punt on turnovers, mean
rank movement is **about 8 places** (7.7–8.4 by tie-break), with a maximum of 52–58 and roughly
**69–82 of 230 players moving ten or more** — again a range, for the tie reason given in §11.

### How this compares to our board

The shape matches ADR-0009 — a fractional weight, not a deletion — which is reassuring, since we
adopted soft punting on the argument that a conceded category is still won by accident some
weeks.

Two differences are worth carrying into any future revision of that ADR. Basketball Monster
**re-standardises the pool after punting**; our board does not, and that is the more
consequential of the two, because it means their punt build changes the replacement level itself.
And their denominator stays at nine, so their punted values are not comparable in magnitude to
their unpunted ones — a trap when reading the two side by side.

---

## 13. Cheat sheet

The whole thing in plain language. No formulas.

### What the numbers are trying to say

Every category column answers one question: **how much better than a typical drafted player is
this guy, in this one stat?** Zero means average. Positive is better, negative is worse. The
units are "standard deviations", which is a statistician's way of saying *how unusual this is
given how spread out the category normally is*.

That last part is why you cannot just compare raw stats. Three rebounds a game above average is
common; three steals a game above average has never happened. Dividing by the category's normal
spread puts them on one scale, so a number like +1.5 means the same thing in every column.

`Value` is just the average of those nine numbers. That is the entire ranking.

### Why "a typical drafted player" and not "a typical NBA player"

The comparison group is the top 156 players — twelve teams times thirteen roster spots, which
is everyone who gets drafted. Comparing against all 500-odd players in the league would make
almost every draftable player look above average and squash the differences that matter.

If your league is not 12 teams of 13, this number changes, and so does every value on the page.
A smaller league means a tougher comparison group and lower numbers for everyone.

### Why turnovers have a minus sign

Turnovers are the only category you want *less* of. So the sign is flipped: a player who turns
it over a lot gets a negative number, same as a player who cannot rebound. That way adding up
all nine works without special cases.

### Why shooting percentages are handled differently

This is the part everyone gets wrong.

A player shooting 90% from the line on two attempts a game and one shooting 90% on twelve
attempts are not equally valuable — the second one actually moves your team's percentage, and
the first barely registers. If you just scored the percentage, they would look identical.

So instead of scoring the percentage, Basketball Monster scores **how many extra makes you get
compared to an average shooter taking the same number of shots**. Shoot exactly average and you
score zero no matter the volume. Shoot above average and the more you shoot the more you help.
Shoot below average on high volume and you actively hurt — which is why a high-usage,
poor-percentage scorer gets punished here in a way that raw percentage never shows.

The same logic runs in both directions, and it is the reason a low-volume specialist never
scores as high in FT% as their percentage suggests.

### What each column is for at a draft table

| Column | Read it as |
|---|---|
| `Value` | The overall ranking number. Higher is better. Zero is roughly a mid-round pick. |
| `Rank` | Position on that list. |
| `Round` | Which round that rank falls in, at 12 teams. |
| The nine `V` columns | Where this player helps and where he hurts. Scan for the big negatives. |
| `g` | How many games they are *projected* to play. Nobody is projected for all 82. |
| `Inj Risk` | The injury grade that produced `g`. |
| `USG` | Share of his team's possessions he uses. High usage means the stats are unlikely to grow much. |
| `b2b` | Back-to-backs on his team's schedule. A team thing, not a player thing. |
| `Conf` | How confident they are in the projection, 1 to 10. |
| `FrV` | Roughly, how much this player will let you down. Higher is calmer. |
| `Tier` | Their analysts' grouping of similar players at that position. |
| `Role` | Starter, marginal starter, or bench. |
| `1W+-` | How much the value moved in the last week. |

### Which numbers are computed and which are opinions

**Computed, and reproducible exactly:** the nine category columns, `Value`, `Rank`, `Round`, and
every per-game stat.

**Computed, but needing information the export does not include:** `USG` and `b2b`.

**Somebody's judgement:** `Inj Risk`, and therefore `g` — which matters more than it looks,
because games played is the denominator of every per-game stat, so an injury opinion quietly
flows into all nine category values. Also `Conf`, `Tier`, `Role`, and the analysts' columns.

**Unknown:** `FrV`. It is clearly a real calculation, but nothing in the export reproduces it.

### What DURANT is, in one page

`Value` treats every category the same way: count how unusual a player is, average the nine.
DURANT changes two things.

**First, it squashes the freaks.** Some categories have a long tail — a handful of players block
shots at rates nobody else approaches. Under a plain z-score that hands them an enormous number
in one column, which then drags their overall rank up more than it should. DURANT bends each
category's scale so the extreme top gets pulled back toward the pack. How hard it bends depends
on the category: blocks get squashed the most, rebounds and steals moderately, and three-pointers
are left completely alone because they were already well behaved.

**Second, it forgives each player their worst category.** Every player gets their single weakest
category thrown out, and DURANT is the average of the remaining eight. So a big man who cannot
shoot free throws simply stops being penalised for it. `DURANT H2H` goes further: it throws out
turnovers for *everybody* first, then throws out your worst of what is left, and averages the
seven that remain.

That second rule is why DURANT flatters specialists. It assumes you will punt whatever each
player is bad at — which is a real strategy, but it decides it for you, player by player, rather
than letting you pick one build and stick to it.

The two versions also **count the categories differently**, which is easy to miss. Plain DURANT
treats all nine equally. DURANT H2H throws turnovers away entirely and then counts steals,
blocks, threes and both shooting percentages at 60% of what a point of scoring is worth, with
rebounds at 94% and assists at 75%. So the H2H version is not just "DURANT minus turnovers" — it
is a noticeably more scoring-and-rebounding-led ranking.

Two things worth knowing before trusting either. Neither has **any sense of injuries** — both are
per-game numbers throughout, so a player who will miss thirty games looks identical to one who
will not. And their handling of shooting percentages is the one piece still not fully understood,
which matches what their author says about it.

### The three mistakes to avoid

1. **Made field goals already include threes.** Points are two per field goal plus one extra per
   three, plus free throws. Count threes twice and every shooter's value is wrong.
2. **The pool average for shooting percentage is weighted by attempts**, not the average of
   everyone's percentage. On this data those differ by seven-tenths of a point, which is enough
   to move players.
3. **Nothing here accounts for availability.** These are per-game values. A player projected for
   44 games and one projected for 73 are rated as if they were the same asset. That judgement is
   yours to add.

---

## 14. Sources

**Basketball Monster.** Three pulls, all 2026-08-30 with a member account: the projections CSV
of season totals, the default `projections.aspx` table (§§1–9), and the same table re-pulled with
the DURANT, DURANT H2H, `Minus 1 Value` and `Balance Value` columns enabled (§10). The DURANT
column tooltips on the Player Rankings and Trade Analysis pages are public, and their account of
the minus-one rule is now confirmed against the data rather than taken on trust.

**Josh Lloyd, in his own voice**, on Locked On Fantasy Basketball and his own channel — 2 Sep
2023 (the origin episode: the acronym, the FT% findings, the refusal to publish the formula),
22 Jul 2025 (the component list), 22 Apr 2026 (names Yeo-Johnson, "per game metric", the
replacement-level omission). Transcripts are YouTube auto-captions, so proper nouns are mangled;
the numbers and the acronym read cleanly and recur across episodes. Full citations, URLs and the
published rank-movement sets are on branch `bbm` in
`docs/references/basketball-monster-durant.md`.

**Basketball Monster article 1831**, *Welcome*, 15 Aug 2022 — the only one still public, and the
source for Lloyd's pre-DURANT manual weights.

**Rosenof**, [2307.02188](https://arxiv.org/abs/2307.02188) (G-score) and
[2409.09884](https://arxiv.org/abs/2409.09884) (H-scoring). The latter cites Lloyd's 2023
podcast for the heavy-tailed-blocks premise and declines to act on it.

**In this repo:** [ADR-0012](../decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md)
on the percentage denominator, [ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md)
on why no data appears above, and the
[draft playbook](fantasy-basketball-draft-playbook.md) and
[quant-vs-expert reconciliation](quant-vs-expert-reconciliation.md) for how our own valuation
compares.
