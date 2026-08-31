# Branch summary: `durant-actual`

- Date: 2026-08-31
- Branch point: `407107d` (2026-08-29, "docs: record the math audit and the quant-vs-expert procedure")
- Scope: everything produced on the `durant-actual` branch, what it leaves open, and what it inherited.
- Constraint honoured: no player row, projection, or ADP value appears below. Every figure is an
  aggregate ([ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md)).

---

## At a glance

Nine commits in one day. **+1,910 / −1 lines across 6 files: 5 new, 1 modified.**
Tests go from 90 to 115.

The whole branch is one arc: take Basketball Monster's valuation, work out what it actually
computes, and then rebuild it so that using the method needs neither their subscription nor their
file format. Three outcomes:

| | Outcome | Where |
|---|---|---|
| A | **The method, specified.** 699 lines in five parts. Part I is a standalone algorithm — inputs, steps, constants, worked example — that depends on nothing external. | [`docs/references/basketball-monster-projections-reverse-engineering.md`](../references/basketball-monster-projections-reverse-engineering.md) |
| B | **The method, implemented.** 401 lines, standard library only, so no runtime dependency and no ADR. Takes projected season totals from any source. | [`scripts/bbm/bbm_reference.py`](../../scripts/bbm/bbm_reference.py) |
| C | **The method, measured.** Against their published columns, and against 25 synthetic tests for the arithmetic that is easy to get silently wrong. | [`tests/test_bbm_reference.py`](../../tests/test_bbm_reference.py) |

Measured accuracy, from [`scripts/bbm/README.md`](../../scripts/bbm/README.md) — their exports are
gitignored, so these are recorded rather than committed as a test:

| | `Value` MAE | Spearman | Max rank move |
|---|---|---|---|
| Projection source A | 0.0075 | 0.99942 | 8 |
| Projection source B | 0.0050 | 0.99968 | 6 |
| `DURANT` | 0.0083 | 0.99902 | — |
| `DURANT H2H` | 0.0079 | 0.99919 | — |

The single most useful conclusion for us is in Part II: **their two projection sources share the
valuation math exactly and still move players about twenty rank places.** Which projections
produced a number matters more than which valuation did.

---

## The nine commits

| # | Commit | Subject | Diff |
|---|---|---|---|
| 1 | `82f7e56` | docs: reverse-engineer Basketball Monster's valuation, and solve DURANT | +835 |
| 2 | `ad2bb1d` | docs: track the bbm branch summary | +471 |
| 3 | `efc7381` | docs: link the Basketball Monster reference from AGENTS.md | +1 / −1 |
| 4 | `2ef24bc` | docs: correct the DUR H2H example, and record what the UI actually offers | +25 / −7 |
| 5 | `631af7d` | docs: correct DURANT H2H, and add projection sources, punts and Conf | +244 / −33 |
| 6 | `e7aead8` | docs: replace two in-sample fits with cross-validated ones, and sharpen "open" | +115 / −33 |
| 7 | `0265182` | docs: make section 11 a procedure, and name the input path behind every number | +169 / −86 |
| 8 | `a39ea00` | feat: reimplement Basketball Monster's valuation from scratch | +739 |
| 9 | `0177304` | docs: restructure as a specification that needs no Basketball Monster access | +497 / −1027 |

What the table hides is the shape. Commit 1 is the original reconstruction; **four of the eight
that follow exist to correct it** (4, 5, 6, 7). Commit 9 is not an edit but a change of purpose —
the document had been organised around their website, open this page, set this dropdown, export
this file, which is a scraping guide. It was rewritten as a specification, which is why it loses
1,027 lines while gaining 497.

Commit 3 is worth carrying forward as a lesson: `CLAUDE.md` is a symlink to `AGENTS.md`, so
staging the symlink path stages nothing and the edit is silently left behind. Edit `AGENTS.md`.

---

## What the reconstruction established

