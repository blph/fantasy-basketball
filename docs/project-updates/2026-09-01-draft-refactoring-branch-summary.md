# `draft-refactoring` — three projections, DURANT H2H, no games-played adjustment

- Date: 2026-09-01
- Branch: `draft-refactoring` (6 commits)
- Status: **built, deployed to the live sheet, and verified there**
- Correction, same day: that verification was not sufficient. The deploy left the board
  with 1755 of its 1800 rank tags wrong, its ▲/▼ profile reading the wrong player, and the
  Settings guards dead — none of it visible to `pytest`, `ruff`, the harness, or the
  three-column `verify.py --sheet` pull, all of which were green.
  See [the bug report](../bugs/2026-09-01-draft-board-tag-rank-misalignment.md) and
  [ADR-0020](../decisions/ADR-0020-identity-anchored-references.md). Item 7 below turned
  out to be more than cosmetic: that dropdown was not wired to anything.

---

## In one paragraph

The board valued players one way from one projection: nine z-scores, discounted by
Rosenof's volatility multipliers, turned into value over replacement, then scaled by
projected games played. It now carries **three projection sources** with **three values
each**, ranks by **Basketball Monster's DURANT H2H**, and **scales nothing by games
played**. Values are computed in Python and written to the sheet as numbers; everything
that has to react on the clock stays a live formula.

## Why

Three findings from the `durant-actual` research contradicted the board:

1. **One projection is a single point of failure.** Identical math over Basketball
   Monster's two sources moves players ~20 rank places on average. On our own data Kawhi
   Leonard is DURH #6 on BMP and #21 on HBP; Embiid is #8 and #30. A single-source board
   cannot show that a ranking is contested.
2. **The valuation was wrong for this format.** Basketball Monster's guidance for
   head-to-head category leagues is DURANT H2H. Our G-score multipliers were documented on
   the sheet as "the second decimal is not reliable" and were being applied to three.
3. **Games played should not scale value.** It is the least predictable part of any
   projection, and the method the board now reproduces has no availability term at all.
   The override machinery was unused anyway — `GP Y-1/2/3` filled on 0 of 200 rows.

---

## The three values

| Value | What it is | Denominator |
|---|---|---|
| `ZSC` | Basketball Monster's plain `Value` — nine z-scores, TO inverted, nothing dropped | 9 |
| `ZSH` | The H2H weighting and minus-one rule on **untransformed** z | 7 |
| `DURH` | DURANT H2H exactly — Yeo-Johnson, standardise, weight, drop the worst live category | 7 |

`ZSH` exists to isolate what the Yeo-Johnson transform is worth. It shares DURH's weights
and drop rule and differs only in the transform, so any rank disagreement between them is
the transform's doing. Without it, adopting DURANT would have been an act of faith.

**Magnitudes are not comparable across value types** — ZSC averages nine, the others seven.
Only ranks are.

---

## What was built

### New — the Python pipeline

| File | What it does |
|---|---|
| `scripts/draft-board/sources.py` | Reads the three exports, normalises names, joins them. An unresolved player raises. |
| `scripts/draft-board/board_values.py` | Assembles the three values per projection, the punt builds, and the tracker constants. |
| `scripts/draft-board/build_data.py` | Resolves a same-dated set, scores it, prints a change report, writes `Data.gs`. |
| `tests/test_sources.py` | 31 tests — parsing, normalisation, the join. |
| `tests/test_board_values.py` | 22 tests — the values, the pools, the punt mechanism, the constants. |
| `tests/test_build_data.py` | 14 tests — date resolution, re-ranking, emission, determinism. |

Three additions to `scripts/bbm/bbm_reference.py`: `weighted_drop_one` (shared by DURH and
ZSH, so the two agree on what "drop one" means), `z_h2h`, and `build_z_h2h_pool`. Also
hoisted a call that was recomputing all nine category values nine times per player inside
the pool iteration.

`scripts/draft-board/gen_data.py` is **deleted** — its markdown-table parser has no
remaining input.

### Rewritten — the sheet

`Build.gs` went from 2257 to 2415 lines. `Board` survives as the **spine** (identity, the
HBP raw line, availability, market, every hand-edited column), which is what keeps
`Refresh data` writing to one tab and leaves the refresh machinery intact — it dropped from
73 columns to 28 and from ~90 formulas to two.

Nine tabs: `Draft Board` · `BMP` · `HBP` · `BMP-ALT` · `Board` · `Punts` ·
`Category Tracker` · `Settings` · `README`.

The Draft Board's 18 value columns are **generated** from `SOURCES × VALUE_KINDS` rather
than typed out, because the projection filter hides one source's six-column span and a gap
there would hide the wrong columns while every offline check still passed.

