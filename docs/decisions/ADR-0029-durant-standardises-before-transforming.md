# ADR-0029: DURANT standardises before it transforms

- Status: Accepted
- Date: 2026-10-01
- Owner: Bryan
- Amends: [ADR-0021](ADR-0021-borrowed-bbm-pool-constants.md) (the DURANT layer's fitted quantities)
- Resolves: the open item at [§III.1](../references/basketball-monster-projections-reverse-engineering.md) of the reverse-engineering doc

## Context

The 2026-10-01 refresh would not calibrate. `calibrate_bbm.py` refused to write constants for
either vendor source: the DURANT layer no longer reproduced Basketball Monster's published
`D*V` columns, failing its tolerance gate on three counting categories per source.

Everything cheap was ruled out first, and this matters because each exoneration narrowed the
answer:

- **Not the export.** A machine-made Playwright export matched the hand download at mean
  |Δminutes| 0.11 (Josh) and 0.00 (Bonus) across ~590 players, and refit to the same rmse to
  four decimals.
- **Not the scrape.** 234 players joined, 0 unjoined, on both sources. (The first pull of each
  came back truncated at 152 and 147 rows; both were re-pulled full. That truncation is a
  separate defect, recorded in [the bug](../bugs/2026-10-01-bbm-durant-composition-order.md).)
- **Not our code.** Refitting the 2026-09-12 scrapes with the same fitter still passed.
- **Not the pool, and not a rescale.** Both are affine in the fitted slope, so neither can break
  the DURANT layer while the plain layer stays exact — and the plain layer stayed exact, at
  rmse ≤ 0.018 on the same players and the same x.
- **Not the stat basis.** Fitting λ freely on assists: per-game 0.0374, totals 0.2268, per-36
  0.2864, value×games 0.2385. Per-game remained far the best.

What was left was the transform itself, and three measurements located it. Spearman between our
per-game stat and their `D*V` was ~0.99998 on **both** dates, so the input was right and still
monotone. Isotonic regression — the best fit achievable by *any* monotone transform — reached
0.0011 on 2026-10-01, as good as on 2026-09-12, so a smooth monotone function of that input still
explained their column completely. And the residual from the best single Yeo-Johnson oscillated
with four sign changes across the stat's deciles, which no one-parameter power family produces.

Rank-based inverse-normal scores (0.07–0.17) and a blend with the plain z (0.0374 → 0.0370) were
both tested and both failed.

## Decision

**Basketball Monster changed the order of the two steps, and we follow them.**

```
until 2026-09-12:  D*V = standardise( YeoJohnson( raw per-game stat, λ ) )
since 2026-10-01:  D*V = affine(      YeoJohnson( standardised z,    λ ) )
```

Fitting the second form against their published columns gives, on all nine categories and both
sources independently:

| | YJ(raw) | YJ(z) |
|---|---|---|
| BMP 2026-09-12 | **0.0034–0.0162** | 0.0169–0.0504 |
| BMP 2026-10-01 | 0.0226–0.0385 | **0.0036–0.0175** |
| BMP-ALT 2026-09-12 | **0.0034–0.0162** | 0.0169–0.0501 |
| BMP-ALT 2026-10-01 | 0.0226–0.0346 | **0.0036–0.0186** |

Each date is fit well by exactly one ordering and badly by the other, at equal parameter count —
λ plus an affine pair, either way — so this is a model distinction rather than extra flexibility
winning. That dates the change to between the two pulls.

**The order is why threes survived.** Yeo-Johnson at λ = 1 is affine, so the two compositions
agree exactly there and nowhere else. Threes' λ sits on the identity (1.0166 on the old scale,
0.986 on the new), and threes was the one counting category whose fit did not move: 0.0048 →
0.0047. That single fact is what identified the change, and
`test_the_two_orders_agree_only_where_lambda_is_one` keeps it executable.

**The sign is applied once, to the z.** The transform always sees a column where more is better,
so turnovers reach Yeo-Johnson already inverted. The recovered slope must therefore be positive
for all nine, and `fit_durant` raises rather than assuming it: a sign applied twice produces an
inverted category that still fits beautifully.

**The DURANT layer now reads the plain layer, so it is built on top of it, not beside it.**
`durant_params` takes the plain block as a required argument — not a defaulted one, because which
z the transform reads is the whole content of the layer. Each DURANT spec carries the plain
constants it standardised with (`z_mean`, `z_sd`, and `rate` for a percentage), so the block stays
self-sufficient and can be passed around alone, as the punt path does.

**Constants files bump to schema 2.** The same fields now hold incompatible numbers — `mean` and
`sd` describe the transformed *z* rather than the transformed raw stat — and a schema-1 file read
as a schema-2 one is wrong on every row and visibly wrong on none.