Their standard `Value` is a nine-category z-score average, and Part I states it as six steps:

1. **Per-game rates.** Divide season totals by games; drop anyone projected for zero games, who
   cannot be rated and will wreck the pool statistics.
2. **The pool.** The top *Q* players by value, where *Q* = teams × roster spots = 156 for us.
   Circular by construction, so it iterates to convergence.
3. **The nine category values.** Seven counting categories are plain z-scores against the pool,
   with **turnovers negated and nothing else**. The two percentages are scored as a
   *volume-weighted impact*, not a bare rate — the pool rate is attempt-weighted, and 80% on four
   attempts is not 80% on ten.
4. **`Value`, `Rank`, `Round`.** `Value` is the **mean** of the nine, not the sum; `Round` is the
   rank divided by team count, rounded up.
5. **DURANT.** A Yeo-Johnson power transform per category, standardised against DURANT's own pool
   — the transform changes the distribution, so the pool constants differ — then **each player's
   single worst category is dropped** and the surviving eight averaged.
6. **DURANT H2H.** Turnovers are zeroed for everyone first, then seven survive the drop, and every
   category is weighted before averaging.

Two structural findings that matter beyond this provider:

- **Made field goals already include threes.** A made three is one field goal worth an extra
  point, not a separate event: `points = 2 × fg_made + threes + ft_made`. Counting it twice makes
  every high-volume shooter wrong, silently, in a way that still looks plausible.
- **A punt does not shrink the denominator.** Weighting a category down scales it, but `Value`
  stays the mean of nine, so punting lowers everyone rather than redistributing. And because the
  pool re-derives, a punt is **not local** — half-punting turnovers moves six players in or out of
  a 156-man pool and shifts the field by about eight rank places. This is the same shape as our
  own [ADR-0009](../decisions/ADR-0009-soft-punt-weighting.md), except that we do not
  re-standardise the pool.

The λ table, the H2H weights, `Q`, and the team count are collected in one place in §I.8, and
split into **league constants you set** and **their fitted constants**, which are labelled for
what they are: one provider, one season, one projection source.

---

## Five things we got wrong, and fixed

This is the branch's spine. Each correction has a commit and a measurement.

### 1. DURANT H2H does apply category weights (`631af7d`)

Commit 1 claimed DURANT applies no weights. True of `DUR`, false of `DURANT H2H`, which scales
every category before averaging: points 1.00, rebounds 0.94, assists 0.75, threes / steals /
blocks / FG% / FT% 0.60 each, and turnovers **0.00** — which is how turnovers are "removed".

Rebuilt with the weights, MAE 0.0025. The equal-weight version the document described gives
0.0963, **38× worse**.

The error survived because the test that "confirmed" H2H consumed their published `DH*V` columns.
It validated the arithmetic *given those columns* and could not detect that they differed from
`D*V`. The end-to-end reconstruction from raw stats is now run for both metrics.

### 2. The worked minus-one example read the rank as a category (`2ef24bc`)

The threes token is a bare `3` that runs into the rank, so `0.99#23` is rank 2 with threes
dropped, not rank 23. The non-greedy parse was already correct — 234 distinct ranks and zero
value-versus-rank inversions across both columns — so only the gloss was wrong.

### 3. In-sample R² is not evidence (`e7aead8`)

Two columns had been called unreproducible on the strength of in-sample R² from a 25-parameter
model fitted to about 200 rows. That figure only rises as features are added and cannot separate
signal from memorisation.

Cross-validated over 54 features, 5-fold:

| Column | In-sample R² | Out-of-sample R² |
|---|---|---|
| Drafting confidence | +0.378 | **−0.391** (worse than predicting the mean) |
| Frustration value | +0.565 | +0.106 |

A regression tree agrees: out-of-sample falls from +0.027 at depth 2 to −0.180 at depth 5 while
in-sample climbs to +0.489. **Both conclusions got stronger, and the old numbers could not have
supported either.** Confidence is now called exogenous; frustration value is called *partly*
explainable rather than not at all. The protocol is written into the document so the figures can
be re-checked.

