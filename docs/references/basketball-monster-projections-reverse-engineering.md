# Basketball Monster's valuation, reverse-engineered

**This is a specification, not a scraping guide.** Part I is everything you need to compute
Basketball Monster's numbers yourself, from any set of projections, with no Basketball Monster
account and no export file. Read it as the algorithm; the provider is incidental.

A working implementation of Part I is committed at
[`scripts/bbm/bbm_reference.py`](../../scripts/bbm/bbm_reference.py) — standard library only,
tested, and measured against their published columns in Part IV.

| Part | What it is | Needs their site? |
|---|---|---|
| **I — The specification** | The algorithm, the constants, a worked example | **No** |
| **II — Where the numbers come from** | Why two projection sets give different answers | No |
| **III — What we could not determine** | Findings, not procedures | No |
| **IV — Validating against Basketball Monster** | Export routes and measured accuracy | Yes, optional |
| **V — Cheat sheet** | The whole thing in plain language | No |

> This repository is public. Under
> [ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md) it publishes no provider
> data, so no player appears here attached to a stat line. The worked example uses an invented
> player. The constants in §I.8 are aggregate statistics we derived.

Written 2026-08-30 on branch `durant-actual`. Nothing here changes the draft board.

---

# Part I — The specification

## I.1 What you need as input

For every player, a **projected stat line as season totals**:

```
games       minutes
points      threes      rebounds    assists    steals    blocks    turnovers
fg_made     fg_att      ft_made     ft_att
```

That is the whole contract. No file format, no column names, no provider. Anything that can
produce these thirteen numbers per player will work — Basketball Monster's projections, ours,
ESPN's, or a spreadsheet you typed by hand.

Three of them are commonly not given directly and have to be built:

- **Points.** If your source gives made field goals rather than points:
  `points = 2 × fg_made + threes + ft_made`. **Made field goals already include three-pointers** —
  a made three is one field goal worth an extra point, not a separate event. Count it twice and
  every high-volume shooter is wrong, silently, in a way that still looks plausible.
- **Rebounds.** Offensive plus defensive, if they are separate.
- **Makes**, if your source gives a percentage and attempts: `fg_made = fg% × fg_att`.

**Keep makes and attempts separate. Do not collapse them to a percentage.** §I.4 needs both, and
a percentage on its own throws away the volume that makes it worth anything.

## I.2 Step one — per-game rates

Divide every total by `games`. **Drop any player projected for zero games** — they cannot be
rated and they will destroy your pool statistics.

Everything from here on is per game. There is no availability term anywhere in this method: a
player projected for 44 games and one projected for 73 are rated as though they were the same
asset. That is a real limitation of the method, not an omission in this document, and §V says
what to do about it.

## I.3 Step two — the pool

Every value is measured against a **pool**, not against the whole league. The pool is the top
**Q** players by `Value`, where

```
Q = number of teams × roster spots per team
```

For a 12-team league with 13 spots, `Q = 156` — the players who actually get drafted. Comparing
against everyone in the league would make almost every draftable player look above average and
squash the differences that matter.

The definition is circular: you need values to pick the pool and the pool to compute the values.
Resolve it by iterating.

```
pool <- any reasonable starting 156 (ranking by projected minutes works fine)
repeat:
    params <- pool statistics (I.4)
    rescore every player
    next <- the top 156 by that score
    stop when next == pool
    pool <- next
```

It converges in one to three rounds. The fixed point is stable but not perfectly unique: seeding
from different orderings lands on pools differing by **one or two boundary players**, worth about
0.001 in the resulting `Value`. Do not expect bit-identical results from a different seed.

Use the **population** standard deviation — divide by *n*, not *n − 1*.

## I.4 Step three — the nine category values

### The seven counting categories

```
value = (player_per_game − pool_mean) / pool_sd
```

for points, threes, rebounds, assists, steals and blocks — and for turnovers with the sign
flipped:

```
turnover_value = −(player_to − pool_mean_to) / pool_sd_to
```

