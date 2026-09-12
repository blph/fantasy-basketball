# ADR-0020: Every derived cell names the player, and the board checks that it did

- Status: Accepted
- Date: 2026-09-01
- Owner: Bryan

## Context

The Draft Board is a re-sortable view over four tabs that never move. Row 5 of the board is
whichever player the current sort puts fifth; row 5 of `BMP` is always the same player.
Every cell on the board is therefore one of two kinds:

- **identity** — `=BMP!$Q$5`, pinned to a player's calculation row, correct wherever the
  board puts that player;
- **positional** — `=$BQ5`, `=$J5`, `RANK($AB5,…)`, meaning "whatever is in my row", correct
  only while the row it reads belongs to the same build.

Both are legitimate. Mixing them **inside one output** is not, and that is what the rank tag
did: `="#"&$BQ5&" "&BMP!$S$5` took the rank positionally and the dropped category by
identity. When the hidden block was left over from an earlier sort, the tag paired one
player's rank with another's dropped category on 1755 of 1800 cells and read like a rank
throughout. Nothing noticed: the harness compares formula strings and never evaluates one,
and the sheet's own alignment guards had silently become `COUNTA(#REF!)`.

See [the bug report](../bugs/2026-09-01-draft-board-tag-rank-misalignment.md).

## Decision

**1. A single displayed value may not mix the two kinds.** If any part of a cell is an
identity reference, every part is, and all of them name the same calculation row. The rank
tags now do. The consequence is the point: a tag can only be wrong when the value beside it
is wrong too, and the value is checked.

**2. The board carries a witness that its blocks belong to its rows.** A hidden `row check`
column resolves the player name from the same calculation row the hidden feed reads.
Settings compares it against `Player` across all 200 rows and reports `MISALIGNED`
otherwise. Positional references stay legal — they are how a re-sortable board works — but
they are no longer unwitnessed.

**3. The sanity checks reach across tabs only through `INDIRECT` over R1C1.** A named range
dies when its tab is recreated; an A1 reference shifts when a column is inserted at or
before it. Both happened, and both left a guard reporting a blank that reads as a pass. A
string is not a reference, so Sheets rewrites neither. The column position comes from the
`D`/`B`/`V` maps at build time, which are the only authority on it.

**4. A rank ships as the rank of the value shipped beside it.** `build_data.py` ranks the
rounded number, because the sheet's `#` column ranks what it was given.

**5. Formula correctness is established in the sheet, on real rows.** `verify.py --sheet`
takes a full `A4:AA203` pull and checks all 1800 tags against `Data.gs`. The offline gates
bound what reaches the sheet; they do not conclude it.

## Consequences

- One extra hidden column on the Draft Board, and one extra row on Settings.
- The tags no longer read the hidden rank columns. Those stay: the "projections disagree"
  conditional formats need a numeric cell, and a format rule may not reference another sheet.
- `INDIRECT` is volatile. Six cells on Settings, evaluated on recalculation, not on the clock.
- A build that leaves the board half-written is now visible on the sheet within a second of
  opening it, rather than after a draft.

## Alternatives rejected

- **Compute the tag in Python and write it as a string.** Cheapest, and it would have
  prevented this. Rejected: the rank has to stay live so the disagreement highlight and the
  tag cannot drift apart, and a written string would hide a stale build rather than expose it.
- **Make every reference positional.** Self-consistent, but then a sort that moved rows
  without rewriting formulas would corrupt everything silently instead of loudly.
- **Trust the writer and add no witness.** The writer was in fact correct; the sheet was
  left half-built by an interrupted run. A guard that costs one column is worth more than
  the assumption that every build finishes.
