# Draft board math audit — 2026-27

- Date: 2026-08-29
- Scope: every calculation on the board — the percentage impacts, the nine z-scores, the
  nine G-scores, `Z TOTAL`, `G TOTAL`, `VOR`, `ADJUSTED VALUE`, the nine punt scores and
  their ranks, the tier chain, `Category profile`, `Left @pos`, `GAP`, and the Category
  Tracker — plus `scripts/draft-board/valuation.py`, `verify.py`, and the Settings
  constants.
- Method: the valuation was **re-derived from the cited papers**, not read back from the
  code, then diffed cell-by-cell against the **live sheet** pulled read-only through
  `playwright-cli`. Methodology was checked against Rosenof arXiv 2307.02188 and
  Basketball Monster's published documentation.
- Constraint honoured: no player row, projection, ADP value or export figure appears
  below. All measurements are aggregate ([ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md)).

---

## Verdict

**The valuation is correct. Every finding is in the tooling around it.**

Every computed cell on the live board reproduces an independent Python implementation, and
the methodology matches its cited sources exactly. Nothing below touches the z-score,
G-score, VOR or adjusted-value math.

| Surface | Checked | Result |
|---|---|---|
| `Board` values | 2 impacts + 9 z + 9 g + Z TOTAL + G TOTAL + VOR + Adjusted Value + 9 punt scores, 200 rows | **6,600 / 6,600 agree** |
| `Board` ranks | Rank (VOR), Adj Rank, 9 punt ranks | **2,200 / 2,200 exact** |
| `Settings` | 12 pool constants, 7 category mean/SD pairs, 9 multipliers | all agree |
| `Draft Board` | Drop, Local med, Break, Tier | 199 / 199 |
| `Draft Board` | Category profile, Left @pos, GAP | 200 / 200 each |
| `Category Tracker` | 9 roster totals, 9 benchmarks, both percentage aggregates, 9 band reads | all agree |
| Error sweep | `#VALUE!` `#NUM!` `#REF!` `#N/A` `#DIV/0!` across Board and Draft Board | none |
| Deployment | bound `Code.gs` vs repo `Build.gs` | byte-identical |
| Repo gates | `pytest`, `ruff check .`, `harness.js` | 90 passed, clean, green |

**Method note.** Google's `gviz` CSV returns display-rounded values, so a naive tolerance
diff measures cell formatting rather than arithmetic. Values were compared at each cell's
own displayed precision, and the eleven `RANK` columns — which Sheets computes on
full-precision values — were required to match exactly. Together those bracket the
underlying numbers from both sides. `gviz` also types each column and silently drops
string results from a numeric column; every string-valued sanity cell was therefore read
individually.

---

## Findings

### F1 — `verify.py` reports a correct board as broken (High)

Run exactly as `AGENTS.md` documents it, the verifier declares **all seven pool constants
wrong and exits 1**, against a board correct in all 6,600 cells. Adding `--no-converge`
makes all seven agree and exits 0.

The cause is F3: `verify.py` converges the pool by default, the sheet has never been
re-seeded, and the two are measuring different 156-player sets. The verifier is right that
they differ and wrong about what it means.

This is the failure mode [ADR-0011](../decisions/ADR-0011-min-gp-pool-gate.md) already
named once for a different check — a sanity block that raises a false alarm teaches the
operator to ignore it, and it is the one automated check standing between a bad refresh
and draft night.

**Fix.** Converge the sheet (F3), which makes the default correct. Then have `verify.py`
name its own convergence mode when constants differ, so the next divergence points at
convergence rather than implying the math is wrong.

### F2 — `Left @pos` counts your own picks as still available (Medium)

The formula excludes players ticked `Gone` but not players ticked `Mine`. Tick a player as
yours without also ticking him Gone and he keeps being counted as available at his
position.

On the board as pulled — 14 `Mine` ticked, 0 `Gone` — **54 of 200 rows overstate what is
left at position, by up to 3 players.**

