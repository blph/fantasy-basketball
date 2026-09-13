# Local draft board — design

Branch: `local-draft-board` · Status: approved and implemented on this branch · 2026-09-12

A complete local copy of the 2026-27 draft board, for AI agents rather than people. It holds
the same player data as the Google Sheet and reproduces the sheet's live draft-day logic, so
an agent can answer questions, run calculations and — later — suggest picks during a live
draft without driving the sheet through Playwright.

Each section below was critiqued by an independent reviewer before approval; the findings
adopted are folded in, and the ones declined are listed with their reason in §7.

---

## 0. Requirements and where each is met

| # | Requirement (owner) | Met by |
|---|---|---|
| 1 | Format chosen for agent use, not human use | §1 compact JSON snapshot read only through the §3 CLI |
| 2 | Never committed or pushed; CLAUDE.md says so | §1 location under gitignored `data/`; §5 `check-no-data.sh` patterns; CLAUDE.md boundaries |
| 3 | The sheet's dynamic calculations run locally | §2 engine |
| 4 | Kept in sync by applying the same updates to both, never by pulling; covers player data, formatting, reordering and calculations; CLAUDE.md says so | §1 one build run writes both; §4 parity check and change procedure; CLAUDE.md rule |
| 5 | More efficient for an agent than Playwright | §3 CLI: one local call per question, compact output, `--show` on writes |
| 6 | Every dependent of the board accounted for | §5 |

**Non-goals for this branch.** No pick-recommendation logic (the engine is the substrate it
will be built on). No port of `review_mock_draft.py` (§5.2). No fix for the live-sheet
reorder-refresh tick bug (§6, I1). No new runtime dependency. The sheet stays the board a
human uses; nothing here changes what it displays except the fixes in §6.

## Decisions taken during design

- **Approach A**: the build writes a local JSON snapshot; a stdlib Python engine re-implements
  the sheet's live formulas; parity with the sheet is verified live. Rejected: a SQLite
  database with SQL views (tier medians and the normal CDF would need Python UDFs anyway,
  splitting the logic across two languages for no gain), and pulling the sheet into CSVs
  (contradicts "never pull"; a static pull cannot recompute when a player is marked gone).
- **Win-rate cutoffs are 40% / 60% / 75%** on both boards — the live sheet's values, confirmed
  by the owner after being shown `docs/references/category-tracker-z-thresholds.md` §6, which
  chose 35/65 so a category *at* the playbook's ~60% target reads CONTESTED. At 40/60 it reads
  STRONG. ADR-0023 records the decision and must answer that argument (§5.6).
- **Mock-draft replay is deferred** with the rest of the `review_mock_draft.py` port.

---

## 1. Data layout and sync

### Files

All under `data/draft-board/`, already covered by `data/**` in `.gitignore` and by the
`^data/` rule in `scripts/check-no-data.sh`.

| File | Written by | Read by |
|---|---|---|
| `board - YYYY-MM-DD.json` | `build_data.py` only, same run as `Data.gs` | engine via CLI, `verify.py`, `export_yahoo_rankings.py --local` |
| `draft-state.json` (or any `--state` path under `data/draft-board/`) | `board.py` only | engine via CLI |
| `draft-state.json.lock`, `*.bak.json` | `board.py` | — |
| `pulls/<timestamp>.json` | `pull_sheet.py` (§4) | `verify.py --local` |

Agents never read `board - *.json` directly: at 200 players × three sources of named fields it
is well past 100k tokens. The file is written compact, not pretty-printed.

### Snapshot schema (v1)

```
{
  "schema": 1,
  "meta":     { generated, digest, data_gs_sha256, sources:{…}, board_rows, injuries:{graded, missing, unused} },
  "settings": { teams, roster, q, season, scoring, tier_mult, cat_band, disagree_gap,
                weak_win, strong_win, bank_win },
  "deriv":    { …Data.gs DERIV verbatim… },
  "cat_labels": ["FG%", …, "BLK"],
  "punt_builds": [ {key:"pFt", label:"Punt FT%"}, … ],
  "players": [
    { "row": 0, "key": <sources.normalise(name)>, "name", "team", "pos", "seed",
      "adp": <number|null>, "inj": "EXTREME|HIGH|MED|LOW|?",
      "hbp_raw": { gp, mpg, fgm, fga, fgp, ftm, fta, ftp, tpm, pts, reb, ast, stl, blk, to },
      "values": {
        "BMP": { "durh": {v, rank, drop}, "zsh": {v, rank, drop}, "zsc": {v, rank},
                 "dh": {cat: v}, "d": {cat: v}, "z": {cat: v} },
        "HBP": { … }, "BMP-ALT": { … } },
      "punts": { "pFt": {score, rank}, … }          // BMP only, as on the sheet
    }, …
  ]
}
```

