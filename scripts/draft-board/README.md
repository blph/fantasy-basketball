# Draft board builder

Builds the 9-cat draft board as a Google Sheet, implementing
[the playbook](../../docs/references/fantasy-basketball-draft-playbook.md).

**Documentation lives in [docs/draft-board/](../../docs/draft-board/):**

- [build-and-maintenance.md](../../docs/draft-board/build-and-maintenance.md) —
  how it was built, how to bring new data in without losing hand edits, and the
  Apps Script traps worth knowing.
- [cheat-sheet.md](../../docs/draft-board/cheat-sheet.md) — what every number on
  the board means. Generated from `Build.gs`; do not edit by hand.

## Files here

| File | What it is |
|---|---|
| `Build.gs` | Layout, every formula, all formatting, the menu |
| `sources.py` | Reads the three projection exports and joins them |
| `board_values.py` | The nine values: ZSC, ZSH and DURH, per projection |
| `build_data.py` | Runs the pipeline and writes `Data.gs` |
| `harness.js` | Mocks the Sheets API and dry-runs the build in Node |
| `export_readme.js` | Regenerates `docs/draft-board/cheat-sheet.md` |
| `valuation.py` | The playbook's z/G/VOR math. No longer what the board runs on — kept because Phase 2 inherits it |
| `verify.py` | Re-checks `Data.gs`'s invariants and diffs a pull of the live board against it |
| `export_yahoo_rankings.py` | Turns the finished board into a CSV Yahoo will import |
| `Data.gs` | The players. Provider data — **gitignored, never commit** |

```bash
python3 scripts/draft-board/build_data.py --dry-run  # 1. what would change
python3 scripts/draft-board/build_data.py            # 2. write Data.gs
cd scripts/draft-board && node harness.js            # 3. dry-run before touching Google
python3 scripts/draft-board/verify.py                # 4. check the numbers independently
```

Then paste into the bound Apps Script project and run **`Draft Board ▸ Refresh
data`**, which updates only what changed and leaves your hand edits alone.

`pytest` covers this directory. `tests/test_valuation.py` pins the properties
that are easy to break and hard to notice: pool rates are aggregates rather than
averages of rates, availability can discount a player but never promote one, the
pool converges rather than trusting the provider's seed order, a category
with no spread fails by name instead of dividing by zero, and the Category
profile labels split at the band, keep turnovers flipped exactly once, drop a
punted category from both lists, and stay measured against the pool rather than
the league.
`tests/test_export_yahoo_rankings.py` covers the Yahoo CSV converter. CI runs
both, plus `ruff` and the harness, on every push.
