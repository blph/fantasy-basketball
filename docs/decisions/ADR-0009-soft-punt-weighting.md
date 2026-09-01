# ADR-0009: Punted categories keep a fraction of their weight, not zero

- Status: Accepted
- Date: 2026-08-27
- Owner: Bryan

> **Superseded in part by [ADR-0019](ADR-0019-punt-builds-restandardise.md).** The soft
> weight and `PUNT_WEIGHT = 0.25` stand. What changed is where the discount lands: it now
> applies to the standardised category value BEFORE the pool is re-derived, rather than
> being subtracted from a finished total against a fixed pool.

## Context

The draft board's six punt columns were the G-score total with the punted
category's term deleted — a weight of exactly zero. The
[playbook](../references/fantasy-basketball-draft-playbook.md) meanwhile told you
to "soft-punt rather than hard-punt," citing Rosenof's finding that his dynamic
algorithm's punted-category weights "peaked around 75% or so" of baseline rather
than collapsing to nothing. The code and its own specification disagreed, and
[ADR-0008](ADR-0008-google-sheet-draft-board.md) did not record the divergence.

A [methodology review](../reviews/2026-08-27-draft-board-methodology-review.md)
surfaced this. Checking the source directly qualified it in four ways the review
did not:

1. The ~75% is a **relative** weight, normalised against the baseline G-score
   weight vector.
2. That vector is **constrained to sum to one**, so the figure is inseparable
   from the "a bit above 100%" it reallocates to other categories.
3. It is measured on **first-round picks only**.
4. Rosenof states that the weights are "estimates of best weights used for
   future players," and that "for player p who the algorithm is choosing, the
   algorithm may implicitly be using a very different weighing mechanism."

The paper also argues repeatedly that a static ranking list cannot execute
punting properly at all, which is exactly what a spreadsheet column is.

So the *direction* is supported and the *number* does not transfer. Against that,
two things argue for soft-punting here specifically. The mechanism Rosenof gives
is format-independent and plainly right: a category you have conceded is still
won by accident some weeks, and those weeks are free. And this league is
Head-to-Head Categories, where every category is settled separately every week —
conceding one costs a loss every week rather than being absorbed into a single
weekly result, which is the format where hard punting is least defensible.

There is a real cost on the other side. Basketball Monster and Hashtag Basketball
appear to hard-punt: BBM's `Punt+` column decomposes as plain subtraction, and it
ships pool recomputation separately as `DynV`. Diverging from them means the
board's build ranks no longer match what leaguemates see on their own screens,
which matters when the point of a build rank is partly to predict their behaviour.

## Decision

A punted category retains a configurable fraction of its G-score contribution
rather than being deleted. `PUNT_WEIGHT` is a named range on the Settings tab,
**defaulting to 0.25**.

```
punt score = G TOTAL − (1 − PUNT_WEIGHT) × (each dropped category's g)
```

The default is our tuning choice, informed by Rosenof's finding rather than
prescribed by it. The playbook and the sheet's own README both say so; neither
cites him as authority for the coefficient.

## Consequences

**Good.** A build stops rating a player who is actively terrible in the punted
category identically to one who is merely neutral there. Those are different
bets, and the second is better — you keep the free weeks. It also discourages the
"stack 3 extreme" shape the playbook's own section 10 rates worst of four.

**Reversible without a code change.** Setting `PUNT_WEIGHT` to 0 reproduces the
previous board exactly, which is the property the Settings tab exists to provide.
`tests/test_valuation.py` pins both ends: weight 0 equals the old hard punt,
weight 1 equals the plain G total.

**Bad.** The board's punt ranks now differ from the public tools by a constant
tilt. When reading a build rank as "who the room will underrate," remember the
room is looking at a hard punt.

**The number is not calibrated.** 0.25 is a starting point. Nothing in the
literature pins it for a static board, and it should be revisited if the punt
lists ever look wrong in practice.
