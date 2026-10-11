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
| `build_data.py` | Runs the pipeline and writes `Data.gs` and the local board snapshot, in one run |
| `board_settings.py` | League and board settings; `SETTINGS_DEFAULTS` in `Build.gs` must equal it |
| `board_snapshot.py` | Paths, digest and loading for the local board snapshot |
| `board_engine.py` | The sheet's draft-day formulas in Python. Recomputes no value |
| `board_names.py` | Resolves a typed or Yahoo-spelled name to one board player |
| `board_state.py` | The local draft state: locked atomic writes, backups, undo |
| `board.py` | The CLI agents read and tick the local board through. Its output is provider data |
| `board_layout.json` | Every tab's labels and addresses, written by `harness.js --write-layout`. Committed |
| `pull_sheet.py` | Downloads the live sheet as xlsx through `playwright-cli` for `verify.py --local` |
| `tick_scenario.py` | The tick scenario on a copy, as one command: ticks, punts, re-sort and refresh, verified after every step |
| `verify_local.py` | The `verify.py --local` comparison: the engine run on the sheet's own ticks and order, cell by cell |
| `harness.js` | Mocks the Sheets API and dry-runs the build in Node |
| `export_readme.js` | Regenerates `docs/draft-board/cheat-sheet.md` |
| `valuation.py` | The playbook's z/G/VOR math. No longer what the board runs on — kept because Phase 2 inherits it |
| `verify.py` | Re-checks `Data.gs`'s invariants and the snapshot against it; diffs a pull of the live board against both (`--local` for the engine) |
| `export_yahoo_rankings.py` | Turns the finished board into a CSV Yahoo will import, from a pull or the local snapshot (`--local`) |
| `Data.gs` | The players. Provider data — **gitignored, never commit** |

```bash
python3 scripts/draft-board/build_data.py --dry-run  # 1. what would change
python3 scripts/draft-board/build_data.py            # 2. write Data.gs and the snapshot
cd scripts/draft-board && node harness.js            # 3. dry-run before touching Google
python3 scripts/draft-board/verify.py                # 4. check the numbers independently
```

Then Claude pushes `Data.gs` into the bound Apps Script project through Playwright and
runs **`Draft Board ▸ Refresh data`**, which updates only what changed and leaves your
hand edits alone. After `Rebuild & re-sort`, `pull_sheet.py` and `verify.py --local`
confirm the local engine still agrees with the sheet. The procedure is in
[build-and-maintenance.md](../../docs/draft-board/build-and-maintenance.md).

`pytest` covers this directory. `tests/test_valuation.py` pins the properties
that are easy to break and hard to notice: pool rates are aggregates rather than
averages of rates, availability can discount a player but never promote one, the
pool converges rather than trusting the provider's seed order, a category
with no spread fails by name instead of dividing by zero, and the Category
profile labels split at the band, keep turnovers flipped exactly once, drop a
punted category from both lists, and stay measured against the pool rather than
the league.
`tests/test_export_yahoo_rankings.py` covers the Yahoo CSV converter, from a pull
and from the local snapshot. The engine, CLI, name resolution, state, verification and
export tests build on synthetic boards from `tests/board_fixtures.py`:

| File | What it holds the local board to |
|---|---|
| `tests/board_fixtures.py` | Synthetic snapshot builder for engine, CLI, state, name resolution, verification and export tests |
| `tests/test_board_settings.py` | `board_settings.py` against `Build.gs`, `config/league.yaml` and the scripts that used to carry a league number |
| `tests/test_board_snapshot.py` | The snapshot file: naming, digest, what `load` refuses |
| `tests/test_build_data.py` | Also: every number in the snapshot equals `Data.gs`, one digest in both, atomic writes |
| `tests/test_board_engine.py` | The engine against hand-computed boards, and its import boundary |
| `tests/test_board_names.py` | Name resolution: aliases, `--team`, partial matches on reads only |
| `tests/test_board_state.py` | The draft state: pin, atomic save, lock, backups, undo |
| `tests/test_board_cli.py` | `board.py` end to end, twenty concurrent writers included |
| `tests/test_board_layout.py` | `board_layout.json`: shape, letters against indices, labels and addresses only |
| `tests/test_pull_sheet.py` | The pull plan and xlsx reading, with no browser |
| `tests/test_tick_scenario.py` | The tick scenario's run gate, tick counts and clean-row picker, with no browser |
| `tests/test_verify_local.py` | `verify.py --local` against a sheet rendered from the engine |
| `tests/test_check_no_data.py` | The commit guard, run against a throwaway git repository |

The settings, snapshot, build-data, layout and pull tests exercise config files,
committed data, a synthetic in-memory xlsx and the files themselves without fixtures.

CI runs all of them, plus `ruff` and the harness with its layout staleness check, on
every push.