`row` is the Board row order — the contract every sheet reference rests on. `hbp_raw` is named
for its source because every calculation tab on the sheet carries HBP's raw line regardless of
projection (`writeCalcSheet`), which the tracker's raw totals inherit. A blank ADP is `null`
here and `""` in `Data.gs`; the equality test maps one to the other.

### Writing

- `emit()` already builds `Data.gs` from in-memory objects. The JSON is rendered from the same
  objects in the same run. Both texts are built in memory, written to temp files in their target
  directories and fsynced, then moved into place with `os.replace`.
- `META.digest` is a sha256 over a canonical serialisation of the payload (players, values,
  punts, deriv, and meta without the digest). It is written into **both** `Data.gs` and the
  JSON. The JSON additionally records `data_gs_sha256`, the hash of the `Data.gs` text as
  written; `Data.gs` cannot hold its own hash.
- The JSON is written only when `--out` is the default. `--dry-run` writes neither file.
- A same-date rebuild overwrites that date's snapshot. This is a generated artefact, not an
  ADR-0004 partition; a draft state pinned to the old digest detects it (§3).
- `find_set` cannot produce a mixed-date set, so the design does not model one.

### Sync guarantees

| What | How it stays in sync |
|---|---|
| Player data and values | One run, one set of objects. A pytest asserts every number in the JSON equals its `Data.gs` counterpart. |
| Settings (teams, roster, tier multiplier, band, gap, cutoffs) | `scripts/draft-board/board_settings.py` is the Python source; `var SETTINGS_DEFAULTS = {…}` in `Build.gs`, written as strict-JSON object syntax, is what `writeSettingsSkeleton` reads. A pytest extracts and parses that object and requires equality; the harness asserts the Settings cells it writes equal the object. `verify.py --local` compares the live sheet (§4). |
| Formulas, layout, formats | CLAUDE.md change-both rule, `board_layout.json` (§4), and `verify.py --local`. |

---

## 2. The engine

`scripts/draft-board/board_engine.py`. Pure functions, standard library only, no I/O, no
printing. Signature style `f(snapshot, state, settings, applied_sort, row_order=None)`:
settings and sort are explicit because the parity check must vary them independently of the
state file, and `row_order` lets verification feed the sheet's displayed order. Every
docstring names the `Build.gs` function it mirrors. It reproduces the sheet's *meaning*, not
its colours: a conditional format becomes a named flag. It contains no recommendation logic
and never recomputes a value — a test asserts it imports nothing from `bbm_reference` or
`board_values`.

### What it computes

