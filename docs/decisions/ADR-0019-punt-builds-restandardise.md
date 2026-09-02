# ADR-0019: Punt builds discount before standardising and re-derive the pool

- Status: Accepted
- Date: 2026-09-01
- Owner: Bryan
- Supersedes: ADR-0009 (in part)
- **Amended by [ADR-0021](ADR-0021-borrowed-bbm-pool-constants.md):** re-deriving the pool is
  structurally impossible for a source that borrows fixed constants, so on BMP — where the
  builds ship — a punt is now a discount applied *after* standardising. The mechanism below
  survives for HBP and any future self-derived source.

## Context

ADR-0009 decided that a punted category keeps a fraction of its weight rather than being
deleted, and shipped `PUNT_WEIGHT = 0.25`. The direction is right and is not revisited
here. What it also fixed, without saying so, was *where* in the calculation the discount
lands:

```
punt score = G TOTAL − (1 − PUNT_WEIGHT) × (each dropped category's g)
```

That subtracts from a finished value. The pool, and therefore every mean and standard
deviation the value was built from, is unchanged. ADR-0009 recorded this as matching the
public tools, which mattered because a build rank is partly a prediction of what your
leaguemates are looking at.

The Basketball Monster research contradicted that. Their published mechanism (§I.9 of the
reverse-engineering document) discounts the standardised category value and then
**re-derives the pool and re-standardises**, because the value changed and so pool
membership changed. Measured there: half-punting turnovers moves six players in and out of
a 156-man pool and shifts the field about eight rank places on average.

So the previous board was not matching the public tool it was diverging from ADR-0009's
soft weight to match. It was doing a third thing.

## Decision

**Discount first, then re-derive the pool, then score.**

```
1. Multiply the punted categories' standardised values by PUNT_WEIGHT.
2. Re-derive the top-Q pool by iterating on the punt-scaled DURANT score.
3. Re-standardise against that pool, apply the H2H weights, drop the worst live
   category, average the seven survivors.
```

The denominator does not shrink. Punting lowers everyone's value rather than
redistributing it between categories.

**Two multipliers are in play and conflating them is the easy mistake.** The *punt scale*
applies to the punted categories only and takes part in pool selection. The *H2H weights*
turn DURANT into DURANT H2H and never affect pool selection. The pool therefore iterates on
the punt-scaled DURANT score — the same metric the unpunted pool iterates on — and only
then is the H2H rule applied.

That ordering is what makes `PUNT_WEIGHT = 1.0` reproduce the unpunted value exactly, and
that identity is asserted in `tests/test_board_values.py`. It is the check that proves the
two paths have not drifted apart, and it is only available because the two multipliers are
kept separate.

`PUNT_WEIGHT` stays at 0.25 and the nine builds of ADR-0010 are unchanged. Builds are
computed for the default projection only.

## Consequences

Good. The punt columns now mean what the research says they mean, and match the tool the
league is most likely reading. The mechanism is tested rather than asserted: one test
proves a punt actually changes pool membership on a fixture with real trade-offs, another
proves weight 1.0 is the identity.

Bad. The builds are more expensive — each is its own pool iteration, so nine builds is nine
more fixed points per refresh. They are computed in Python where that costs about a second,
which is only affordable because of ADR-0016; in the sheet it would not have been.

**A punt is no longer a local edit.** Under the old mechanism you could reason about a
build one column at a time. Now discounting one category moves players in and out of the
pool and shifts everyone slightly, including players in categories you are not punting.
That is a more faithful model and a less intuitive one, and it is worth knowing before
reading a build rank as though only the punted category changed.

`PUNT_WEIGHT = 0` no longer reproduces a hard punt exactly, because the pool moves too. The
ADR-0009 test that pinned that identity is retired with the G-score model it belonged to.

## Alternatives rejected

**Keep subtracting after the fact.** Cheaper, and reasoning about it is easier. But it
computes a quantity with no published definition — neither our own soft-punt model nor
Basketball Monster's — which is the worst of the three options available.

**Re-derive the pool but skip the re-standardisation.** Half the mechanism. Pool membership
would change while the constants stayed put, so the values would be standardised against a
set they were not drawn from.