`HDR` moved 2 → 3 for the control strip (sort dropdown + three projection checkboxes), so
every external read range shifted: `A3:E202` → `A4:G203`.

### Design decisions worth naming

- **Colour goes where the information is.** The board is sorted by the active value column,
  so a gradient there reads as a value ramp. The other eight get no fill; their *tags*
  carry the disagreement signal instead. Nine gradients would be noise and eight would
  encode nothing you cannot read from row position.
- **Group separators are drawn as a left border on each group's first column**, never a
  right border on its last, so any subset stays correctly bounded when others are hidden.
- **`GONE` and `MINE` moved into the frozen pane.** They are the only cells you write during
  a draft and previously scrolled off the moment a value column was in view.
- **`CONTESTED` gets the only saturated fill on the tracker**; `WEAK` keeps red bold text
  but loses its red block. The marginal-value derivation says the next pick belongs in a
  contested category, so that is what should draw the eye.
- `warnBg` moved `#FFF3D6` → `#FFECC7`; it sat four hex points from the input yellow.

---

## Two corrections that would have shipped silently

**`K = k / w`, not `k × w`.** A weighted DURANT column's standard deviation is *exactly* its
weight, so `Z_team` in DH units is `w` times `Z_team` in z units. My first table used the
wrong pool *and* inverted the operation, which would have understated every win probability
while every number on the sheet still looked plausible. Asserted in `verify.py` and the
tests so it can be neither skipped nor applied twice.

**The Category profile must divide by the weight.** A fixed band is unreachable for any
category weighted below 1, so FG%, FT%, 3PM, STL and BLK — five of eight — would never have
fired. On the unweighted basis `CAT_BAND = 1.00` is *retained*: recalibrating the way
ADR-0013 did gives 2.54 flags per player and 10% unlabelled, against its targets of ~2.6
and ~9%.

---

## Five defects only the live deploy could find

Every one passed `pytest`, `ruff` and the harness. Every one broke the build in Google.
Each now has a check, verified by re-breaking it and watching the check fail.

| Defect | Why it was invisible offline |
|---|---|
| `clear()` does not remove merges | Only bites when rebuilding over a *different* layout, which building twice from scratch cannot reproduce. The harness now seeds an old-layout merge and rebuilds over it. |
| A conditional format rule may not reference another sheet | The disagreement highlight used a named range, and every named range lives on Settings. It took down the entire Draft Board rule set. |
| `sheetRef` allowed spaces unquoted | `Category Tracker!$G$7` never parsed; both profile columns returned `#ERROR!` on all 200 rows. The hyphen case (`BMP-ALT`) was handled — the space is the one that looks harmless. |
| Sheets reads `"3PM"` as a time | The tag rendered `#1 0.625` — 3:00 PM as a day fraction. It is the only category label that parses as anything else. |
| `readCheckState` ran after the wipe | A full rebuild silently discarded every `GONE` and `MINE` tick. Re-sorting preserved them, so it looked intentional. |

The last one mattered most: on draft day it is the difference between an inconvenience and
losing the board's state mid-draft.

A sixth, found during verification: bare `RANK()` gives ties the same number and skips one,
so the `#` column stopped being a permutation of 1..200. Six pairs tie at four decimals on
the current data. Fixed with an expanding-range `COUNTIF` tie-break.

---

## Deployment record

Pushed through `playwright-cli` into the bound `Code.gs`, in ~11KB chunks, verified by
character count before saving and again after a reload.

**A staging copy was made first and abandoned.** Copying the sheet creates a *new* Apps
Script project, whose consent screen asked for "see, edit, create, and delete all your
Google Sheets spreadsheets". I did not grant it. The live board's script already holds that
permission, so deploying there needed no new authorization. The copy is in the trash.

All hand-edited state was pulled out before anything was touched and restored afterwards:
7 `GONE` ticks, 1 `MINE` (Jokic), no notes, no GP overrides.

### Verified in the sheet

- No `#VALUE!`, `#REF!`, `#ERROR!` or `#NUM!` on any tab.
- All 200 `DURH` values agree with the Python pipeline — worst delta 0.0005, which is
  exactly the three-decimal display boundary.
- Ranks 1..200 contiguous, matching the calculation tabs.
- Draft state survives a full rebuild, reattached to the right players by name.
- The projection filter hides exactly one six-column block; group separators still bound the
  survivors.
- The tracker computes all five read states from one ticked player, `NORMSDIST` included.

---

## One thing to know before draft day

**Raw totals and `Z` can disagree in direction, and blocks is where you will see it.** A
roster can sit below the average team's raw blocks and still show a positive `Z`. That is
the transform refusing to let a handful of elite shot blockers define "average" — blocks
carry the strongest compression, λ = −1.69. The `Z` is what the board ranks on and what the
win probability comes from. There is a note on the tab.