| Output | Mirrors | Rule |
|---|---|---|
| Order | `boardOrder` | Applied source × kind value, descending; ties on Board `row`. |
| `rank` | `buildDraftTab` RANK+COUNTIF | Position in that order. |
| `rnd` | `buildDraftTab` | `ceil(rank / teams)` — `teams` from settings. |
| `drop`, `med`, `brk`, `tier` | `buildDraftTab` | Row 0: tier 1, others blank. Row i ≥ 1: `drop = sel[i-1] - sel[i]`; `med` = median of drops over rows `max(0,i-7)..min(199,i+7)`, ignoring row 0's blank, even counts averaged `(a+b)/2`; `brk` when `med > 0 and drop > tier_mult * med` — plain floats in the sheet's operation order, no rounding; tier accumulates. Over all 200 rows, independent of GONE. |
| `gap` | `buildDraftTab` | `adp - rank`, null without ADP. |
| `best_build` | `bestBuildFormula` | Always BMP. Base = BMP DURH rank; span = nine punt ranks in `PUNTS` order; `"—"` if `min ≥ base` or no ranks; else first-minimum label with `"Punt "` stripped, two spaces, `"+" + (base - min)`. |
| `strengths`, `weaknesses` | `profileFormulas` | Applied source's unweighted `d`; `d ≥ cat_band` / `d ≤ -cat_band`; conceded categories excluded; `"▲ "`/`"▼ "` + labels joined `", "`, else `"—"`. |
| `left_at_pos` | `posLeftFormula` | Rows with the same tier, GONE false, and `re.search(this_pos.replace(",", "|"), candidate_pos)`. Counts the row itself and MINE rows not GONE. |
| `in_pool` | `writeCalcSheet` | BMP DURH rank ≤ q. |
| `disagree` | `addDraftRules` | Per source × kind: `"higher"` if `rank - src_rank ≥ gap`, `"lower"` if `src_rank - rank ≥ gap`. Live gap (the sheet bakes it into rules at build time; §4 lists this as a known gap). |
| `gp_flag`, `gp_warn` | `writeBoardFormulas`, `addDraftRules` | My GP = override, else projected GP (the intended rule; §6 C1). `"CHECK"` if `abs(gp - my_gp) > 10`. Warn when 68 ≤ projected GP ≤ 74. |
| `inj` | Board mirror | Verbatim. |
| Tracker rows | `buildTrackerTab` | `n` = MINE count. Benchmark rows: `rank ≤ min(q, teams × n)` — by rank, **not** GONE (labelled `benchmark: "by_rank"`). Per category: My team = MINE sum of `hbp_raw` (FG%/FT% makes over attempts, null with a flag on zero attempts); Average team = benchmark mean × n (percentages sum/sum); `Z = (Σ MINE dh − n × mean benchmark dh) / sqrt(n)` on the applied source's `dh`; `win = Φ(Z × K)` via `math.erf`, K from `deriv.k_tracker`; `read` = PUNTED if conceded (checked first, so it shows at n = 0), else blank at n = 0, else BANKED ≥ bank, STRONG ≥ strong, WEAK ≤ weak, else CONTESTED. |
| My roster | `buildTrackerTab` | MINE players by rank; plus the off-board count (§3). |
| Punts | `buildPuntsTab` | Per build: rows with a punt rank; `(rank, name, score, adp, gap = adp - rank or null)`; sorted by gap descending with null ADP as −1e9, ties on Board row; top 40. |
| Checks | `writeSanityBlock` | Both alignment checks (structural locally), board row count, MINE count, ADP coverage `"N of 200"`, generated date and digest, injury counts with `" — N UNGRADED"` when any `?`. |

Not reproduced: colours, widths, gradients, borders, the projection-filter checkboxes (view
state), the README tab (already `cheat-sheet.md`).

### Tests (synthetic fixtures only)

Hand-computed small boards covering: rank ties; a non-BMP applied sort (HBP raw totals with
BMP-ALT `dh`); median window at i = 1..7 and 193..199; `med ≤ 0`; a drop equal to 2 × med in
decimal but not in binary; best build with min = base and with all punt ranks blank; null ADP;
conceded category with n = 0; benchmark capped at q; zero attempts; MINE-not-GONE in
`left_at_pos`; blank Pos and bare `G`/`F` in the position regex; Punts tie groups at the
40-row cutoff.

---

## 3. The CLI and draft state

`scripts/draft-board/board.py`, stdlib `argparse`, entry point `main(argv, root)` where `root`
defaults to `data/draft-board/` and tests pass `tmp_path`.

### Global flags

`--state PATH` (must resolve under `root`), `--json` (default output is TSV).

TSV output begins with one `#` context line — applied sort (`what-if` when `--sort` was given
on a read), snapshot date and digest prefix, MINE / GONE / off-board counts — then a header
row. Tabs and newlines in notes are escaped. Warnings go to stderr. There is no option to
write output to a file; help text states the output is provider data and never belongs in
`docs/` or `tests/`.

### Commands

**Reads**

| Command | Returns |
|---|---|
| `status` | Pin (date, digest), whether a newer snapshot exists, applied sort, counts, settings in effect, pick-number gaps/duplicates. |
| `board [--sort S:K] [--available] [--mine] [--top N] [--pos P] [--tier N] [--fields …]` | Draft Board rows in order. `--sort` is a what-if. `--available` = not GONE. Default fields: rank, tier, rnd, name, team, pos, inj, applied value, gap, left_at_pos. |
| `player NAME… [--full]` | Compact by default (identity, applied value and rank, flags, strengths/weaknesses, best build, notes); `--full` adds all nine values with tags and disagreement, `dh`/`d`, punts. All-or-nothing: one unresolved name prints nothing and exits 3. |
| `tracker` | Eight category rows, players ticked, My roster, off-board count. |
| `punts [BUILD] [--top N]` | BUILD by key (`pFt`) or label (`Punt FT%`). |
| `check` | Sanity checks plus state integrity; recomputes the snapshot digest. |

