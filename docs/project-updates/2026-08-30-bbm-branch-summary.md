# Branch summary: `bbm`

- Date: 2026-08-30
- Branch point: `407107d` (2026-08-29, "docs: record the math audit and the quant-vs-expert procedure")
- Scope: everything produced on the `bbm` branch, what is deployed, and what it leaves open.
- Constraint honoured: no player row, projection, or ADP value appears below. All figures are
  aggregate ([ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md)).

---

## At a glance

Nine commits over two days. **+3,604 / −77 lines across 24 files: 14 new, 10 modified.**
Tests go from 90 to 198.

Four bodies of work landed:

| | Workstream | Outcome |
|---|---|---|
| A | **DURANT** reconstructed from its published description | Eleven Board columns and two Draft Board columns, **deployed and verified live** |
| B | **Category distribution analysis** of all nine scoring categories | Five analysis modules, a committed review, one live mis-calibration found |
| C | **Correctness fixes** to three checks and to the sheet deploy path | All three fixed; the `defineNames` trap documented after it destroyed the board twice |
| D | **Parser consolidation** in `gen_data.py` | One parser, sixteen tests, output proven byte-identical |

The branch also confirmed something worth stating on its own: **Basketball Monster's standard
rankings are already ours.** `valuation.py` reproduces their published ranking at Spearman
0.9979.

---

## The nine commits

| # | Commit | Date | Files |
|---|---|---|---|
| 1 | `c900014` docs: record what DURANT actually does, and where it came from | 08-29 | 2 files, +294 |
| 2 | `3167056` feat: reconstruct DURANT, and confirm our z-layer is Basketball Monster's | 08-29 | 3 files, +530 |
| 3 | `befe394` fix: stop three checks from lying about the board | 08-29 | 4 files, +106/−26 |
| 4 | `d9ec213` feat: carry DURANT on the board as a second opinion | 08-29 | 4 files, +308/−5 |
| 5 | `4a0d1fe` feat: add a surgical deploy step for the DURANT columns | 08-29 | 1 file, +48/−2 |
| 6 | `6571cb2` fix: make defineNames survivable, and finish the DURANT deploy | 08-30 | 1 file, +66/−6 |
| 7 | `2e37c7d` fix: label the DURANT block, and rebuild every consumer of a named range | 08-30 | 1 file, +54/−4 |
| 8 | `4b394a8` refactor: give the provider export one parser, and cover it with tests | 08-30 | 3 files, +231/−34 |
| 9 | `52c702f` feat: value the percentage charts, and report on category normality | 08-30 | 14 files, +1,974/−6 |

Commits 4 through 7 are one deploy told in four parts: build the columns, add a surgical step
to push them, survive the failure that step caused, then finish the labelling. Nothing between
them was a rewrite. Each fixed a defect the previous one exposed.

---

## Workstream A: DURANT as a second opinion

### The reference document

[`docs/references/basketball-monster-durant.md`](../references/basketball-monster-durant.md),
357 lines across 21 sections. Basketball Monster's method sits behind a paid membership, so
the document recovers it from podcast transcripts and from the column tooltips on their public
pages. It is committed because re-obtaining it is expensive.

What it establishes about the mechanism: DURANT applies a Yeo-Johnson power transform per
category, standardises, applies fixed unpublished weights, and drops or half-weights each
player's own worst category. It is per-game and carries no availability term. It is not a
percentile or rank transform, despite what "Applying Normalised Transformations" suggests.

Three corrections to claims that circulate:

- Lloyd states that DURANT does **not** fix the FT% problem, contrary to what gets repeated.
- "DURANT 2.0" is a redated in-place edit of the original article, not a new method.
- DURANT has **no replacement level at all**, which is the one place our board does more than
  theirs.

### The reconstruction

[`scripts/draft-board/durant.py`](../../scripts/draft-board/durant.py), 231 lines, 42 tests.

It reads the `Pool` that `valuation.py` builds, so the pool, the percentage impacts, and the
turnover convention are shared rather than forked. Yeo-Johnson is implemented directly
(`yeo_johnson`, `yj_loglik`, `fit_lambda`) rather than pulled from SciPy, which was not a
declared dependency at the time. `LLOYD_WEIGHTS` holds the fixed weights. `apply_minus_one`
implements the minus-one rule across all four regimes the tooltips document: `none`, `roto`,
`h2h`, `durant_h2h`.

