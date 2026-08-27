# Draft board builder

Builds the 9-cat draft board as a Google Sheet, implementing
[the playbook](../../docs/references/fantasy-basketball-draft-playbook.md).
Interim tooling for the 2026-27 draft, ahead of the Phase 2 pipeline
([ADR-0008](../../docs/decisions/ADR-0008-google-sheet-draft-board.md)).

Every value a player is judged on is a **live formula in a cell**, not a number
the script computed. The board has to be auditable on the clock.

## Files

| File | What it is | Committed |
|---|---|---|
| `Build.gs` | Layout, every formula, all formatting, the custom menu | yes |
| `gen_data.py` | Parses a Hashtag Basketball export into `Data.gs` | yes |
| `harness.js` | Mocks the Sheets API and dry-runs the whole build | yes |
| `Data.gs` | The players. Provider data — **gitignored, never commit** | no |

## Rebuilding

```bash
# 1. Generate the data file from an export under data/ (gitignored)
python3 scripts/draft-board/gen_data.py data/player_data/player_data_MMDD.md \
        scripts/draft-board/Data.gs

# 2. Dry-run before touching Google. Catches range and API errors in seconds.
cd scripts/draft-board && node harness.js
```

Then in the spreadsheet: **Extensions ▸ Apps Script**, paste `Build.gs` into
`Code.gs` and `Data.gs` into a second script file, save, and run
`buildDraftBoard()`.

A full build runs close to the six-minute execution cap, so it is split into
steps that each finish in well under a minute. Use them when iterating:

| Menu item | Rebuilds |
|---|---|
| `Full rebuild (from Data.gs)` | everything |
| `Step 1 — Settings only` | Settings |
| `Step 1b — Reformat Board` | Board formatting, leaving data and formulas |
| `Step 2 — Draft Board only` | the draft-day tab |
| `Step 3 — Punts, Tracker, README` | the rest, then tab order |

Each step writes its outcome to `Settings!A41`, which survives a thrown
exception — the execution log does not.

## Two operations that are not automatic

**`Re-seed pool from current ranks`.** The pool is "the top 156 by value", but
you need values to know who those are. Seed Rank breaks that circle: membership
keys off a static rank rather than a live one, avoiding a circular reference.
Running this copies current Adj Rank into Seed Rank — one iteration. Twice is
enough; the set stops changing.

**`Rebuild & re-sort`.** Draft Board row order is deliberately static so nothing
moves while you are hand-editing mid-draft. This re-sorts against current
Adjusted Values and preserves checkbox state by matching on player name.

## The export has two quirks

Both are handled by `gen_data.py`, and both will silently corrupt a hand-rolled
parser:

- **Header rows repeat** roughly every 13 players, interleaved through the file.
- **`R#` sometimes holds two numbers** (`18 38`) — the rank plus a
  rank-movement indicator. Only the first is the rank.

Percentages arrive as `0.573(10.5/18.3)`, so makes and attempts are available.
They are required: FG% and FT% are volume-weighted, and valuing them as bare
rates is silently wrong.

`gen_data.py` asserts contiguous ranks, no duplicate names, and no unparsed
rows, rather than skipping bad rows. A dropped player is a wrong board.

## Apps Script constraints worth knowing

Each of these broke a build during development:

- **A frozen column may not split a merged cell.** Block headers are merged
  across their columns, so `setFrozenColumns` has to land on a block boundary.
- **A new sheet is 26 columns.** The Board needs 67. `ensureGrid()` grows it
  first; `setColumnWidth` past the last column throws.
- **A string starting with `=` is stored as a formula**, whatever the cell's
  number format. The README tab's formula reference leads each one with a space.
- **Conditional format rules resolve in order.** A general row-banding rule
  added first suppresses the specific rules that follow it, so banding is added
  last.
- **Column grouping is cumulative.** Re-running the formatter stacks new groups
  on old ones and collapses columns nobody asked to hide; `resetColumnGroups()`
  flattens first.

## The harness

`harness.js` mocks enough of the Sheets API to execute `buildDraftBoard()` in
Node and assert what actually breaks: range and array dimension mismatches,
writes past the grid, frozen columns splitting merges, and calls to methods that
do not exist. It also checks the generated formula strings land in the right
cells.

It runs without `Data.gs`, synthesizing a 200-player pool, so it works on a
clean clone. It caught three real bugs that would otherwise have cost a
round-trip through Google's authorization flow each.
