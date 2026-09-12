# ADR-0015: DURANT H2H replaces the G-score sum as the board's value

- Status: Accepted
- Date: 2026-09-01
- Owner: Bryan
- Supersedes: ADR-0008 (in part), ADR-0012 (in part)
- **Amended by [ADR-0021](ADR-0021-borrowed-bbm-pool-constants.md):** the standardisation
  constants are borrowed as well as the lambdas. Deriving our own pool did not reproduce the
  published numbers this ADR exists to reproduce, and no pool does.

## Context

The board valued a player as the sum of nine z-scores, each discounted by a
weekly-volatility multiplier taken from Rosenof's Table 8 and normalised to assists
(AST 1.00 … STL 0.59), then expressed as value over replacement.

Two things were wrong with that for this league.

The multipliers were never trustworthy at the precision they were used. ADR-0008 and the
Settings tab both record it: "the ordering is reliable; the second decimal is not," from
one season of one dataset, with a note to re-derive in Phase 4. They were applied to three
decimal places anyway.

More importantly, the model does not describe how a category head-to-head week is won.
Summing nine discounted z-scores prices a player as a bundle of nine simultaneous edges.
The `durant-actual` research established what Basketball Monster actually does, and what
its author recommends for this exact format: **DURANT H2H for head-to-head category
leagues.** Its shape encodes two things our sum did not — that categories are not equally
winnable, and that a roster does not need all nine.

## Decision

**The board's primary value is DURANT H2H, reproduced exactly**, alongside two comparison
values. Per projection:

| Value | Definition | Denominator |
|---|---|---|
| `ZSC` | Basketball Monster's plain `Value`: nine z-scores, turnovers inverted, percentages by attempt-weighted impact, population SD | 9 |
| `ZSH` | The H2H weighting and the minus-one rule applied to **untransformed** z | 7 |
| `DURH` | Yeo-Johnson per category → standardise on a pool iterated on the DURANT score → weight → drop the worst live category | 7 |

**Basketball Monster's H2H weights replace the Rosenof multipliers**: PTS 1.00, REB 0.94,
AST 0.75, and 3PM, STL, BLK, FG%, FT% at 0.60 each. **Turnovers carry weight 0 — that is
*how* DURANT H2H removes them**, not a special case. The Rosenof vector stays on Settings
as a labelled, explicitly unused reference, because it is the basis of the reasoning in the
playbook and deleting it would strand that argument.

**ZSH exists to isolate what the Yeo-Johnson transform is worth.** It shares DURH's weights
and its minus-one rule and differs only in the transform, so any rank disagreement between
them is the transform's doing and nothing else. Without it, adopting DURANT would be an act
of faith; with it, the transform is measurable on our own data.

`ZSC` averages nine and the other two average seven, so **magnitudes are not comparable
across value types even for one player.** Only ranks are. The README and the block headers
say so.

## Consequences

Good. The board's numbers now agree with the tool the league's other managers are most
likely reading, which matters because a build rank is partly a prediction of their
behaviour. The valuation is validated: `bbm_reference.py` reproduces Basketball Monster's
published DURANT H2H to MAE 0.0079 with Spearman 0.99919. And the minus-one rule prices
what the format actually rewards — a roster that wins seven categories, not one that is
mediocre in nine.

Bad. Three values across three projections is nine numbers per player where there was one.
That is the horizontal-budget problem the projection filter and the tag columns exist to
manage, and it is a genuine cost on a sixty-second clock.

The λ constants are Basketball Monster's fitted values for one season and one provider.
Fitting our own by maximum likelihood gets every direction right and no value right
(blocks −1.38 against their −1.69), so their objective is unrecovered. Use their constants
to reproduce their numbers; that is what we do, and it means the transform is borrowed
rather than derived.

Superseded in part: ADR-0008's live-formula valuation chain and the tier-multiplier
context in ADR-0012 both assumed a single summed G-score. The tier mechanism itself is
unchanged and still reads `TIER_MULT = 2.0`; only the column it measures has moved.

## Alternatives rejected

**Keep the G-score sum and add DURANT beside it.** Four values per projection rather than
three, for a metric already superseded by ZSH, which answers the same question — does
weighting help — against the weight vector we actually trust.

**Fit our own λ.** Attempted and recorded: maximum likelihood over our pool agrees on every
sign and no magnitude. Fitting our own would produce numbers that are ours, defensible, and
no longer Basketball Monster's — losing the one property that makes them checkable against
a published source.
