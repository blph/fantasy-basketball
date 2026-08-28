# Reviewing a mock draft

How to grade a mock draft against the board and produce a report comparable across mocks.
Run it after every mock from your real slot; the [playbook](../references/fantasy-basketball-draft-playbook.md)
§7 prep list asks for two or three.

- The method being graded against: [the playbook](../references/fantasy-basketball-draft-playbook.md),
  §8 (the in-draft decision rule), §9 (the round plan), §10 (punting and marginal value).
- What every board number means: [cheat-sheet.md](cheat-sheet.md).
- How the board is fed: [build-and-maintenance.md](build-and-maintenance.md).

Reports go in `docs/reviews/mock-drafts/`, which is **gitignored**. They quote ADP and
projected GP, and `GAP + Adj Rank` recovers ADP exactly, so a report is provider data
([ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md)). `check-no-data.sh`
does not scan `.md` under `docs/`, so the `.gitignore` entry is the only guard. This
document carries no numbers and is committed.

---

## What you supply

1. **The full draft log** — every pick in order, with the manager who made it.
2. **Your manager name**, exactly as the log spells it.
3. **The mock's team count.** Often not the league's team count, and it moves Q.

---

## Step 1 — Pull the board

**Never review from the exported rankings CSV.** `export_yahoo_rankings.py` reduces the
board to `rank,name,team,position` by design, dropping TIER, Adjusted Value, GAP and the
punt columns — the four things this review turns on. **Never use Drive's file-content
reader either**: it renders the sheet as prose and truncates at about rank 77, silently.

```bash
playwright-cli -s=fantasy open --persistent \
  'https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit'
```

Once the page title is the sheet's name rather than a sign-in page, the session is
authenticated. Fetch each range from inside that page so the request carries its cookies:

```bash
playwright-cli -s=fantasy eval \
  "() => fetch('https://docs.google.com/spreadsheets/d/<SHEET_ID>/gviz/tq?tqx=out:csv&sheet=<TAB>&range=<RANGE>&headers=0', {credentials:'include'}).then(r => r.text())"
```

| Tab | Range | What it carries |
|---|---|---|
| `Draft Board` | `A2:Z202` | `#`, **TIER**, Player, Team, Pos, AdjVal, ProjGP, MyGP, ADP, GAP, Best build, Category profile, Left @pos |
| `Board` | `A3:CA202` | the z and g blocks, VOR, Adj Rank, nine punt scores, nine punt ranks |
| `Settings` | `A1:H90` | Teams, Q, GP divisor, MIN_GP, tier multiplier, punt weight, pool constants, tracker bands |
| `Punts` | `A1:AH16` | top risers per build, for cross-checking build detection |

The response arrives as a JSON-quoted string on the second line of the tool output.
`json.loads` it, then parse as CSV. Save both CSVs outside the repo; they are provider
data.

### Board column map

Zero-indexed over `Board!A3:CA202`. The header row spans merged blocks, so positions are
the only reliable handle.

| Cols | Contents |
|---|---|
| 0-4 | Seed Rank, Player, Team, Pos, In Pool |
| 5-19 | GP, MPG, FGM, FGA, FG%, FTM, FTA, FT%, 3PM, PTS, REB, AST, STL, BLK, TO |
| 20-21 | FG Impact, FT Impact |
| 22-31 | z FG%, FT%, 3PM, PTS, REB, AST, STL, BLK, TO, then **Z TOTAL** |
| 32-41 | the same nine as g-scores, then **G TOTAL** |
| 42-43 | VOR, Rank (VOR) |
| 44-50 | GP Y-1, Y-2, Y-3, **My GP Est**, GP Flag, **Adjusted Value**, **Adj Rank** |
| 51-53 | ADP, XRank, **GAP** |
| 54-62 | nine punt scores, in `PUNTS` order |
| 63-71 | nine punt ranks, same order |

`PUNTS` order is FT%, FG%, AST, 3PM, BLK, FG%+REB, AST+STL, PTS+FT%, FG/FT/TO
([ADR-0010](../decisions/ADR-0010-punt-build-set.md)).

**Stop-the-line check.** For any row, `G TOTAL − VOR` must equal Settings'
`Replacement G-score`. If it does not, the pull is stale or the range has shifted. Fix
that before computing anything.

---

## Step 2 — Reconstruct the draft

Snake order: round 1 as listed, round 2 reversed, alternating. For `T` teams your overall
picks are `slot`, `2T − slot + 1`, `2T + slot`, and so on.