Turnovers are the only inverted category. Nothing else is.

### The two percentage categories

**Not** a z-score of the percentage. A player shooting 90% on two attempts and one shooting 90%
on twelve are not the same asset, and standardising the bare rate calls them equal.

First, the pool's rate — **attempt-weighted**, not the average of the players' percentages:

```
pool_fg_rate = Σ fg_made(pool) / Σ fg_att(pool)
```

These differ by more than you would guess: on a real 156-player pool the attempt-weighted FG% is
.4899 and the simple average of individual percentages is .4969 — seven tenths of a point, which
is enough to move players.

Then each player's **impact**, in makes per game:

```
fg_impact = fg_made − fg_att × pool_fg_rate
```

Read it directly: *makes above what a pool-average shooter would have produced on the same
attempts*. Shoot exactly pool average and you score zero however much you shoot. Shoot above it
and volume amplifies the gain; below it and volume amplifies the damage.

Finally, z-score the impact column exactly like a counting category — mean and population SD of
the pool's impacts.

Identically for free throws.

## I.5 Step four — `Value`, `Rank`, `Round`

```
Value = (sum of the nine category values) / 9
Rank  = position in descending Value, 1 = best
Round = ceil(Rank / number_of_teams)
```

`Value` is the **mean**, not the sum. A uniform ÷9 reorders nothing, but every magnitude here is
one ninth of the comparable figure on a board that sums — including ours.

## I.6 Step five — DURANT

DURANT is a second, separate metric over the same inputs. Two ideas: pull in the skewed tails so
one freakish category cannot dominate, and forgive each player their worst category.

```
1. Per-game rates, exactly as I.2.
2. Yeo-Johnson transform each category with its own lambda (I.8).
   For the percentage categories, transform the impact from I.4, not the rate.
3. Standardise the transformed column against the pool — same mean/SD treatment as I.4.
   Build this pool by iterating on the DURANT score, not on Value; the constants differ.
4. Drop each player's single lowest of the nine.
5. DURANT = the arithmetic mean of the eight that survive.  All nine weigh the same.
```

The Yeo-Johnson transform, for a value *x* and parameter *λ*:

```
x >= 0 :  ((x+1)^λ − 1) / λ          for λ ≠ 0,     ln(x+1)        for λ = 0
x <  0 :  −(((−x+1)^(2−λ) − 1)/(2−λ)) for λ ≠ 2,    −ln(−x+1)      for λ = 2
```

It is used rather than Box-Cox because it is defined for negative values, which the percentage
impacts need. λ = 1 is the identity; λ = 0 is a log; λ below 0 compresses a long right tail hard.

## I.7 Step six — DURANT H2H

Same first three steps. Then:

```
4. Multiply each of the nine by its category weight (I.8).
   Turnovers carry weight 0 — that is *how* they are removed.
5. Drop the lowest of the remaining eight weighted values.
6. DURANT H2H = the arithmetic mean of the seven that survive.
```

So DURANT H2H is not "DURANT minus turnovers". It is a differently weighted metric that also
drops turnovers, and it tilts noticeably toward scoring and rebounding.

## I.8 Every constant, in one place

Two kinds of number live here, and conflating them is the main way to go wrong.

**League constants — yours to set.**

| | Value used here | What it is |
|---|---|---|
| `Q` | 156 | Pool size: teams × roster spots |
| teams | 12 | Divisor for `Round` |

**Basketball Monster's fitted constants — one provider, one season, one projection source.**
These reproduce *their* published 2026-27 numbers from the Josh source. They are measurements,
not universal truths.

Yeo-Johnson λ per category:

| Category | λ | Category | λ |
|---|---|---|---|
| Points | +0.4151 | Blocks | **−1.6863** |
| Threes | +1.0166 | Turnovers | −0.1778 |
| Rebounds | −0.4381 | FG% impact | +0.1727 |
| Assists | +0.0065 | FT% impact | +1.5038 |
| Steals | −0.3513 | | |

