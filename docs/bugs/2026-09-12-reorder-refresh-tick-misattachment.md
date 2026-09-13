# A reordering refresh moves GONE and MINE ticks onto other players

- Found: 2026-09-12, while designing the local draft board
  ([design §6](../draft-board/2026-09-12-local-board-design.md), defects I1 and C1)
- Status: **I1 open.** Recorded here, not fixed; the fix belongs on a follow-up branch.
  **C1 fixed** in the commit that adds this file (see [the second defect](#c1-the-same-refresh-blanked-my-gp--fixed)).
  Not yet deployed to the sheet.
- Severity: **High** for I1, whenever a refresh reorders the Board while any tick exists. The
  draft state is corrupted rather than wiped, and every tick still looks deliberate. Medium for C1.

## What happens

`Draft Board ▸ Refresh data` has two paths. When the new export keeps the same players in the
same order, `refreshInPlace` writes only changed cells and nothing moves. When the player set or
order changes (the ordinary case since three sources feed the board), `refreshWithReorder`
rewrites the Board in the new order and re-attaches the Board's hand columns by name. The
calculation tabs are rewritten in the same new order.

The Draft Board is not touched, and that is the defect. Each Draft Board row is formulas
pinned to a Board **row number**, fixed when the tab was last built:

```js
// Build.gs, buildDraftTab
function bref(col) { return '=' + cellRef('Board', col, n); }   // e.g. ='Board'!$B$17
...
row[D.player] = bref(B.player); row[D.team] = bref(B.team); row[D.pos] = bref(B.pos);
```

The GONE and MINE checkboxes, on the other hand, are plain values in the Draft Board's own
rows. After the refresh, Board row 17 holds a different player, so Draft Board row *i* shows a
new name, team and values beside the same tick. Nothing errors.

The refresh then says `Re-sort the Draft Board.`, and the re-sort saves the damage by name:

```js
// Build.gs, readCheckState -- called by buildDraftTab when Rebuild & re-sort passes no prior
var names = sh.getRange(R0, at.Player, n, 1).getValues();   // the NEW names on each row
var gone  = sh.getRange(R0, at.GONE,  n, 1).getValues();    // the OLD ticks on each row
var mine  = sh.getRange(R0, at.MINE,  n, 1).getValues();
...
state[names[i][0]] = { gone: gone[i][0] === true, mine: mine[i][0] === true, ... };
```

`restoreCheckState` then writes each tick beside the player it was saved under, in the new sort
order. Once that has run, the sheet has no record of which player a tick originally belonged to.

### Notes are overwritten on every re-sort, reorder or not

The Draft Board's Notes cell is a formula into the Board, `row[D.notes] = bref(B.notes)`, which
follows its player by construction. `readCheckState` still captures the note, and
`restoreCheckState` writes the whole Notes column back as values once any note exists:

```js
// Build.gs, restoreCheckState
var cols = [[D.drafted, 'gone', false], [D.mine, 'mine', false],
            [D.notes, 'notes', '']];
...
if (any) sh.getRange(R0, col, out.length, 1).setValues(out);
```

That replaces 200 formulas with literals and blanks. After it, a note typed on the Board does
not appear on the Draft Board. A note typed on the Draft Board never reaches the Board, so the
next reordering refresh, which carries Board notes by name, does not carry it. `readCheckState`'s
own comment describes the same trap for `INJ` and removed it there; Notes were left behind.

## Why nothing caught it

- The harness never runs a refresh followed by a re-sort. Its `readCheckState` check uses a
  hand-built sheet whose names and ticks already agree, and it asserts `Notes travel with the
  checkboxes`, so the Notes half is pinned as intended behaviour.
- `verify.py --sheet` compares values and tags, not ticks. The local board's parity check
  (`verify.py --local`) takes ticks read back from the sheet as truth, and the design lists this
  defect among its known gaps for that reason.

## Exposure on the live sheet

On 2026-09-12 the sheet carries 13 MINE ticks, no GONE ticks, no Punted categories and no Notes.
The next reordering `Refresh data` would move those 13 ticks onto whichever players then occupy
their Board rows. Notes are empty, so the Notes half has not yet done any damage.

Local draft state (`board.py`) is keyed by the normalised player key (`sources.normalise`),
with the display name stored beside it, and is unaffected.

## Workaround until it is fixed

1. Before any `Refresh data`, pull `Draft Board` `Player`, `GONE` and `MINE` through Playwright
   (procedure in [build-and-maintenance.md](../draft-board/build-and-maintenance.md)) and keep
   the names of the ticked players. Do not commit that pull: it is provider data.
2. Refresh, then `Rebuild & re-sort`.
3. Clear every GONE and MINE tick and re-tick from the list by name. Do not trust any tick the
   refresh left in place.
4. Keep notes on the Board tab, not the Draft Board.

Never refresh during a live draft.

## Proposed fix (follow-up branch)

- In `refreshData`, when the order changes, call `readCheckState` on the Draft Board **before**
  `refreshWithReorder` rewrites the Board. At that point the displayed names still belong to the
  ticks. At the end of the refresh, rebuild the Draft Board with that state
  (`buildDraftTab(ss, sh, board, prior)`), so ticks re-attach by name in the same action.
  `buildDraftTab` on a live sheet appends conditional-format rules
  ([2026-09-02 bug](2026-09-02-conditional-format-duplication.md)), so land that fix first or
  together with this one.
- Drop Notes from `readCheckState` and `restoreCheckState`. The Draft Board cell mirrors the
  Board, exactly like `INJ`, and the Board's notes already travel by name. Invert the harness
  assertion to `Notes do NOT travel with the checkboxes`.
- Harness: a refresh-then-re-sort run on mocks with ticks, asserting every tick stays on its
  named player.
- Verify in the sheet on a copy, never the live board: steps 4 and 5 of the tick scenario in
  the design's §4.

## C1: the same refresh blanked My GP — fixed

### What happened

`writeBoardFormulas` seeds every Board `My GP Est` cell with `=$<GP column><row>`, and the GP
flag reads it: `=IF(<My GP>="","",IF(ABS(<GP>-<My GP>)>10,"CHECK",""))`. `refreshWithReorder`
captures a My GP override only when the cell no longer holds a formula. It then rewrites the
Board, reseeds the formulas and puts the hand columns back:

```js
// Build.gs, refreshWithReorder, before the fix
for (var j = 0; j < POOL_ROWS; j++) {
  var rec = keep[newNames[j]];
  var v = rec && rec[hc] !== undefined ? rec[hc] : '';
  if (v !== '') { any = true; restored++; }
  out.push([v]);
}
if (any) board.getRange(R0, hc, POOL_ROWS, 1).setValues(out);
```

Once one override existed, `any` was true and the column was written whole. Every row without
an override got `''` over the formula `writeBoardFormulas` had just written. The flag then read
blank on all of those rows and said nothing, which looks the same as "no disagreement". It never
recovered by itself: every later reordering refresh reseeded the formulas and blanked them again.
Only a Full rebuild or `Step 3` restored them. The Draft Board's `My GP` column mirrors the Board,
so it went blank too.

On 2026-09-12 the live sheet's `My GP Est` column is filled, so the live board has not hit this.

### Fix

A row with no saved override gets its seeding formula back instead of `''`:

```js
if (v !== '') { any = true; restored++; }
else if (hc === B.myGp) v = '=$' + a1col(B.gp) + (R0 + j);
```

The formula is assigned after the test, so the count of re-attached edits in the refresh toast
still counts only real edits.

### Verified

- Offline: the harness seeds a scratch Board, overrides one My GP, and runs
  `refreshWithReorder` with the previous order reversed. Before the fix it reported
  `199 rows lost it; first: row 4 holds ""`. After the fix, every unoverridden row holds its
  seeding formula, the override lands on its player's new row, and the toast counts 2 edits
  (the override and a note).
- **In the sheet: not yet.** The harness takes on trust that `setValues` stores a string
  beginning with `=` as a formula, which only Sheets can confirm. It is step 5 of the tick
  scenario (a My GP override followed by a reordering `Refresh data`, on a copy), and this
  defect is not closed until that step passes.
