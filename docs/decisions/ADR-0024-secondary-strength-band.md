# ADR-0024: A secondary strength band at +0.50, and no secondary weakness

- Status: Accepted
- Date: 2026-09-17
- Owner: Bryan
- Extends: [ADR-0013](ADR-0013-category-profile-column.md), [ADR-0018](ADR-0018-tracker-on-durant-basis.md)

## Context

The Category profile names a strength only at +1.00 unweighted DURANT SDs. That band
is calibrated against our own rostered pool, whose spread is narrower than the public
tables', so it is a stricter bar than the same number would be on a league-wide z
([ADR-0013](ADR-0013-category-profile-column.md)).

It is strict enough to go quiet at the moment it is wanted. Measured on the 2026-09-12
projections, top 156 by DURH: **32% of the drafted pool carries no `▲` at all**, and the
mean player carries 1.31. So when the Category Tracker reads `AST CONTESTED` in round
eight and you scan the `▲ Strengths` column for assists, the board's honest answer is
often that nobody left is strong at assists. The players who would move that category
are sitting between +0.50 and +1.00, and the board says nothing about them.

The tracker itself makes this concrete. Its whole argument is that the return on the
next unit of edge peaks at a coin flip: a category at 50% is where the next pick should
go, and you do not need an elite contributor to move it, you need a positive one. The
profile column had no way to say "positive".

## Decision

**Ship a third PROFILE column, `△ Secondary`, naming every category where the applied
source's unweighted DURANT value satisfies `CAT_BAND_SEC <= d < CAT_BAND`, with
`CAT_BAND_SEC = 0.50` held in Settings beside `CAT_BAND`.**

The interval is **half-open**. A closed upper bound would list every primary strength
twice, in two adjacent columns, which is worse than not shipping the column.

Punted categories drop out of all three lists, exactly as they already do for two.

### Why 0.50

Calibrated, not inherited, the way ADR-0013 requires. `secondary_calibration` in
`board_values.py` re-measures this on every build and `verify.py` prints it, so a change
of basis re-reads the number rather than assuming it:

| floor | secondary/player | no strength label at all |
|---|---|---|
| 0.40 | 1.44 | 5% |
| **0.50** | **1.19** | **9%** |
| 0.60 | 0.97 | 12% |
| 0.75 | 0.60 | 18% |

0.50 roughly doubles how much the column says while leaving the primary band untouched,
and it cuts the silent share from 32% to 9%. 0.75 is the published "strong contributor"
line, and at 0.75 more than half the pool still has no secondary, so it barely answers
the question the column exists to answer. 0.40 crowds: 18 of 156 players carry five or
more labels across the two columns.

Every category stays reachable, which is the check ADR-0013 established. On BMP the
secondary counts run 13 to 29 across the eight, so no category can fail to fire.

### Why no secondary weakness

Asymmetry is the point, not an oversight. A weakness list answers "what does this player
cost me", and that is a threshold question: a hole either has to be covered or it does
not. A near-miss weakness changes no pick, because you are not shopping for the least bad
hole, you are shopping for the player who fills the one you have. The strength side is
different precisely because it is a shopping list.

Ignoring the asymmetry would also have doubled the width cost for a column nobody would
scan on the clock.

### Why a separate column rather than one cell

The two lists cannot share a cell **and** differ in colour. A Google Sheets cell renders
in one text colour; per-character styling exists only through `setRichTextValue()`, which
writes a static value and destroys the formula. These cells are formulas on purpose, so
they react to a punt tick and a source switch without a rebuild.

Splitting is also *narrower*. The worst case is seven combined labels, about 50
characters: one cell holding both needs roughly 260px, two columns sized to their own
distributions need 132 + 110.

### The colours, and the one that was not used

`▲ Strengths` is dark green (`COLOR.posText`) and bold; `△ Secondary` is a softer green
(`COLOR.posTextSoft`, new) at regular weight. **Both are text colours. Neither column
gains a background fill**, and both stay in the banding list.

That is deliberate. `COLOR.mineBg` (`#E6F4EA`) already occupies the very-light-green
background slot, and every candidate fill for a secondary column lands within a few hex
points of it. This file has already made that mistake once and recorded the fix: `warnBg`
was moved off `#FFF3D6` because it sat four hex points from `inputBg` — two meanings, one
swatch. A second light green would repeat it, and on a MINE row the conditional format
would overpaint it anyway.

The filled and hollow triangles carry the same split with no colour at all, following the
GAP column's stated principle: the glyphs are the non-colour channel, so the distinction
survives greyscale and colour blindness.

## Consequences

**It moves the Draft Board layout, so it needs a full rebuild** — and for a reason
ADR-0013 got slightly wrong. That ADR says the Category Tracker "bakes in A1 letters at
write time". It no longer does: the tracker reads `DB_MINE`, `DB_RANK`, `DB_DH_<cat>` and
so on, and the letters live in those named ranges' *definitions*. The hazard is unchanged
and if anything quieter. `rebuildAndResort` does not call `defineNames`, and `sheetByName`
clears rather than deletes, so the old named ranges survive pointing at the pre-insert
columns. Run `Rebuild & re-sort` after this change and the tracker computes eight win
probabilities off the wrong columns, with no `#REF!` and no error. `build-and-maintenance.md`
is corrected in this commit.

`Rebuild & re-sort` would also simply throw, because `D_LAST` goes 78 to 79 and that path
has no `ensureGrid`. Loud, and the safer of the two failures.

**Two Settings off-by-ones were one line each from shipping silently.** The new row pushes
`Disagreement gap` from `S_LEAGUE + 8` to `+9`. The integer number format pinned to `+8`
would have rendered a stored `0.50` as `1` — the cell right, the reading wrong, nothing
erroring — and the yellow input tint ended at `+8`, which would have left `Disagreement
gap` grey, meaning "editing this does nothing" on the one league cell where that is
actively untrue.

**Adding a Settings key invalidates every existing snapshot.** `META.digest` covers
`settings`, so the local board had to be rebuilt from the provider exports in the same
change. Nothing in CI catches this, because no test reads `data/`; only `verify.py --local`
does, and it fails on its own line.

**A third formula clause is a third copy of the two array traps.** It reuses the shared
`head` binding, so the raw `TRANSPOSE` and the `ARRAYFORMULA`-wrapped `IF` are inherited
rather than rewritten. The harness now asserts all three clauses, and asserts the
half-open bound explicitly — but the harness compares formula strings and never evaluates
one, so neither trap is caught offline and the punt trap only fires once a box is ticked.

**Still a static read.** The column does not know what you have already drafted, and does
not know which categories the tracker currently calls contested. Making it react would
close a real cycle across the two tabs. The category-correlation gap ADR-0013 left open is
untouched: a second moderate shot-blocker is flagged `△ BLK` exactly like the first.

**One more column of horizontal scroll.** The visible board goes from about 2202px to
about 2312px. Nothing else was resized to pay for it.

## Sources

- [ADR-0013](ADR-0013-category-profile-column.md) — the band, its calibration method, and the ±1.00 reading
- [ADR-0018](ADR-0018-tracker-on-durant-basis.md) — the unweighted DURANT basis, and the marginal-value argument that peaks at a coin flip
- [ADR-0016](ADR-0016-values-computed-in-python.md) — why this stays a live formula when the values do not
- [RotoBaller, *Finding Combo-Player Values Using Z-Scores and ATC Projections*](https://www.rotoballer.com/finding-combo-player-values-using-z-scores-and-atc-projections/718924) — +0.75 as the published "strong contributor" line