**The lambda bracket is `[-15, 15]`, not the `[-2, 2]` SciPy defaults to.** The percentage
impacts are small signed numbers clustered near zero, and `fg_impact` peaks near −6.9 on real
data. A narrow bracket pins at the edge of the search and returns the wrong transform while
looking fine. This is the branch's most reusable trap.

### Two measured results

**Their standard `Value` is our z-score layer.** Measured against Basketball Monster's free
rankings table: every counting category regresses on its per-game stat at R² ≥ 0.9948, so it
is a plain z with no transform. The pool reproducing their recovered means and SDs is N = 156,
the same Q we use. Their `Value` is the arithmetic mean of the nine category values where ours
sums, which cannot reorder anyone. Our z-scores reproduce their published ranking at
**Spearman 0.9979, mean 3.11 places**. There is nothing to reconcile on that layer.

**The reconstruction behaves like the real thing.** Of the nine players Lloyd named in 2023 as
moving under DURANT that appear on our board, **eight move in the direction he published**, on
a different season and from an independent implementation. Run over Basketball Monster's own
stat lines it also reproduces the headline oddity DURANT is marketed against.

### The decision: [ADR-0014](../decisions/ADR-0014-durant-as-a-second-opinion.md)

**DURANT ships as a column. It does not drive the ranking.** Three reasons:

1. **The premise does not survive our format.** DURANT normalises the *marginal* distribution.
   A category is won by a 13-man team total, where the central limit theorem flattens that skew
   long before it reaches a win probability. Rosenof cites Lloyd by name for the non-normality
   premise and still declines to transform, on exactly this argument.
2. **The cost is not marginal.** Comparing per-game against per-game, adopting DURANT moves
   players a mean of **18.6 places, with 135 of 200 moving ten or more**. In a category league
   you win blocks with blocks, not with rank order.
3. **Its punting philosophy contradicts ours.** DURANT decides for you which category each
   player concedes. Our board makes you choose a build and values everyone against it, which is
   the point of the Punts tab and of `PUNT_WEIGHT`.

The governing principle is already written down in
[quant-vs-expert-reconciliation.md](../references/quant-vs-expert-reconciliation.md): take
their information, never their rank. A column is information.

### What shipped in `Build.gs`

**Eleven Board columns:** `dFg`, `dFt`, `d3`, `dPts`, `dReb`, `dAst`, `dStl`, `dBlk`, `dTo`
(the nine transformed categories), `durTot` (the DURANT H2H total: turnovers dropped, then the
worst remaining category), and `durRank`.

**Two Draft Board columns:** `DURANT` (its rank) and `vs us` (our rank minus its rank), so a
disagreement is visible on the clock without changing the order you draft in.

Every new column sits after the existing ones, after `Notes` on the Board and after the hidden
mirror block on the Draft Board. `Refresh data` writes by fixed position and the Category
Tracker bakes in column letters, so a shift would have cost a full rebuild and every hand edit
with it.

Supporting machinery:

- `fitDurantLambdas()`, a `Fit DURANT lambdas` menu item running the MLE over the live pool and
  writing the nine values to Settings. The means and SDs beside them are formulas and follow
  the pool on their own. **Lambda does not, so a stale lambda is a wrong transform, silently.**
- `step1c_DurantColumns`, a surgical deploy writing only `dFg` through `durRank`, leaving
  columns 1 to 73 untouched. A full `writeBoardFormulas` would reseed `My GP Est` from
  `Projected GP` and take any override with it.
- `step1d_BoardFormulas`, the one step that declares named ranges, followed immediately by
  every consumer. It doubles as the repair path.
- `writeBoardHeaderRow`, split out of `writeBoardData` so both callers share it.
- A DURANT band in `formatBoard`, in its own colour rather than the G-score purple it exists to
  be compared against, plus number formats and column widths.
- A `README_ROWS` entry, regenerated into the cheat sheet.

`DUR_W` on Settings holds the nine weights, defaulted to Lloyd's published pre-DURANT hand
weights because DURANT's own are withheld. Zeroing them costs nothing.