**The DURANT percentage rate is gone.** It used to be fitted jointly with λ in a two-dimensional
search, because transforming the impact left the rate unidentified by any linear fit. Reading the
plain z means the rate is already measured, once, by the plain layer. So one fitter now covers all
nine categories, a percentage DURANT entry carrying a `rate` is refused, and the λ drift warning
covers all nine rather than exempting the two percentages that used to wander along a ridge.

**Both DURANT gates tighten: counting 0.030 → 0.025, percentage 0.050 → 0.030.** The loose
counting gate is what let this register as a bare failure rather than an obvious one, and the
percentage allowance existed only to stop the §III.1 residual blocking a refresh. On 2026-10-01
the worst of the nine is steals at 0.015, so 0.025 leaves real headroom while still catching a
return to the old order, which lands at 0.027–0.039 on five of seven counting categories.

**The change applies to all three sources, including HBP.** This is Basketball Monster's method
and we implement it once. HBP has no published counterpart to verify against, but the board
compares ranks across sources (ADR-0021), and two sources composing the layers differently would
make that comparison meaningless in a new and invisible way.

## Consequences

**§III.1 is resolved as a side effect.** Both percentage categories now fit at 0.0098–0.0186,
against the MAE 0.0345 and 0.0273 the doc has recorded as unreproducible since the original
reverse-engineering. It follows necessarily: if DURANT reads the plain z, the percentage DURANT
value inherits the plain layer's single attempt-weighted rate instead of needing its own. The
remark in §III.2a that the two layers recover *different* pool rates — 0.4918 against 0.4976,
cited as evidence they were not computed from one shared intermediate — is now obsolete. They are.

**The DURANT layer inherits the plain layer's residual.** This is new, and it is the cost of the
nesting. Points and assists, whose plain fit lands near 0.0035, come out near 0.0037; steals,
whose plain fit is 0.013, comes out near 0.015. Fitting against *their* published z column instead
scores about 0.004 everywhere, and we deliberately do not, because the pipeline rebuilds z from
our own stat lines and the recovered mean/SD — so fitting on their z would report an accuracy the
board cannot reproduce.

**Measured against their published columns after the change**, on 191 matched board rows:

| | BMP | BMP-ALT |
|---|---|---|
| DURH MAE | 0.0029 | 0.0029 |
| DURH max | 0.0231 | 0.0197 |
| DURH dropped category disagrees | 2 of 191 | 3 of 191 |

DURH is what the board ranks on (ADR-0015), and 0.0029 matches the 0.0030 §III.2a records for the
layer when it was working. ZSC is unchanged by this ADR and still fails its 0.020 per-row maximum
on 1 row (BMP) and 2 rows (BMP-ALT) — every one of them a player whose stat line Basketball
Monster revised after publishing the value we scraped, with the worst unrevised row at 0.0113.
That is the drifted-export condition `consistent_players` exists to name, not a defect here.

**Their plain `DUR` aggregate also changed, and is deliberately left unidentified.** Their own nine
published columns rebuild their own `DUR H2H` at MAE 0.0025 on both dates, so the weights, the
minus-one rule and the mean-of-seven are untouched. The minus-one rule for plain `DUR` gave 0.0025
on 2026-09-12 and gives 0.0911 on 2026-10-01, and no simple rule over their nine beats 0.0135. The
board never reads that column — `verify.py` compares only `Value` (→ ZSC) and `DUR H2H` (→ DURH) —
so chasing it would spend real effort on a number nothing depends on. Recorded as open in
[the bug](../bugs/2026-10-01-bbm-durant-composition-order.md).

**The λ are on a new scale and are not comparable to the old ones.** `LAMBDAS_BBM_2026_27_JOSH_Z`
replaces `LAMBDAS_BBM_2026_27_JOSH` as the search seed, the drift reference and the derived-path
default. Blocks moves from −1.6863 to about −0.04 without their transform having become any
gentler. The old set is kept, because the reverse-engineering doc quotes it and because it is what
reproduces a 2026-09-12 or earlier pull.

**The drift warning is noisier across sources.** The seed is Josh's, and Bonus's refitted λ differ
from it by more than the 0.05 threshold on five of nine. That was already the design before this
ADR — one seed, both sources — and the warnings never block a refresh, so it stays. Worth knowing
that a note on a Bonus refresh may be a genuine source difference rather than a retune.

## Alternatives rejected

**`--force` past the gate.** It would have written constants whose DURANT layer was wrong by up to
0.19 on individual players, for two of three sources, on the column the board ranks by. A wrong
number that looks right is worse than no number.

**Widening the tolerance.** The gate was correct and the fit was wrong. Widening it would have
hidden exactly the change it caught, and the triage rule in
[build-and-maintenance.md](../draft-board/build-and-maintenance.md) says never to.

**Pairing the 2026-10-01 exports with the 2026-09-12 constants.** Wrong on every row and visibly
wrong on none, which is why `bbm_constants.parse` refuses a date mismatch outright.

**Waiting for it to settle.** Reasonable before the cause was known — early October is their
churniest period — but the two dates separate cleanly in opposite directions, which is a change of
method rather than a transient.