Read that column as how badly each category needed fixing. **Blocks** get compressed hardest —
the most right-skewed category, and the thing DURANT exists to address. **Assists** land on
+0.0065, indistinguishable from a log. **Threes** land on +1.0166, indistinguishable from the
identity: DURANT leaves them alone because they were already near-normal, which is a useful sign
the fit is not just chasing curves. **FT% impact** is the only λ above 1, *expanding* rather than
compressing, because it is the one category skewed left.

DURANT H2H category weights:

| Points | Rebounds | Assists | Threes · Steals · Blocks · FG% · FT% | Turnovers |
|---|---|---|---|---|
| 1.00 | 0.94 | 0.75 | 0.60 each | **0.00** |

### Deriving your own λ, for a different season or projection set

The λ above are frozen to one snapshot. For your own projections, fit them.

The standard method is maximum likelihood: choose λ to maximise

```
−(n/2) · ln(variance of the transformed values) + (λ−1) · Σ sign(x)·ln(|x|+1)
```

over the pool, by golden-section search on λ ∈ [−4, 4].
[`fit_lambda`](../../scripts/bbm/bbm_reference.py) does this.

**It will not reproduce Basketball Monster's λ.** Fitted on the same pool, maximum likelihood
gives:

| | pts | 3PM | reb | ast | stl | blk | to |
|---|---|---|---|---|---|---|---|
| Maximum likelihood | +0.065 | +0.798 | −0.345 | −0.028 | −0.166 | **−1.380** | −0.301 |
| Basketball Monster | +0.415 | +1.017 | −0.438 | +0.007 | −0.351 | **−1.686** | −0.178 |

Every direction agrees — blocks most compressed, threes nearest the identity, assists nearest a
log — but the values do not. Their λ come from a different objective, a different pool, or hand
tuning; we could not determine which. **So: use their constants to reproduce their numbers, and
fit your own to apply the method.** Do not expect the two to agree.

## I.9 Punt weighting

Both Basketball Monster and our own board support punting a category by weight rather than
deleting it. The rule:

```
1. Multiply the punted category's standardised value by its weight w.
2. Re-derive the pool and re-standardise — Value changed, so pool membership changed.
3. Value = the mean of the nine.  The denominator stays 9.
```

Two consequences that surprise people.

**The denominator does not shrink.** Weighting a category to 0.5 does not renormalise the
average, so punting lowers everyone's `Value` rather than redistributing it.

**A punt is not local.** Because the pool re-derives, players with nothing to do with the punted
category move. Half-punting turnovers moves six players in or out of a 156-man pool and shifts
the field by about eight rank places on average.

## I.10 Worked example

An invented player, using the Basketball Monster constants from §I.8 so the arithmetic is
checkable. 70 games, 32.0 minutes, and this per-game line:

```
22.4 pts · 2.1 3PM · 7.5 reb · 4.8 ast · 1.2 stl · 0.9 blk · 2.6 TO
8.2 FGM on 17.4 FGA (.471)   3.9 FTM on 4.6 FTA (.848)
```

Points check: `2 × 8.2 + 2.1 + 3.9 = 22.4`. ✓

Pool constants (the recovered Josh 2026-27 set): pool means 17.01484 pts, 1.70472 3PM, 5.98620
reb, 3.89834 ast, 1.00745 stl, 0.70573 blk, 1.86440 TO; SDs 5.51789, 1.04527, 2.55316, 2.12316,
0.31981, 0.52317, 0.77879. Pool FG% .491810 with impact mean −0.000887 and SD 0.653027; pool FT%
.798766 with impact mean +0.002772 and SD 0.321948.

