# ADR-0010: Which punt builds the board ships

- Status: Accepted
- Date: 2026-08-27
- Owner: Bryan

## Context

The board shipped six builds: single punts on FT% and FG%, then FG%+REB,
AST+STL, PTS+FT%, and the FG%/FT%/TO triple. `Build.gs` described them as "the
six builds from playbook section 10," which overstated it —
the playbook lists `BLK + FG%` among its working pairings and the code does not
implement it. [ADR-0008](ADR-0008-google-sheet-draft-board.md) declares four
deliberate deviations and this substitution is not among them.

A [methodology review](../reviews/2026-08-27-draft-board-methodology-review.md)
flagged the omission as a defect. Checking the published guides reversed that
conclusion and turned up a second, larger gap.

**On `BLK + FG%`: the playbook is wrong and the code was accidentally right.**
The guides treat punt-blocks and punt-FG% as competing routes to the same
small-ball roster, not as complements. Elite Fantasy Basketball, which publishes
a dedicated punt-blocks guide, names FG% as one of three categories a
punt-blocks roster must actively **protect**, and frames the choice as
either/or: punt FG% "has a higher ceiling… however, it is also a harder strategy
to pull off and comes with a lower floor" than punt blocks. Conceding both is
not a pairing; it is the three-category "punt big-man stats" build, which is a
different and much harder thing.

**The real gap was in the single punts.** RotoBaller states that "the four most
popular categories to punt are threes, free-throw percentage, field goal
percentage, and assists." The board covered two of those four. Punt AST is
described as "the easiest build to understand, the easiest to pull off"; punt
3PM had no column at all. Punt BLK is less popular than the top four by its own
publisher's admission, but it is repeatedly described as the build you pivot
*into* mid-draft — which makes it the one most valuable to have pre-computed,
since it is the one you fall into rather than plan.

## Decision

Ship **nine** builds: five single punts, then four groupings.

| Build | Drops | Why |
|---|---|---|
| Punt FT% | FT% | Canonical single |
| Punt FG% | FG% | Canonical single |
| Punt AST | AST | Canonical single; the easiest build to execute |
| Punt 3PM | 3PM | Canonical single |
| Punt BLK | BLK | The mid-draft pivot you fall into after a guard-heavy start |
| Punt FG%+REB | FG%, REB | Playbook pairing |
| Punt AST+STL | AST, STL | Playbook pairing |
| Punt PTS+FT% | PTS, FT% | Playbook pairing |
| Punt FG/FT/TO | FG%, FT%, TO | The "simplest trifecta"; multi-source |

`BLK + FG%` is **not** shipped, and has been removed from the playbook's working
pairings with the reasoning above. Punt TO does not ship as a standalone either:
it appears in the guides only as a rider on FG% and usage builds, and nobody
publishes a standalone punt-turnovers guide.

Nine sits inside the range the guides recommend — Elite Fantasy Basketball
suggests "a backup strategy (or six)," SportsEthos works through nine singles
plus combinations.

## Consequences

**Good.** The four canonical single punts are all covered for the first time, and
so is the build you are most likely to land in without planning it. `PUNTS` is a
data structure, so each build costs three lines.

**Bad, and operationally sharp.** Three more builds is six more Board columns and
eighteen more on the Punts tab. More importantly it **moves the column layout**,
and `Refresh data` writes into a fixed layout — so changing the build set
requires a full rebuild, which does not preserve the `Notes` column. This is now
documented in [build-and-maintenance.md](../draft-board/build-and-maintenance.md).

**Guarded against drift.** The "Best build" indicator's labels and the Punts tab's
column span are now generated from `PUNTS` rather than hand-listed, and the
harness asserts that the score and rank columns stay contiguous in build order —
the Draft Board `MATCH`es across the rank span as a single range, so a gap there
would silently mislabel every build.

**Still not adaptive.** Nine static columns are nine static columns. Rosenof's
point that punting is inherently adaptive and "cannot be executed properly with
a static ranking list" stands; this widens the net rather than answering it.
