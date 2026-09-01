# Basketball Monster's valuation, reverse-engineered

**This is a specification, not a scraping guide.** Part I is everything you need to compute
Basketball Monster's numbers yourself, from any set of projections, with no Basketball Monster
account and no export file. Read it as the algorithm; the provider is incidental.

A working implementation of Part I is committed at
[`scripts/bbm/bbm_reference.py`](../../scripts/bbm/bbm_reference.py) — standard library only,
tested, and measured against their published columns in Part IV.

## The four values, at a glance

Basketball Monster publishes four different values over the same projections. They share the
per-game inputs of §I.1–I.2 and diverge after that.

| Value | What it is | How to reproduce | When to use it |
|---|---|---|---|
| **`Value`**<br>plain z-score | Each category z-scored against the pool, turnovers inverted, then the **mean of the nine**. | §I.3–I.5. No transform, no weights, all nine equal. | The industry baseline — *"Z-scores have been the basis of fantasy category rankings forever. Not just here, but Yahoo and ESPN's player rater also use Z-scores."* Not what Lloyd recommends for category leagues. |
| **`Minus 1 Value`** | The same nine, with each player's **single worst category dropped**, averaged over eight. | §I.3–I.5, then drop the minimum and divide by 8. | *"I firmly believe that in order to properly evaluate a player's head-to-head value, you need to remove their worst category."* |
| **`DURANT`** | Yeo-Johnson transform per category → standardise → drop the worst → mean of eight. All nine weighted equally. | §I.6. Needs the λ table in §I.8. | **Roto category leagues.** *"Roto requires you to accumulate value across the full set of selected categories over the entire season, so the standard DURANT calculation is better suited to that format."* |
| **`DURANT H2H`** | DURANT **plus fixed category weights**, turnovers weighted to zero, then drop the worst of the rest → mean of seven. | §I.7. Needs the λ table **and** the weight vector, both in §I.8. | **Head-to-head category leagues — this league.** *"DURANT H2H is specifically designed for head-to-head category leagues."* |

**Lloyd's recommendation, in his own words** (article 2310, 14 Aug 2026):

> "My general recommendation is simple: Use DURANT for roto category leagues. Use DURANT H2H for
> head-to-head category leagues. Use your league's customised fantasy-points calculation for points
> leagues."

With the caveat attached in the same article:

> "This does not mean you should blindly draft from the DURANT H2H order. It also does not mean the
> system has automatically created the correct punt build for your particular team."

Only `DURANT H2H` weights the categories. Only `DURANT H2H` removes two — turnovers always, plus
each player's worst of the remaining eight. §I.11 carries the author's full reasoning.

---

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

Written 2026-08-30 on branch `durant-actual`. **This is now what the draft board runs on** (ADR-0015). It was research when written.

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

Everything from here on is per game. **There is no availability term anywhere in this method** — a
player projected for 44 games and one projected for 73 produce values from the same arithmetic.
That is by design and worth knowing when you read the output; it is not an omission in this
document. §V covers what it means in practice.

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

