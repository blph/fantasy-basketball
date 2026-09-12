# ADR-0016: Values are computed in Python; the sheet holds numbers

- Status: Accepted
- Date: 2026-09-01
- Owner: Bryan
- Supersedes: ADR-0008 (in part)

## Context

ADR-0008 made a strong commitment: "every value a player is judged on is a live formula
referencing named ranges — not a number computed in the script and pasted." It bought real
things. Any cell could be clicked and read, retuning a constant recalculated the whole
board, and a spreadsheet nobody can audit is just a slower database.

ADR-0014 and ADR-0015 put that commitment out of reach. The board now needs three values
across three projections, and DURANT H2H requires a Yeo-Johnson transform per category,
standardisation against a pool that must be **iterated to a fixed point on the DURANT
score itself**, and a per-player drop of the worst live category.

The pool iteration is what settles it. Sheets cannot express a fixed point without circular
references; the existing board already sidesteps this with a static `Seed Rank` and a
menu action you run repeatedly and manually. That was tolerable for one pool. This design
needs nine — three values across three sources — plus one more per punt build.

## Decision

**Compute every value in Python and write it to the sheet as a number. Keep as live
formulas everything that has to react during a draft.**

Numbers, from `build_data.py` via `Data.gs`: the nine values, their ranks, each value's
dropped category, the per-category DURANT H2H columns, the punt builds, and the pool
constants.

Live formulas, unchanged in kind: rank, tier, drop, local median, break, round, GAP, the
Category profile, `Left @pos`, the Category Tracker, and everything keyed off the `Gone`
and `Mine` checkboxes. Ticking `Mine` still updates the tracker instantly.

The math engine is `scripts/bbm/bbm_reference.py`, which is committed, tested, and
validated against Basketball Monster's published output.

## Consequences

Good. The hard arithmetic moves from a formula language with no tests into code with 182
of them. The pool fixed point becomes a loop rather than a menu item run by hand until it
stops moving — and `Re-seed pool from current ranks`, along with the whole class of "did I
run it enough times" error, disappears. `verify.py` gains a check it could never have had
before: because the sheet now holds numbers, a pull of the live board can be diffed against
what was written to it.

Bad, and worth stating plainly. **Retuning a constant no longer recalculates the board.**
Changing `PUNT_WEIGHT` or a weight on Settings does nothing until the pipeline is re-run
and `Data.gs` re-pushed. That is a real loss of the property ADR-0008 valued most, and the
mitigation is only partly technical: those cells are rendered grey rather than
input-yellow, and the block labels say the values are applied upstream. Someone will still
try to tune one. The Settings tab has to be explicit about which numbers are live and which
are reported, because quietly leaving the old wording would be the worst outcome available.

Auditability changes character rather than disappearing. It moves from "click the cell and
read the formula" to "read the tested implementation, and read the pool constants the sheet
reports". The three calculation tabs carry the full working — raw, impact, z, transformed,
weighted — so a value can still be traced across a row; what is gone is the ability to see
it recompute.

`Data.gs` grows from ~26KB to ~185KB, which is ~15 chunks through the Monaco editor rather
than two.

## Alternatives rejected

**Keep everything live in Sheets.** Nine pools to converge by hand, roughly 36,000 formula
cells across three calculation tabs, and Yeo-Johnson plus drop-the-worst written in a
formula language whose two known array traps (`ARRAYFORMULA` around an `IF` argument, and
`LET` bindings evaluating outside an enclosing `ARRAYFORMULA`) both produce board-wide
failures that every offline check passes.

**Hybrid: z-values live, DURH precomputed.** Two provenances in one block of columns, with
the *default* sort — the number that matters most — being the one you cannot audit in-cell.
The worst of both.