---

## Records

New: ADR-0014 (three sources) · ADR-0015 (DURANT H2H) · ADR-0016 (values computed in
Python) · ADR-0017 (no GP adjustment) · ADR-0018 (tracker and profile on the DURANT basis) ·
ADR-0019 (punt builds re-standardise).

Superseded: ADR-0011 outright; ADR-0008, ADR-0009, ADR-0012 and ADR-0013 in part.

`docs/references/category-tracker-z-thresholds.md` was untracked research; it is now
committed, marked implemented, and carries the `K = k / w` derivation as §5a.

The playbook keeps §5, §6 and §6a **unchanged** and gains a note that they are superseded.
Rewriting them would destroy the reasoning this branch was built on — the argument for the
G-score is what makes the argument against it legible.

---

## What remains

### Blocking, before the board is used for a real draft

1. **`review_mock_draft.py` has not been repointed.** 898 lines with 468 lines of tests,
   built on the old Board layout and `adjusted_value`. It will not run against this board.
   This was deferred deliberately and flagged in the plan, not discovered late. It needs:
   the `COL_*` offsets remapped, `DB_ADJVAL` pointed at the BMP DURH column,
   `check_replacement` replaced (there is no replacement level any more — the equivalent
   stop-the-line check is that the pulled rank column is 1..N contiguous and the value
   column descends), `tracker_trace` rewritten for the eight-category Win % model, and
   `GKEYS`/`p.g` removed with the g-scores.

2. **A real refresh has never been run end to end.** The board was built from `Data.gs`
   step by step. `Draft Board ▸ Refresh data` — the path used for every subsequent
   projection update — has not been exercised against the live sheet. The reorder path in
   particular is now the *normal* case and deserves a deliberate test with a changed
   200-player set before it is met for the first time on draft week.

### Worth doing, not blocking

3. **The turnovers gap.** The tracker has no TO row because DURANT H2H prices turnovers at
   zero. The league settles them every week. If it bites, the honest fix is a ninth row on
   the plain-z basis with its own `k = 0.485`, clearly marked as a different basis — not a
   re-weighting of DURANT H2H, which would stop being DURANT H2H.

4. **`k_FG` and `k_FT` are provisional.** Rosenof quotes their variances to one significant
   figure, which puts `k_FG` anywhere in 0.31–0.37. The calibration procedure is in §9 of
   the thresholds document and needs a season of weekly results.

5. **The games-played research is uncaptured.** ADR-0017 rests on the material already
   quoted in the repo plus the video URL. The transcript would make it properly sourced.

6. **`valuation.py` and `bbm_reference.py` both exist**, implementing different models.
   `docs/roadmap.md` now flags that Phase 2 has to choose which one it ports.

7. **Cosmetic.** The sort dropdown clips to `BMP · DUR` at its current width. Harmless, but
   it is the control you look at to know what the board is sorted by.

### Not started

8. **The `Injuries` column is empty by design.** It has formatting rules for `OUT` and
   `GTD`/`Q`/`DTD` and nothing feeds it.

9. **`XRank` is still empty**, as it was before this branch.

---

# Addendum — the board did not actually reproduce Basketball Monster's numbers

- Date: 2026-09-01, later the same day
- Status: **fixed, deployed to the live sheet, and verified there against Basketball
  Monster's own published columns** — a check that did not exist before this work

## What was wrong

Comparing the deployed board against basketballmonster.com on the same projections, Nikola
Jokic read DURH **1.082** against their **1.09** and ZSC **1.028** against their **1.02**.
Across the 234 players they publish: ZSC MAE 0.0075 and DURH 0.0079, outside two-decimal
display rounding on 73 and 77 rows respectively, and the **dropped-category tag disagreed on
15 of 234** — a claim printed on the tab you draft from.

Everything borrowed was already right. Refitting the λ against their published `D*V` columns
recovers our own to three decimals; the H2H weights recover to four; the drop rule, the
divisor and turnovers-at-zero all hold; the `BMP` export matches their page to within display
rounding. **The gap was entirely in the pool constants** — the mean, SD and attempt-weighted
rate each category is standardised against. Their SDs run 1–4% wider than a top-156 of these
projections, in both directions by category, and no pool reproduces both moments: the means
want N between 143 and 177, the SDs anything from 85 to 318.

The decisive measurement is that this reproduces using **their own published per-game lines**
— top-156 by their own `Value`, RMS SD error still 1.65%. So it was never our data, our
export's freshness, or the pool iteration. Basketball Monster standardises against a wider
distribution than the projections they publish.

