# Category distribution normality — 2026-27

- Date: 2026-08-30
- Scope: the shape of the nine scoring categories as the board standardises them —
  FG% and FT% as **volume-weighted impact**, the seven counting stats as projected —
  and whether z-scoring is a sound thing to do to them.
- Method: measured over the **converged rostered pool** (seed ≤ 156 and GP ≥ 25,
  re-seeded on adjusted rank until membership settles; n = 156, three passes, no
  shortfall) by `scripts/analysis/normality.py`, which reuses `valuation.py`'s own
  `fg_impact` / `ft_impact` rather than restating them. Regenerate with
  `python3 scripts/analysis/category_distributions.py`; the full tables and the
  nine charts land in gitignored `data/exports/`.
- Constraint honoured: no player row, projection, or ADP value appears below. All
  measurements are aggregate ([ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md)).

---

## Verdict

**None of the nine is Normal, every test says so, and that finding is nearly
useless on its own.** At n = 156 Shapiro-Wilk rejects all nine, so it separates
none of them. What separates them is effect size and the gap from the Normal the
z-score assumes.

The reading that matters: **the non-normality is real at the player level and
mostly gone by the level decisions are made at.** Categories are settled on a
13-man roster's total, and summing flattens it. The one place it still bites is
the ±1.00 Category band, which is a documentation problem, not a math one.

| Tier | Meaning | Categories |
|---|---|---|
| A | normal enough | _none_ |
| B | skewed but usable | 3PM, PTS |
| C | materially non-normal | FG% impact, REB, AST, TO |
| D | wrong shape for a z | FT% impact, STL, BLK |

Tier D does not mean "worse than C". It means the mean and SD do not describe the
population, so the z still orders players correctly while the *distance* between
them stops being a quantity to reason with.

## The three findings

**1. The tests and the properties that matter disagree in both directions.**

3PM passes every moment test (skew −0.11, and the smallest gap from Normal of the
nine) and is genuinely the best-behaved category here. An earlier chart appeared
to show it as bimodal; that was 39 distinct reported values drawn into 22 bins —
an artifact of snapping bin edges to whole reporting quanta, now fixed by lifting
that floor for low-cardinality columns. STL, meanwhile, fails on **discreteness,
not shape**: 16 distinct values across 156 players, so roughly ten players share
each value and Shapiro-Wilk is measuring the provider's 0.1 rounding grid. SciPy
issues no warning. The battery now prints a distinct-value count and marks the
continuity-assuming tests invalid below 30.

**2. The bimodality coefficient does not work here, in both directions.**

BC reads 0.33 on FT% impact and 0.52 on BLK — both below its 0.555 flag, i.e.
"unimodal" — and those are precisely the two categories whose second mode survives
2.89× and 1.93× Silverman's bandwidth. It then reads 0.56 on REB, above the flag,
for a category with exactly one mode. BC is a deterministic function of skew and
kurtosis, so it can only repeat what those two already say: heavy tails push it
down, light tails push it up, and neither has anything to do with how many modes
there are. The **critical bandwidth** — the smallest smoothing at which the density
goes unimodal — is what actually finds them, and Hartigan's dip test was
deliberately not hand-rolled to do the same job.

**3. BLK is where the board pays, and only a non-p-value measurement finds it.**

At z = −1, blocks holds **3.2%** of the pool where a Normal promises 15.9%. Blocks
are bounded at zero and the pool mean sits barely one SD above that bound, so the
left tail the z-score prices largely cannot exist.

[ADR-0013](../decisions/ADR-0013-category-profile-column.md) already records this
as a known limitation, in the words "roughly five players". This is that
limitation with a derivation behind it — it is five players, and the ±1.00 band
implies about 25.

## Does it matter? Mostly not

A 13-man roster's category total, over 20,000 draws without replacement
(seed `20260830`):

