# ADR-0017: No games-played adjustment

- Status: Accepted
- Date: 2026-09-01
- Owner: Bryan
- Supersedes: ADR-0008 (in part), ADR-0011

## Context

The board scaled value over replacement by projected availability:
`ADJUSTED VALUE = VOR × My GP Est / 72`. The playbook derives it as exact rather than
approximate, given replacement-level backfill, and the board was careful about the one way
it can go wrong — scaling was switched off below replacement so availability could never
promote a player.

The mechanism was sound. The input was not.

Basketball Monster's author, whose projections the board now runs on, is explicit that
games played is "the least predictable part of any projection" and that he does not draft
from total-value rankings himself. The method reproduced in ADR-0015 has **no availability
term anywhere**: a 44-game player and a 73-game player are rated by identical arithmetic,
stated as design rather than omission.

Multiplying a well-estimated per-game value by a badly-estimated game count produces a
number that looks more precise than either input. And the board's own audit found the
override machinery entirely unused: `GP Y-1/2/3` filled on 0 of 200 rows, `My GP Est`
differing from the projection on 0 of 200. The adjustment was running on a raw provider
number with no human judgement applied to it at all.

## Decision

**Nothing multiplies by games played.** `ADJUSTED VALUE`, `Adj Rank` and `GP_DIVISOR` are
removed. Rank, tier, round, GAP and the tracker benchmark all key off the selected value.

**The GP columns stay** — projected GP, `My GP Est`, `GP Y-1/2/3` and the CHECK flag — as
context for a judgement call, muted and collapsed by default. The block header says
`GP · context only`. Availability is a real consideration on draft day; it is just not a
multiplier.

**`MIN_GP` is retired with it (ADR-0011).** That gate required `Projected GP >= 25` for
pool membership, bolted to the `Seed Rank` circularity that no longer exists — pool
membership is now a fixed point computed in Python, and rows projected at zero games are
dropped before scoring. Basketball Monster applies no such gate, and keeping ours would put
the board permanently off the numbers it is meant to reproduce, for no stated benefit.

The concern ADR-0011 named is real, so it stays visible rather than being removed:
`verify.py` and the Settings tab report each pool's minimum and median games and the count
of members under 25 games. On the current data that count is **0 in all three pools**, so
the gate was binding on nobody. If it ever climbs, revisit on evidence.

## Consequences

Good. The board stops laundering a weak estimate through precise-looking arithmetic, and
its numbers now match the source they are reproduced from. A whole column of derived value
and its rank come off the board, which is 18 columns of horizontal budget returned to the
nine that replaced them.

Bad. **Durability is now entirely a judgement call, made by reading a column rather than by
the board doing it for you.** For a genuinely fragile player this is a step backwards from a
mechanism that, whatever its input, was directionally right. The mitigation is presentational
only: the GP block stays, the amber 68–74 "generic haircut" band stays, and the CHECK flag
stays. If the projection's own GP estimates ever become trustworthy enough to price, this is
reversible — but it should be reversed with evidence, not with the assumption that a number
is better than no number.

The quant-vs-expert procedure loses its main instrument: it routed most accepted overrides
into `My GP Est` precisely because that was the safe place to encode judgement. Those
overrides now inform a read rather than moving a rank. That document needs revisiting.

## Alternatives rejected

**Keep the adjustment and improve the GP input.** The playbook already specifies how — three
years of history, regressed, age-adjusted, then 15 to 30 hand overrides. It was never done,
across a full season of the board existing. A mechanism that depends on work that does not
happen is a mechanism that runs on a provider default.

**Show a GP-adjusted column beside the unadjusted one.** Re-introduces the number this
record removes, one column away from the one that replaced it, and invites reading whichever
supports the pick you already wanted.