```
pV   = (22.40 − 17.01484) / 5.51789      = +0.97595  ->  +0.98
3V   = ( 2.10 −  1.70472) / 1.04527      = +0.37816  ->  +0.38
rV   = ( 7.50 −  5.98620) / 2.55316      = +0.59291  ->  +0.59
aV   = ( 4.80 −  3.89834) / 2.12316      = +0.42468  ->  +0.42
sV   = ( 1.20 −  1.00745) / 0.31981      = +0.60208  ->  +0.60
bV   = ( 0.90 −  0.70573) / 0.52317      = +0.37133  ->  +0.37
toV  = −(2.60 −  1.86440) / 0.77879      = −0.94454  ->  −0.94

fg%V  impact = 8.20 − 17.40 × 0.491810   = −0.35749
      z      = (−0.35749 − −0.000887) / 0.653027 = −0.54608  ->  −0.55
ft%V  impact = 3.90 −  4.60 × 0.798766   = +0.22568
      z      = (+0.22568 − +0.002772) / 0.321948 = +0.69236  ->  +0.69

sum   = +2.54684
Value = 2.54684 / 9 = +0.28298  ->  +0.28
```

Look at the two percentage lines, because they are the part everyone gets wrong. He shoots .471
from the field — below the pool's .4918 — on high volume, and is punished for it at −0.55. He
shoots .848 from the line, well above the pool's .7988, but on only 4.6 attempts, so he is
rewarded +0.69 rather than the +2 a raw-rate z-score would have handed him. That asymmetry is the
entire point of the volume weighting.

---

# Part II — Where the numbers come from

`Value` is **not a property of a player**. It is a property of the pair
**(a projected stat line, a pool)**. Change either and the number changes, without any of the
math in Part I changing at all.

This is the single most common source of confusion when two "Basketball Monster values" disagree,
and it applies equally to any two projection sets you might compare.

## II.1 A worked disagreement

Basketball Monster publishes two projection sources for the same season — internally, two
different people's forecasts. They run through *identical* math: same z-scores, same 156-player
pool, same volume-weighted percentages, same mean of nine. Verified in §IV.3.

For their top-ranked player the two sources give `Value` **1.44** and **1.22**. Here is the whole
of that −0.22, category by category:

| | pV | 3V | rV | aV | sV | bV | fg%V | ft%V | toV | sum | ÷9 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Δ | −0.08 | +0.28 | −0.05 | −0.28 | −0.08 | −0.15 | **−0.77** | **−0.57** | −0.28 | −1.98 | **−0.22** |

**Two thirds of the gap is the two percentage columns.** The second source projects him about
three points lower on field-goal percentage and two and a half lower on free-throw percentage.
Because percentage value is volume-weighted (§I.4) and he is a very high-volume shooter, a
2.8-point drop in FG% costs −0.77 in that column alone. Nothing else in the line moves anything
like as much — his rebounds change by four hundredths.

That is the general lesson, not a quirk of one player: **when two projection sets disagree about
a high-volume player, the percentage categories will usually dominate the difference**, because
they are the only two categories where the value scales with volume as well as with rate.

## II.2 The pool moves too

The second effect is easy to forget. The pool is the top *Q* by `Value`, so a different projection
set produces a **different pool**, and therefore different means and standard deviations for every
category. Every player is measured against a slightly different yardstick.

Across the 212 players common to both sources: mean rank movement is about **20 places**
(19.8–20.6 depending on tie-break), maximum 93–98, with roughly **130–140** moving ten or more.
Mean absolute `Value` difference 0.078.

Those rank figures are ranges on purpose. `Value` is published to two decimals and 140 of 230
players share theirs with somebody, so exact counts shift with how ties are broken; the ranges
span 40 random tie-breaks plus the source's own ordering, which is itself sorted by rank and so
understates movement.

## II.3 What follows

- **Never compare a value across projection sets** without saying which produced it. A 20-place
  average movement is larger than most methodology choices — larger, for instance, than DURANT's
  entire category-weighting decision.
- **Choosing your projections matters more than choosing your valuation.** If you are rebuilding
  this, the effort is better spent on the stat lines than on refining the last decimal of the
  math.
