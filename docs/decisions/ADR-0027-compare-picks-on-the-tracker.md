# ADR-0027: Compare picks, beside the Category Tracker, ranked on expected categories won

- Status: Accepted
- Date: 2026-09-17
- Owner: Bryan

## Context

On the clock, the owner decides between a handful of players by ticking one `MINE`, reading
the Category Tracker, unticking him, and trying the next. That is slow, and between tries the
board says he has drafted someone he has not.

What he wants to know is which of those players leaves him best placed across the categories,
given the players he already has, and what the tracker would read after each. The tracker
already computes that for the roster he has. So the question is how to run it one pick ahead,
for several candidates at once.

## Decision

**A candidate's column is the tracker, recomputed as if he were ticked `MINE`.** That means
n + 1 players, the benchmark cut at `MIN(Q, TEAMS × (n + 1))`, and the same `K` and cutoffs as
[ADR-0018](ADR-0018-tracker-on-durant-basis.md) and [ADR-0023](ADR-0023-win-rate-cutoffs-40-60.md).
Nothing new is modelled, and the column shows exactly what the tracker will read once he is
ticked. A test holds the engine to that equality.

**Candidates rank on expected categories won: Σ Win % over the categories not ticked
Punted.** This is a categories league, so every category is a separate weekly result, and the
sum is the expected number of category wins against an average drafted opponent. Its marginal
value is largest near a coin flip. That makes the ranking agree with the tracker's standing
advice to spend the next pick on a CONTESTED row. A tie goes to the lower board `#`.

**The small row reads the gap to the best candidate, not the change from now.** With every
pick, the benchmark moves up by `TEAMS` players and the divisor becomes √(n + 1). Both apply to
every candidate alike, so a change against now can read negative for all of them at once. The
gap to the best says what the choice is worth: whether it is a toss-up or a real difference.
The tracker's own total now sits under its Win % column, so the before and after can still be
read across.

> **Superseded in part by [ADR-0028](ADR-0028-cmp-replaces-gone.md).** The slots are no
> longer dropdowns. They fill from the Draft Board's `CMP` ticks, which took `GONE`'s place.
> The rest of this record stands.

**Five single-select dropdown slots, not one multi-select.** Apps Script cannot create a
multi-select dropdown: `DataValidationBuilder` has no such option, and no API offers one.
Every Full rebuild also clears all the validation on the tracker tab. A multi-select set by
hand would vanish at the next rebuild, and nothing would say so. A slot is a dropdown over a
hidden, live list of everyone not GONE or `MINE`, in board order, and typing into it narrows
the list. It rejects a partial name. A name taken after it was typed stays in its slot, and
the slot's status reads `gone`.

**Candidates are sheet inputs, not draft state.** They are read the way the ticks are:
`verify.py --local` reads the five slots from a pull and holds every panel cell to the engine.
The local command, `board.py compare NAME…`, takes the names as arguments and writes nothing
to `draft-state.json`.

## Consequences

Good:

- A shortlist is scored in one step, and nothing on the board is ticked while it is.
- The answer uses the same model, the same numbers and the same Read states as the tracker
  beside it, so the two cannot disagree.
- The panel is rebuilt with the tab, and verified with it.

Bad:

- **It is one pick ahead and no further.** It does not know who will still be there next
  round. The board `#` sits above each name so that "fits now" can be weighed against "will
  still be there". The ranking does not weigh it.
- It inherits every limit of the tracker:
  - turnovers are invisible;
  - the opponent is an average of the drafted pool, not a real manager who specialises;
  - `k_FG` and `k_FT` are still provisional.

  A gap of a few hundredths of a category is within that noise.
- Five slots cost 716 px beside the tracker, plus six hidden columns. Names longer than about
  19 characters clip in their slot.
- The two cutoffs and the Read strings are now written in two places in `Build.gs`, the
  tracker's Read column and the panel's. The engine's `READS` is the one both are checked
  against.

## Alternatives rejected

- **A native multi-select chip dropdown, set by hand.** This is the control the owner first
  asked for. It cannot be built by the script, and a rebuild removes it silently.
- **One "add candidate" cell and an `onEdit` that appends to a list.** Each add waits on a
  script, from half a second to two seconds. It fails silently. It needs its own way to remove
  a name, and it widens the one trigger that runs on every tick.
- **A CONSIDER checkbox column on the Draft Board.** It needs no search, but it shifts every
  Draft Board column map, the layout and the local engine's input with them. It also leaves
  the answer on a different tab from the tick.
- **Candidates as rows and categories as columns.** The tracker reads categories down the
  rows. Turning the grid sideways means the eye has to transpose it to compare the two.
- **The probability of winning the week outright.** That is the objective in a
  most-categories league, not in this one. It also needs the turnover category the board
  cannot measure.