Normalise names before joining: strip diacritics (`Jokić`, `Dončić`, `Porziņģis`,
`Şengün`) and the `Jr. / III / II / Sr. / IV` suffixes. Some drafted players fall outside
the board's 200 rows. **Count them and report the count**, because opponent totals are
then scaled up from however many matched, and that scaling is an assumption the reader
needs.

---

## Step 3 — Compute the six artifacts

Each player contributes his per-game line × `My GP Est / GP divisor`. That is the board's
own availability model, and per playbook §6a it is the exactly-correct expected season
value under replacement-level backfill, not an approximation. Team FG% and FT% are always
team makes ÷ team attempts — never the mean of individual rates.

### A. Standings

Round robin: your team against each opponent, nine categories each, giving `9 × (T − 1)`
category outcomes. Report the record and where it places in the field.

### B. Category profile and gap-to-flip

Per category: your total, your rank, your record, and the distance to the next matchup you
would flip — absolute and as a percentage. For categories won outright, the surplus over
the best rival. This is where wasted capital becomes visible, and it is usually the most
surprising table in the report.

### C. Category Tracker trace

Reproduce the tracker as `Build.gs` defines it, after each of your picks: benchmark is the
mean of the top `Teams × n` by Adj Rank, times `n`. Thresholds come from Settings — the
FG% band, the FT% band, and the counting band as a share of the benchmark. Emit the
STRONG / EVEN / WEAK grid, one row per pick.

**The most diagnostic artifact in the review.** A category reading WEAK in every row is a
deficit never addressed. One reading STRONG in every row is capital that kept being spent
after it stopped paying. One reading EVEN throughout is where §10 says the next pick was
worth most.

### D. Build detection

Sum each of the nine punt-build scores across your roster. The highest is the build you
actually drafted, declared or not. Compare it against the standard G TOTAL: when a punt
column wins by a wide margin, playbook §6b applies — the build revealed itself and the
primary sort should have switched to it.

### E. Marginal value (§10)

Convert per-category records to win rates and interpolate §10's table — 5% → 0.31,
30% → 0.97, 50% → 1.09, 85% → 0.60, 95% → 0.26 — to price the next slice of capital in
each category. Then place the shape against §10's four simulated archetypes: Balanced
(63 across, 79.4%), Soft punt 2 (73×7 / 27×2, 80.5%), Stack 3 hard (72.5%), Stack 3
extreme (63.6%).

### F. Tier-legal alternatives

For each pick, the shortlist is the players **in the same tier** still on the board.
Playbook §8 step 1 makes the live tier the shortlist; anything outside it is a reach and
does not belong in the comparison. Rank the shortlist two ways:

- by **Adjusted Value** — did the pick capture the value?
- by **need-fit**, the sum of the player's g-scores across the categories the tracker read
  WEAK or EVEN at that moment — did it fix what was broken?

Record how many candidates the tier held. **A tier of one is a forced pick and is not
graded on choice.**

Then compute the **tier-legal ceiling**: hill-climb allowing only same-tier
substitutions. That is the honest benchmark; a ceiling built from reaches measures
nothing.

Climb from three deterministic starts — as drafted, best Adjusted Value in each tier, and
best g-total in each tier — because a single start lands in a local optimum well short of
the true best. **Report the result as a lower bound.** It is a floor on what was
reachable, not a proof of the maximum, and saying so keeps the achieved-versus-ceiling
ratio honest.

---

## Step 4 — Grade

### Per pick

Start at **9.0** and apply in order. A pick that takes the top of its tier, fits the
roster and carries no market edge lands at 9.0; market timing earns the last point.

| Component | Adjustment |
|---|---|
| Value capture | `− min(2.5, 2.5 × (AdjV rank in tier − 1) / (n − 1))` |
| Roster fit | `− min(3.5, 0.6 × (best need-fit in tier − this need-fit))` |
| Market timing | `+ clamp(GAP / 25, −1.0, +1.0)`; zero when GAP is blank |
| Availability | `− clamp((pool average GP − My GP Est) / 10, 0, 1.5)` |
| Dominated | `− 2.0` when a same-tier player had **both** higher Adjusted Value and better need-fit |
| §8 violation | `− 1.5` when a same-tier player sat within 0.25 of Adjusted Value with materially better need-fit and was passed |
| §9 violation | `− 1.0` when the pick contradicts its round band |
| Forced pick | when `n = 1`, zero the value-capture, roster-fit and dominated terms |
| Rounds 1-2 | zero the roster-fit term |

