# The board's values did not match Basketball Monster's

- Date: 2026-09-01
- Reported by: Bryan
- Severity: **Medium** — every value in all nine source × value columns was off by roughly
  0.008, and the dropped-category tag was wrong on 15 of 234 players. The board's stated
  purpose (ADR-0015) is to reproduce Basketball Monster's DURANT H2H, and it did not.
- Status: **fixed, deployed to the live sheet, and verified there** against Basketball
  Monster's own published columns — a comparison that did not exist before this work.
  See [ADR-0021](../decisions/ADR-0021-borrowed-bbm-pool-constants.md).
- Outstanding: the `BMP-ALT` export has since drifted from Basketball Monster's live Bonus
  projections, so six of its players still disagree. That is a data problem, not this one —
  see [What is still wrong](#what-is-still-wrong-and-why-it-is-not-this-bug).

## Symptom

Comparing the board against basketballmonster.com/projections.aspx, Josh Projections
(= our `BMP` source), on the same 2026-09-10 projections:

| Nikola Jokic | ours | Basketball Monster |
|---|---|---|
| DURH | 1.082 | **1.09** |
| ZSC | 1.028 | **1.02** |

Small, but wrong in the one direction that matters: the board exists to show their numbers.

## What was actually wrong

Pulling all 234 players Basketball Monster publishes and comparing against `Data.gs`:

| | |
|---|---|
| ZSC vs their `Value` | MAE 0.0075, max 0.0267 — outside display rounding on **73 of 234** |
| DURH vs their `DUR H2H` | MAE 0.0079, max 0.0294 — outside display rounding on **77 of 234** |
| DURH dropped-category tag | wrong on **15 of 234** (Karl-Anthony Towns, Zion Williamson, Tyler Herro, Jalen Suggs, Naz Reid, …) |

The dropped-category tag is the visible half. A tag reading `#12 BLK` when Basketball
Monster says `STL` is a claim about which category a player is weakest in, printed on the
tab you draft from.

## What was NOT wrong

Everything we had already borrowed from Basketball Monster checked out, measured against
their published columns for all 234 players:

| Ingredient | Verdict |
|---|---|
| Yeo-Johnson λ (`LAMBDAS_BBM_2026_27_JOSH`) | **correct.** Refitting against their `D*V` columns recovers 0.4155 against our 0.4151, 1.0165 against 1.0166, −1.6855 against −1.6863. Residual 0.004 — the two-decimal display floor. The same λ hold for their Bonus source. |
| `H2H_WEIGHTS` | **correct.** Recovered 1.0000 / 0.6011 / 0.9397 / 0.7500 / 0.5999 / 0.6001 / 0.6003 / 0.5998 against our 1.00 / 0.60 / 0.94 / 0.75 / 0.60 / 0.60 / 0.60 / 0.60. |
| Drop rule, `/7` divisor, turnovers at weight zero | **correct.** |
| The `BMP` export itself | **correct.** Every stat line agrees with their page to within display rounding; the largest excess anywhere was 0.021. |

## Mechanism

Every per-category value is `(stat − mean) / sd` against a pool. We derived that pool
ourselves — the top 156 by the value in question, iterated to a fixed point
(`bbm_reference.build_pool`, `build_durant_pool`, `build_z_h2h_pool`). Basketball Monster's
constants are not those constants.

Regressing their published `pV` on our exact per-game points recovers the mean and SD they
actually used, because a z-score is linear in the stat and the fit residual is at the
display floor:

```
                BBM recovered      ours (top-156)      delta
points  mean       17.0131            17.0994          +0.51%
        sd          5.5189             5.4004          −2.15%
threes  mean        1.7047             1.7289          +1.42%
        sd          1.0453             1.0273          −1.72%
steals  mean        1.0077             1.0319          +2.40%
        sd          0.3199             0.3070          −4.02%
blocks  mean        0.7060             0.6865          −2.76%
        sd          0.5235             0.5170          −1.24%
DURANT points      5.5213 / 0.9866   5.4823 / 1.0362
```

The means are close; the SDs are not, and they miss in both directions by category. That is
what produces a per-player error of a few thousandths with no consistent sign, and what
flips a dropped-category tag whenever two categories sit within that margin.

### Why no pool reproduces it

Searching every pool size from 60 to 509 by our own ZSC ordering:

| category | N matching their mean | N matching their SD |
|---|---|---|
| points | 159 | 85 |
| threes | 174 | 144 |
| rebounds | 150 | 158 |
| assists | 158 | 135 |
| steals | 177 | 232 |
| blocks | 143 | 150 |
| turnovers | 158 | 318 |

The means all want something near 156. The SDs want anything from 85 to 318. There is no
pool. The joint best-fit N is 160, and it is barely better than 156.

**And this reproduces using Basketball Monster's own live stat lines.** Building the top-156
from the numbers on their own page, rather than from our export, still leaves an RMS SD
error of 1.65%. So it is not our data, not export staleness, and not our pool iteration —
Basketball Monster standardises against a wider distribution than the projection set they
publish.

This was already the standing hypothesis at
[reverse-engineering §III.2](../references/basketball-monster-projections-reverse-engineering.md),
which guessed "realised production rather than projections" and concluded **"Practical
effect: none, if you derive your own pool from your own projections."** That conclusion was
wrong for this board. ADR-0015 makes reproducing their published numbers the whole point.

## Why nothing caught it

Same shape as the tag-misalignment bug: every gate was green.

| Gate | Why it passed |
|---|---|
| `pytest` | Tests the arithmetic against itself. `pool_params` is correct — it computes the mean and SD of the pool it is given. |
| `ruff` | Nothing to say. |
| `harness.js` | Compares formula strings. The values are numbers now (ADR-0016). |
| `verify.py --sheet` | Checks the sheet against `Data.gs`. Both carried the same wrong number. |
| The reverse-engineering doc's §IV.3 | Measured `Value` MAE at 0.0075 and **recorded it as a pass**. It is the bug, logged as an accuracy figure. |

**Nothing in the repository compared our output to Basketball Monster's.** Every check
verified internal consistency, and the board was internally consistent throughout.

## Fix

Recover Basketball Monster's constants rather than deriving our own, for the two sources
where they publish them. `calibrate_bbm.py` scrapes their value columns, regresses them on
our own stat lines, and writes the recovered mean, SD, percentage rate and λ to a dated
per-source file that the pipeline requires and pairs to the export date. Nothing is
hardcoded: the constants are refitted on every refresh, because they are a property of a
projection set that changes.

λ moved onto the same footing in the same change. They were the one borrowed constant
frozen in source, and a stale λ would have been invisible in exactly the same way.

HBP keeps its own derived pool — Basketball Monster publishes nothing to recover for it.

**Outliers are rejected from the fit.** Basketball Monster revises between exports, and one
player whose row has since changed does not merely mispredict itself — it tilts the
regression and corrupts constants applied to every player in the universe. The cut is
derived from the spread of the residuals (median + 8 robust sigmas), not typed: on the
current `BMP` export it rejects nobody, and on `BMP-ALT` it rejects six.

## Verified in the sheet

Measured against Basketball Monster on the same 2026-09-10 projections, `BMP` source, after
a full rebuild and a full `A4:AA203` pull of the live board:

| | before | after |
|---|---|---|
| ZSC vs their `Value` | MAE 0.0075, max 0.0267, **73 of 234** outside display rounding | **MAE 0.0034, max 0.0098, 0 of 189** |
| DURH vs their `DUR H2H` | MAE 0.0079, max 0.0294, **77 of 234** outside | **MAE 0.0030, max 0.0095, 0 of 189** |
| DURH dropped category | **15 of 234 wrong** | **3 of 189, every one a tie inside 0.009** |

Nikola Jokic, the row that started this, now reads `+1.089 #1 3PM` and `+1.022` against
their 1.09 and 1.02.

The three remaining dropped-category disagreements are gaps of 0.0006, 0.0031 and 0.0088
between the two candidate categories — closer than either side can resolve, given their
two-decimal publication and the residual §III.1 leaves on the percentage columns. `verify.py`
counts them and reports them, and only counts a disagreement *against* the board when the
two categories were far enough apart to be separable.

Also checked: all nine tabs carry no error values, and the sheet agrees with `Data.gs` on
1800 values and all 1800 rank tags.

## What is still wrong, and why it is not this bug

The `BMP-ALT` export has drifted from Basketball Monster's live Bonus projections since it
was taken. Six players have genuinely different stat lines — Jamal Murray at 65 games
against our 73, DeMar DeRozan at 17.0 points against our 14.7, Aaron Gordon at 15.1 against
17.4. The constants are recovered correctly around them, because the calibration drops them
before fitting. But those players' *values* are still computed from the stale line, so
`verify.py --published` fails `BMP-ALT` on all four gates:

```
BMP-ALT   ZSC   MAE 0.0051  max 0.1264  outside display rounding on 6 of 190
          DURH  MAE 0.0053  max 0.1521  outside display rounding on 6 of 190
```

That is the check working. **The fix is a same-dated re-export of all three sources**, which
is the download step in the refresh procedure. `BMP` shows no such drift: every stat line
matches their page to within display rounding, worst excess 0.021.

## A trap found on the way

Recreating a tab makes Sheets rewrite every formula that pointed into it. Running
`Step 1 — Settings only` against a finished board turned the Draft Board's tier formula into
`IF($AC6>#REF!*$AD6,…)` on all 200 rows, and `TIER` and `RND` to `#REF!`. `step1` does call
`defineNames` afterwards, and that is not enough — redefining a name does not repair a
formula whose text has already been rewritten. Only a rebuild that writes those formulas
again does. The step actions are for building the workbook up in order after a failure, not
for patching one tab of a live board.

## The gate that would have caught it

`verify.py --published`, comparing our computed values against Basketball Monster's
published columns for every player they list. It reports MAE, max and the dropped-category
disagreement count, and it fails the build past a tolerance set just above the two-decimal
display floor.

That check is the point of the fix as much as the constants are. The board is checkable
against a published source — that is ADR-0015's whole argument for using their method — and
until now nothing checked it.
