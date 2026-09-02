# ADR-0021: The Basketball Monster sources borrow their standardisation constants

- Status: Accepted
- Date: 2026-09-01
- Owner: Bryan
- Supersedes: [ADR-0015](ADR-0015-durant-h2h-primary-value.md) in part,
  [ADR-0019](ADR-0019-punt-builds-restandardise.md) in part

## Context

[ADR-0015](ADR-0015-durant-h2h-primary-value.md) made reproducing Basketball Monster's
DURANT H2H the board's purpose. The board did not reproduce it. Nikola Jokic read DURH
1.082 against their 1.09 and ZSC 1.028 against their 1.02, every value in all nine source ×
value columns was off by roughly 0.008, and the dropped-category tag — a claim printed on
the tab you draft from — disagreed with them on 15 of 234 players. See
[the bug report](../bugs/2026-09-01-durh-zsc-pool-constants.md).

Everything we had already borrowed was correct. Refitting the Yeo-Johnson λ against their
published `D*V` columns recovers our constants to three decimals; the H2H weights recover to
1.0000 / 0.6011 / 0.9397 / 0.7500 / 0.5999 / 0.6001 / 0.6003 / 0.5998 against our
1.00 / 0.60 / 0.94 / 0.75 / 0.60 / 0.60 / 0.60 / 0.60; the drop rule, the divisor and the
turnovers-at-zero mechanism all hold; and the `BMP` export's stat lines match their page to
within display rounding.

The gap was entirely in the **pool constants** — the mean, the standard deviation and the
attempt-weighted rate each category is standardised against. We derived those from a
top-156 fixed point over our own projections. Basketball Monster's are different:

| | their constant | our top-156 | gap |
|---|---|---|---|
| points mean | 17.0131 | 17.0994 | +0.51% |
| points sd | 5.5189 | 5.4004 | **−2.15%** |
| steals mean | 1.0077 | 1.0319 | +2.40% |
| steals sd | 0.3199 | 0.3070 | **−4.02%** |
| blocks mean | 0.7060 | 0.6865 | −2.76% |
| DURANT points | 5.5213 / 0.9866 | 5.4823 / 1.0362 | |

The means are close and the SDs are not, and they miss in both directions by category.
Searching every pool size from 60 to 509, the means want N between 143 and 177 while the
SDs want anything from 85 to 318. **No pool reproduces both moments**, and this holds when
the search is run over Basketball Monster's own published per-game lines rather than our
export — an RMS SD error of 1.65%. So it is not our data, not export staleness and not our
pool iteration. They standardise against a wider distribution than the projection set they
publish; the reverse-engineering doc's [§III.2](../references/basketball-monster-projections-reverse-engineering.md)
guessed realised production and could not confirm it, and its conclusion that the practical
effect is nil is false for a board whose purpose is to publish their numbers.

## Decision

**Recover their constants by regression and use those for `BMP` and `BMP-ALT`.**

A published value is exactly linear in the stat, so the constants fall out of a fit against
their own columns: regress `pV` on our per-game points and the slope is `1/sd`, the
intercept `−mean/sd`. The percentage categories take a two-variable fit over makes and
attempts, which identifies the pool rate rather than assuming it. The DURANT layer searches
λ and the rate jointly, minimising the residual against their published column — **not**
maximum likelihood, which is already known not to reproduce their λ.

`scripts/draft-board/calibrate_bbm.py` does the recovering; `bbm_constants.py` reads the
result; `score_source(..., params=...)` consumes it.

**Nothing is hardcoded.** The constants are a property of a projection set that moves, so
they are refitted on every refresh and written to a dated file beside the export they belong
to. The pipeline will not resolve a date that has no fit, and a fit paired with the wrong
export is a hard error at three independent points — the filename, the file's own
`export_date`, and `find_set`.

**λ moved onto the same footing.** `LAMBDAS_BBM_2026_27_JOSH` was the last borrowed constant
frozen in source, with exactly the same failure mode: Basketball Monster retunes it and a
stale λ is invisible. It is now the fitter's search seed and a drift reference, not the
board's transform. The only Basketball Monster constants still in source are the H2H
weights, which are published and fixed rather than fitted.