- **The percentage categories deserve the most scrutiny** in any projection set you adopt,
  because they carry the most leverage per unit of disagreement.

---

# Part III — What we could not determine

Findings, not procedures. Everything here is honest about its limits.

## III.1 DURANT's two percentage categories

The metric itself is solved: given the nine DURANT category values, both aggregates reproduce at
the rounding floor. Seven of the nine input columns rebuild from raw stats at MAE ≤ 0.013.

**The two percentage inputs do not.** `Dfg%V` reaches only MAE 0.0345 and `Dft%V` 0.0273 against
Yeo-Johnson applied to the §I.4 impact — and the tell is the Spearman, **0.9977 and 0.9980
rather than 1.0**. A monotone transform of the correct input would order players *identically*.
Something slightly different is being transformed.

Ruled out: the raw percentage (R² 0.83 / 0.72), and impact scaled by the square root of attempts
(R² 0.96 / 0.93). Both worse on every measure.

This is also where the metric's author says the method is unfinished — *"I actually haven't found
a way to do it yet"* — so the residual may reflect something ad hoc in the original rather than a
gap in the reconstruction.

**Practical effect:** if you are implementing Part I, your percentage columns will differ from
theirs by about 0.03 and your DURANT aggregate by about 0.008. Everything else is tighter.

## III.2 The pool's spread

The pool means recovered from their published columns agree with a top-156 pool to within 0.5%,
but the standard deviations run **1–3% wider**, and no subset of the projections reproduces both
moments at once.

Ruled out: a larger or smaller *Q* (no nested pool fits both — points wants N ≈ 159 for its mean
and 179 for its spread; steals 177 and 233), filtered-out players, a different selection basis,
sample vs population SD, and export quantisation. A 6,000-swap local search got the spreads right
only by pulling the means off.

**Standing hypothesis:** their constants come from a wider distribution than the current
projection set — realised production rather than projections. Projections are regressed toward
the mean and so are narrower than the outcomes they predict, and the size of the gap per category
tracks how predictable that category is: steals, the noisiest and most heavily shrunk, shows the
largest gap at 1.028; rebounds, the most persistent, shows none at 0.996. That ordering is what
shrinkage predicts.

**The experiment that settles it:** take a prior season's *actual* per-game statistics, form the
top 156 by that season's value, and compare its moments to the recovered constants.

**Practical effect:** none, if you derive your own pool from your own projections as Part I says.
This only matters if you are trying to match their exact constants.

## III.3 Columns that are judgement, not arithmetic

Three of their columns look computed and are not. Each was tested properly and each failed.

**Drafting confidence** — an integer 1–10. The natural hypothesis is that it measures how much
their metrics disagree about a player. It does not:

| Feature | Correlation |
|---|---|
| Value level, as a control | +0.223 |
| \|Value − DURANT\| | +0.162 |
| \|source A rank − source B rank\| | −0.131 |
| \|source A Value − source B Value\| | **−0.074** |
| \|DURANT − DURANT H2H\| | +0.023 |

The disagreement measures are the weakest entries and several carry the wrong sign. Categorical
structure explains almost nothing (best single grouping η² = 0.120). A regression tree over 54
features scored by 5-fold cross-validation reaches out-of-sample R² of **+0.027 at depth 2** and
goes *negative* deeper, while in-sample climbs to +0.489 — memorisation, not signal. A
cross-validated linear model over the same features: in-sample +0.378, **out-of-sample −0.391**,
worse than predicting the mean.

**Frustration value** — cross-validated in-sample R² +0.565 but **out-of-sample +0.106**. About a
tenth of it is recoverable (the surviving part is availability); nine tenths is not. Almost
certainly built from game logs, which a season projection does not contain.

**Tier** — not computed from value at all: in 18 of 34 position-tier groups the within-tier
numbering disagrees with the value order, so a `#2` outranks its own `#1`. Hand-curated.

