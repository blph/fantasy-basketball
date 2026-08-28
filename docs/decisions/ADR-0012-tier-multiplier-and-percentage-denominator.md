# ADR-0012: Tier multiplier of 2.0, and closing the percentage-denominator question

- Status: Accepted
- Date: 2026-08-28
- Owner: Bryan

## Context

Two loose ends from the [methodology review](../reviews/2026-08-27-draft-board-methodology-review.md),
both left open when the fixes landed, and both now settled against measurements
taken from the live board rather than from reasoning.

## Decision 1 — the tier multiplier drops from 4.0 to 2.0

[ADR-0008](ADR-0008-google-sheet-draft-board.md) set it to 4.0, arguing that the
playbook's suggested 2 "produces 46 tiers, which is unusable; 4.0 produces 14."
Two things were wrong with that.

**The measurement is stale.** It was taken when the tier window ran nine rows up
the board and five down. Correcting that to a genuinely centred window changed
what every multiplier produces, and the cheat sheet has been carrying a note to
re-check ever since. Nobody did.

**The criterion was wrong.** Tier *count* is not what makes a tier useful. Size
where you are picking is. Measured on the converged board:

| Multiplier | Tiers | Worst tier inside the top 100 |
|---|---|---|
| 4.0 | 20 | **picks 25–70, 46 players** |
| 3.0 | 32 | picks 26–48, 23 players |
| 2.5 | 36 | picks 26–48, 23 players |
| **2.0** | **48** | **picks 52–63, 12 players** |

At 4.0 the board told you that picks 25 through 70 were interchangeable — rounds
three to six, which is exactly the window playbook section 9 calls the one where
your build reveals itself. That is not a conservative tier, it is a wrong one:
it says "you can wait" through the entire middle of the draft.

**Correction, same day.** This record originally led with the stale measurement,
which reads as though centring the window created the problem. It did not. Both
windows, both multipliers, against the same converged values:

| Window | Multiplier | Tiers | Largest tier inside the top 100 |
|---|---|---|---|
| Skewed `r−9..r+5` — as originally shipped | 4.0 | 15 | **picks 25–63, 39 players** |
| Centred `r−7..r+7` | 4.0 | 20 | picks 25–70, 46 players |
| Skewed | 2.0 | 48 | picks 30–42, 13 players |
| Centred | 2.0 | 48 | picks 52–63, 12 players |

The blob was there from the start: 39 players under the original board. Centring
made it worse — 39 to 46 — but did not cause it, and the board shipped for weeks
with a 39-player tier across rounds three to six.

Two things follow. The root cause is the criterion, not the window: measuring
count instead of size hid a defect that existed under either. And **2.0 was the
right value under both windows**, so this ADR does not correct a calibration that
drifted — it corrects a choice that was wrong when it was made.

2.0 gives 48 tiers, more than ADR-0008 rejected. That is accepted deliberately.
Twenty-six of them fall inside the top 100, averaging about four players each,
and none exceeds twelve. A decision every four picks is a usable instrument; one
46-player blob is not. The playbook's original suggestion was right, and
ADR-0008 rejected it for measuring the wrong quantity.

The playbook's own "12 to 15 tiers across 200 players" target is listed in its
section 12E as the author's invention with no source, so it does not outrank a
measurement.

## Decision 2 — the percentage denominator stays as it is, and the question closes

[ADR-0009](ADR-0009-soft-punt-weighting.md)-era work added diagnostic cells to
Settings because it was unresolved whether Rosenof's Table 5(b) sigma means the
spread of raw success rates or the SD of the volume-weighted impact column. The
board divides by the impact SD. The instruction was to read the numbers before
changing anything. Here they are, from the live pool:

| | SD of impact | SD of rate | ratio |
|---|---|---|---|
| FG% | 0.0489 | 0.0619 | 0.789 |
| FT% | 0.0857 | 0.0813 | 1.054 |

Worth noting the review predicted both ratios would exceed 1, on the model
`SD(impact) ≈ σ_R·√(1+CV²)`. FG% contradicts that, so the review's model of the
relationship was wrong even though the question it raised was real.

What the choice actually costs, computed by scoring every player both ways:

- 24 players of 200 move 10 or more places; 3 move 20 or more.
- Mean absolute movement: 4.5 places.
- Of the moves of 10 or more, **4 touch the top 50**.

**Decision: keep the impact SD, and stop calling this open.** The reasoning that
favours it is unchanged — if a team's category outcome is the mean of its
members' impacts, dividing by the SD of impact puts the percentage categories on
the same "share of a team standard deviation" footing the counting categories
get. And the measurement says the alternative barely touches the picks that
decide a draft. Carrying an open question that costs four places in the top 50
is not worth the cost of it being open.

The diagnostic cells stay on Settings, so the numbers remain visible if the pool
ever shifts enough to change the answer.

## Consequences

**Good.** The tier column becomes usable in the rounds it exists for. The
percentage question stops being a thing anyone has to re-derive.

**Bad.** 48 tiers is a lot of lines on the board, and some breaks will be noise
rather than cliffs — at 2.0 the threshold is less selective by construction. The
tier column is a prompt to think, not an instruction.

**Reproducibility.** ADR-0008's claim that the board was verified against an
independent Python implementation is now backed by a committed one:
`scripts/draft-board/verify.py`, over `scripts/draft-board/valuation.py`. It was
unreproducible when that ADR was written.