### 4. A verification run against the wrong export (`0265182`)

The section comparing the two projection sources had quietly been checked against the rendered
table's one-decimal columns rather than a totals export, and the resulting softer R² explained
away as display rounding. That concealed a change of method.

The real route exists — Stats Display Format = Total Stats with Filters = All Players — and once
both sources are pulled the same way, source B reproduces through the documented steps at
R² 0.99983–0.99999 and Value MAE 0.0043, against source A's 0.0075 by the identical path. This
also killed a lead: the two sources' pool standard deviations are indistinguishable once measured
the same way.

Following the rewritten section literally exposed one more break — a step derived points from a
column the totals export does not have. It now covers both export shapes.

### 5. A divide-by-zero in the new module (`a39ea00`)

A category with zero spread in the pool divided by zero. It now scores flat, which is the right
answer when a category cannot separate anyone. Found by writing the tests, not by running the
code.

---

## The reimplementation

[`scripts/bbm/bbm_reference.py`](../../scripts/bbm/bbm_reference.py) is independent by design.
The earlier work could only be used by someone holding a subscription and following a click-path;
this runs next season against our own projections, or anyone's.

**The contract is thirteen numbers per player** — games, minutes, points, threes, rebounds,
assists, steals, blocks, turnovers, FG made and attempted, FT made and attempted. No file format,
no column names, no provider.

Public surface:

| Function | Does |
|---|---|
| `per_game` | Totals → rates; excludes zero-games players |
| `build_pool` | Iterates the top-*Q* pool to convergence, returns the pool and its constants |
| `category_values` / `value` | The nine, and their mean; both accept `punt_weights` |
| `rank_and_round` | Rank, and round = ⌈rank / teams⌉ |
| `yeo_johnson` / `fit_lambda` | The transform, and maximum-likelihood λ by golden-section search |
| `build_durant_pool` / `durant` / `durant_h2h` | DURANT's own pool, and both aggregates |
| `from_components` / `from_totals_with_percentages` | Adapters for the two export shapes |

Their fitted constants are named `LAMBDAS_BBM_2026_27_JOSH` — one provider, one season, not a
universal truth. **Maximum likelihood does not recover them.** Fitted on the same pool, every
*direction* agrees — blocks compressed hardest, threes nearest the identity, assists nearest a log
— and no *value* does. So: use their constants to reproduce their numbers, and fit your own to
apply the method. The constant's docstring records this.

Verification for commit 9 was deliberately adversarial: a clean-room implementation written from
Part I's text alone, without consulting the module, reproduces the module's `Value`, `DURANT` and
`DURANT H2H` to zero difference and selects the identical pools. That is the evidence that Part I
is complete and unambiguous.

---

## The 25 tests

Synthetic and hand-authored per [ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md);
they check the arithmetic, never the provider's data. Grouped by what they defend:

- **Sign and scale** — turnovers inverted and nothing else; counting values are plain z-scores;
  population rather than sample SD.
- **The percentages** — the pool rate is attempt-weighted, not a mean of rates; shooting exactly
  at pool average scores zero *at any volume*; below average on high volume hurts more than on low.
- **Aggregation** — `Value` is the mean of nine, not the sum; `Round` is ⌈rank / teams⌉.
- **The pool** — returns *Q* players, converges, and excludes the weakest.
- **Yeo-Johnson** — λ = 1 is the identity shifted, λ = 0 is a log on the positive side, the
  transform is monotone increasing, and `fit_lambda` recovers a known transform.
- **DURANT** — drops the player's own worst category; H2H zeroes turnovers, averages seven, and
  discounts the right categories.
- **Punts** — a weight scales only the punted category, and the denominator stays at nine.
- **Adapters** — `from_components` does not double-count threes; `from_totals_with_percentages`
  rebuilds makes from a rate and attempts.

