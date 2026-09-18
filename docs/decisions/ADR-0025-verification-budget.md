# ADR-0025: Verification is tiered, gated on a formula fingerprint, and has a written budget

- Status: Accepted
- Date: 2026-09-17
- Owner: Bryan

## Context

Adding one display column to the draft board ([ADR-0024](ADR-0024-secondary-strength-band.md))
cost several minutes of wall-clock and a large share of a usage window. Almost none of it was
the change.

Two independent causes, which look like one problem and are not.

**The scenario ran when it had nothing to check.** `tick_scenario.py` gated on
`git diff --name-only <last-pass> -- Build.gs board_engine.py`. `Build.gs` is one 2,600-line
file that builds all nine tabs, every colour, every column width and the README. Any line in it
trips the gate. **Correcting a column width ran a four-minute browser scenario** that exercises
checkboxes, a re-sort and a data refresh — none of which a width can reach. The gate tested
which file was edited, which is a proxy for what changed, and a bad one.

**The token cost was the agent, not the scripts.** Measured over that session:
`tick_scenario.py` emits eight lines, about 200 tokens; `pytest -q`, `ruff` and `harness.js`
emit about 80 between them; `verify.py --local` emits six. The scripts are frugal and always
were. The cost was three subagents sweeping the repo for a dependency map that is already
written down (~250k tokens) and two screenshots taken to confirm success that `verify.py
--local` had already proved. Nothing in the repo said not to, so nothing stopped it.

Both need fixing, and fixing only the visible one would have tuned the cheap thing and left the
expensive one in place.

## Decision

**Tier the scenario, gate it on the generated formulas, and write the budget into `CLAUDE.md`.**

### Two tiers

| tier | steps | cost | consent |
|---|---|---|---|
| `ticks` (default) | copy, clear, MINE, GONE, punt ×2 | 130s measured | none |
| `full` (`--full`) | adds re-sort and `Refresh data` | plus two Apps Script runs | `--allow-consent` |

Where the 130s goes, measured: six pulls at about 3s each is 18s; the rest is the copy, the
delete, and one browser round-trip per toggle. That is also why scoping the pulls, rejected
below, would not have helped.

Steps 4 and 5 each trigger a full Apps Script execution on the copy, and those two are most of
the wall-clock. They are also the two furthest from any ordinary board edit.

### The gate reads formulas, not filenames

`node harness.js --tick-fingerprint` builds the workbook offline in about two seconds and
prints two hashes over the **generated formula text**:

- `tick` — every formula reading the `GONE` column, the `MINE` column, or the tracker's
  `Punted` range. Both vocabularies count: the Draft Board reads them as column letters, the
  Category Tracker as the `DB_MINE` / `DB_GONE` named ranges. Matching only letters would miss
  every tracker formula the ticks drive, which is the half the ticks exist to exercise.
- `rebuild` — every formula the re-sort and `Refresh data` paths rewrite.

`tier_needed` compares both to the last passing run and returns `none`, `ticks` or `full`.
`board_engine.py` is watched separately, by git: it is not in the sheet so no hash covers it,
but it is what every step compares against.

Three properties make this safe rather than merely cheaper:

1. **Formulas only.** A cell holding a value contributes nothing, because the scenario proves
   how the sheet *recalculates* and a literal does not recalculate. This is why a width, a
   colour, a header or a README row cannot move a hash.
2. **Column letters are kept in the hashed text**, not normalised away. A formula still reading
   `$H4` after `GONE` moved to `I` is precisely the silent breakage the scenario exists to
   catch, so it must move the hash. Row numbers *are* normalised, because 200 rows of the same
   formula are one shape.
3. **Unknown never reads as unchanged.** A first run, or a stamp written before the fingerprint
   existed, returns `full`. A tick-tier pass records only the `tick` hash — stamping `rebuild`
   would mean the steps it skipped never ran again.

### A written budget

`CLAUDE.md` gains a `Verification budget` section: a table of measured costs, and hard rules
against launching a subagent for draft-board work, screenshotting to confirm success, running
an expensive step without saying what it costs first, and printing cells.

## Consequences

**The scenario now costs what the change deserves.** A width, colour or doc edit opens no
browser at all. A profile-formula edit runs 40s. Only a change reaching the rebuild path pays
four minutes. Verified against the change that prompted this: the width correction moves
neither hash; the punt-clause edit and a column insert both move `tick`.

**Coverage is unchanged.** Every step still pulls and runs the full `verify.py --local`
comparison over every cell. This ADR changes *when* the scenario runs and *how much of it*, and
nothing about what a running step checks.

**One optimisation was investigated and rejected**, and the reason is worth recording. Scoping
each step's pull to the ranges that step can affect looks like an obvious saving — 94 ranges
down to about 12. It saves nothing. `pull()` is a single xlsx download of the whole workbook,
and the ranges are how those bytes are sliced in memory afterwards. The plan that opened this
work assumed per-range fetches and was wrong. The one real saving found there was the redundant
re-pull after clearing inherited ticks when nothing was inherited, which is now skipped.

**The budget constrains the agent, not the scripts**, and it is the half that actually costs.
It is written as `DO NOT` rules beside the other boundaries rather than as advice, because the
previous state of the world was advice — there was nothing to violate, so nothing was violated,
and 250k tokens went on a sweep whose findings were already in `docs/`.

**A gate can now be wrong in a new way.** If a tick-driven formula is ever written through a
path the fingerprint does not walk — a formula built at runtime from a string the harness does
not evaluate, say — it would not move the hash and the scenario would not run. The mitigation
is that the harness builds the workbook the same way the sheet does, and that any new formula
still has to pass the harness's own assertions. `--force` exists for when judgement says run it
anyway.

## Sources

- [ADR-0024](ADR-0024-secondary-strength-band.md) — the change whose cost prompted this
- [ADR-0022](ADR-0022-local-draft-board.md) — the local engine the scenario compares against
- [build-and-maintenance.md](../draft-board/build-and-maintenance.md) — the gate and tiers as an operating procedure