**It is a reconstruction, not a copy.** Two components Lloyd names, waiver-wire availability
and inter-category correlation, are not modelled at all, because no public description of
either exists. The column is labelled as a reconstruction on the sheet's own README, and it
must not be quoted as "what Basketball Monster says".

---

## Workstream B: category distribution analysis

### Five new modules under `scripts/analysis/`

| Module | Lines | Job |
|---|---|---|
| `category_series.py` | 153 | The pool and the nine valued series. Imports `valuation.py`'s `fg_impact` / `ft_impact` rather than restating them, so it cannot drift from the sheet. |
| `normality.py` | 313 | The test battery: Shapiro-Wilk, Anderson-Darling, D'Agostino-Pearson K², ECDF-vs-Normal, critical bandwidth, bimodality coefficient, floor mass, and the tier rubric. |
| `implications.py` | 191 | `team_total_moments`, `band_yield`, `rank_int_movement`. Turns a verdict into something to act on or dismiss. |
| `report.py` | 423 | Rendering only. Keeps the statistics testable without parsing prose, the same split `valuation.py` and `verify.py` already use. |
| `category_distributions.py` | 238 | The CLI. Nine histograms and the report from one pool in one invocation, so a caption cannot disagree with the table beside it. |

Jarque-Bera was deliberately omitted: it reads the same two moments as K² and refers them to a
chi-square(2) null it approaches only slowly, so it would restate K² less accurately rather
than offer a second opinion. Hartigan's dip test was deliberately not hand-rolled.

### Two chart defects fixed

The nine histograms plotted FG% and FT% as **bare rates**, which AGENTS.md forbids valuing, and
covered all 200 export rows while the board standardises over the converged 156-player pool.
Both are fixed. The two percentage charts are now volume-weighted impact taken from
`valuation.fg_impact`, over the pool the z-scores are actually built on.

### The verdict

**None of the nine is Normal, every test says so, and that finding is nearly useless on its
own.** At n = 156 Shapiro-Wilk rejects all nine, so it separates none of them. The verdict
tiers key off effect size and the gap from Normal instead; no p-value reaches a verdict.

| Tier | Meaning | Categories |
|---|---|---|
| A | normal enough | *none* |
| B | skewed but usable | 3PM, PTS |
| C | materially non-normal | FG% impact, REB, AST, TO |
| D | wrong shape for a z | FT% impact, STL, BLK |

Tier D does not mean worse than C. It means the mean and SD stop describing the population, so
the z still orders players correctly while the *distance* between them stops being a quantity
to reason with.

### The three findings

**1. BLK is where the board pays.** At z = −1 the pool holds **3.2%** of its players where a
Normal promises 15.9%: five players against the roughly 25 the ±1.00 band implies. Blocks are
bounded at zero and the pool mean sits barely one SD above that bound, so the left tail the
z-score prices largely cannot exist.
[ADR-0013](../decisions/ADR-0013-category-profile-column.md) already records this as a known
limitation in the words "roughly five players". This is that limitation with a derivation
behind it. The band wants reading as a yield, not a probability.

**2. 3PM is not bimodal.** It has one mode and the smallest gap from Normal of the nine. The
earlier chart's second hump was 39 distinct reported values drawn into 22 bins, an artifact of
snapping bin edges to whole reporting quanta. That floor is now lifted for low-cardinality
columns.

**3. STL fails on discreteness, not shape.** Sixteen distinct values across 156 players, so
roughly ten players share each value and Shapiro-Wilk is measuring the provider's 0.1 rounding
grid. SciPy issues no warning. The battery now prints a distinct-value count and marks the
continuity-assuming tests invalid below 30.

The **bimodality coefficient is reported as a negative result**: it is wrong in both directions
on this data, reading "unimodal" for the two categories whose second mode survives 2.89× and
1.93× Silverman's bandwidth, and above its flag for a category with exactly one mode. A test
class pins this so nobody "fixes" it later. Critical bandwidth is what actually finds modes.

### The missing evidence, supplied

ADR-0014 declined to transform on a central-limit argument **that no code in the repository
computed**. A seeded 20,000-draw simulation of 13-man roster totals now supplies it:

