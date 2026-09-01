# Category Tracker on z-scores: deriving the thresholds

## Status

**Implemented on the `draft-refactoring` branch**, under
[ADR-0018](../decisions/ADR-0018-tracker-on-durant-basis.md), with one correction the
derivation below did not anticipate — see §5a.

Two things changed between this research and its implementation. The tracker is fed
**DURANT H2H category values** rather than the plain z this document assumes, which
requires the basis correction in §5a. And the **turnovers row is gone**: DURANT H2H prices
turnovers at zero, so a DH turnover column is identically 0.0 for every player and cannot
be thresholded. Eight rows, not nine.

Everything else below stands as written: the derivation in §2, the `k` constants in §4,
the percentage basis correction in §5, the win-rate targets in §6, and the five read states
in §7.

Original scope note, preserved: the Category Tracker tab and its Settings constants. The
valuation itself and the Draft Board ranking were untouched by *this* document — they moved
separately, under ADR-0015.

---

## 1. What exists today, and why it cannot survive the move

The tracker compares raw units. `My team` is a sum of per-game counting stats, or a
volume-weighted rate for FG% and FT%. `Average team` is the same quantity for a
draft-scaled benchmark. `Edge` is the difference, and `Read` thresholds that difference
against one of three bands on Settings:

| Setting | Value | Applies to |
|---|---|---|
| `TRACK_FG_BAND` | 0.005 | FG% only, absolute rate units |
| `TRACK_FT_BAND` | 0.010 | FT% only, absolute rate units |
| `TRACK_COUNT_BAND` | 8% | the seven counting rows, as a share of the benchmark |

Three bands, because raw units cannot share one. That is the whole reason for the split,
and the split was forced by a real failure. Two findings produced the current shape:

**F3** ([2026-08-27 review](../reviews/2026-08-27-draft-board-methodology-review.md)). One
8%-of-benchmark rule applied to all nine rows. On a counting total, 8% is an achievable
edge. On a rate, the benchmark *is* the rate, so 8% means 3.8 points of team FG% and 6.2
points of team FT%. No twelve-team roster spreads that far, so both rate rows read EVEN in
round 3 and still read EVEN in round 13. The two categories where a 9-cat roster most often
falls apart quietly were the two the indicator could not see. The fix was the two absolute
rate bands above, adopted from the review's own stated guess.

**F4** (same review). The benchmark was the whole 156-player pool mean. After five rounds
every manager holds five players and those sixty are the best sixty on the board, not sixty
drawn at random, so the target was far too low and every counting row read STRONG through
round ten. The fix scaled the benchmark with the draft: `AdjRank <= TEAMS * COUNTIF(Mine)`.
That fix is correct and this document preserves it.

Both fixes work. Neither is calibrated. The Settings note says so, and so does the
playbook's uncalibrated-items table: *"Mine, and explicitly uncalibrated. Starting guesses
pending a season of real standings."*

**Moving to z removes the reason the three bands exist.** A z-score has already been
divided by its own category's spread, so FG% and PTS land on one scale for the first time.
The open question is what number to put on that scale. The rest of this document argues it
does not have to be a fourth guess.

---

## 2. The derivation

### 2.1 The model