**HBP keeps its own derived pool.** Basketball Monster publishes nothing to recover for
Hashtag's projections.

**Outliers are rejected from the fit.** Basketball Monster revises between exports, and one
player whose row has since changed does not merely mispredict itself — it tilts the
regression and corrupts constants applied to every player in the universe. The cut is
derived from the spread of the residuals (median + 8 robust sigmas), not typed: on a clean
pairing it rejects nobody, and on the current `BMP-ALT` export it rejects six.

## Consequences

**The board reproduces their numbers.** On `BMP`, ZSC falls from MAE 0.0075 to 0.0034 and
DURH from 0.0079 to 0.0030, with **no row outside display rounding** where there were 73 and
77, and the dropped-category disagreement falls from 15 to 3 — all three of which are ties
inside 0.009, closer than either side can resolve at two decimals.

**A refresh now needs a live subscription and a working browser session.** The pipeline
hard-fails without a same-dated fit for each vendor. That is intended, and it is also a new
way for a refresh to be impossible at six o'clock on draft night.

**The two percentage categories stay imperfect.** Basketball Monster transforms something
slightly different from our impact column — the Spearman against it is 0.998, not 1.0
(§III.1) — so `Dfg%V` and `Dft%V` keep a residual around 0.010 and 0.017 that no amount of
constant-fitting removes. It is why the three remaining dropped-category ties exist.

**HBP and the vendors now sit on different bases** on the same screen: theirs, and ours.
Magnitudes were already incomparable across sources because the pools differ; this is a
second reason. Ranks remain the comparison. The Settings tab says so in a `Standardised
against` column rather than leaving it to be inferred.

**ZSC and ZSH report identical constants for the vendors.** They still select different
top-156s, but a pool no longer determines a constant, so both read the one plain-z block.
This looks like a bug and is not; the Settings note says so.

**Punt builds change** — this is where ADR-0019 is amended. It has a punt re-derive the pool,
and that is structurally impossible under fixed constants: scaling before standardising
cannot move a mean that is not being computed. On `BMP`, where the builds ship, a punt is now
a discount applied after standardising. The alternative — leaving punts on the derived path
while DURH borrows — is worse and quietly so: it breaks the identity that a punt weight of
1.0 reproduces the unpunted DURH, and the punt GAP column would compare two bases while
looking fine. The mechanism survives for HBP and any future self-derived source. **Punt
ranks move as a result.**

**The fit is on ~234 rows and the constants are applied to ~510.** Players outside their
published list are extrapolated, hardest in blocks where λ = −1.69 compresses steeply.

**[ADR-0006](ADR-0006-no-provider-data-redistribution.md) is not weakened.** Eighteen means,
eighteen SDs and four rates are not player rows, but they are derived from provider output
and someone will want to commit them for reproducibility. They live under
`data/player_data/` with the scraped table they were fitted from — gitignored, and blocked
again by `check-no-data.sh`. Reproducibility comes from re-running the calibration.

**[ADR-0016](ADR-0016-values-computed-in-python.md) is not contradicted**: where the
computation happens is unchanged. Its argument that auditability moved to "read the pool
constants the sheet reports" now requires the basis to be reported alongside them, or a
borrowed constant reads as a derived one.

## Alternatives rejected

**Accept the difference and document it.** Our values were internally consistent and
rank-equivalent at Spearman 0.999. But ADR-0015's whole justification for DURANT H2H is that
the numbers agree with the tool other managers read, and a dropped-category tag that
disagrees on 6% of players is a wrong claim printed on the board.

**Ingest their published per-category columns directly** and apply only our drop and weight
rules. Exact by construction, but their columns are two decimals, so DURH would quantise;
only the ~234 players they publish would be covered; and the board would become a scraper
rather than a model of a documented method.

**Keep deriving, but tune the pool** until it matches. There is no pool. The means and the
SDs want different N in every category, and a tuned Q would be a number chosen to make one
season's data agree — the opposite of a derivation.