> **Method note.** An earlier version of this document reported in-sample R² for the first two and
> called them unreproducible on that basis. In-sample R² for a many-parameter model on ~200 rows
> only rises as features are added and cannot separate signal from memorisation. The
> cross-validated figures above replace it. Protocol: 5-fold, fixed permutation seeded with
> `numpy.default_rng(0)`, ridge at λ = 1e-3, CART with minimum leaf 8, out-of-sample R² pooled
> across held-out folds. Negative means worse than the mean.

## III.4 Usage rate

The standard possession formula:

```
USG% = 100 × (FGA + 0.44×FTA + TO) × (TeamMinutes/5)
            / (Minutes × (TeamFGA + 0.44×TeamFTA + TeamTO))
```

Structurally confirmed — everything after the player's own `(FGA + 0.44×FTA + TO)/Minutes` behaves
as a single team-level constant, with a within-team SD of 0.00065 against 0.00882 between teams.
Reproducing it to the decimal needs team totals over every player on each roster, which a
fantasy-relevant subset does not provide.

---

# Part IV — Validating against Basketball Monster

**Optional, and needs a subscription.** Nothing in Parts I–III depends on this. It is here so
that while access lasts you can check an implementation of Part I against the numbers it is
modelled on — and so a future reader knows exactly how the constants in §I.8 were obtained.

## IV.1 Getting the two exports

Both come from `projections.aspx`, and **both follow whichever `Projection Source` is selected**,
so set that first and record it.

| Export | Settings | Gives you |
|---|---|---|
| **Totals** | `Stats Display Format` = Total Stats, `Filters` = All Players → `Export to CSV` | Season totals, every player — the Part I input |
| **Rendered** | `Stats Display Format` = Per Game Stats → `Export to CSV` | The published `Value`, `Rank` and nine category columns — the check |

Column layouts differ between them; `from_components` and `from_totals_with_percentages` in
[`bbm_reference.py`](../../scripts/bbm/bbm_reference.py) map both onto the §I.1 contract.

Their DURANT columns are off by default: `Edit Display and Value Columns` → search `durant` →
tick `DURANT`, `DURANT Category Values`, `DURANT H2H`, `DURANT H2H Category Values`. Use **Save**,
not just Apply — Apply is lost on reload. `Minus 1 Value` in the same picker publishes the
worst-category-removed metric directly.

Punt weights live behind `Punt Settings`: nine numeric inputs, `min=0`, `step=0.01`. **A weight of
`0` is read as blank and silently does nothing** — use a small non-zero value for a hard punt.

## IV.2 Parsing traps

- The rendered table **repeats its header** every so often: a 234-player export arrives as 254
  rows. Filter on `Rank` matching `^\d+$`.
- Totals are **comma-formatted** (`2,108.0`). Strip commas or large totals silently fail to parse.
- The totals export gives **percentages, not makes**. Rebuild with `fg% × fga`.
- **Everything is quantised.** Their internal projections are fractional and every export rounds.
  Recovering makes from a displayed percentage times exported attempts leaves a median gap of
  0.29 — exactly the budget from rounding makes, attempts and the percentage.
- Join on **player id**, never on name. In the rendered table it is the `i=` parameter of each
  player link.
- DURANT aggregates are **composite strings**: `1.18#2to` is value 1.18, rank 2, dropped category
  turnovers. The token for three-pointers is a bare `3` that runs into the rank, so `0.99#23` is
  *rank 2, threes* — parse with a **non-greedy** rank group and sanity-check that recovered ranks
  have no value-versus-rank inversions.

## IV.3 Measured accuracy

[`bbm_reference.py`](../../scripts/bbm/bbm_reference.py), run against both sources through the
Part I procedure — same code, the only difference being which source produced the files:

| | Bar | Source A | Source B |
|---|---|---|---|
| Each category value linear in its raw per-game stat | R² ≥ 0.9998 | 0.99981–0.99999 | 0.99983–0.99999 |
| `Value` = mean of the nine | MAE ≤ 0.010 | 0.0075 | 0.0050 |
| Rank correlation | Spearman ≥ 0.999 | 0.99942 | 0.99968 |
| Maximum rank displacement | ≤ 10 | 8 | 6 |
| Pool size reaching unit variance | — | 156 | 156 |

