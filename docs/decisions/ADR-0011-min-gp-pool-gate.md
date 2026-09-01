# ADR-0011: Pool membership also requires a minimum projected games played

- Status: Superseded by ADR-0017
- Date: 2026-08-27
- Owner: Bryan

> **Superseded by [ADR-0017](ADR-0017-no-games-played-adjustment.md).** The gate was bolted
> to the `Seed Rank` circularity, which no longer exists: pool membership is now a fixed
> point computed in Python, and rows projected at zero games are dropped before scoring.
> The availability concern recorded below is still real and is now reported as a
> diagnostic rather than enforced as a gate.

## Context

The [playbook](../references/fantasy-basketball-draft-playbook.md) defines the
valuation pool as "the top 156 by value" and nothing else. The draft board has
always applied a second condition:

```
In Pool = IF(AND(Seed Rank <= Q, Projected GP >= MIN_GP), 1, 0)
```

with `MIN_GP` defaulting to 25. That gate was never recorded.
[ADR-0008](ADR-0008-google-sheet-draft-board.md) lists four deliberate
deviations and this is not among them, so it read as an implementation detail
when it is in fact a change to what "average" means for every number on the
board. A [methodology review](../reviews/2026-08-27-draft-board-methodology-review.md)
found it, along with two consequences nothing surfaced.

**The pool can be smaller than Q.** Every mean, SD and aggregate rate is
computed over `COUNTIF(In Pool, 1)` members, which is at most Q and sometimes
fewer, while `REPLACEMENT = LARGE(G TOTAL, Q)` still uses Q. The statistics that
set the value scale and the point that defines zero on it are drawn from
slightly different sets.

**The maintenance doc's own check was wrong.** It instructed the operator to
verify "pool count 156" — a quantity the gate makes legitimately variable. Under
`MIN_GP` a count below 156 is the correct result, so the instruction either
raises a false alarm on draft eve or teaches the operator to ignore a sanity
block that also carries the per-game/season-totals gate, which is the one
stop-the-line check on the sheet.

On the current export the gate binds on nobody: the pool comes out at exactly
156. That is luck, not design — the minimum projected GP in the top 156 happens
to be 25.

## Decision

**Keep the gate, and declare it.** A projection source occasionally carries a
highly-ranked player on a tiny projected sample, and one such line can move a
category mean and SD noticeably in a 156-player pool. Excluding him from the
*statistics* while keeping him *on the board* is the right split: he is still
draftable, he just does not get a vote on what average means.

`REPLACEMENT` continues to use `Q`, not the live pool count. Replacement level is
a statement about how many players get drafted, which does not change because
one of them has a short projection.

Two things ship alongside it:

- A **`Pool shortfall = Q − COUNTIF(In Pool, 1)`** row in the Settings sanity
  block, reading `0 — pool is exactly Q` in the normal case and naming the count
  otherwise.
- The maintenance doc's check becomes "Q minus the shortfall shown," not "156".

## Consequences

**Good.** The gate stops a short-sample projection from distorting the pool
statistics, and the shortfall row makes its effect visible instead of silent.
The sanity block stops producing a false alarm, which is what keeps operators
reading it.

**Bad.** The pool and the replacement level are still defined over marginally
different sets when the gate binds. The divergence is bounded by the shortfall,
which is now printed, and is zero on current data — but it is real, and anyone
changing `MIN_GP` upward should watch that number.

**The board's notion of "average" is conditioned on availability.** Excluding
low-GP players raises the means slightly and shrinks the SDs slightly, making
every remaining player's z-scores marginally less extreme. This is a defensible
choice and it is now a recorded one rather than an accident.