Clamp to 1-10. Bands: 9.5 A+, 8.8 A, 8.3 A−, 7.8 B+, 7.2 B, 6.7 B−, 6.2 C+, 5.5 C,
5.0 C−, 4.5 D+, 3.8 D, below that F.

Three of those deserve their reasoning stated, because each replaced a version that gave
wrong answers:

- **Market timing is capped at ±1.0, not ±1.5, and the base is 9.0 rather than 10.** With
  a ±1.5 bonus against a base of 10 the score clamped at the top, so every pick with a
  large GAP graded A+ no matter how badly it fitted. Cheapness must not buy back a fit
  failure.
- **Rounds 1-2 are exempt from the fit term.** Playbook §9 says take best available and
  commit to nothing, and §8 adds that the overrides "start earning their keep around round
  3". A lopsided first-round pick is the plan working. The §8 tiebreak still applies at
  every pick, because that rule is not round-dependent.
- **Dominated is the sharpest test in the rubric.** Higher Adjusted Value *and* better
  need-fit, in the same tier, leaves no reading under which the pick was right: the board
  preferred the other player and so did the roster.

### Round bands (§9)

| Rounds | Expected | Violation |
|---|---|---|
| 1-2 | Best available adjusted for games played; commit to nothing | Poor need-fit is **not** a violation here |
| 3-6 | The build reveals itself | The tracker's WEAK categories are unchanged and the pick deepens them |
| 7-10 | Fill the two weakest non-punted categories | The pick's best category already reads STRONG |
| 11+ | Upside, specialists, playoff-week schedule | The pick is the safest available veteran — these are churn slots (§8a) |

The formula is a first pass, in the spirit of the playbook's own tier multiplier: a
starting point, not a law. Override it, with the reason stated.

### Overall

Grade six dimensions separately rather than averaging picks. They fail independently, and
the split is the actionable part.

| Dimension | Measured by |
|---|---|
| Value capture | share of picks that were the top tier-legal Adjusted Value |
| Market timing | the distribution of GAP across the picks |
| Availability | mean My GP Est against the pool average GP |
| Tier discipline | any pick taken outside the live tier |
| Roster construction | whether the tracker's WEAK categories ever changed a pick |
| Build commitment | whether the sort switched once a build revealed itself (§6b) |

Give one headline figure out of 10, and state the achieved-versus-ceiling ratio beside it.
**A high ceiling ratio next to a low roster-construction grade means the board carried
you** — the most common result, and the one worth naming plainly.

---

## Step 5 — Write the report

In this order: method and caveats · result and standings · the build actually drafted ·
the Category Tracker trace · marginal value · round by round · grades · generalized rules
· corrections to earlier drafts.

Caveats go first, not last. Every review has them and they bound every number in it.

Keep the corrections section even when it is empty. A review that revises an earlier
conclusion is more useful than one that quietly replaces it, and the next mock is graded
against the same history.

---

## Caveats to state every time

- **Team count.** If the mock's count differs from Settings `B4`, Q is wrong for that mock
  and replacement level moves. This is [methodology-review](../reviews/2026-08-27-draft-board-methodology-review.md)
  finding F1 in live form.
- **Unmatched players.** How many fell outside the board's 200 rows, and that opponent
  totals are scaled from those that matched.
- **ADP provenance.** It is the export provider's aggregate, not Yahoo's (F12). Read GAP
  as "cheap somewhere", not "cheap in this room".
- **Blank GAP is not zero.** An unpriced player is not a fairly priced one.
- **Position is not in the model** (F10). `Left @pos` counts what remains; it does not
  value scarcity. Judge that tiebreak by hand.

---

## Traps

Every one of these produced a wrong conclusion the first time this review was run.

- **The exported CSV has no tiers.** It causes recommendations that cross tier
  boundaries, and they look entirely reasonable until you check. Pull the sheet.
- **Single-swap analysis understates everything.** Substituting one player and recomputing
  usually shows no change, because one player is roughly 8% of a roster and the deficits
  run deeper than that. On a roster sitting near several category boundaries, improvements
  cascade rather than add. Run the multi-swap or hill-climb version before concluding a
  pick was harmless.
- **`ADP − pick number` is not GAP.** GAP is `ADP − Adj Rank` and lives on the board. Both
  are informative; reporting one as the other is not.
- **Never benchmark against a ceiling built from reaches.** Constrain counterfactuals to
  the live tier.
- **The board moves.** It is edited between exports, so ranks drift a spot or two from any
  saved CSV. Pull fresh for every review, and date the report.