**Writes** — take an exclusive `fcntl.flock` on `draft-state.json.lock` (never on the state file
itself), re-read state under the lock, apply all-or-nothing, write a temp file in the same
directory, fsync, `os.replace`, fsync the directory. Every write echoes each resolved player's
board name, team and rank, and accepts `--show board,tracker` to print those views after the
write in the same call.

| Command | Effect |
|---|---|
| `gone NAME… [--undo] [--force] [--pick N] [--team T] [--offboard]` | Sets GONE. `--undo` on a MINE player is refused without `--force`. |
| `mine NAME… [--undo] [--pick N] [--team T] [--offboard]` | Sets MINE **and** GONE — the sheet's instruction is to tick GONE for every pick including yours. `--undo` clears MINE only. |
| `concede CAT… [--undo]` | Tracker's Punted. Accepts `fg`, `fg%`, `FG%`; rejects `TO`. |
| `sort S:K` | Applied sort. Case-insensitive `bmp-alt:durh`; stored as `{source, kind}`. |
| `note NAME TEXT`; `gp`, `xrank`, `gp1`, `gp2`, `gp3 NAME N\|--clear` | Hand columns. `gp --clear` returns My GP to projected GP. |
| `undo` | Reverts the last state edit from its event's before/after values. Refuses `new` and `rebase`. |
| `new [--force]` | Empty state pinned to the newest snapshot. Refuses a non-empty state without `--force`; writes a timestamped `.bak.json` first. |
| `rebase` | Moves the pin to the newest snapshot after writing a `.bak.json`; reports added / dropped / moved players. A GONE player absent from the new board moves to `offboard`; a MINE player absent is a hard error. Never run during a live draft; run only after `verify.py --local` passes. |

### Name resolution

`sources.normalise` (the key the board was joined on, `ALIASES` included), then `YAHOO_ALIASES`
in `board.py` for Yahoo spellings, then `--team` to break a tie (reversing
`export_yahoo_rankings.TEAM_FIXUPS`). Reads fall back to a unique partial match, else list up to
five `difflib` suggestions. Writes accept only an exact key or alias; a fuzzy candidate is an
error with suggestions. An unresolved alias is an error, never a skip.

**Off-board picks** (late rounds pick players outside the 200 rows): a name with no board
candidate at `difflib` ratio ≥ 0.8 is recorded in `offboard` with a stderr warning. A name
*with* a near candidate exits 3 with suggestions unless `--offboard` is given, so a misspelt
board player is never filed off-board. `tracker` always states how many of your picks are
off-board and uncounted — the sheet has the same blind spot.

### State schema (v1)

```
{ "version": 1,
  "snapshot": { "date", "digest" },
  "applied_sort": { "source": "BMP", "kind": "durh" },
  "conceded": ["FT%"],
  "players": { <key>: { name, gone, mine, pick, notes, my_gp, xrank, gp1, gp2, gp3 } },
  "offboard": [ { name, pick, mine } ],
  "events": [ { ts, cmd, args, before, after } ] }
```

`my_gp: null` means "equals projected GP". Events are uncapped — a draft is about 156 picks
plus edits. Every command verifies the pin: missing snapshot or digest mismatch exits 4.

### Exit codes

0 ok · 2 usage (argparse's own) · 3 name resolution · 4 integrity (pin, corrupt state, a state
key not on the pinned board). Only `check` exits non-zero for a failing sanity check.

### Tests

A synthetic snapshot builder (invented names, ~15 rows, settings scaled down) in `tmp_path`:
lock contention between two processes, all-or-nothing multi-name writes, `undo` for each
reversible command, `new`/`rebase` backups, rebase with a dropped GONE and a dropped MINE
player, off-board with and without a near match, Yahoo alias and `--team` tie-break, output
context line, exit codes.

---

## 4. Parity checking and procedures

### `board_layout.json`

`node scripts/draft-board/harness.js --write-layout` writes
`scripts/draft-board/board_layout.json`: tab names, header labels, column positions, named-range
addresses and row bounds for Draft Board, Board, the three calculation tabs, Category Tracker,
Punts and Settings. Always generated from the harness's **synthetic** players — it ignores a
local `Data.gs` — so it is identical on every machine and carries no provider data. It is
committed. `node harness.js` fails if the file is stale; a pytest asserts the engine's and
`verify.py`'s column maps equal it.

