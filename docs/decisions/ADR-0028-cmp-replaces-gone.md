# ADR-0028: CMP replaces GONE, and Compare picks fills from it

- Status: Accepted
- Date: 2026-09-18
- Owner: Bryan
- Supersedes: ADR-0027 (in part)

## Context

The Draft Board carried a `GONE` checkbox beside `MINE`, for ticking every player another
manager takes. The owner does not tick it, and does not intend to. So the column did nothing,
and `Left @pos`, the one column that read it, always counted every player as still available.

Compare picks ([ADR-0027](ADR-0027-compare-picks-on-the-tracker.md)) took its candidates from
five dropdown slots on the Category Tracker. You scan for candidates on the Draft Board, then
retype their names on another tab. The owner asked for the candidates to be picked where they
are found.

## Decision

**`CMP` takes `GONE`'s place.** It is the same column, 8, inside the frozen pane, and a
checkbox on every row. Nothing else on the Draft Board moves for it. It is named `CMP`, not
`CONTESTED`, because CONTESTED already names a tracker Read state. Its named range is `DB_CMP`,
and the build removes the retired `DB_GONE`.

**Compare picks fills from the CMP ticks.** Each slot is a formula: the players ticked `CMP` and
not `MINE`, best board # first. A `MINE` tick takes a player out, because he is no longer a
choice and the tracker already counts him. The dropdowns, their hidden source column and the
per-slot status cells are gone. Everything else ADR-0027 decided stands: the model, the ranking
on expected categories won, the gap to the best, and the per-cell formulas.

**More than five ticked compares the best five by board #, and says so.** The panel's note reads
"Top 5 of 7 ticked, by board #". A candidate dropped without a word would look like one the
board had never seen.

**Two routes clear every CMP tick, and a menu item backs them both:**

- **The Clear all box beside the Compare picks title.** This is where the comparison is read.
  It is a checkbox used as a button: `onEdit` unticks every `CMP`, then the box.
- **Any `MINE` tick.** The comparison was for that pick, so the moment it is made is when the
  shortlist stops meaning anything. A pasted block counts if it ticks MINE. Unticking MINE
  never clears.
- **`Draft Board ▸ Clear compare`.** It does the same job. The board already backs its `onEdit`
  controls with menu items, because a simple trigger fails silently.

Both routes are the simple `onEdit` trigger, which needs no authorisation and survives a rebuild.

**A rebuild never turns an old GONE tick into a CMP tick.** Ticks are carried through a rebuild by
header label. When a label is missing, the carry falls back to the column map's position. For
`CMP`, that position held `GONE` until this change. So `CMP` has no fallback: a sheet whose
header does not say `CMP` has no CMP ticks to carry.

**`Left @pos` leaves the sheet, and `gone` stays on the local board as the agent's pick log.**
The sheet cannot know who is left without GONE. An agent logging picks on draft day, with
`board.py gone`, still can. So the local board keeps `gone` and its own Left @pos, as it already
keeps pick numbers the sheet has never had. `verify.py --local` reads no GONE from the sheet and
never compares either of them.

## Consequences

Good:

- Candidates are picked in the pane where they are found, with one click each.
- A column that did nothing now does the one job the board lacked.
- The panel needs no typing and has no dropdown behaviour to depend on.
- No Draft Board column moved for CMP.

Bad:

- **The sheet no longer knows who has been drafted.** A player another manager takes stays in
  Compare picks until you untick him, tick Clear all, or tick MINE on your own pick. The
  README says so under the things that are not automatic.
- **Ticking MINE discards the rest of the shortlist.** A runner-up you meant to take next round
  has to be ticked again. That was chosen over leaving a stale comparison on screen.
- **`Left @pos` is gone from the sheet.** Its columns to the right moved left by one, which the
  layout, the pull and verify follow from the generated map.
- **The clearing lives in a simple trigger, which swallows its own errors.** The harness drives
  every case in its mock. The tick scenario proves both routes on a copy of the live sheet. The
  menu item is the fallback.

## Alternatives rejected

- **Keep GONE and add CMP beside it.** That makes the frozen pane wider, for a column nobody
  ticks.
- **Call the column CONTESTED.** That is the owner's word for it, but the tracker's Read column
  already uses it for a category near a coin flip, and it is the only amber fill on that tab.
- **A clear box at the top of the CMP column.** Row 1 there is the sort dropdown and row 2 the
  CLOCK banner. The box would have no room for a label, and it would split the banner.
- **Six slots.** The panel would reach about 850 px. Five, plus a note naming what was left out,
  answers the question the owner asked: the best, then second, third and fourth.
