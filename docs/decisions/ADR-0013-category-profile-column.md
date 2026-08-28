# ADR-0013: The Category profile column names strengths from z, not G

- Status: Accepted
- Date: 2026-08-27
- Owner: Bryan

## Context

The Draft Board could say how much a player was worth (`ADJUSTED VALUE`) and
which build liked him (`Best build`), but nothing said **what he was actually
good and bad at**. The Category Tracker would report `AST — WEAK` in round six
and there was no instrument on the board that answered "so who fixes that?" —
you had to unhide the CATEGORY FEED block and read raw per-game numbers, which
is not a draft-clock operation.

The column is a *descriptor*, not a second valuation. `ADJUSTED VALUE` prices a
player; this only names the categories where he moves your totals.

Two things had to be decided: which per-category score to threshold, and where
to put the threshold.

## Decision

**Ship one column, `Category profile`, on the Draft Board, built on the
per-category z-score with a symmetric band of ±1.00 SD held in Settings as
`CAT_BAND`.** It reads `▲ FG%, REB, BLK  ▼ FT%, 3PM`, in fixed 9-cat order, with
`—` when nothing clears the band either way. A category ticked `Punted` on the
Category Tracker drops out of both lists.

### Why z and not G

The board is sorted by G and it would have been the consistent-looking choice.
It is the wrong one here, for a reason worth stating plainly: the G multipliers
discount a category by its week-to-week volatility, which answers *how much is
this edge worth* — and `ADJUSTED VALUE` has already applied that discount. This
column asks the prior question, *does he have an edge at all*, which is a
counting question, and it is the same quantity the Category Tracker measures
(raw totals against an average team). Reusing G applies the volatility discount
twice into a display that is not a valuation.

The practical cost is decisive. Calibrated over the top 156 by Adjusted Value:

| basis | band | mean flags/player | median | no label at all | STL strong | BLK weak |
|---|---|---|---|---|---|---|
| **z** | **±1.00** | **2.60** | **2** | **9%** | **25** | **23** |
| z | ±0.75 | 4.03 | 4 | 3% | 25 | 41 |
| g | ±1.00 | 1.94 | 2 | 22% | 9 | 5 |
| g | ±0.75 | 3.22 | 3 | 5% | 19 | 26 |

Steals carry a 0.59 multiplier, so on the G basis nine players in the entire
pool are strong at steals and three are weak. The column would fall silent on
steals at exactly the moment the tracker says you need some. On z at ±1.00 the
strong counts land at 20–27 across all nine categories.

### Why ±1.00, and one band for all nine

One SD above the average rostered player is the published reading of a strong
single-category contributor. RotoBaller states it outright: players "with
Z-Scores in each category of at least +0.75 are considered strong contributors,"
and +1.00 in every category "is the definition of a true multi-category player."
FantaZscores: 1.00 is "really good", −1.00 "really bad". Basketball Monster's
own per-category columns are z-scores on the same scale, "where 0.00 is your
league average."

**The number coincides with theirs; the reference population does not.** Public
tables standardise against the previous season's league-wide average. Ours is
the rostered pool — top Q, `GP >= MIN_GP` — whose SDs are narrower and whose
mean is higher, so our ±1.00 is a stricter bar than their ±1.00. That is why
`CAT_BAND` is a Settings cell rather than a literal, and why the table above
exists: the band is calibrated on the actual pool, not inherited.

One band serves all nine categories, which looks like the mistake the Category
Tracker already made — it shipped a single 8%-of-benchmark rule that "made
STRONG and WEAK unreachable on FG% and FT%," and now carries three bands. The
objection does not transfer. The tracker compares **raw units**: a rate margin
in FG% points against a counting margin as a share of a total, which no single
number can serve. A z-score has already been divided by its own category's
spread, and that division *is* the per-category calibration the tracker has to
supply by hand. The check is the same either way — look for a category that can
never reach the band — and the strong side passes it everywhere.

### Why punt-aware

The sources genuinely disagree about what to do with a weak category. SportsEthos
argues against filling one at all: "you should never be trying to actively make a
category worse anyway," pool your resources into fewer areas. The balanced school
advises using the late rounds to add specialists so the roster has no holes. The
board already sits between them — the tracker tells you to "aim for roughly 60%
in your live categories, not 90%" — and the `Punted` checkboxes are how you tell
it which school you have picked this draft. Dropping punted categories from both
lists keeps the column pointed only at categories still being contested.

## Consequences