### Pulling the sheet — `scripts/draft-board/pull_sheet.py`

Builds one `playwright-cli -s=fantasy eval` function from `board_layout.json`, runs it from the
repo root (the persistent profile is keyed by working directory), and writes
`data/draft-board/pulls/<timestamp>.json`.

- Sheet id from `.env` `DRAFT_SHEET_ID`; `--sheet-id` overrides (the copy in the scenario).
- gviz `tqx=out:json` with header `X-DataSource-Auth: true` — without it the private sheet
  answers `access_denied`. Each cell carries raw `v` and formatted `f`.
- **Single-type ranges only.** gviz type-sniffs each column and silently drops minority-type
  cells, in CSV and JSON alike (verified live: Settings B4:B11 returned 6 of 8 cells). Ranges
  are split by type from the layout, and every range asserts its expected cell count — except
  a boolean range, which never refuses on a blank cell: an un-ticked checkbox is a genuinely
  empty cell, not an explicit `FALSE`.
- Every range is fetched in turn inside the one eval, not with `Promise.all`: firing all ~94 at
  once made exactly one come back non-JSON on 5+ consecutive live attempts, at a different
  index each time, and the resulting `SyntaxError` named no range. Sequential, the identical
  plan succeeded 94 of 94; a bad reply now comes back as a structured error naming the range
  (never the sheet id) and `main` exits 1 on it.
- gviz omits every row whose fetched cells are all empty wherever that falls in the range, not
  only at the end (verified live: Break alone came back 45 of 200 rows, ADP/XRank/GAP together
  171 of 200), silently shifting every later row up one with nothing to say so. A range whose
  columns can all be blank on the same player row also asks gviz, via `tq=select`, for an
  always-filled anchor column (Draft Board and Board: `player`; Category Tracker's category
  rows: `cat`) inside a wider bounding range, and strips the anchor's own cell back out once
  the reply is in hand; an anchored reply that still comes back short is refused outright.

Ranges: Draft Board header row and data rows by type block (strings, numbers, booleans,
hidden blocks); Board hand columns; Settings input cells and reported cells (weights, k/w/K
block) by type; Category Tracker category rows and My roster separately; Punts blocks; the
Settings digest/date stamp.

(§4 as approved named this `pull_sheet.js`; it is Python so the range plan, the `.env` read and
the count assertions live with `verify.py` rather than in a string of JavaScript.)

### `verify.py --local PULLS.json`

1. **Comparable?** Every pulled header row equals `board_layout.json`, else exit 3 ("the sheet
   is not running this Build.gs"). The sheet's stamped digest equals the snapshot's, else
   exit 3. Settings MISALIGNED checks read `aligned`, else exit 3.
2. **Engine input, in memory only**: the sheet's GONE / MINE / Punted ticks, Board hand columns,
   Settings input cells, and displayed row order. Nothing is written to `draft-state.json`.
3. The existing value-and-tag diff (`diff_sheet`, header row stripped).
4. Every derived Draft Board column, tracker row, My roster and Punts block: numbers compared
   exactly on raw `v` (1e-9), strings on `f`. Tie groups in `#` and Punts compared as sets until
   proven equal live. The disagreement condition checked from pulled ranks and the gap.
5. Reported Settings cells must equal `deriv` exactly. Input cells that differ from
   `SETTINGS_DEFAULTS` are their own failure (drift to fix on one side).
6. `SORT_BY` differing from the applied sort (derived from which source rank equals `#`) is
   reported, not failed — `onEdit` sets it without re-sorting.
7. Output aggregate only: counts and board row numbers, never names.

`verify.py` moves to `main(argv)`. Exit codes: 0 pass · 1 mismatch · 2 usage or missing input ·
3 not comparable.

**Known gaps** (not verifiable from values): conditional-format bindings and colours; the
disagreement gap baked into rules at build time; the I1 tick misattachment (§6) — ticks read
back from the sheet are taken as truth; a My GP override indistinguishable from its seed
formula in a values pull.

**Triage rule.** If the sheet evaluates differently from `Build.gs`'s formula text (an array
trap), fix `Build.gs`. If the engine differs from a correctly evaluating sheet, fix the engine.
Never widen a tolerance. Write it up in `docs/bugs/`.