Rosenof models a head-to-head category as a normal differential between two teams
([2307.02188](https://arxiv.org/abs/2307.02188), §3.3 and appendix). His published form
fixes **one** player and randomises the rest, because he is pricing a single draft pick:

```
D ~ N( μ − μ(p),  (2N−1)·σ²  +  2N·τ² )
```

where σ is the spread of season averages across the player pool and τ is the
root-mean-square of players' week-to-week standard deviations.

The tracker asks a different question. It knows the whole roster. So the model has to be
re-run with **every one of my players fixed and the opponent random**:

```
T_me    n known players    mean Σ μ(q)      weekly variance  n·τ²
T_opp   n random players   mean n·μ         variance         n·(σ² + τ²)

Var(D) = n·σ² + 2n·τ² = n·(σ² + 2τ²)
```

*Cross-check.* Running the same algebra with one fixed player and `N−1` random ones gives
`(N−1)(σ²+τ²) + τ²` for team A plus `N(σ²+τ²)` for team B, which is
`(2N−1)σ² + 2Nτ²`. That reproduces the paper exactly, which confirms the setup.

### 2.2 The result

Substituting the per-player z-score, `z_q = (μ(q) − μ)/σ`, the σ cancels:

```
                      ⎛  Σ z_q       1           ⎞
P(win category c) = Φ ⎜ ────────  ·  ─────────── ⎟  =  Φ( Z_team · k_c )
                      ⎝   √n        √(1 + 2r_c)  ⎠

    Z_team = Σ z_q / √n        the standardized team edge
    r_c    = τ_c² / σ_c²       the category's noise ratio
    k_c    = 1/√(1 + 2r_c)     converts team z to win probability
```

Two things fall out of this that are worth stating plainly.

The `√n` is what makes the scale hold at any roster size. Team totals are sums, and the
spread of a sum of n draws grows as `√n`, so dividing by it gives a number that means the
same thing in round 2 and round 13. The current tracker achieves the same property by
moving its benchmark; this achieves it by construction.

`k_c` is the entire content of the threshold problem. It says how much of a paper edge
survives a single week. Everything below is the work of getting it right.

*Attribution.* The model, the variance components, and the normal approximation are
Rosenof's. The whole-roster form and the `Z_team = Σz/√n` framing are derived here, in his
model, and are not in the paper.

---

## 3. `k` is not the board's G-multiplier

This is the trap, and it is worth a section because the two quantities look
interchangeable and are not.

```
g_c = 1 / √(1 + κ·r_c)      κ = 2N/(2N−1) ≈ 1.04     what the board uses
k_c = 1 / √(1 + 2·r_c)                               what the tracker needs
```

The factor differs because the two answer different questions. `g` prices one marginal
player against a field that is otherwise random, so it carries one player's worth of extra
weekly noise. `k` prices a whole known roster against a whole random one, so it carries
**two** rosters' worth. Reusing the board's g columns in the tracker overstates win
probability by four to five points across the range that matters.

A second, larger trap sits on top of it: the board's `MULT_*` constants are **normalized to
assists** (`AST 1.00, STL 0.59`), not Rosenof's raw fractions (`AST 75%, STL 44%`).
Normalizing is harmless for ranking, since it scales every player's total by the same
constant. It is meaningless for probability. Anyone reaching for `MULT_STL = 0.59` as a
win-probability multiplier is off by a factor of 1.8 before the `g` versus `k` error even
applies.

**The tracker gets its own nine constants, derived from Table 8's raw variance components
rather than from any rounded multiplier.**

---

## 4. The nine constants

Rosenof's Table 8 publishes σ² and τ² directly, computed on the 2022-23 season with Q set
to the top 156 players by base Z-score. Deriving `r` from those raw numbers avoids
compounding the rounding in the published percentages.

| Category | σ² | τ² | r = τ²/σ² | **k** |
|---|---|---|---|---|
| Assists | 41.87 | 31.55 | 0.754 | **0.632** |
| Threes | 9.52 | 9.04 | 0.950 | **0.587** |
| Rebounds | 52.01 | 57.55 | 1.107 | **0.558** |
| Blocks | 2.35 | 2.70 | 1.149 | **0.551** |
| Points | 325.52 | 448.32 | 1.377 | **0.516** |
| Turnovers | 5.45 | 8.85 | 1.624 | **0.485** |
| Free Throw % | 0.009 | 0.018 | 1.800 † | **0.466** |
| Field Goal % | 0.003 | 0.007 | 3.748 † | **0.343** |
| Steals | 1.01 | 4.20 | 4.158 | **0.328** |

† The two percentage rows carry a basis correction. Section 5 derives it.

### The z threshold at each candidate win rate

`Z* = Φ⁻¹(p) / k_c`.

| Category | k | 60% | **65%** | 70% | **75%** |
|---|---|---|---|---|---|
| AST | 0.632 | 0.40 | **0.61** | 0.83 | **1.07** |
| 3PM | 0.587 | 0.43 | **0.66** | 0.89 | **1.15** |
| REB | 0.558 | 0.45 | **0.69** | 0.94 | **1.21** |
| BLK | 0.551 | 0.46 | **0.70** | 0.95 | **1.22** |
| PTS | 0.516 | 0.49 | **0.75** | 1.02 | **1.31** |
| TO | 0.485 | 0.52 | **0.79** | 1.08 | **1.39** |
| FT% | 0.466 | 0.54 | **0.83** | 1.13 | **1.45** |
| FG% | 0.343 | 0.74 | **1.12** | 1.53 | **1.97** |
| STL | 0.328 | 0.77 | **1.18** | 1.60 | **2.06** |

### What the spread buys

The instinct on a z scale is a single band at 1.00 SD, which is what the Category profile
column already uses for individual players. Applied to team z, one band would mean this:

| At Z_team = 1.00 | Win probability |
|---|---|
| Assists | 73.6% |
| Threes | 72.1% |
| Rebounds | 71.2% |
| Blocks | 70.9% |
| Points | 69.7% |
| Turnovers | 68.6% |
| Free Throw % | 67.9% |
| Field Goal % | 63.4% |
| Steals | 62.9% |

The same word covering an eleven-point spread in what it means. Steals needs nearly
**twice** the team z that assists does to be worth the same, and at 75% steals is
effectively unbankable: 2.06 team standard deviations is a roster nobody assembles by
accident. That is the correct answer and a useful one. It is also the same finding the
board already acts on in valuation, arriving from the other direction.

---

## 5. The percentage categories need a basis correction

Rosenof defines `σ_R` as the spread of players' raw success **rates**, while his `τ_R` is
already volume-weighted. The board's `z FG%` divides by the SD of the **impact** column,
settled in [ADR-0012](../decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md)
after measuring both. So `r` for the two percentage rows is computed on a mixed basis and
has to be moved onto the board's before it can be used.

The board already prints the conversion. From the live pool, recorded in ADR-0012 and in
the playbook:

| | SD of impact | SD of rate | ratio |
|---|---|---|---|
| FG% | 0.0489 | 0.0619 | 0.789 |
| FT% | 0.0857 | 0.0813 | 1.054 |

```
r_board = r_rate / ratio²

FG%:  2.333 / 0.789²  =  3.748   →  k = 0.343    (0.420 uncorrected)
FT%:  2.000 / 1.054²  =  1.800   →  k = 0.466    (0.447 uncorrected)
```

Skipping this leaves FG% wrong by roughly 25%, in the direction of overstating how much a
FG% edge is worth. Note the ratios sit on opposite sides of 1, so the correction moves the
two rows in opposite directions and no single fudge factor covers both.

### These two numbers are the least trustworthy in the document

Table 8 quotes `σ²_FG = 0.003` and `τ²_FG = 0.007` to **one significant figure**. A true
σ² anywhere in 0.0025 to 0.0035 puts `k_FG` between roughly 0.31 and 0.37, which moves the
65% threshold between 1.04 and 1.24. FT% is quoted to one figure as well and is only
slightly better behaved.

This is the same caveat the board's cheat sheet already carries about the g multipliers:
*"the second decimal is not [robust], least of all on FG% and FT%."* It lands awkwardly,
because FG% and FT% are the two rows the tracker is blind to today. Ship them marked
provisional, and calibrate them first. Section 9 gives the procedure.

---

## 5a. The second basis correction: weighted values

*Added at implementation. The derivation above assumes `Z_team` is measured in units where
a category's standard deviation is 1. Feeding the tracker DURANT H2H values breaks that
assumption, and the fix is exact rather than fitted.*

`durant_category_values` standardises each category to mean 0 and SD 1 over the DURANT
pool. The H2H weight is then a pure scalar, so a **weighted** column's SD is exactly its
weight. Measured over the real BMP pool, to four decimal places:

```
Cat     SD(D)  SD(DH)  weight
PTS    1.0000  1.0000    1.00
REB    1.0000  0.9400    0.94
AST    1.0000  0.7500    0.75
3PM    1.0000  0.6000    0.60
STL    1.0000  0.6000    0.60
BLK    1.0000  0.6000    0.60
FG%    1.0000  0.6000    0.60
FT%    1.0000  0.6000    0.60
TO     1.0000  0.0000    0.00
```

So `Z_team` measured in DH units is exactly `w` times `Z_team` in z units, and:

> **K_c = k_c / w_c**

| Cat | k (§4) | w | **K** | Z\* 65% | Z\* 75% |
|---|---|---|---|---|---|
| 3PM | 0.587 | 0.60 | **0.978** | 0.39 | 0.69 |
| BLK | 0.551 | 0.60 | **0.918** | 0.42 | 0.73 |
| AST | 0.632 | 0.75 | **0.843** | 0.46 | 0.80 |
| FT% | 0.466 | 0.60 | **0.777** | 0.50 | 0.87 |
| REB | 0.558 | 0.94 | **0.594** | 0.65 | 1.14 |
| FG% | 0.343 | 0.60 | **0.572** | 0.67 | 1.18 |
| STL | 0.328 | 0.60 | **0.547** | 0.70 | 1.23 |
| PTS | 0.516 | 1.00 | **0.516** | 0.75 | 1.31 |

**Getting this backwards is the failure mode to guard against.** Multiplying by the weight
instead of dividing understates every win probability, and nothing in the sheet would look
wrong — the numbers stay plausible, the reads just come back too cautious. `verify.py` and
`tests/test_board_values.py` both assert `K_c × w_c == k_c`, so the correction can be
neither skipped nor applied twice.

**The Yeo-Johnson layer is second-order.** Regressing each DURANT column on its plain-z
column over the same pool gives slopes from 0.908 (blocks, the most compressed by the
transform) to 0.996 (threes, whose λ is almost exactly 1). Both columns have unit SD by
construction, so the transform reshapes without rescaling and `K = k/w` holds to first
order. The slope table is printed by `verify.py` as the standing diagnostic.

---

## 6. Choosing the win-rate targets

With `k` fixed, one number sets all nine thresholds: the win rate that counts as strong.
That number should come from the playbook's own strategy, and it does.

The playbook's biggest correction (§10) is that **marginal value peaks at a coin flip**.
Winning a category 60-30 pays exactly what winning it 46-45 pays, so margin past a win is
wasted capital. Rosenof's H-scoring algorithm found this on its own: when a category was
already above average it invested less and kept it slightly above 50%, then spent
elsewhere.

That claim is measurable in this framework. The marginal return on the next unit of z is
`φ(Φ⁻¹(p))`, so efficiency relative to a coin flip is `exp(−Φ⁻¹(p)²/2)`:

| Win rate | Efficiency vs. peak |
|---|---|
| 50% | 100% |
| 60% | 97% |
| **65%** | **93%** |
| 70% | 87% |
| **75%** | **80%** |
| 80% | 70% |
| 85% | 59% |

The shape decides the bands.

**Strong at 65%, weak at 35%.** Symmetric, and deliberately bracketing the playbook's own
"aim for roughly 60%, not 90%" target so that a category sitting *at* target reads
contested rather than finished. At 65% the next pick still returns 93% of peak value, so
the label means "you are ahead here", not "stop".

**Banked at 75%.** Efficiency has fallen to 80% of peak, and the category has stopped
being where the next pick belongs. This is the point of adding a fourth state.

These three are the only real knobs. They belong on Settings as **win rates**, which is
the first time the tracker's tunable constant will be a quantity the owner can reason
about. The nine `k` values sit beside them as structural constants, in the same spirit as
the existing g multipliers: derived from a published source, not tuned.

*Attribution.* The efficiency table is derived here. The strategy it quantifies is
Rosenof's H-score finding, by way of playbook §10. The specific cutoffs 0.65 / 0.35 / 0.75
are a judgment call, but a bounded one: the argument fixes their ordering and roughly
their spacing, and any nearby choice behaves similarly.

---

## 7. Recommended tracker shape

### Columns

```
Category | My team | Average team | z | Win % | Read | Punted
```

Keep `My team` and `Average team` unchanged. The `SUMIF`, `benchCount` and `benchRate`
logic is correct, and the raw numbers are worth seeing: "I have 12.4 threes" is concrete in
a way no standardized score is.

Replace `Edge` with `z`, and add `Win %`. Edge becomes redundant once z is present, and z
is the same quantity expressed on a scale that works.

### Formulas

```
n        = COUNTIF(Mine, TRUE)

Z_team,c = ( SUMIF(Mine, TRUE, z_c) − n · AVERAGE(FILTER(B_Zc, B_ADJRANK <= TEAMS*n)) ) / SQRT(n)

Win%     = NORMSDIST( Z_team,c * K_c )

Read     = IF(Punted, "PUNTED",
           IF(Win >= BANK_WIN,   "BANKED",
           IF(Win >= STRONG_WIN, "STRONG",
           IF(Win <= WEAK_WIN,   "WEAK", "CONTESTED"))))
```

`NORMSDIST` and `NORMSINV` both exist in Google Sheets, so the exact normal CDF is
available and there is no reason to reuse the paper's first-order Taylor approximation.

### Read states

| State | Condition | Rendering |
|---|---|---|
| WEAK | Win ≤ 35% | red, bold |
| CONTESTED | 35% < Win < 65% | plain. **The next pick goes here.** |
| STRONG | 65% ≤ Win < 75% | green, bold |
| BANKED | Win ≥ 75% | muted, italic, whole row |
| PUNTED | checkbox ticked | muted, italic, whole row |

BANKED renders exactly like PUNTED because they mean the same thing operationally: stop
looking here. A conceded category and a won category are both places where the next pick
returns less than it would elsewhere, and the tab should go quiet on both. This is the
change that puts the playbook's biggest correction into the instrument instead of leaving
it in prose.

### The centering decision, and its bias

`Z_team` above centers on the drafted set but scales pool-wide. That is a deliberate
compromise and its direction should be stated in the ADR.

Centering on `AVERAGE(FILTER(z_c, drafted))` preserves the F4 fix: the benchmark still
moves every round. Scaling stays pool-based, which is free because a board z already has
σ = 1 by construction, and it keeps the nine `k` values fixed and auditable.

The cost: an opponent's mid-draft roster is drawn from the top of the pool, so its true
spread is tighter than pool-wide, and using the wider figure **understates** your edge. The
error is largest in round 1 and is exactly zero at a full roster, where the drafted set is
the pool and the two definitions coincide. Conservative in the safe direction. The tab will
never call you strong when you are not.

The alternative is to recompute `k` each round from the live spread of the drafted set:

```
k_live = 1 / √(1 + 2·r_c / s_c²)      s_c = STDEV(FILTER(z_c, drafted))
```

More correct, and it knows that a one-player roster cannot be strong at anything. It costs
nine live `STDEV(FILTER(...))` formulas that have to be verified in the sheet. Not
recommended for a first implementation. Section 9 proposes printing `s_c` as a diagnostic
so the decision can be revisited on evidence rather than on argument.

---

## 8. Implementation notes for later

Recorded so the next person does not rediscover them.

**The Draft Board carries no z columns.** `Mine` lives on the Draft Board (`D` map,
`Build.gs:1067`), which holds only a hidden raw-stat feed at `D.hFgm..D.hTo`. The z columns
live on the Board tab (`B.zfg..B.zto`). A second hidden feed block is needed, mirroring the
existing one:

- extend the `D` map with `zFg..zTo` after `hTo`
- populate with `ref(B.zfg)` and so on, copying `Build.gs:1219-1234`
- `writeGrid`, then group and hide alongside the existing feed at `Build.gs:1437-1438`
- add `B_ZFG..B_ZTO` named ranges using the `gcols` loop pattern at `Build.gs:910`

**Derive every column letter through `a1col()`.** The harness asserts this, because a
shifted column repoints a formula at the wrong data and still computes.

**Turnovers lose their sign flip.** `z TO` is already flipped on the board so that higher
is better, so `Z_team` needs no special case, and the current `Edge` sign flip disappears.
But the raw `My team` and `Average team` cells still read "lower is better" and will now
disagree in direction with the z beside them. Label the row and verify it on real rows.
This is exactly the kind of silent sign error the repo's first priority names.

**Retire three Settings constants, add twelve.** `TRACK_FG_BAND`, `TRACK_FT_BAND` and
`TRACK_COUNT_BAND` go. `CAT_BAND` stays: it belongs to the Category profile column and is
unrelated. The twelve additions are three win rates and nine `k` values, laid out in
`CAT_LABELS` order so the harness's existing ordering assertion covers them.

**Verification, in the sheet.** A green harness is not a deployed change, and the harness
never evaluates a formula. After pushing `Build.gs` into `Code.gs` and running the menu:

1. Zero ticks: `z`, `Win %` and `Read` all blank. No `#DIV/0!`.
2. One tick: `√n = 1`, no division error, plausible Win %.
3. **A deliberately average roster: Win % ≈ 50% on all nine.** The single best check that
   centering and scaling are both right.
4. The top 13 by Adj Rank: strongly positive across the board, and at n=13 the drafted set
   is the full 156, so this is the case where the model is exact.
5. The TO row: tick two high-turnover players, confirm `z` goes negative while raw
   `My team` goes up.
6. FG% and FT%: confirm they can reach STRONG and WEAK at all. That is the whole point of
   F3.
7. Punted and Banked: both grey the full row, and Punted still strips the category from
   the Draft Board's Category profile column.
8. Screenshot it. Two real defects on this tab were invisible in cell values and obvious
   on sight.

**One open defect to fix in the same pass.** F8 in the
[2026-08-29 math audit](../reviews/2026-08-29-draft-board-math-audit.md): the benchmark
filter `TEAMS * COUNTIF(Mine)` is uncapped, so at 14 ticks it reaches to rank 168 when only
156 players are ever drafted. Cap it at `Q`. The z formulation inherits the same filter and
the same bug.

---

## 9. What stays provisional, and how to calibrate it

Three things ship uncalibrated. Ranked by how much they matter:

1. **`k_FG` and `k_FT`.** One significant figure in the source, as section 5 sets out.
2. **The 0.65 / 0.35 / 0.75 cutoffs.** Argued, not measured.
3. **The fixed-`k` approximation.** Bias direction known, magnitude unknown.

### Calibrating `k` against real results

Once a season of weekly category results exists, `k_c` is directly measurable and needs no
new theory.

For each team-week, compute that team's `Z_team` in category c from the projections, and
record whether it won the category. Probit-regress the win indicator on `Z_team`. **The
fitted slope is `k_c`.** Compare against the table in section 4.

This also tests the model rather than only its constants. If the fitted slopes land near
the derived values, the whole-roster form holds. If they are uniformly lower, real rosters
specialize more than the random-draw assumption allows, and `Z_team` needs a measured team
SD instead of `√n`.

### The one diagnostic worth printing now

Print `s_c = STDEV(FILTER(z_c, drafted))` per category on Settings, and act on none of it.
This is the repo's existing habit with the FG impact-versus-rate ratio: keep the number
visible so the decision can be revisited on evidence. If `s_c` sits well below 1 through
the middle rounds, the fixed-`k` approximation is costing more than assumed and the live
variant earns its complexity.

### What this model does not capture

Stated so nobody has to rediscover them:

- **Games played.** Summing per-game z assumes every player plays the same number of games
  in a week. The current tracker has the identical limitation, so this is not a regression,
  but the move to z is the moment to decide it deliberately rather than inherit it.
- **Category correlation.** Points and threes move together; FG% and rebounds move together
  through position. The model treats the nine as independent, as does the playbook's own
  simulation, which notes real correlation makes both stacking and punting somewhat easier
  than the model implies.
- **Managers are not random.** Rosenof defends the random-selection assumption in §4.1.1
  and his simulations support it, but punt builds concentrate category strength and push
  real between-team spread above the random-draw model. The calibration above measures
  this directly.
- **A static board cannot punt optimally.** Rosenof says so plainly (§4.2). The tracker
  reports position; it does not choose strategy.

---

## 10. Summary

The threshold does not need to be guessed. It follows from Rosenof's published variance
components and one stated strategic target:

```
P(win category c) = Φ( Z_team · k_c )      Z_team = Σz/√n,   k_c = 1/√(1 + 2r_c)
```

Three arbitrary numbers become three win rates and nine derived constants. The tracker
gains a `Win %` column that is more actionable than any label, and a `BANKED` state that
enacts the playbook's own advice about over-investment. The two least certain numbers,
`k_FG` and `k_FT`, are exactly the two rows the tracker cannot see today, and they are the
first thing to calibrate.

---

## References

### External

**Rosenof, Zach. *Static quantification of player value for fantasy basketball*.**
[arXiv:2307.02188](https://arxiv.org/abs/2307.02188), v5, 10 September 2024. The backbone
of this document.
- §3.1, model assumptions: random selection from Q, N players per team, the objective as
  expected categories won.
- §3.3 and the appendix, *Detailed justification of G-score*: the differential
  `D ~ N(μ − μ(p), (2N−1)(σ²+τ²) + τ(p)²)`, the CDF-at-zero step, and the first-order
  Taylor approximation. The whole-roster variance in section 2 is derived from this.
- Table 5(a)-(c): the definitions of σ_M, τ_M, σ_R, τ_R and κ. Table 5(b) is where the
  percentage-basis ambiguity of section 5 originates.
- **Table 8**: the empirical σ² and τ² per category, 2022-23 season, Q = top 156 by base
  Z-score. **Every `k` in section 4 comes from these two columns.**
- §4.1.1-4.1.5: the model's own stated limits, cited in section 9.
- §4.2: static ranking lists cannot punt optimally.
- §4.4.2: κ = 2N/(2N−1), between 1.040 and 1.043 for twelve- and thirteen-player teams.

**Rosenof, Zach. *Optimizing for Rotisserie Fantasy Basketball*.**
[arXiv:2501.00933](https://arxiv.org/abs/2501.00933), January 2025. Checked and **not
used.** Its objective function targets season-long rotisserie standings, not the weekly
head-to-head matchup this league plays. Recorded so the next reader does not spend time
on it expecting otherwise.

**Yahoo Fantasy, [Head-to-Head scoring](https://help.yahoo.com/kb/head-to-head-scoring-yahoo-fantasy-sln6212.html).**
Confirms the format the win probability is computed against: Head-to-Head Categories, every
category settled separately each week. Rosenof calls the same format *Each Category*, and
his simulations report it separately from *Most Categories*.

### In-repo

**[docs/references/fantasy-basketball-draft-playbook.md](fantasy-basketball-draft-playbook.md)**
- §5, G-score: the sigma/tau/kappa formulas and the normalized multiplier table, which
  section 3 warns against reusing here.
- §10, Punting: the marginal-value table (value peaks at a coin flip), the "aim for
  roughly 60%, not 90%" target, and the H-score soft-punting finding. Section 6 rests on
  this.
- The percentage-impact formula and the impact-versus-rate discussion, source of the
  ratios in section 5.
- The uncalibrated-items table: the current rate bands, listed there as guesses.

**[docs/reviews/2026-08-27-draft-board-methodology-review.md](../reviews/2026-08-27-draft-board-methodology-review.md)**
F3 (the 8% band is unreachable on the two rate rows) and F4 (the pool-mean benchmark reads
STRONG through round ten). These produced the tracker's current shape, and F3's closing
note is what requires an ADR for this change.

**[docs/reviews/2026-08-29-draft-board-math-audit.md](../reviews/2026-08-29-draft-board-math-audit.md)**
F8: the benchmark filter is uncapped and reaches past rank 156. Carried forward in
section 8.

**[docs/decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md](../decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md)**
The decision to divide the percentage impact by the SD of the impact column rather than of
the raw rate, and the measured ratios (FG% 0.789, FT% 1.054). Section 5's correction
depends entirely on this.

**[docs/decisions/ADR-0013-category-profile-column.md](../decisions/ADR-0013-category-profile-column.md)**
The Category band calibration at 1.00 SD, and the reasoning for why that column uses z
rather than g. The tracker's case is the mirror image: it asks "how much is this edge
worth", which is precisely the question the noise discount answers.

**[docs/decisions/ADR-0009-soft-punt-weighting.md](../decisions/ADR-0009-soft-punt-weighting.md)**
Soft-punt weighting, and the precedent for adopting a Rosenof finding as direction while
treating the coefficient as a local tuning choice. Section 6 follows the same pattern.

**`scripts/draft-board/Build.gs`**
- `buildTrackerTab()` at line 1515: the tab as it stands.
- Settings tracker thresholds at lines 720-726, and the note beneath them.
- The `D` map at line 1067 and the hidden category feed at lines 1219-1234 and 1437-1438:
  the pattern a z feed would copy.
- Named ranges at line 910, and the normalized multipliers at line 676.

### What is derived here rather than sourced

In the style of the playbook's own accounting, so a later reader knows which numbers to
challenge:

| Claim | Status |
|---|---|
| The whole-roster variance `n(σ² + 2τ²)` and `P(win) = Φ(Z_team · k)` | Derived here, inside Rosenof's model. Cross-checked against his published one-player form |
| `Z_team = Σz/√n` as the tracker's display quantity | Mine |
| `k = 1/√(1+2r)` and the nine values | Derived here from Rosenof's Table 8 |
| The percentage basis correction `r_board = r_rate / ratio²` | Mine, using ADR-0012's measured ratios |
| The efficiency table `exp(−Φ⁻¹(p)²/2)` | Derived here. Quantifies a finding that is Rosenof's |
| The 0.65 / 0.35 / 0.75 cutoffs | Judgment, argued from the efficiency curve and the playbook's 60% target. Bounded, not measured |
| The BANKED state | Mine |
| Centering on the drafted set while scaling pool-wide, and its bias direction | Mine |
