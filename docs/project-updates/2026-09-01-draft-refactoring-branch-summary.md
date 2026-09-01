# `draft-refactoring` — three projections, DURANT H2H, no games-played adjustment

- Date: 2026-09-01
- Branch: `draft-refactoring`
- Status: **built, deployed and verified in the sheet**

## What changed, in one paragraph

The board valued players one way from one projection: nine z-scores, discounted by
Rosenof's volatility multipliers, turned into value over replacement, then scaled by
projected games played. It now carries **three projection sources** and **three values
each**, ranks by **Basketball Monster's DURANT H2H**, and **scales nothing by games
played**. The values are computed in Python and written to the sheet as numbers; the
draft-day logic stays a live formula.

## Why

Three findings from the `durant-actual` research contradicted the board:

1. **One projection is a single point of failure.** Identical math over Basketball
   Monster's two sources moves players ~20 rank places on average. On our own data Kawhi
   Leonard is DURH #6 on BMP and #21 on HBP; Embiid is #8 and #30. A single-source board
   cannot show that a ranking is contested.
2. **The valuation was wrong for this format.** Basketball Monster's own guidance for
   head-to-head category leagues is DURANT H2H. Our G-score multipliers were documented on
   the sheet as "the second decimal is not reliable" and were being applied to three.
3. **Games played should not scale value.** It is the least predictable part of any
   projection, and the method the board now reproduces has no availability term at all.
   The override machinery was also entirely unused — `GP Y-1/2/3` filled on 0 of 200 rows.

## The three values

| Value | What it is | Denominator |
|---|---|---|
| `ZSC` | Basketball Monster's plain `Value` — nine z-scores, TO inverted, nothing dropped | 9 |
| `ZSH` | The H2H weighting and minus-one rule on **untransformed** z | 7 |
| `DURH` | DURANT H2H exactly — Yeo-Johnson, standardise, weight, drop the worst live category | 7 |

`ZSH` exists to isolate what the Yeo-Johnson transform is worth: it shares DURH's weights
and its drop rule and differs only in the transform, so any rank disagreement between them
is the transform's doing. Without it, adopting DURANT would have been an act of faith.

**Magnitudes are not comparable across value types** — ZSC averages nine, the others seven.
Only ranks are.

## Two corrections that would have shipped silently

**`K = k / w`, not `k × w`.** A weighted DURANT column's standard deviation is *exactly* its
weight, so `Z_team` in DH units is `w` times `Z_team` in z units. My first table used the
wrong pool and inverted the operation, which would have understated every win probability
while every number on the sheet still looked plausible. It is asserted in both `verify.py`
and the test suite so it can be neither skipped nor applied twice.

**The Category profile must divide by the weight.** A fixed band is unreachable for any
category weighted below 1, so FG%, FT%, 3PM, STL and BLK — five of eight — would never have
fired. On the unweighted basis, `CAT_BAND = 1.00` is retained: recalibrating the way
ADR-0013 did gives 2.54 flags per player and 10% unlabelled, against its targets of ~2.6
and ~9%.

## Five defects only the live deploy could find

Every one passed the harness, `pytest` and `ruff`, and every one broke the build in Google.
Each now has a check that catches it.

| Defect | Why it was invisible |
|---|---|
| `clear()` does not remove merges | Only bites when rebuilding over a *different* layout, which building from scratch twice cannot reproduce. The harness now seeds an old-layout merge. |
| A conditional format rule may not reference another sheet | The disagreement highlight used a named range, and every named range lives on Settings. It took down the whole Draft Board rule set. |
| `sheetRef` allowed spaces unquoted | `Category Tracker!$G$7` never parsed; both profile columns returned `#ERROR!` on all 200 rows. The hyphen case was handled; the space looks harmless. |
| Sheets reads `"3PM"` as a time | The tag rendered `#1 0.625` — 3:00 PM as a day fraction. It is the only category label that parses as anything else. |
| `readCheckState` ran after the wipe | A full rebuild silently discarded every `GONE` and `MINE` tick. Re-sorting preserved them, so it looked intentional. |

The last one is the one that mattered most: on draft day it is the difference between an
inconvenience and losing the board's state mid-draft.

## What is on the sheet now

Nine tabs: `Draft Board` · `BMP` · `HBP` · `BMP-ALT` · `Board` · `Punts` ·
`Category Tracker` · `Settings` · `README`.

The `Board` tab survives as the spine — identity, the HBP raw line, availability, market,
and every hand-edited column — which is what keeps `Refresh data` writing to one tab and
leaves the refresh machinery intact. It went from 73 columns to 28 and from ~90 formulas to
two.

The Draft Board's 18 value columns are generated from `SOURCES × VALUE_KINDS` rather than
typed out, because the projection filter hides one source's six-column span and a gap there
would hide the wrong columns while every offline check still passed.

**The Category Tracker has eight rows, not nine.** DURANT H2H prices turnovers at zero, so
a DH turnover column is identically 0.0 for every player and cannot be thresholded. This is
the sharpest cost of the change and it is recorded as such in ADR-0018: we now have no
instrument for a category the league settles every week.

## Verified in the sheet

- No `#VALUE!`, `#REF!`, `#ERROR!` or `#NUM!` on any tab.
- All 200 `DURH` values agree with the Python pipeline to within display rounding.
- Ranks are 1..200 contiguous, matching the calculation tabs.
- Draft state survives a full rebuild, reattached to the right players by name.
- The projection filter hides exactly one block and the group separators still bound the
  survivors.
- The tracker computes all five read states from one ticked player.

## One thing to know before draft day

**Raw totals and `Z` can disagree in direction, and blocks is where you will see it.** A
roster can sit below the average team's raw blocks and still show a positive `Z`. That is
the transform refusing to let a handful of elite shot blockers define "average" — blocks
carry the strongest compression, λ = −1.69. The `Z` is what the board ranks on and what the
win probability comes from. There is a note on the tab.

## Records

ADR-0014 (three sources) · ADR-0015 (DURANT H2H) · ADR-0016 (values computed in Python) ·
ADR-0017 (no GP adjustment) · ADR-0018 (tracker and profile on the DURANT basis) ·
ADR-0019 (punt builds re-standardise). ADR-0011 is superseded outright; ADR-0008, ADR-0009,
ADR-0012 and ADR-0013 in part.

## Carried, not resolved

- The Josh Lloyd games-played transcript was not captured; ADR-0017 rests on the quoted
  material already in the repo plus the video URL.
- `k_FG` and `k_FT` remain the least trustworthy constants in the model — Rosenof quotes
  their variances to one significant figure. Shipped provisional.
- `review_mock_draft.py` has **not** been repointed. It still reads the old Board layout and
  `adjusted_value`, so it will not run against this board until it is updated.
- The old `Punted` tick was on turnovers, which no longer has a row. Nothing was lost that
  the new model does not already do by construction.