Unlike the λ, **these are published** — Basketball Monster lists them in
[article 1957](https://basketballmonster.com/article.aspx?article=1957), and they match the values
recovered here by regression (1.0000, 0.9400, 0.7504, 0.5996–0.6002, 0.0000) to four decimals. The
two were arrived at independently, so each confirms the other. §I.11 gives the author's account of
how they were chosen: *"Factors considered when assigning weights include game-to-game variance and
year-to-year consistency."*

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
log — but the values do not. Maximum likelihood is therefore not the objective Basketball Monster
fitted to; what they used is not published, and we could not recover it. **So: use their constants
to reproduce their numbers, and fit your own to apply the method to a different pool.** Do not
expect the two to agree.

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

## I.11 The author's own account

The specification above says *what* the arithmetic does. This section says *why*, in Josh Lloyd's
words, from two Basketball Monster articles. Both are member-gated.

- **[Article 2310](https://basketballmonster.com/article.aspx?article=2310)**, *Welcome to a new
  season at Basketball Monster*, **14 Aug 2026** — the current guidance. Says which value to use
  for which format.
- **[Article 1957](https://basketballmonster.com/article.aspx?article=1957)**, *DURANT 2.0 &
  DURANT H2H*, 27 Aug 2026 but marked **"REPUBLISHED FROM 2024"**, with the original DURANT article
  appended below the update — the fullest account of the *reasoning*, and the source of the weight
  vector.

**Where they differ, 2310 is the newer word.** 1957 calls DURANT H2H *"a supplementary tool"* and
says DURANT *"isn't something I would base all of my fantasy decisions on"*; that is the 2023–24
stance. By 2026 the recommendation is direct and format-specific — see *Which one to use* below.

### Which one to use

> "My general recommendation is simple: Use DURANT for roto category leagues. Use DURANT H2H for
> head-to-head category leagues. Use your league's customised fantasy-points calculation for points
> leagues."

On the roto case: *"Roto requires you to accumulate value across the full set of selected categories
over the entire season, so the standard DURANT calculation is better suited to that format."*

On the H2H case: *"DURANT H2H is specifically designed for head-to-head category leagues… It is a
stronger starting point for head-to-head leagues because it removes turnovers, accounts for the
different behaviour of each category and recognises that you do not need to dominate every category
to win a weekly matchup."*

And on what it is not:

> "This does not mean you should blindly draft from the DURANT H2H order. It also does not mean the
> system has automatically created the correct punt build for your particular team."

> "Overall value is a guide, not a draft list… The numerical gap between two players may be
> extremely small. One player might be ranked 15 spots higher because of a fraction of a steal, a
> slight field-goal percentage difference or one category that does not fit your team. Look at the
> categories. Look at your build. Look at what becomes difficult to find later in the draft. The
> overall number is useful, but the individual statistical profile is usually more important."

He also confirms DURANT is not editorialised: *"It is still based entirely on our projections. It is
not a separate set of hand rankings or an adjustment based on whether we like a player."*

### Per game or totals

Neither DURANT variant carries an availability term (§I.2), and that is a display choice on their
side rather than an omission:

> "Per-game rankings show how valuable a player is whenever he plays. Total rankings combine that
> production with projected games played. If you want injuries and expected absences incorporated
> directly into the order, switch to Totals. If you want to compare players based on their nightly
> production, use Per Game."

> "Games played is also the least predictable part of any projection. I produce our games-played
> estimates, but I do not personally draft straight from total-value rankings."

### Projected minutes are deliberately inflated

Important if you build anything on their projections, and easy to mistake for an error:

> "You may also notice that a team's projected minutes add up to more than 240 per game. That is
> intentional. We include approximately 5 to 10 per cent additional playing time to account for
> injuries, absences and the reality that the same rotation will not remain healthy for the entire
> season."

So team minutes will not sum to 240, bench players carry more minutes than a healthy opening-night
rotation would give them, and any per-minute work built on these numbers inherits that 5–10%
padding.

### Where the transform came from

The origin was a single number that did not sit right — a blocks z-score of 4.64:

> "a Z-score of 4.64 is such a vast outlier that the implied probability of finding a number that
> significant in a normal sample was close to 1 in 500,000. That can't be right, I thought
> especially when there were four other players with block Z-scores that put them at a probability
> of occurring of at best 1 in 1,400."

The diagnosis:

> "That probability assumes a normal distribution—a bell curve. So, I looked at NBA stats. None of
> them are distributed normally. There is no bell curve for blocks or any NBA stat. Blocks, and all
> NBA stats, except free throw percentage, are heavily right-skewed."

And the consequence he had already been seeing subjectively:

> "weird steals and blocks numbers would often push players higher up the ranking than it felt like
> they should, while poor free throw percentage and field goal percentage players may be punished
> too much."

Which is why free-throw percentage is the one category whose recovered λ is **above** 1 in §I.8:
it is the one skewed the other way.

**The transform changed between versions.** The original article describes **Box-Cox**; the 2.0
update describes the **Yeo-Johnson** transformation, chosen because it *"is capable of handling
negative and zero values, which is crucial for basketball statistics that often include zeros
(e.g., blocks, steals) and negative impacts (e.g., shooting percentages)."* The fit in §I.8
confirms Yeo-Johnson. Anyone implementing from the older text would use the wrong family.

His stated aims for it: *"Reducing the Impact of Outliers"*, *"Improving Predictive Accuracy"*,
*"Enhancing Consistency"*.

### Why the minus-one rule

> "DURANT H2H uses the minus 1 approach, which removes a player's worst category from their
> evaluation. This reflects the common H2H strategy of punting, where managers intentionally
> disregard one or more categories to strengthen their team in others."

Stated benefits: it *"Aligns with Punting Strategies"* and *"Enhances Player Value Recognition"* by
focusing on a player's strengths. And from the original article:

> "I firmly believe that in order to properly evaluate a player's head-to-head value, you need to
> remove their worst category. I also believe in not including turnovers."

(The article follows that with a named example — a low-usage guard finishing far above a superstar
in turnover-inclusive category rankings. The players and their ranks are omitted here under
[ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md).)

### Why the categories are weighted

> "In H2H leagues, not all statistical categories impact weekly matchups equally. Weighting
> categories allows managers to align strategies with their team's strengths and mitigate
> variance."

And the basis for the specific values in §I.8:

> "Factors considered when assigning weights include game-to-game variance and year-to-year
> consistency."

### Why turnovers are excluded entirely

Three reasons, given directly:

> "Turnovers correlate closely with high-usage stats like points and assists. They also have high
> variance and are influenced by streaming strategies in H2H leagues."

With the intended effects: *"Avoid Penalizing High-Usage Players"* — high-turnover players central
to their team's offence *"aren't unfairly downgraded"* — plus *"Simplify Roster Management"* and
*"Reflect H2H Dynamics"* — *"Turnovers become less indicative of a player's value in a
streaming-heavy format."*

### How his own framing changed

Worth reading in order, because the tone shifted between the two articles.

**2023–24 (article 1957), when DURANT was new** — a second lens, held tentatively:

> "I don't know how successful DURANT will be in determining the most valuable players in fantasy.
> That's what this season is for… It isn't something I would base all of my fantasy decisions on,
> but I would pay attention to the guys that rank much higher or lower in DURANT and see if maybe
> there is a hidden angle there."

> "I think after draft day, DURANT can give us a better representation of the actual impact players
> are having."

And for the H2H variant: *"Consider using DURANT H2H as a supplementary tool for assessing player
value during drafts."*

**2026 (article 2310)** — a direct recommendation by format, quoted under *Which one to use* above.
DURANT H2H is no longer "supplementary" but *"a stronger starting point for head-to-head leagues"*.

The caution that survives both is about how the number is applied, not whether to trust the method:
overall value is a guide, not a draft list. And from 1957, a limit on the whole enterprise:
*"we will never get an exact ranking system for category leagues; there are too many variables
involved."*

### One note for anyone implementing from the article

The appended original section describes the standardisation sample as:

> "I used a sample of all NBA players, not your league sample… So, overall values for DURANT are
> higher because of the larger sample."

The 2026-27 columns behave differently: the nine `D*V` columns sit at mean ≈ 0 and SD ≈ 1 over the
top 150 by `DURANT`, drifting to −0.49 by rank 234 — that is, standardised on the league pool, the
same as `Value`. The aggregate *is* higher than `Value` as the article says (+0.18 on the top 156),
but that follows from the minus-one rule: dropping each player's worst category raises their
average.

Given that section is republished from 2024 and the transform itself demonstrably changed between
versions, read this as the implementation having moved on. It is recorded here only because
following the older text would put the pool in the wrong place. §I.3 is what the current data does.

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

The second rule is deliberate, and mirrors how category leagues are actually played. In the
author's words, it *"reflects the common H2H strategy of punting, where managers intentionally
disregard one or more categories to strengthen their team in others."* Turnovers come out of the
H2H version for their own stated reasons: they track high-usage stats like points and assists, they
swing hard week to week, and they are distorted by streaming.

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
in Lloyd's own voice on three occasions and in article 1957. The **H2H category weights are
published** there; the **Yeo-Johnson λ are not**, and no third-party replication of them existed
before this one.

**Basketball Monster article 2310**, *Welcome to a new season at Basketball Monster*, Josh Lloyd,
14 Aug 2026. Member-gated. The **current** first-party guidance: which value to use for which league
format, the per-game versus totals choice, the deliberate 5–10% minutes overage, and a second
independent publication of the H2H weight vector. Where it and 1957 differ, this is the newer word.

**Basketball Monster article 1957**, *DURANT 2.0 & DURANT H2H*, Josh Lloyd, published 27 Aug 2026
and marked "REPUBLISHED FROM 2024", with the original DURANT article appended below the update.
Member-gated. The fullest account of *why* the method is built the way it is, and the first
publication of the H2H weight vector. Its usage guidance is the 2023–24 stance, superseded by 2310.

**Basketball Monster article 2185**, *Welcome To Basketball Monster 2025/26*, Josh Lloyd,
14 Aug 2025. Member-gated. The 2025 predecessor of 2310, and the first to say *"Use DURANT (or
DURANT H2H) for category leagues."*

**Basketball Monster article 1831**, *Welcome*, 15 Aug 2022 — the only one still public, and the
source for Lloyd's pre-DURANT manual weights (threes, steals and blocks at 0.8, turnovers punted).
The shape survives into the H2H weights of §I.8; the values do not.

**Rosenof**, [2307.02188](https://arxiv.org/abs/2307.02188) (G-score) and
[2409.09884](https://arxiv.org/abs/2409.09884) (H-scoring). The latter cites Lloyd's 2023 podcast
by name for the heavy-tailed-blocks premise — independent confirmation of when that argument was
first made publicly. Relevant background for anyone comparing this method against our own board's
G-score layer.

**In this repo:** [ADR-0012](../decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md)
on the percentage denominator — the same volume-weighted construction as §I.4, arrived at
independently; [ADR-0009](../decisions/ADR-0009-soft-punt-weighting.md) on soft punting, the same
shape as §I.9 except that we do not re-standardise the pool;
[ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md) on why no data appears above;
and the [draft playbook](fantasy-basketball-draft-playbook.md) and
[quant-vs-expert reconciliation](quant-vs-expert-reconciliation.md) for how our own valuation
compares.