---

## What this branch leaves open

Part III of the reference document, restated. Each was tested properly and each is recorded as a
finding rather than papered over.

- **DURANT's two percentage inputs.** The metric itself is solved — both aggregates reproduce at
  the rounding floor from the published category columns, and seven of nine inputs rebuild from
  raw stats at MAE ≤ 0.013. The two percentage inputs reach only 0.0345 and 0.0273, and the tell
  is the **Spearman: 0.9977 and 0.9980 rather than 1.0**. A monotone transform of the correct
  input would order players identically, so something slightly different is being transformed.
  The raw percentage and impact-scaled-by-√attempts are both ruled out. The metric's author says
  this part is unfinished, so the residual may be in the original.
- **The pool's spread.** Recovered means agree with a top-156 pool to within 0.5%; the standard
  deviations run **1–3% wider**, and no subset reproduces both moments. Standing hypothesis:
  their constants come from realised production rather than projections, which are regressed
  toward the mean and so narrower — and the per-category gap tracks predictability exactly as
  shrinkage predicts. **The experiment that settles it:** take a prior season's actual per-game
  statistics, form the top 156 by that season's value, compare the moments. No practical effect
  if you derive your own pool.
- **Three columns that are judgement, not arithmetic** — drafting confidence, frustration value,
  and tier. Tier is hand-curated: in 18 of 34 position-tier groups the numbering disagrees with
  the value order.
- **Usage rate.** Structurally confirmed — everything after the player's own term behaves as a
  single team-level constant, within-team SD 0.00065 against 0.00882 between teams — but
  reproducing it to the decimal needs team totals over every roster, which a fantasy-relevant
  subset does not provide.
- **Adopting any of DURANT would need its own ADR.** Rosenof's H-scoring paper cites the
  heavy-tailed-blocks premise and declines to act on it, resting on the central limit theorem:
  categories are won by 13-man team totals, which are near-normal however skewed the individuals
  are. A successful reconstruction does not touch that argument.

---

## Inherited from `bbm`, and not resolved here

Commit `ad2bb1d` carried [`2026-08-30-bbm-branch-summary.md`](2026-08-30-bbm-branch-summary.md)
onto this branch. **The `bbm` branch itself is unmerged**, so that document describes work whose
artifacts do not exist in this tree, and four of its links dangle here:

- `docs/decisions/ADR-0014-durant-as-a-second-opinion.md`
- `docs/decisions/ADR-0015-analysis-tooling-dependencies.md`
- `scripts/draft-board/durant.py`
- `docs/references/basketball-monster-durant.md`

Also `docs/reviews/2026-08-30-category-distribution-normality.md`. **Merging `bbm` fixes this;
editing the file does not.** Until then, read that summary as a description of another branch.

---

## Deployment status

**Nothing on this branch is deployed, and nothing needs to be.** No draft-board code, no
`Build.gs`, no sheet. The reference document says so in its own header — "Nothing here changes the
draft board" — and `bbm_reference.py` is a standalone module that no board code imports.

AGENTS.md's definition of done ("in the sheet and verified there") applies to draft-board work.
This branch is a specification, a reference implementation, and its tests.

---

## Verification

Run on 2026-08-31 against the branch tip `0177304`:

- `pytest` — 115 collected, 25 of them in `tests/test_bbm_reference.py`; 90 before this branch.
- `ruff check .` — clean.
- `git diff --stat main...durant-actual` — 6 files, +1,910 / −1.
- `scripts/check-no-data.sh` — clean; no provider data in the repo.

Every figure quoted above is copied from the commit that produced it, from
[`scripts/bbm/README.md`](../../scripts/bbm/README.md), or from the reference document — none is
recomputed or estimated here. Where a figure exists in two forms, the README's measured table
wins, which is why source A's `Value` MAE reads 0.0075 rather than the 0.0064 of the first
reconstruction.
