# Basketball Monster reordered DURANT's two steps, and the refresh stopped calibrating

- Date: 2026-10-01
- Reported by: Bryan ("new data is ready in the downloads folder")
- Severity: **High** — the 2026-10-01 refresh could not proceed at all. `calibrate_bbm.py`
  refused to write constants for either vendor source, so `build_data.py` had nothing to
  score with and both boards stayed on 2026-09-12 data.
- Status: **fixed and verified against Basketball Monster's own published columns**
  ([ADR-0029](../decisions/ADR-0029-durant-standardises-before-transforming.md)). DURH now
  reproduces at MAE 0.0029 on both sources.
- Outstanding: two separate items below, neither blocking — their plain `DUR` aggregate is
  unidentified, and the first scrape of a source can come back truncated.

## Symptom

The calibration failed its tolerance gate on three counting categories per source:

```
calibration failed: the fit is outside tolerance, so the scrape is probably bad or their
columns have changed:
  durant.pV rmse 0.0384 > 0.030
  durant.rV rmse 0.0367 > 0.030
  durant.aV rmse 0.0374 > 0.030
```

The same fitter, same code, on the previous refresh's files:

| cat | BMP 09-12 | BMP 10-01 | ALT 09-12 | ALT 10-01 |
|---|---|---|---|---|
| pV | 0.0040 | **0.0384** | 0.0034 | 0.0226 |
| 3V | 0.0048 | 0.0047 | 0.0053 | 0.0062 |
| rV | 0.0049 | **0.0367** | 0.0047 | **0.0340** |
| aV | 0.0040 | **0.0374** | 0.0042 | **0.0346** |
| bV | 0.0142 | 0.0271 | 0.0162 | **0.0311** |
| toV | 0.0077 | 0.0285 | 0.0074 | 0.0280 |

Every counting category degraded 5–10× except **threes**, which did not move at all. The plain-z
layer, fitted on the identical data, still reproduced every category at rmse ≤ 0.018.

## What it was not

Worth recording in order, because each exoneration is what narrowed the answer — and because the
first two were the obvious suspects and both were wrong.

**Not the export.** The natural first guess, and Bryan's: a wrong export setting would produce
exactly this signature, since the plain layer absorbs any affine rescale into its fitted slope
while Yeo-Johnson cannot. Tested by driving their page through Playwright and clicking their own
*Export to CSV* with the source, scope and filter set deliberately. The machine-made export
matched the hand download at mean |Δminutes| **0.11** (Josh) and **0.00** (Bonus) across ~590
common players; the 104 differing lines were roster membership at the fringe, among players with 0
to 16 projected games. Refitting against it reproduced the failure to four decimals.

**Not the scrape.** 234 players joined, 0 unjoined, both sources. See the truncation item below —
the *first* pull of each source was short, and that is a real defect, but it is not this one.

**Not our code.** Refitting the 2026-09-12 scrapes on the new code still passed.

**Not the pool, and not a rescale.** Both are affine in the fitted slope, so neither can break the
DURANT layer while the plain layer stays exact.

**Not the stat basis.** Fitting λ freely on assists: per-game 0.0374, totals 0.2268, per-36 0.2864,
value×games 0.2385.

**Not rank-based normal scores** (0.07–0.17, worse on both dates) and **not a blend with the plain
z** (0.0374 → 0.0370, with a coefficient of −0.025 on the z).

## Diagnosis

Three measurements, in the order that mattered:

1. **Spearman between our per-game stat and their `D*V` was ~0.99998 on both dates** — identical.
   §III.1's own discriminator: a monotone transform of the correct input orders players
   identically, so the input was right and the deviation from 1.0 was quantisation present on both
   dates equally.
2. **Isotonic regression reached 0.0011 on 2026-10-01**, as good as on 2026-09-12. That is the best
   fit achievable by *any* monotone transform, so a smooth monotone function of that same input
   still explained their column completely. The family had changed, not the input.
3. **The residual from the best single Yeo-Johnson oscillated** across the stat's deciles —
   +0.046, −0.023, −0.039, −0.035, −0.020, +0.002, +0.029, +0.040, +0.028, −0.025. Four sign
   changes, which no one-parameter power family produces.

Then the hypothesis that fit everything: their own published plain-z column is in the same scrape,
so it could be fed to the transform directly. Yeo-Johnson **of the standardised z** fits all nine
categories at 0.0038–0.0059, on both sources, on 2026-10-01 — and fits 2026-09-12 badly, where the
old order fits perfectly.

**Threes is the tell.** Yeo-Johnson at λ = 1 is affine, so the two orderings agree exactly there
and nowhere else. Threes' λ sits on the identity, which is why it was the one category that did not
move.