The reverse-engineering doc had this diagnosed at §III.2 and concluded **"Practical effect:
none, if you derive your own pool from your own projections."** That was wrong for a board
whose stated purpose (ADR-0015) is to publish their numbers. That line is now corrected.

## Why every gate was green

The same shape as the tag-misalignment bug above. `pytest` tests the arithmetic against
itself, and `pool_params` is correct — it computes the mean and SD of the pool it is handed.
The harness compares formula strings. `verify.py --sheet` compares the sheet to `Data.gs`,
and both carried the same wrong number. §IV.3 of the reverse-engineering doc had even
*measured* `Value` at MAE 0.0075 and recorded it as an accuracy figure rather than a defect.

**Nothing in the repository compared our output to Basketball Monster.** Every check
verified internal consistency, and the board was internally consistent throughout.

## What changed

**Recover their constants instead of deriving our own**, for the two sources where they
publish them ([ADR-0021](../decisions/ADR-0021-borrowed-bbm-pool-constants.md)). A published
value is exactly linear in the stat, so a regression against their own columns returns the
mean and SD they used; the percentage categories take a two-variable fit that identifies the
pool rate rather than assuming it; the DURANT layer searches λ and the rate together against
their published column.

**Nothing is hardcoded.** The constants are a property of a projection set that moves, so
they are refitted every refresh and written beside the export they belong to, paired by date
and rejected three ways if that pairing breaks. **λ moved onto the same footing** — it was
the last borrowed constant frozen in source, with the same invisible-staleness problem, and
is now the fitter's search seed rather than the board's transform. The only Basketball
Monster constants still in source are the H2H weights, which are published rather than
fitted.

**Outliers are rejected from the fit** at a cut derived from the residual spread, not typed.
Basketball Monster revises between exports, and one stale row does not merely mispredict
itself — it tilts the regression and corrupts constants applied to all ~510 players.

New: `calibrate_bbm.py` (scrape, fit, report), `bbm_constants.py` (read, and refuse the wrong
file), `verify.py --published`, `score_source(..., params=...)`, a `Standardised against`
column on Settings, and 37 tests including a round trip that recovers constants deliberately
unlike both the pool's own and the module's seed.

## Verified in the sheet

| | before | after |
|---|---|---|
| ZSC vs their `Value` | MAE 0.0075, 73 of 234 outside rounding | **MAE 0.0034, 0 of 189** |
| DURH vs their `DUR H2H` | MAE 0.0079, 77 of 234 outside rounding | **MAE 0.0030, 0 of 189** |
| DURH dropped category | 15 of 234 wrong | **3 of 189, all ties inside 0.009** |

Jokic now reads `+1.089 #1 3PM` and `+1.022` against their 1.09 and 1.02. All nine tabs
carry no error values; 1800 values and all 1800 rank tags agree between the sheet and
`Data.gs`.

## What this does not fix

1. **`BMP-ALT`'s export has drifted from Basketball Monster's live Bonus projections.** Six
   players — Jamal Murray at 65 games against our 73, DeRozan at 17.0 points against our
   14.7 — have genuinely different stat lines. The constants are recovered correctly around
   them, but those players' *values* are computed from a stale line, so `verify.py
   --published` fails BMP-ALT on all four gates and should. **A same-dated re-export of all
   three sources is the fix**, and it is the user's export step, not something the pipeline
   can do. `BMP` has no such drift.

2. **The two percentage categories stay imperfect** (§III.1). Their DURANT percentage input
   is not quite our impact column — Spearman 0.998, not 1.0 — leaving a residual of about
   0.010 and 0.017 that no constant-fitting removes. It is why three dropped-category ties
   remain.

3. **Punt ranks moved.** ADR-0019 has a punt re-derive the pool; under fixed borrowed
   constants there is no pool to re-derive, so on BMP a punt is now a discount applied after
   standardising. Leaving punts on the derived path would have been worse and quieter: it
   breaks the identity that a punt weight of 1.0 reproduces the unpunted DURH.

4. **A refresh now needs a live subscription and a working browser session**, and hard-fails
   without a same-dated fit. Intended, and also a new way for a refresh to be impossible on
   draft night.

## One trap found on the way

**Do not run `Step 1 — Settings only` against a finished board.** Recreating the Settings tab
makes Sheets rewrite every formula that pointed into it: the Draft Board's tier formula
became `IF($AC6>#REF!*$AD6,…)` on all 200 rows and `TIER`/`RND` went to `#REF!`. `step1` does
call `defineNames` afterwards and that is not enough — redefining a name does not repair a
formula whose text has already been rewritten. Only a rebuild that writes those formulas
again does. Documented in the operating manual and in AGENTS.md.