### Tick scenario

Run on a **copy** of the spreadsheet made through Playwright (File ▸ Make a copy — it carries
the bound script, named ranges and rules), never on the live sheet. Authorise the copy's
script once through Playwright; if that authorisation cannot be completed, stop and ask the
owner. Scenario:

1. 0 MINE; then 8 MINE; then 13+ MINE (hits the `min(q, teams × n)` cap).
2. GONE spread across positions and tiers, including MINE-and-GONE rows.
3. One and two conceded categories.
4. A changed sort followed by Rebuild & re-sort (ticks reattach by name).
5. A My GP override followed by a reordering `Refresh data` (verifies the §6 C1 fix).

After each step: `pull_sheet.py --sheet-id <copy>`, `verify.py --local`. Delete the copy
afterwards — it is provider data in Drive. When only `board_engine.py` changed and the sheet's
build and digest did not, re-run `verify.py --local` against the cached scenario pulls.

### Procedures (docs/draft-board/build-and-maintenance.md)

**Refresh** — the existing twelve steps, amended:
- Step 4 `build_data.py` also writes the snapshot.
- Step 6 `verify.py` also checks JSON ↔ `Data.gs` equality and the digest.
- New required step after Rebuild & re-sort and before the screenshots: `pull_sheet.py`, then
  `verify.py --local`.
- Then `board.py rebase` if a state exists — only after verify passes, never mid-draft.

**Change** to `Build.gs` formulas, layout, formats, settings or README text:
1. Edit `Build.gs`, `board_engine.py`, tests and `board_layout.json` in the same commit.
2. `pytest`, `ruff check .`, `node harness.js`.
3. Deploy `Code.gs` via Playwright from a committed SHA.
4. Full rebuild or Rebuild & re-sort as the change requires.
5. `verify.py --local` on the live sheet; the tick scenario on a copy.
6. Regenerate the cheat sheet.

**Draft day** — a short section: `board.py new`, then per pick `board.py gone|mine NAME --pick N
--show board,tracker`; never refresh either board during a live draft.

---

## 5. Dependents and deliverables

### 5.1 Code

| File | Change |
|---|---|
| `build_data.py` | Snapshot emission, `META.digest`, atomic writes; constants from `board_settings.py`. |
| `board_settings.py` (new) | Teams, roster, q, season, scoring, tier multiplier, band, gap, cutoffs. |
| `board_engine.py`, `board.py`, `pull_sheet.py` (new) | §2–§4. |
| `verify.py` | JSON ↔ `Data.gs` check, `--local`, `main(argv)`, exit codes. `load()` keeps parsing `Data.gs`. |
| `harness.js` | `SETTINGS_DEFAULTS` cell assertions; synthetic `META.digest` and the stamp cell; `--write-layout` and the staleness check, both synthetic-only. |
| `board_layout.json` (new, committed) | §4. |
| `Build.gs` | `SETTINGS_DEFAULTS` (cutoffs 0.40/0.60); digest and date stamped by `refreshData` and `buildDraftTab`, reading `META` only inside a `typeof META` guard; §6 C1 fix; `README_ROWS` text — cutoffs, the SORT STALE claim removed, the tracker benchmark described as rank-based; the win-rate note under the cutoff cells. |
| `export_yahoo_rankings.py` | `--local`, mutually exclusive with the CSV argument; pins a snapshot and prints its date and digest; ignores ticks; applied sort = state file's if present, else settings default; `SEASON`/`DRAFTED_POOL` from `board_settings.py`. Test: identical output from the CSV path and the local path on one synthetic board. |
| `review_mock_draft.py` | Fail fast on a current-layout pull by checking header labels (a current `A2:Z202` pull is today accepted and misread). Nothing else. |
| `calibrate_bbm.py` | `Q` from `board_settings.py`. |
| `scripts/check-no-data.sh` | Block `scripts/draft-board/Data.gs`, `board - *.json`, `draft-state*.json`, `*.bak.json` anywhere; add `DRAFT_SHEET_ID` to the credential pattern and a `spreadsheets/d/<long id>` pattern. |
| `.env.example` | `DRAFT_SHEET_ID=`. |
| `.gitignore` | Fix the stale `gen_data.py` comment. |
| `.github/workflows/checks.yml` | Harness job runs the layout staleness check; update the synthetic-data comment. |
| Tests | Engine, CLI, snapshot equality, settings and layout equality (including `bbm_reference.Q`, and `config/league.yaml` `team_count`/`season` read by regex — pyyaml is not a dependency), engine import boundary; `tests/conftest.py` docstring. |

