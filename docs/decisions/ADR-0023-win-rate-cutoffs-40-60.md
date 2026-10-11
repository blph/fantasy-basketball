# ADR-0023: Win-rate cutoffs of 40% and 60%, on both boards

- Status: Accepted
- Date: 2026-09-12
- Owner: Bryan
- Supersedes: ADR-0018 (in part)

## Context

ADR-0018 put the Category Tracker on a win probability and adopted the cutoffs argued in
`docs/references/category-tracker-z-thresholds.md` §6: WEAK at or below 35%, STRONG at or
above 65%, BANKED at or above 75%. §6 chose 35/65 on purpose. The pair is symmetric about a
coin flip and brackets the playbook's "aim for roughly 60%, not 90%" target, so a category
sitting *at* target reads CONTESTED, which is still where the next pick goes, rather than
STRONG.

The owner drafts on 40% / 60% / 75%. On 2026-09-12 the live sheet's Settings cells held those
values, while `Build.gs` still wrote 0.35 and 0.65. A Full rebuild would have reset them without
a word. The local board (ADR-0022) has to compute what the sheet computes, and it had two
numbers to choose from.

The reason: in mock drafts the 35–65 band left too many rows CONTESTED to act on. When most of
the eight rows say "spend the next pick here", the read no longer ranks anything.

## Decision

**WEAK at or below 40%, STRONG at or above 60%. BANKED stays at 75%.** The rest of ADR-0018
stands: the model, `K = k / w`, the benchmark cap at Q, the five read states and the order
they resolve in, and the unweighted profile column.

**One source for both boards.** The cutoffs live in `scripts/draft-board/board_settings.py`,
along with the league size, tier multiplier, category band and disagreement gap. `Build.gs`
carries the same values as `SETTINGS_DEFAULTS`, and `writeSettingsSkeleton` writes them into
the Settings cells. A pytest fails when the two copies differ. The harness fails when a Settings
cell did not come from the object. The cells stay yellow inputs, so a cutoff can still be moved
on the sheet. The local board's parity check (`verify.py --local`) reports that as drift to settle
on one side, not as a value to follow.

## What it costs

**A category at the playbook's ~60% target now reads STRONG.** That is the outcome §6 chose
35/65 to avoid. Under 35/65 a 60% category read CONTESTED and kept drawing picks. Under 40/60
it reads STRONG, and anyone following "spend the next pick on a CONTESTED row" moves on.

Moving on from 60% lowers that category's priority; it does not give it up. §6's own efficiency
curve shows how little is lost. The return on the next unit of edge, relative to a coin flip, is
`exp(−Φ⁻¹(p)² / 2)`:

| Win rate | Efficiency vs. peak |
|---|---|
| 40% or 60% | 97% |
| 35% or 65% | 93% |
| 75% | 80% |

A pick spent on a 60% category still earns 97% of what it would earn at a coin flip. STRONG at
60% therefore does not mean the pick would be wasted there. It means other rows are closer, and
the difference is small. Waste starts where BANKED starts, and BANKED has not moved.

In return, the CONTESTED band narrows. In `Z × K` units it goes from ±0.385 to ±0.253, about a
third narrower. The rows still CONTESTED are the close ones, which is what the label is for.

Symmetry is kept. 40% and 60% are Φ(−0.253) and Φ(+0.253), so a nearly-lost category is still
flagged at the same distance from a coin flip as a nearly-won one.

## Consequences

Good. The tracker names fewer rows, and the ones it names are the close calls. The sheet, the
repository and the local board carry one tested set of numbers, so a Full rebuild can no longer
reset the cutoffs silently. The cheat sheet's cutoff text is generated from the same object.

Bad. A category at target reads STRONG, and the reader has to take STRONG as "ahead, lower
priority", not "stop". The README keeps "stop looking" for BANKED, which is the reading this
record intends. The cutoffs are still a judgement, not a measurement. ADR-0018's calibration
path, probit-regressing weekly category results on `Z_team`, is still how evidence would replace
the judgement, and it still needs a season of results. `k_FG` and `k_FT` are still provisional
(ADR-0018 puts `k_FG` anywhere in 0.31–0.37). At a cutoff that uncertainty moves Win % by about
a point, so a percentage category within a point of 40% or 60% can read either side of it.

The research document is not rewritten. §6 keeps its case for 35/65 under a status note pointing
here, because that case is the argument this record had to answer.

## Alternatives rejected

**Keep 35/65.** The documented choice, and the better one for a manager who wants every
at-target category contested. Rejected in use: in mock drafts it named too many rows to act on.

**Keep the sheet at 40/60 and the repository at 35/65.** This was the state before this record.
A Full rebuild resets the cells, the cheat sheet quotes cutoffs the sheet does not use, and the
local board would have to pick one of two numbers. Two sources for one number is the drift this
record exists to remove.

**Move only STRONG, to 60%, and leave WEAK at 35%.** This narrows the band on the side that
prompted the change. It breaks the symmetry §6 argued for: a nearly-lost category would have to
be further from a coin flip than a nearly-won one before the tracker said so, and nothing in the
model justifies that.