## Fix

[ADR-0029](../decisions/ADR-0029-durant-standardises-before-transforming.md). The DURANT layer
standardises before it transforms; the sign goes on the z once; `durant_params` takes the plain
block as a required argument; constants files bump to schema 2; the DURANT percentage rate is gone
and one fitter covers all nine categories; both DURANT gates tighten.

Verified against their published columns on 191 matched board rows: DURH **MAE 0.0029, max 0.0231**
(BMP) and **MAE 0.0029, max 0.0197** (BMP-ALT). The synthetic round-trip in
`tests/test_calibrate_bbm.py` recovers invented constants *and* invented λ through the new
composition, and `tests/test_bbm_reference.py` pins the order, the λ = 1 coincidence, and the
single sign application.

### Two fixtures were constructing impossible states

Both `invented_params` and `borrowed_from` built the DURANT block from the plain block and *then*
perturbed the two independently. Under the old order that was harmless, since the layers were
parallel. Under the new one it produces a file whose plain column and DURANT column describe
different z-scores — something `bbm_constants.parse` can never emit, because it copies the plain
constants across. Both now perturb the plain block first and build DURANT from the result.

## What is still outstanding, and why neither blocks

### Their plain `DUR` aggregate also changed

Their own nine published columns rebuild their own `DUR H2H` at MAE 0.0025 on **both** dates, so
the weights, the minus-one rule and the mean-of-seven are untouched. Plain `DUR` is a different
story: the minus-one rule gave 0.0025 on 2026-09-12 and gives 0.0911 on 2026-10-01, and the best
simple rule over their nine (a fractional drop weight of 0.55, which is not a plausible published
rule) only reaches 0.0135.

Left unidentified deliberately. The board never reads that column — `verify.py:82` compares only
`Value` (→ ZSC) and `DUR H2H` (→ DURH), and the board's three values are DURH, ZSH and ZSC. Worth
revisiting only if a future column needs it.

### A refresh alone cannot pass step 12

Found while deploying this fix, and unrelated to it. `verify.py --local` failed on eight cells —
the Settings tracker block's **D-on-z slope**, `E16:E23` — with all 15,594 Draft Board cells, the
tracker, the punts and the Settings inputs agreeing. The sheet's eight values matched the
2026-09-12 snapshot *exactly*: they were stale, not wrong.

`writeSettingsSkeleton` is the only thing that writes that block, and only `buildDraftBoard`
(Full rebuild) and `step1_Settings` call it. `refreshData` does not. Since those slopes move
whenever the projections move, the documented procedure — step 8 `Refresh data`, step 11
`Rebuild & re-sort`, step 12 `verify --local` with "exit 0 is the pass" — could never pass on a
refresh that moved them. The 2026-09-12 deploy must have ended in a full rebuild.

Worked around for now by adding **step 11a** to the procedure: run `Full rebuild (from Data.gs)`
before verifying. The better fix is to have `refreshData` rewrite those eight cells, which would
let a refresh stand on its own; it is a `Build.gs` change, so it needs a `Code.gs` redeploy and it
moves the `rebuild` fingerprint hash, which pulls in the tick scenario.

### The first scrape of a source can come back truncated

On this refresh the first pull returned **152** rows for BMP and **147** for BMP-ALT, against 234 on
a retry. `scrape()` posts back to set their "Only Top Players" filter and then waits a flat
`time.sleep(2)`, with no settle loop of the kind `_settle()` provides after the source switch.

Two consequences, both real:

- The injury table is written **before** the `MIN_ROWS` check, so the 147-row pull wrote a
  147-grade `BBM Injury Risk` file and only then exited. A short pull silently produces an
  incomplete injury column, and a blank in a risk column reads as `LOW`.
- `MIN_ROWS = 150` did not catch the 152-row BMP pull, which went on to fit a truncated set and
  failed tolerance on only one category. A slightly longer truncation would have passed the gate
  and written wrong constants.

Not fixed here, to keep this change to one subject. Both files were re-pulled full and the injury
table rewritten with 234 grades before anything was built.

### ZSC still fails its per-row maximum on two players

Unchanged by this work — ZSC comes entirely from the plain layer, whose recovered constants are
bit-identical before and after. `verify.py --published` reports 1 row (BMP) and 2 rows (BMP-ALT)
over the 0.020 per-row tolerance, at 0.0265 and 0.0325. Every one of them is a player
`consistent_players` had already flagged as having a stat line Basketball Monster revised after
publishing the value we scraped; the worst unrevised row is 0.0113. Re-exporting does not help,
because the fresh Playwright export carries the same lines — the drift is between their own
projections table and their own value columns. The remedy is upstream and the condition is named,
not hidden.
