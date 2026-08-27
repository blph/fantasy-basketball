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
| `gen_data.py` | Parses a provider export into `Data.gs` |
| `harness.js` | Mocks the Sheets API and dry-runs the build in Node |
| `export_readme.js` | Regenerates `docs/draft-board/cheat-sheet.md` |
| `Data.gs` | The players. Provider data — **gitignored, never commit** |

```bash
python3 scripts/draft-board/gen_data.py data/player_data/player_data_MMDD.md \
        scripts/draft-board/Data.gs      # 1. build the data file
cd scripts/draft-board && node harness.js # 2. dry-run before touching Google
```

Then paste into the bound Apps Script project and run **`Draft Board ▸ Refresh
data`**, which updates only what changed and leaves your hand edits alone.