| Category | Player skew → team total | Player excess kurtosis → team total |
|---|---|---|
| FG% impact | +1.07 → +0.27 | +1.30 → +0.05 |
| FT% impact | −1.52 → −0.40 | +7.07 → +0.32 |
| BLK | +1.62 → +0.39 | +3.83 → +0.17 |
| AST | +1.01 → +0.26 | +1.21 → +0.07 |
| STL | +0.96 → +0.26 | +1.24 → −0.02 |

Every category lands inside the approximately-symmetric band at roster level. The argument
holds.

### Recommendations, from [the review](2026-08-30-category-distribution-normality.md)

- **Do not transform.** Rank-based inverse normal was measured for completeness: Spearman
  0.967, **11.2 mean places**, 93 of 200 moving ten or more, five crossing the drafted-156
  line. It is cheaper than Yeo-Johnson and strictly more destructive, because it maps every
  category onto an identical Gaussian. It would also **destroy the mean-zero identity the
  impact columns depend on**, which is why the board divides by SD with no centring term, is
  pinned by `tests/test_valuation.py`, and is a live `Build.gs` formula.
- **Do not winsorize.** At n = 156 a 99th-percentile cap touches about 1.5 players per tail
  while changing the SD, and therefore every z, in that category. On FT% impact the low tail
  *is* the signal.
- **Read the ±1.00 band as a yield.** The strong side is well calibrated at 13 to 17% per
  category. The weak side on blocks is 3.2%. Documentation change, no math change, and the only
  place the board is genuinely mis-calibrated today.
- **Add a post-refresh falsifier.** Re-run after each export and check that no category changed
  tier. Nothing would notice today.
- **Route bounded, win-probability saturation to its own ADR.** It needs no distributional
  assumption and it is the one alternative these measurements strengthen.

### Two live corrections it surfaced

**Two verdicts depend on a re-seed.** The sheet held the single-pass pool. The two pools share
150 of 156 members, and running the battery over both moves **AST and TO from B to C**. This is
a reason to run the re-seed, not a reason to distrust either number. (The re-seed has since
been run, in commit 6.)

**`basketball-monster-durant.md` quoted two different pools without saying so**, reporting BLK
skew as +1.53 in one section and +1.60 in another. The canonical converged figures are BLK
+1.62 / +3.83 and FT% impact −1.52 / +7.07. Neither figure was wrong; they answer different
questions. This happened because nothing in the repository computed a skew until now, so every
such figure was produced ad hoc in a session and could not be re-derived. The document is
annotated; ADR-0014 is Accepted and was left untouched.

### [ADR-0015](../decisions/ADR-0015-analysis-tooling-dependencies.md): the dependency record

`numpy` and `matplotlib` were imported by `scripts/analysis/` and **declared nowhere**,
resolving from a user-site install on the owner's machine. CI installs `pip install -e ".[dev]"`
and nothing else, so the analysis scripts could never run there and no test could import them.
Nothing failed, because nothing tested them. The gap was invisible rather than absent.

`numpy`, `matplotlib` and `scipy` are now declared in the `dev` extra with version floors. The
project still ships **zero runtime dependencies**. They go in `dev` rather than a separate
`analysis` extra so that CI installs them and `pytest` actually covers that code, which is the
whole point. The precedent is narrow: "analysis tooling that never enters `src/`". Anything the
pipeline, database, or an app imports is still a runtime dependency needing its own ADR.

The alternative was hand-rolling Royston's algorithm and the Stephens tables. In a repository
whose first stated priority is that a wrong number that looks right is worse than no number, an
unvalidated statistical test is precisely the thing not to write.

---

## Workstream C: fixes to checks that were lying

### F2, `Left @pos` on the Draft Board

The formula excluded players ticked `Gone` but not players ticked `Mine`, so your own picks
kept counting as available at their position. On the live board that **overstated 54 of 200 rows
by up to three players**, and it erred toward "you can wait", which is the wrong direction for a
scarcity column. Nothing made you tick both boxes. `Mine` is now excluded too, and the cheat
sheet row was rewritten to match.

`harness.js` does not pin this formula, so the fix was proven in the sheet.

### F1, `verify.py` reporting a correct board as broken

