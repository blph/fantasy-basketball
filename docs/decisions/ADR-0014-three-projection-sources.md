# ADR-0014: Three projection sources on one board, joined by name

- Status: Accepted
- Date: 2026-09-01
- Owner: Bryan

## Context

The board has always run on one projection. `decision-log.md` has carried "a second
projection source" as an open decision since ADR-0007, and named the cost plainly: with
one source, "everyone agrees he is 40th" and "opinions range 22nd to 71st" look identical.

The Basketball Monster research measured that cost. Running *identical* math over
Basketball Monster's two projection sources moves players a mean of ~20 rank places, with
a maximum near 95, and about 130 of 212 shared players move ten or more. Two thirds of a
typical gap comes from the two percentage categories alone. The conclusion recorded there
is blunt: **choosing your projections matters more than choosing your valuation.**

A single-source board cannot show any of that. It reports one number with no indication of
whether it is contested.

## Decision

**Carry three projection sources and show all three, unblended.**

| Label | Source | Shape |
|---|---|---|
| `HBP` | Hashtag Basketball | per game, top 200, carries team, position and ADP |
| `BMP` | Basketball Monster, Josh's projections | season totals, ~570 rows, `player_id` |
| `BMP-ALT` | Basketball Monster, bonus projections | same schema, second opinion |

**HBP is the spine.** It decides which 200 players are on the board and supplies every
identity column. The two vendor files supply stat lines only.

**Each source is scored over its own universe.** Pools are drawn from ~510 players for the
vendors and 200 for Hashtag, because a value is a property of the pair (stat line, pool)
and mixing them would produce a number belonging to neither. Hashtag publishes only its
top 200, so its pool is a truncated candidate set; that asymmetry is reported on Settings
rather than hidden.

**The join is a normalised name plus an explicit alias table.** The two vendors share an
id space and join on `player_id`. Hashtag has no id at all, so `sources.normalise` folds
diacritics, strips generational suffixes, and drops case and punctuation. Two players the
normaliser cannot reconcile — the vendors disagree on the name itself, not its spelling —
are handled by a two-entry `ALIASES` table: `Cameron Johnson → Cam Johnson`,
`Herbert Jones → Herb Jones`.

**An unresolved player is a hard error.** Never a skipped row, per AGENTS.md. A silently
dropped player is a hole in the board that looks exactly like a player nobody rates.

## Consequences

Good. Disagreement is visible where it matters: on the current data Kawhi Leonard is DURH
#6 on BMP and #21 on HBP, and Embiid is #8 and #30. Those are the rows worth slowing down
on, and the old board could not point at them. The board also stops depending on one
vendor's release schedule for its identity columns.

Bad. Three files must move together, so a refresh has more that can go wrong; `build_data.py`
refuses a partial or mixed-date set for that reason. The join is a name match, which is
exactly the fragility ADR-0007 flags for the eventual ESPN↔Yahoo crosswalk — the difference
is that here it is 200 rows, checked on every run, and fatal on failure rather than silent.

The board is 18 value columns wider. That is a real cost on a tab used under a pick clock,
and it is why the projection filter exists.

## Alternatives rejected

**Blend the three into a consensus.** Averaging destroys the only thing three sources
give you that one does not — the spread. It also invents a stat line no provider stands
behind, which then has no pool of its own to be standardised against.

**Union the three player sets.** ~520 rows, of which ~320 would have no team, position or
ADP, and the board would need those hand-filled to be draftable. The gain is players
Hashtag ranks outside its top 200, who are below replacement in a 156-man pool anyway.