### 5.2 `review_mock_draft.py`

Already listed as **blocking before a real draft** in
`docs/project-updates/2026-09-01-draft-refactoring-branch-summary.md`. This branch points to that
entry rather than filing a new one, adds the fail-fast guard, marks its command stale in
`AGENTS.md`, and puts a stale banner on `docs/draft-board/mock-draft-review.md` (whose column map
is itself evidence that hand-kept maps drift). The port — onto the engine, the state `events`
pick log and `sources.normalise`, including a tracker replay — is the follow-up.

### 5.3 Documentation

| File | Change |
|---|---|
| `AGENTS.md` (`CLAUDE.md` links to it) | Overview/status; Commands for `board.py`, `pull_sheet.py`, `verify.py --local`, `harness.js --write-layout`; Boundaries — the local board is provider data and never committed; it is kept in sync by applying the same change to both and never pulled from the sheet; agents read it through `board.py`, not the file; CLI output is provider data; `data/draft-board/` joins the write exception; a sheet change and its engine change land in the same commit; Definition of done adds "and the local engine agrees, verified by `verify.py --local`"; `review_mock_draft.py` marked stale; one line pointing to the draft-day procedure. |
| `README.md` | Status line, "Where things are", Data and API access, Getting started. |
| `data/README.md` | Tree gains `draft-board/` and `pulls/`; stale `player_data_MMDD.md`; write-exception paragraph. |
| `docs/roadmap.md` | Interim deliverables; "how draft state is tracked live"; the valuation-implementations note now counts a second implementation of the draft-day logic. |
| `apps/README.md` | Whether the snapshot is the Phase 3 static-JSON feed (it is not; it is the interim draft-board copy). |
| `docs/api/data-providers.md` | Gitignored-in-full sentence gains the snapshot. |
| `docs/draft-board/build-and-maintenance.md` | §4 procedures; pulls saved to `data/draft-board/pulls/` (replacing "outside the repo"); the draft-day section. |
| `docs/draft-board/cheat-sheet.md` | Regenerated. |
| `scripts/draft-board/README.md` | File table and test paragraph. |
| `docs/reviews/2026-09-12-sheet-access-route-evaluation.md` | The gviz JSON header route; the copy used for the scenario; consumers of pulls. |
| `.claude/agents/nba-9cat-analyst.md` | Reading list and provider-data guardrail include `data/draft-board/` and `board.py` output. |
| `docs/references/category-tracker-z-thresholds.md` | Status note pointing to ADR-0023; body unchanged. |
| `docs/bugs/2026-09-12-reorder-refresh-tick-misattachment.md` (new) | §6 I1. |
| `docs/decisions/ADR-0022-local-draft-board.md` (new) | Approach A and its rejected alternatives; relationship to ADR-0001 (consistent: Python writing static JSON), ADR-0008 and ADR-0016 (adds a second implementation of the live logic, supersedes nothing); same-date overwrite; whether it settles "Draft Assistant interaction model" (it settles draft-state tracking for agents, not the Phase 3 app). |
| `docs/decisions/ADR-0023-win-rate-cutoffs-40-60.md` (new) | Supersedes ADR-0018 in part; answers the at-target argument. ADR-0018 gains the in-part pointer. |
| `docs/decisions/decision-log.md` | Both ADRs; the "expected next" entry. |
| `docs/project-updates/2026-09-12-local-draft-board-branch-summary.md` (new) | Branch summary. |

### 5.4 Commit sequence

Each commit green on `pytest`, `ruff check .` and `node harness.js`; each ADR and each
`AGENTS.md` change in the commit it describes.

