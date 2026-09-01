# ADR-0018: The Category Tracker moves to a win-probability model on the DURANT H2H basis

- Status: Accepted
- Date: 2026-09-01
- Owner: Bryan
- Supersedes: ADR-0013

## Context

The Category Tracker reported an `Edge` — my roster's total minus a benchmark team's —
thresholded into STRONG, EVEN or WEAK against three constants in raw units: 0.005 for FG%,
0.010 for FT%, and 8% of the benchmark for the seven counting rows. Three constants because
raw units cannot share one, and all three documented on the sheet as uncalibrated guesses.

`docs/references/category-tracker-z-thresholds.md` worked out the replacement: an edge in
standard deviations, converted to a probability of actually winning the category, using
Rosenof's variance components. `P(win) = Φ(Z_team · k_c)`, where `k` prices a whole known
roster against a whole random one. That research was explicit that implementing it needed
an ADR. This is it.

Two things then changed underneath it. ADR-0015 moved the board to DURANT H2H, so the
per-category numbers available to the tracker are weighted DURANT values rather than the
plain z the research assumed. And those weights include **turnovers at zero**.

## Decision

**Feed the tracker DURANT H2H category values and report a win probability.**

Columns: `Category | My team | Average team | Z | Win % | Read | Punted`. `My team` and
`Average team` stay raw stats, because a roster's actual rebound total is what a human
recognises; `Z` and `Win %` carry the verdict.

```
Z_c   = ( SUMIF(Mine, dh_c) − n·AVERAGE(FILTER(dh_c, drafted)) ) / SQRT(n)
Win%  = NORMSDIST(Z_c · K_c)
Read  = PUNTED | BANKED ≥75% | STRONG ≥65% | WEAK ≤35% | CONTESTED otherwise
```

**`K_c = k_c / w_c`, and this is exact rather than fitted.** DURANT standardises each
category to unit SD over its pool, and the H2H weight is a pure scalar, so a weighted
column's SD is exactly its weight and `Z_team` in DH units is exactly `w` times `Z_team`
in z units. Verified to four decimal places against the real pool. Getting it backwards
understates every win probability while leaving every number on the sheet looking
plausible, so `verify.py` and the test suite both assert `K_c × w_c == k_c`.

**The turnovers row is removed.** DURANT H2H prices turnovers at zero — that is *how* it
removes them — so a DH turnover column is identically 0.0 for every player. It cannot be
thresholded, and a row that can only ever read EVEN is worse than no row. Eight categories.

**Five read states, not three.** BANKED and PUNTED both mean *stop looking here* and render
identically. CONTESTED means *the next pick goes here* and gets the only saturated fill on
the tab. This follows the marginal-value derivation directly: the return on the next unit of
edge peaks at a coin flip and is down to 80% of peak by 75%, so a nearly-lost category and a
nearly-won one are both places to stop spending.

**The benchmark filter is capped at Q.** `rank <= MIN(Q, TEAMS × n)` closes open defect F8,
where the uncapped form reached rank 168 of a 156-player pool at fourteen ticks.

**The Category profile column moves to the same basis, but thresholds the *unweighted*
DURANT values.** A weighted column's SD is its weight, so a single band is unreachable for
the five categories weighted below 1 — FG%, FT%, 3PM, STL and BLK would never have fired.
Dividing by the weight restores one band across all eight, and is also the right basis by
ADR-0013's own argument: the weight is the how-much-is-it-worth term, and this column asks
the prior question, does he have the edge at all.

**`CAT_BAND` stays at 1.00.** Recalibrated the way ADR-0013 calibrated it, on the new basis:
2.54 flags per player and 10% of players unlabelled, against ADR-0013's targets of ~2.6 and
~9%. Normalising by the weight makes the inherited constant correct rather than requiring a
new one.

Retired: `TRACK_FG_BAND`, `TRACK_FT_BAND`, `TRACK_COUNT_BAND`.

## Consequences

Good. "REB 62%" is a number you can act on; "REB STRONG" was a label whose threshold nobody
had calibrated. The three raw-unit constants collapse into eight structural ones with a
published derivation. The tracker and the board now measure the same quantity, so
`▲ REB` on a player and a rising REB win probability are the same fact at two scales — which
was not true when the profile read z and the board ranked on G.

Bad. **Turnovers are now invisible on the tracker**, in a league that settles them every
week. This follows from DURANT H2H rather than from a judgement that turnovers do not
matter, and it is the sharpest cost of ADR-0015. Turnovers remain visible as a raw stat on
the Board and calculation tabs. If losing the category proves expensive, the honest fix is a
ninth row on the plain-z basis with its own `k = 0.485`, clearly marked as a different
basis — not a re-weighting of DURANT H2H, which would stop being DURANT H2H.

`k_FG` and `k_FT` remain the least trustworthy numbers in the model: Rosenof's Table 8
quotes their variances to one significant figure, which puts `k_FG` anywhere in 0.31–0.37.
Shipped as provisional. The calibration procedure — probit-regress weekly category outcomes
on `Z_team`, where the fitted slope *is* `k_c` — is recorded in §9 of the research document
and needs a season of results.

The model still assumes opponents are drawn at random from the drafted pool. Real managers
specialise, which makes a contested category less contested than it looks.