| Category | Player skew → team total | Player excess kurtosis → team total |
|---|---|---|
| FG% impact | +1.07 → +0.27 | +1.30 → +0.05 |
| FT% impact | −1.52 → −0.40 | +7.07 → +0.32 |
| BLK | +1.62 → +0.39 | +3.83 → +0.17 |
| AST | +1.01 → +0.26 | +1.21 → +0.07 |
| STL | +0.96 → +0.26 | +1.24 → −0.02 |

Every category lands inside the approximately-symmetric band at roster level. This
is the argument [ADR-0014](../decisions/ADR-0014-durant-as-a-second-opinion.md)
rests on, and until now it existed only as an assertion — no code in the repository
computed it. It holds.

Caveat: the two impacts are summed as if roster-additive, which they are not
exactly, since a team's FG% is its own attempt-weighted aggregate. The direction is
unaffected.

## Recommendation: accept and document

**Do not transform.** ADR-0014 declined already and the simulation above is its
missing evidence. For completeness the cost was measured: a rank-based inverse
normal (Blom, per category, board rebuilt from it against a baseline that
reproduces `valuation.py` exactly) gives Spearman 0.967, **11.2 places** of mean
movement, 93 of 200 players moving ten or more, and five crossing the drafted-156
line. ADR-0014 rejected Yeo-Johnson at 18.6 mean places as "not marginal"; this is
cheaper but strictly more destructive, because rank-INT maps every category onto an
identical Gaussian — the gap between the best blocker and the second best collapses
to the gap between the top two order statistics of a standard Normal, whatever the
block totals were.

It also **destroys the mean-zero identity of the impact columns**, which is why the
board divides by SD with no centring term, is pinned by `tests/test_valuation.py`,
and is a live `Build.gs` formula. Transforming would need a centring term
everywhere, an ADR superseding 0012 and 0014 in part, and a sheet rebuild.

**Do not winsorize.** At n = 156 a 99th-percentile cap touches about 1.5 players per
tail while changing the SD, and therefore every z, in that category. On FT% impact
the low tail *is* the signal: a poor free-throw shooter on high volume genuinely
loses you the category, and capping him deletes exactly what the volume weighting
exists to price. The playbook's section-11 table lists this as an open option; it
should be closed.

**Read the ±1.00 band as a yield, not a probability.** The strong side is well
calibrated at 13–17% per category, which is what ADR-0013 tuned. The weak side on
blocks is 3.2%. Documentation change, no math change — and the only place the board
is genuinely mis-calibrated today.

**Add a post-refresh falsifier.** Re-run after each export and check no category has
changed tier; a tier change means the pool's composition moved. Nothing would notice
today.

**Route bounded, win-probability saturation to its own ADR.** ADR-0014 leaves it
open, it needs no distributional assumption, and it is the one alternative these
measurements strengthen. It should not arrive via a normality report.

## Two things this corrects

**Two verdicts depend on a re-seed that has never been run.** Audit finding F3
records that `Re-seed pool from current ranks` has not been run on the live sheet,
so the sheet holds the single-pass pool. The two pools share 150 of 156 members,
and running the battery over both moves **AST and TO from B to C**. Everything else
is robust. This is a reason to run the re-seed, not a reason to distrust either
number.

**`basketball-monster-durant.md` quotes two different pools without saying so.** It
reports BLK skew **+1.53** in the Lloyd section and **+1.60** in the DURANT section;
those are the single-pass and converged pools respectively. ADR-0014 is Accepted and
carries the single-pass pair, and is not edited. The canonical converged figures are
BLK **+1.62 / +3.83** and FT% impact **−1.52 / +7.07**; the single-pass pair reads
+1.54 and −1.41. Neither is wrong — they answer different questions. This happened
because nothing in the repository computed a skew until now, so every such figure
was produced ad hoc in a session and could not be re-derived.

## Selection caveat, which constrains everything above

The pool is the top 156 by adjusted value with GP ≥ 25, selected jointly on all
nine categories. **That truncation creates skew.** "PTS skews +0.53" is a fact about
a right-truncated draw, not about NBA scoring, and it is also why these nine
measurements are not independent of one another. Turnovers are measured as reported,
where higher is worse; the valuation inverts them, so TO's skew *as valued* is −0.66.