Run as documented, `verify.py` converges the pool. The sheet had never been re-seeded, so the
two were different 156-player sets and **all seven pool constants reported DIFFER against a
board correct in all 6,600 cells.** A false alarm that looks identical to a genuine break.

`constants()` was extracted, and `explain_mismatch()` now re-checks against the other pool and
either names the convergence difference with its next action or rules it out. A false alarm
became a diagnosis.

### F6, `converge_pool` mutating its caller's data

It reassigned `seed` on the caller's players and left it reassigned, so anything reading `seed`
afterwards got this function's output instead of the provider's rank. That silently turned a
correlation against the provider into a correlation against ourselves, and it made the F1
diagnosis report the opposite of the truth until it was fixed. The seed is now restored in a
`finally`, on every exit path including the raise.

### The `defineNames` trap

Deploying the DURANT columns turned the whole board to `#REF!`. Twice.

`defineNames` removes the names it owns before re-adding them. **Removing a named range does not
merely break dependent formulas. Sheets rewrites their text to `#REF!`, permanently, and
re-adding the name a millisecond later does not bring them back.** The full build never shows
this, because it writes every formula immediately afterwards. Calling `defineNames` from
`step1_Settings`, which rewrites only Settings, therefore destroyed every computed column on the
Board.

Three changes came out of it:

1. `defineNames` resolves every range before removing anything, so a bad range makes the whole
   operation a no-op instead of a board-wide failure.
2. `step1_Settings` no longer declares names at all.
3. `step1d_BoardFormulas` is the one step that does, followed immediately by both consumers in
   the order the full build uses. It is also the repair path, and far cheaper than the full
   rebuild that was otherwise the only way back.

**The hazard is wider than that.** `defineNames` breaks every consumer, and there are four:
Board, Settings, Draft Board, and Category Tracker. Rewriting only the first two left the Draft
Board's `Category profile` and `Left @pos` as `#REF!`. `step1d` now rebuilds all four in one
pass, and `buildDraftTab` carries the checkbox state across.

### The unlabelled block, and three plumbing misses

The eleven DURANT columns shipped with **no header band and no column labels**. Every other
block on the Board says what it is; a block of unlabelled numbers is worse than not shipping it,
because a column you cannot name is a column you cannot check. Three causes: `step1d` wrote
formulas but never the header row, and could not, because the labels lived inside
`writeBoardData`, which also rewrites raw data across the full width and would have blanked the
hand-edit columns; and `formatBoard` had no block entry for the DURANT range, so it got no band
and no number formats.

`RANK()` against the `B_DURTOT` named range returned `#N/A` on all 200 rows even though the name
resolved to the right cells and the values were numeric. The punt ranks have always used an
explicit range derived from the column map and have always worked, so DURANT rank now matches
them. The column letter is still derived via `a1col()`, never written literally.

Two plumbing misses left the new columns empty: `writeBoardFormulas` builds rows to `B_LAST` but
writes contiguous blocks explicitly, and the DURANT block had no `writeBlock` call; and `D_LAST`
was still `D.hTo`, so Draft Board rows were only ever built 33 wide. `step1_Settings` also
ensured only 75 rows while the DURANT block starts at 78, so the block would have been written
outside the grid.

---

## Workstream D: one parser for the provider export

`gen_data.py` read `sys.argv` and ran its parse-assert-write body **at import time**, so it
could not be imported at all. Under pytest that was not a failure but a side effect: `import
gen_data` parsed nothing and **wrote a file named `-q`**, taking pytest's own flag as the output
path.

The parse body moved into `main(argv)`. The three integrity asserts became `check()`, which
returns named complaints instead of raising on the first one. `load()` is parse-plus-check, so a
caller cannot get players without the guard against a dropped or duplicated player: the defect
class that shifts every seed rank below it, moves the pool boundary, moves all eight pool
constants, and still computes.

`COLS` moved here from `verify.py`, which now imports it. The file that writes the column order
owns it.

**Behaviour is unchanged, and proven so.** `Data.gs` regenerates byte-identical (md5
`c844f09603390a5c11f3465eae22e21f`) and `verify.py` prints the same pool constants before and
after.

The file had no tests. It has sixteen now, on synthetic fixtures.