This is the scarcity tiebreak column, and the error runs in the dangerous direction: it
makes a position look *less* picked-over than it is, which is an argument to wait. The
cheat sheet says `Gone` must be ticked "for players other managers took", which reads as
though your own picks are handled. They are not, and nothing enforces it.

**Fix.** One term — `*(<mine col>=FALSE)` alongside the existing `(<gone col>=FALSE)` in
`Build.gs`. Then `Mine` alone is sufficient and the workflow stops depending on
double-ticking.

### F3 — The pool has never been converged (Medium)

The board's pool is **exactly** the provider-seed first-pass pool; `Re-seed pool from
current ranks` has not been run once. Python settles in three passes, and the settled pool
differs by six players in and six out.

Cost on the current export: mean absolute movement **0.33 places**, max **4**, nothing
moving 5 or more, maximum movement inside the top 60 of **2**, and **no change to the
drafted 156**.

Negligible today. It matters because it is the input to every constant on the board, it is
what makes F1 fire, and nothing guarantees the next export is this benign.

**Fix.** Run `Re-seed pool from current ranks` twice and confirm `In Pool` stops moving.
Worth a line in the pre-draft checklist — one invocation is one pass, and nothing on the
sheet reports whether it has settled.

### F4 — The GP-inversion guard can never fire (Low)

`verify.py:141-146` counts players where `vor < 0 and adjusted_value(vor, gp, 72) > vor`.
But `adjusted_value` returns *exactly* `vor` when `vor < 0`, by construction, so the
condition is unsatisfiable and the counter is always zero. It also sets the process exit
code, so that exit status carries no information.

It reads as a live guard on the rule `AGENTS.md` treats as load-bearing — availability must
discount and never promote. It is a function tested against itself.

**Fix.** Point it at the sheet's `ADJUSTED VALUE` column so it tests the deployed formula.

### F5 — `--punt-weight` verifies nothing, and says it did (Low)

The flag is parsed at `verify.py:81`, but both punt identity assertions hardcode `0.0` and
`1.0`. The flag reaches only the success message, which therefore claims a check that never
ran against the configured weight.

**Fix.** Assert against `args.punt_weight`, or print the weights actually tested.

### F6 — `converge_pool` silently mutates the caller's players (Low)

`valuation.py:246-247` writes converged ranks back onto `p.seed` on the objects it was
handed. Any caller reading `p.seed` afterwards gets the adjusted rank, not the provider's.

This produced a false result inside this audit: a first correlation run reported the board
tracking the provider's rank at a perfect 1.0000, because it was comparing the board
against itself. Caught, but it cost a measurement.

**Fix.** Work on copies, or return the seed map rather than writing it back.

### F7 — Nothing offline can check `GAP` (Low)

`Player` has no `adp` field, so `verify.py` parses ADP out of `Data.gs` and drops it. `GAP`
is one of the two market columns read on the clock and has no second implementation. It is
correct on the live board — verified here, 200/200 — but only because this audit went to
the sheet for it.

**Fix.** Add `adp: float | None` to `Player` and a `GAP` check to the verifier.

### F8 — The tracker is carrying more players than the roster holds (Low)

Leftover mock-draft state rather than a formula defect, but it exposes one: the benchmark
is `TEAMS × COUNTIF(Mine)`, uncapped. At 14 ticks it averages over the top 168 players when
only 156 are drafted, reaching into players who would never be rostered.

**Fix.** Clear the stale ticks before draft day, and cap the benchmark at `Q`.

### Two smaller notes

- **The pool Z-total sanity cell reads 0.098 and is labelled "should be ~0" with no
  threshold.** The residual is real and explainable — the provider rounds FG% and FT% to
  three decimals independently of the makes and attempts, so the impact columns do not
  cancel perfectly. `tests/test_valuation.py` pins it below 0.05 on synthetic players;
  live it is roughly twice that. Benign, but 0.098 cannot be told from a genuine break
  without a stated tolerance.
- **`config/league.yaml` uses `fg3m` and `tov`; the code uses `tpm` and `to`.** Seven of
  nine keys match, and `review_mock_draft.py`'s docstring claims all nine do.

---

## Methodology, against its sources

Each of these was re-derived from the paper, not taken from a code comment.

| Check | Verdict |
|---|---|
| The nine G-multipliers vs Rosenof Table 8 | **Exact.** They are the table's *G/Z percent column* normalised to AST = 75%; all nine match to within 0.0033 — rounding of an integer-percent column |
| Using a multiplier at all | **It is the paper's own definition.** G and Z share a numerator and differ only in the denominator, so `G = Z × (Z-denom / G-denom)` is an identity, not an approximation of form |
| FG%/FT% impact | Matches Rosenof's percentage numerator. Because the pool rate is the attempt-weighted aggregate, the impact column's mean is *identically* zero, so dividing by its SD is a proper z-score with no centring term |
| Turnovers | Inverted once, in `z_scores`, with the multiplier applied to the flipped value. The Tracker's Edge flips on the TO row and only there |
| Q = 156 | Matches the league (12 × 13) and the paper's own worked example |
| `Adjusted Value = VOR × GP / 72` | Basketball Monster's *recommended* setting, "Total Value with Added Replacement Games". The identity: `GP·v_p + (82−GP)·v_r`, minus the constant `82·v_r`, is `GP × VOR`. The divisor is cosmetic — it cannot move a player across the `VOR = 0` boundary, so it cannot change a rank |
| Percentage denominator | [ADR-0012](../decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md)'s measurement reproduces independently: the rate-SD alternative moves 19 players 10 or more places with 4 in the top 50, against the ADR's 24 and 4. Its conclusion holds |

### Sensitivity

Each judgement call was perturbed to its defensible alternatives and the board re-ranked.

| Alternative | Mean move | Max | Top-50 moves ≥ 5 |
|---|---|---|---|
| FG/FT multipliers from the raw Table 8 variances | 0.7 | 4 | 0 |
| FG/FT multipliers from the rounded denominators | 1.2 | 10 | 0 |
| Rate SD instead of impact SD | 4.1 | 20 | 4 (moves ≥ 10) |
| Plain Z — drop the G-score entirely | 7.2 | 37 | 15 |
| Unconverged vs converged pool (F3) | 0.33 | 4 | 0 |

**The FG/FT multiplier question can be closed.** Table 8 reports the two percentage rows to
one significant figure, and the code comment schedules a Phase 4 re-derivation. Across all
three defensible readings the worst case is ten places and **zero** top-50 moves of five or
more. Not worth the time.

**The G-score is doing real work.** Dropping it moves 57 players ten or more places and 15
inside the top 50 — this is not a cosmetic layer.

### Does the ordering make sense?

Against the export provider's own independently-computed 9-cat rank the board correlates at
**0.959** Spearman, and against ADP at **0.825** (162 of 200 carry an ADP). Divergences run
in explicable directions — players rise on peripherals and fall when they are volume
scorers whose other categories do not pay.

---

## Still open

Neither is a bug; both are logged in the
[2026-08-27 methodology review](2026-08-27-draft-board-methodology-review.md) and were out
of scope here.

- **Category correlation.** The nine z-scores are summed as if independent, but blocks
  travel with rebounds and assists with turnovers, so a total double-counts correlated
  strengths. The largest remaining methodological gap; it bites from about round four.
- **`PUNT_WEIGHT` = 0.25 is uncalibrated**, as
  [ADR-0009](../decisions/ADR-0009-soft-punt-weighting.md) states plainly.
- **The board has no expert input.** Confirmed live: 0 of 200 rows carry GP history, a
  `My GP Est` override, a note, or an XRank. ADP is the only external signal.