1. `check-no-data.sh` patterns, `.env.example`, `.gitignore` comment.
2. `board_settings.py`; constants repointed; `SETTINGS_DEFAULTS` in `Build.gs` with 0.40/0.60; harness and pytest equality; `README_ROWS` text; regenerated cheat sheet; ADR-0023, ADR-0018 pointer, thresholds-doc note.
3. `Build.gs` C1 fix; `docs/bugs` I1 write-up.
4. `build_data.py` snapshot, digest, atomic writes; `Build.gs` digest stamp; harness `META`; JSON ↔ `Data.gs` test; ADR-0022; `AGENTS.md` boundaries.
5. `board_engine.py` and tests.
6. `board.py` and tests; `AGENTS.md` commands.
7. `board_layout.json`, `--write-layout`, staleness check, CI.
8. `pull_sheet.py`, `verify.py --local`, procedures in `build-and-maintenance.md`.
9. `export_yahoo_rankings.py --local`.
10. `review_mock_draft.py` guard, stale banners.
11. Remaining docs (§5.3).
12. Deploy and verify (§5.5); branch summary.

### 5.5 Definition of done

1. `Build.gs` from a committed SHA deployed into the sheet's `Code.gs` via Playwright, verified
   by line count and markers before and after save.
2. `Draft Board ▸ Full rebuild` once — the only route that rewrites the README tab and the
   Settings notes changed in commit 2 (CLAUDE.md forbids `Step N` actions on a finished board).
   Record the owner's 13 MINE ticks by name first and confirm they survive, re-ticking by name
   if not. Thereafter Refresh data and Rebuild & re-sort as normal.
3. `build_data.py` run producing `Data.gs` and the snapshot from one run; `Data.gs` pushed.
4. `pull_sheet.py` and `verify.py --local` pass against the live sheet.
5. The tick scenario passes on a copy, and the copy is deleted.
6. `board.py new`, a handful of reads and writes against the real snapshot, `board.py check`
   clean.
7. Branch summary written; PR opened.

---

## 6. Live-sheet defects found during design

| ID | Defect | Evidence | This branch |
|---|---|---|---|
| C1 | A reorder refresh blanks every non-overridden My GP Est once any override exists; the GP flag then goes silent and never recovers. | `refreshWithReorder` restore loop, `Build.gs:821-831` | Fixed: rows without a saved override get the seeding formula back. |
| I1 | After a reorder refresh, Draft Board rows still point at fixed Board rows, so GONE / MINE ticks stay on sheet rows while the names under them change; the next re-sort saves them under the wrong players. `restoreCheckState` also overwrites the Notes formula with literals. | `buildDraftTab` `Build.gs:1206`; `readCheckState` / `restoreCheckState` `Build.gs:1489-1543` | Written up in `docs/bugs/`; fix on a follow-up branch. Local state is keyed by the normalised player key and unaffected. |
| — | "Data generated" on Settings is written only by a Full rebuild, so it is stale after every Refresh. | `writeSanityBlock` called only from `writeSettingsSkeleton`, `Build.gs:473,854,988` | Fixed by the digest/date stamp. |
| — | Docs claim a `SORT STALE` header that no code writes. | `Build.gs:2331`; `build-and-maintenance.md:280` | Claim removed. |
| — | The cheat sheet says the tracker benchmark needs GONE; the formula ranks by position. | `cheat-sheet.md:22`; `Build.gs:2127` | Text corrected. |
| — | Tracker raw totals are always HBP's line whatever the projection, while the code comment says they follow the selected projection. | `writeCalcSheet` `Build.gs:641-648` | Mirrored and documented; not changed. |

---

## 7. Review findings declined

| Finding | Why declined |
|---|---|
| Render `Data.gs` from the JSON dict | Rewrites the file the sheet's contract rests on, for no visible gain; the equality test covers drift. |
| Emit settings into `Data.gs` and have Settings read them | Makes the sheet's own input cells depend on the pipeline. |
| A separate `pick` command, and inferring MINE from the draft slot | `--pick N` on `gone`/`mine` covers gap detection with less surface. |
| A `--date` flag on reads | Conflicts with the pinned state; not needed. |
| Amend the `phase-N/<slug>` branch convention | A separate convention change; the owner named this branch. |
| A project skill for the draft-day workflow | `AGENTS.md` loads in every session here and the Chrome workflow is not designed yet. |
| Mock-draft replay now | Owner deferred it with the port. |

## Resolved after review

**ADR-0023 rationale** (owner, 2026-09-12). In mock drafts the 35–65 band left too many rows
CONTESTED to act on; 40/60 narrows CONTESTED to the genuinely close categories. The ADR states
the cost as well: a category sitting exactly at the ~60% target now reads STRONG, the outcome
35/65 was chosen to avoid, while the next pick there still returns about 97% of peak value.