A new AGENTS.md boundary records the rule: do not write a fourth parser. A second parser that
disagrees produces two internally consistent boards that differ.

---

## Tests

**90 → 198 collected, a gain of 108.** All pass, and `ruff check .` is clean.

| File | Tests | Note |
|---|---|---|
| `tests/test_durant.py` | 42 | New. Yeo-Johnson, lambda fitting, the minus-one regimes, the pool wiring. |
| `tests/test_normality.py` | 37 | New. Six classes, including `TestBimodalityCoefficientIsWrongInBothDirections`, which pins a negative result. |
| `tests/test_gen_data.py` | 16 | New. `TestCellHelpers`, `TestParse`, `TestCheck`, on synthetic fixtures. |
| `tests/test_category_series.py` | 11 | New. The series and their metadata. |
| `tests/test_valuation.py` | 29 → 31 | The `converge_pool` seed restoration. |
| `tests/test_export_yahoo_rankings.py` | 24 | Unchanged. |
| `tests/test_review_mock_draft.py` | 37 | Unchanged. |

`tests/conftest.py` now puts `scripts/analysis/` on the import path alongside
`scripts/draft-board/`, and carries its own warning: both go on a flat path, so module names are
global and a future `scripts/draft-board/normality.py` would shadow the analysis one silently
and in import order. The real fix is a package under `src/`, which is Phase 2 work.

---

## Documentation and governance

- **[ADR-0014](../decisions/ADR-0014-durant-as-a-second-opinion.md)** and
  **[ADR-0015](../decisions/ADR-0015-analysis-tooling-dependencies.md)**, both Accepted, both
  with their decision-log rows, both committed alongside the change they describe.
- **[basketball-monster-durant.md](../references/basketball-monster-durant.md)**, 357 lines:
  mechanism, sourcing (primary from Lloyd's own words, primary from Basketball Monster,
  secondary, and an explicit "not found" section), reproduction targets, corrections to claims
  that circulate, and what it would take to get certainty.
- **[The normality review](2026-08-30-category-distribution-normality.md)**, 162 lines, the
  committed aggregate companion to the gitignored generated report.
- **Three new AGENTS.md boundaries:** do not write a fourth parser; do not describe the 200-row
  export when you mean the pool; the FG%/FT% rule applies to charts and analysis, so plot
  `fg_impact`, not `FG%`.
- **AGENTS.md dependency paragraph rewritten** to state the zero-runtime-dependency position
  and the narrow dev-dependency exception, plus a new command entry for
  `category_distributions.py` and two new "Deeper docs" links.
- **Cheat sheet regenerated** from `README_ROWS`: a new `DURANT` row, and a corrected
  `Left @pos` row reflecting the F2 fix.

---

## Deployment status

The DURANT columns are **deployed and verified live in the sheet**:

- 6,600 of 6,600 Board cells agree with Python.
- `Adj Rank` and all 1,800 punt rank cells exact.
- DURANT rank populated on all 200 rows; the sheet's DURANT total and rank match Python 200/200.
- The Apps Script fitter and `durant.py` agree on all nine lambdas.
- All five tabs free of errors.
- **The pool is converged for the first time.** `Re-seed pool from current ranks` had never been
  run, so `verify.py` now passes in its documented default mode instead of reporting seven false
  differences.

Workstreams B, C (except the `Left @pos` formula, which is live) and D are repo-only and need no
deploy.

---

## What this branch leaves open

- **The AST and TO tier verdicts** were measured against both pools before the re-seed ran. They
  should be re-measured now that the sheet is converged.
- **The post-refresh falsifier does not exist yet.** Nothing checks that a category's tier
  survived an export.
- **Bounded, win-probability saturation needs its own ADR.** ADR-0014 leaves it open and the
  normality measurements strengthen it. It should not arrive via a normality report.
- **DURANT's two unmodelled components**, waiver-wire availability and inter-category
  correlation, have no public description to reconstruct from.
- **The stale-lambda hazard.** Lambda is a fit, not a setting, and it does not follow the pool.
  Re-run `Fit DURANT lambdas` after any refresh that moves the pool.
- **The flat test import path** is a shadowing hazard until Phase 2 puts this code in a package.