**Good.** No new Board columns: the z block already exists, so `Refresh data`,
the fixed Board layout, the hand-edited columns and the punt replacement levels
are all untouched. Confirmed live before deploying: the z block sits exactly at
`W:AE`, `Settings!B71` was free for `CAT_BAND`, and the tracker's `Punted` cells at
`F7:F15` are literal checkboxes — so the Draft Board reading them closes no cycle.
The live pool matched the local one (`Z-total` 0.278 against `verify.py`'s 0.2778),
so the ±1.00 calibration carried over unchanged.

**Known limitation, not a defect to paper over.** Blocks are right-skewed with a
hard floor at zero, so the minimum z_BLK in the pool is about −1.19 and `▼ BLK`
fires for roughly five players. This is the standard non-normality problem with
z-scores in low-count categories, and the review that flagged it for the totals
applies here too. The strong side (23 players) still answers "who fixes my
blocks", which is the question that matters. An asymmetric band would hide the
skew rather than address it.

**Operationally sharp, and in a new way.** This moves the **Draft Board** layout,
not the Board layout, so unlike a punt-build change ([ADR-0010](ADR-0010-punt-build-set.md))
it does not break `Refresh data`. But the Category Tracker sums Draft Board
columns through formulas that bake in A1 letters at write time, and
`Rebuild & re-sort` rebuilds only the Draft Board — so a tracker left un-rebuilt
keeps summing the old positions and reports **wrong totals with no error**. Any
Draft Board column move now requires a full rebuild, in the order documented in
[build-and-maintenance.md](../draft-board/build-and-maintenance.md). Deployed with
a full rebuild on 2026-08-28; the tracker's live formulas were then read back and
confirmed to point at the shifted columns (`$U` for Mine, `$W`/`$X` for FGM/FGA,
`$AC` for REB).

**It cost 240px of a tab that had about 100px spare.** Measured live: columns F-T
already used ~745px of an ~845px scrollable region, and `Gone`/`Mine` are the two
controls used on the clock. `VOR`, `G` and `XRank` are now collapsed into `+/-`
groups to pay for it — VOR and G duplicate audit numbers already on the Board tab,
and XRank was empty on all 200 rows. Collapsed rather than hidden, so any of them
comes back without a rebuild.

**Two array traps, both invisible offline, both caught only in the sheet.** The
harness compares generated formula strings and never evaluates one, so a fully
green build shipped `#VALUE!` into all 200 rows: Sheets does not array-evaluate an
`IF` passed as an argument to another function, so `TEXTJOIN` received a scalar.
Wrapping the `IF` in `ARRAYFORMULA` fixed that and exposed a second, quieter one —
a `LET` binding is evaluated *outside* the enclosing `ARRAYFORMULA`, so
`live,TRANSPOSE(punted)<>TRUE` collapsed to a 1×1 `FALSE` the instant a category
was punted, and every profile silently went to the em-dash with no error anywhere.
The fix binds the raw `TRANSPOSE` and does the `<>TRUE` inside the `ARRAYFORMULA`.
This is the same trap already recorded on the punt replacement levels in
`writeSettingsFormulas`, which is twice now.

**Two hazards fixed on the way through.** `readCheckState` read the old sheet
with the new column map, so the first rebuild after any insertion would have
restored `Gone` from the old `Mine` column — corrupting draft state rather than
wiping it. It now locates the columns from the sheet's own header row. And a
formula naming a not-yet-created sheet is a permanent `#REF!`, so `buildDraftTab`
creates the Category Tracker if it is missing.

**A new cross-tab dependency, and a constraint that comes with it.** The Draft
Board now reads `Category Tracker!F7:F15`. That is not circular only because
those cells are literal checkboxes; making `Punted` auto-detect a build from the
roster would close a real cycle across both tabs.

**Still a static read.** The band does not know what you have already drafted. A
second elite shot-blocker is flagged `▲ BLK` exactly like the first, though he is
worth much less to you — the category-correlation gap the methodology review
names remains open, and this column does not close it.

## Sources

- [RotoBaller, *Finding Combo-Player Values Using Z-Scores and ATC Projections*](https://www.rotoballer.com/finding-combo-player-values-using-z-scores-and-atc-projections/718924) — the +0.75 / +1.00 per-category thresholds
- [FantaZscores, *About Z-Scores*](https://fantazscores.com/about-z-scores)
- [Basketball Monster, *Welcome and FAQ*](https://basketballmonster.com/Help.aspx) — per-category `V` columns, 0.00 = league average
- [Rosenof, *Static quantification of player value for fantasy basketball*, arXiv 2307.02188](https://arxiv.org/abs/2307.02188) — the G-score and the volatility multipliers
- [RotoWire, *Fantasy Basketball Category Rankings Explained*](https://www.rotowire.com/basketball/article/fantasy-basketball-category-rankings-explained-96969)
- [SportsEthos, *Draft Guide 2026: Punt Strategy*](https://sportsethos.com/top-posts/fantasy-basketball-draft-guide-2026-punt-strategy/)
- [Yahoo Sports, *9-Cat Leagues, 101*](https://sports.yahoo.com/fantasy/article/fantasy-basketball-9-cat-leagues-101-draft-strategy-for-the-2025-26-nba-season-173554094.html)
- [NBC Sports, *Draft Prep: Means & Z-Scores*](https://www.nbcsports.com/fantasy/basketball/news/article-numbers-game-draft-prep-means-z-scores)
- [Methodology review, 2026-08-27](../reviews/2026-08-27-draft-board-methodology-review.md) — the tracker-band history and the non-normality note