DURANT, using their λ from §I.8: `DURANT` MAE **0.0083**, Spearman 0.99902; `DURANT H2H` MAE
**0.0079**, Spearman 0.99919.

The residual is export quantisation plus the two open items in Part III, and it is largest exactly
where it should be — steals and free-throw makes, the smallest totals, where losing half a unit
costs most in relative terms.

**If your implementation lands near these figures, it is right. If `Value` MAE is near 0.10 rather
than 0.008, check the H2H weight vector and the attempt-weighted pool rate first** — those are the
two mistakes that produce roughly that error.

## IV.4 Confirming the minus-one rule

Their DURANT columns name the dropped category, which turns the hardest part of the
reconstruction into a read rather than an inference. Measured across 234 players:

| Claim | Result |
|---|---|
| The named category is that player's minimum | **234 / 234** |
| `DURANT` = unweighted mean of the eight survivors | MAE 0.0025 |
| `DURANT H2H` never drops turnovers | **0 of 234** |
| `DURANT H2H` = mean of the seven survivors, weighted | MAE 0.0025 |
| Its named category is the minimum of the remaining eight | **234 / 234** |

The H2H weight vector in §I.8 was recovered by regressing each `DH*V` column on its `D*V`
counterpart: every slope within 0.0005 of a round value, every intercept below 0.0005, R² ≥
0.99996. Rebuilding H2H with **equal** weights instead gives MAE 0.0963 — 38× worse, and the
signature of getting that vector wrong.

---

# Part V — Cheat sheet

The whole thing in plain language. No formulas.

### What the numbers mean

Every category column answers one question: **how much better than a typical drafted player is
this guy, in this one stat?** Zero is average, positive is better. The unit is "standard
deviations" — statistician for *how unusual is this, given how spread out the category normally
is*.

That last part is why you cannot just compare raw stats. Three rebounds a game above average is
common; three steals a game above average has never happened. Dividing by the category's normal
spread puts them on one scale, so +1.5 means the same thing in every column.

`Value` is the average of those nine numbers. That is the entire ranking.

### Why "a typical drafted player"

The comparison group is the top 156 — twelve teams times thirteen spots, everyone who gets
drafted. Comparing against all 500-odd players in the league would make almost every draftable
player look above average and squash the differences that matter.

**If your league is not 12×13, this number changes and so does every value.** A smaller league
means a tougher comparison group and lower numbers for everyone.

### Why turnovers have a minus sign

They are the only category you want *less* of, so the sign is flipped. That way adding up all nine
works without special cases.

### Why shooting percentages are handled differently

This is the part everyone gets wrong.

A player shooting 90% from the line on two attempts and one shooting 90% on twelve are not equally
valuable — the second actually moves your team's percentage. Score the percentage alone and they
look identical.

So instead of scoring the percentage, you score **how many extra makes you get compared to an
average shooter taking the same number of shots**. Shoot exactly average and you score zero no
matter the volume. Shoot above average and the more you shoot the more you help. Shoot below
average on high volume and you actively hurt — which is why a high-usage, poor-percentage scorer
gets punished here in a way raw percentage never shows.

### Why two projection sets disagree

Because `Value` describes a *stat line*, not a player. Feed in different projections and you get
different values — and the pool changes too, so everyone is measured against a slightly different
yardstick.

When two sets disagree about a high-volume player, it is usually the **shooting percentages**
doing it, for the reason just above: they are the only categories where value scales with volume
as well as rate. A three-point difference of opinion on field-goal percentage can swing a
high-volume scorer more than every counting stat combined.

Practical consequence: **worry about your projections before you worry about your math.**

### What DURANT does differently

Two things.

