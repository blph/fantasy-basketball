# ADR-0022: A local copy of the draft board for agents, kept in step by construction

- Status: Accepted
- Date: 2026-09-12
- Owner: Bryan

## Context

The 2026-27 draft board is a Google Sheet ([ADR-0008](ADR-0008-google-sheet-draft-board.md)).
Its values arrive as numbers from `build_data.py`, and its draft-day logic stays live in the
sheet: rank, tier, round, GAP, the category profile, `Left @pos`, the Category Tracker, the
Punts tab ([ADR-0016](ADR-0016-values-computed-in-python.md)).

An agent can reach that board by only one route: Playwright, driving the owner's signed-in
browser. That is right for deploying `Code.gs` and running the menu, and it stays the only
route to the sheet. It is the wrong tool for answering a question. Each read is a page
round trip, a gviz range sniffs types and silently drops minority-type cells, and none of it
recomputes. A pulled table cannot answer "what does the tracker say if this player is
gone?" without ticking the box in the owner's live sheet. During a live draft, an agent that
needs a browser session to count categories is too slow to help.

What an agent needs is the same board locally: the same players, the same numbers, and the
same live logic, answerable in one local call. It also needs a guarantee that the local copy
and the sheet are the same board. A copy that drifts is a wrong number that looks right, the
failure this project ranks first.

## Decision

**Approach A: a snapshot, a standard-library engine, a CLI over both, and a parity check
against the live sheet.**

1. **Snapshot.** `build_data.py` writes `data/draft-board/board - YYYY-MM-DD.json` in the
   same run, and from the same in-memory objects, as `Data.gs`. The rounding helpers are
   shared, so every number is the float `Data.gs` carries. The JSON is compact and named by
   field (players, the nine values per source with ranks and dropped categories, the
   per-category columns, the punt builds, DERIV, and the league settings). It is written
   only when `--out` is the default `Data.gs`, and never on `--dry-run`. Both files are
   written to temps and fsynced before either is moved into place.
2. **One digest in both files.** The digest is a sha256 over a canonical serialisation of
   the snapshot. It is written into the JSON and into `Data.gs` as `META.digest`. The JSON
   also records the sha256 of the `Data.gs` text; `Data.gs` cannot hold its own hash. The
   sheet stamps `META.digest` on Settings from every path that changes its data: Full
   rebuild, Refresh data, Rebuild & re-sort. `verify.py` asserts every number in the JSON
   equals its `Data.gs` counterpart, and that the digests agree.
3. **Engine.** `board_engine.py` re-implements the sheet's live formulas in standard-library
   Python, as pure functions naming the `Build.gs` function each one mirrors. It never
   recomputes a value.
4. **CLI.** Agents read the board through `board.py`, never by opening the file. The file
   holds 200 players across three sources of named fields, well past 100k tokens. Draft
   state (GONE, MINE, conceded categories, hand columns) lives in a local state file keyed
   by the normalised player key (`sources.normalise`), with the display name stored beside
   it, and pinned to one snapshot's date and digest.
5. **Parity.** Values are compared by construction. Formulas are compared by pulling the
   live sheet through Playwright and running the engine on the sheet's own ticks and order.
   A sheet change and its engine change land in the same commit.

The local board is **never pulled from the sheet** and the sheet is never fed from it. Both
are written by one build and kept in step by applying each change to both. Pulling the
sheet is how parity is checked, not how the copy is made.

## Consequences

**The draft-day logic now has two implementations**, `Build.gs` formulas and
`board_engine.py`. That is a real cost. Every formula change is two changes, and a change
made to one side only is exactly the drift this ADR exists to prevent. It is kept honest by
the parity check (`verify.py --local`) against the live sheet on real rows, never by
inspection. The triage rule is fixed: if the sheet evaluates differently from its own
formula text, fix `Build.gs`; if the engine differs from a correctly evaluating sheet, fix
the engine; never widen a tolerance. The branch that introduces this record changes `Build.gs`
in its first commits, before `board_engine.py` exists (the settings source, the C1 fix and this
digest stamp), a bootstrap exception to the same-commit rule; from the engine's own commit on,
every change to the sheet's logic lands in the same commit as its engine change.

**A same-date rebuild overwrites that date's snapshot.** The snapshot is a generated
artefact like `Data.gs`, not an [ADR-0004](ADR-0004-daily-append-only-snapshots.md)
partition, and nothing appends to it. A draft state pinned to the old digest detects the
overwrite and refuses to run until it is rebased, so an overwrite cannot silently change
the board under a draft in progress.

**The snapshot is provider data.** It is a complete copy of the board: every player and
every value. [ADR-0006](ADR-0006-no-provider-data-redistribution.md) applies in full. It
lives under gitignored `data/`, `check-no-data.sh` blocks it by name, and neither it nor the
CLI's output belongs in `docs/` or `tests/`. `data/draft-board/` joins `data/exports/` as a
directory the draft-board workflow may write.

**"Data generated" stops going stale.** It used to be written only by a Full rebuild, so it
went stale after every Refresh data. The stamp that carries the digest rewrites the date on
the same paths.

**Relation to earlier records.** Consistent with
[ADR-0001](ADR-0001-python-and-static-html-stack.md): Python writing static JSON. It adds
a local consumer to [ADR-0008](ADR-0008-google-sheet-draft-board.md)'s sheet without
changing what the sheet is or shows. It adds a second implementation of the live logic that
[ADR-0016](ADR-0016-values-computed-in-python.md) kept in the sheet, without moving any of
it. It supersedes nothing.

**It settles draft-state tracking for agents, and nothing more.** The "Draft Assistant
interaction model" in the decision log asks how the Phase 3 app takes live draft input. This
record answers a narrower question: how an agent tracks a draft against the interim board,
by explicit per-pick entry through the CLI. The app's model stays open.

**Update, 2026-09-13: the pull downloads the workbook.** `pull_sheet.py` now fetches the sheet
as one xlsx through the owner's browser instead of ~94 gviz range requests: about 3 seconds
instead of 1.5 minutes. xlsx keeps each cell's own value and type, so the gviz hazards below
(minority-type cells dropped, all-empty rows omitted) no longer apply to the pull. Before the
switch, an xlsx pull of the live sheet matched the last gviz pull on every cell the ticks do
not drive and passed `verify.py --local` in full.

## Alternatives rejected

**A SQLite database with SQL views.** Tier medians over a sliding window and the tracker's
normal CDF would need Python user-defined functions anyway. That splits the logic across
two languages for no gain, and adds a file format no one reads by eye either.

**Pull the sheet into CSVs.** It contradicts the rule that the local copy is never pulled.
A static pull also cannot recompute: marking a player gone would mean ticking the owner's
live sheet and pulling again. And gviz silently drops minority-type cells, so a pull is not
even a faithful copy of what it read.

**Render `Data.gs` from the JSON.** It rewrites the file the sheet's whole contract rests on
(row i is the same player in every block) for no visible gain. The equality check already
catches drift between the two.

**Emit the league settings into `Data.gs` and have Settings read them.** It makes the
sheet's own input cells depend on the pipeline, and it breaks the distinction Settings draws
between yellow inputs and grey reported values. Settings stay in `board_settings.py` and
`SETTINGS_DEFAULTS`, held equal by test.