**It squashes the freaks.** Some categories have a long tail — a handful of players block shots at
rates nobody approaches. A plain z-score hands them an enormous number in one column, which drags
their overall rank up more than it should. DURANT bends each category's scale so the extreme top
gets pulled back. Blocks get squashed hardest; three-pointers are left alone entirely because they
were already well behaved.

**It forgives each player their worst category.** Everyone's single weakest category is thrown out
and DURANT averages the remaining eight. A big man who cannot shoot free throws simply stops being
penalised for it.

`DURANT H2H` goes further: it throws out turnovers for *everybody*, then throws out your worst of
what is left, and averages seven. It also **counts the categories unequally** — steals, blocks,
threes and both percentages count 60% of what a point of scoring counts, rebounds 94%, assists
75%. So it is a noticeably more scoring-and-rebounding-led ranking, not just "DURANT without
turnovers".

That second rule is why DURANT flatters specialists: it assumes you will punt whatever each player
is bad at. A real strategy — but it decides it for you, player by player, rather than letting you
pick one build and stick to it.

### The three mistakes to avoid

1. **Made field goals already include threes.** Points are two per field goal plus one extra per
   three, plus free throws. Count threes twice and every shooter is wrong.
2. **The pool's shooting percentage is weighted by attempts**, not the average of everyone's
   percentage. Those differ by about seven tenths of a point — enough to move players.
3. **Nothing here accounts for availability.** These are per-game numbers throughout. A player
   projected for 44 games and one projected for 73 are rated identically. That judgement is yours
   to add, and our own board adds it separately.

---

# Sources

**Basketball Monster.** Exports taken 2026-08-30 with a member account: season totals and the
rendered table, under both projection sources, plus two punt-weighted variants. Column tooltips on
the Player Rankings and Trade Analysis pages are public and carry the DURANT definitions; their
account of the minus-one rule is confirmed against data in §IV.4.

**Josh Lloyd, in his own voice**, on Locked On Fantasy Basketball and his own channel — 2 Sep 2023
(the origin episode: the acronym, the FT% findings, the refusal to publish the formula), 22 Jul
2025 (the component list), 22 Apr 2026 (names Yeo-Johnson, "per game metric", the replacement-level
omission). Transcripts are YouTube auto-captions, so proper nouns are mangled; the numbers and the
acronym read cleanly and recur across episodes. Full citations, URLs and the published
rank-movement sets are on branch `bbm` in `docs/references/basketball-monster-durant.md`.

**DURANT** stands for "Dynamic Unbiased Rankings Applying Normalised Transformations", confirmed
in Lloyd's own voice on three occasions. The coefficients are deliberately unpublished, and no
third-party replication existed before this one.

**Basketball Monster article 1831**, *Welcome*, 15 Aug 2022 — the only one still public, and the
source for Lloyd's pre-DURANT manual weights (threes, steals and blocks at 0.8, turnovers punted).
The shape survives into the H2H weights of §I.8; the values do not.

**Rosenof**, [2307.02188](https://arxiv.org/abs/2307.02188) (G-score) and
[2409.09884](https://arxiv.org/abs/2409.09884) (H-scoring). The latter cites Lloyd's 2023 podcast
for the heavy-tailed-blocks premise and declines to act on it, resting on the central limit
theorem: categories are won by 13-man team totals, which are near-normal however skewed the
individuals are. That argument is untouched by a successful reconstruction, and adopting any of
DURANT would need its own ADR.

**In this repo:** [ADR-0012](../decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md)
on the percentage denominator — the same volume-weighted construction as §I.4, arrived at
independently; [ADR-0009](../decisions/ADR-0009-soft-punt-weighting.md) on soft punting, the same
shape as §I.9 except that we do not re-standardise the pool;
[ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md) on why no data appears above;
and the [draft playbook](fantasy-basketball-draft-playbook.md) and
[quant-vs-expert reconciliation](quant-vs-expert-reconciliation.md) for how our own valuation
compares.
