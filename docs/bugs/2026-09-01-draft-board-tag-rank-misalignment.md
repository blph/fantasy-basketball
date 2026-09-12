# The rank tags showed the wrong player's rank

- Date: 2026-09-01
- Reported by: Bryan
- Severity: **High** — wrong on 195 of 200 rows in all nine value columns, on a board used
  live on draft night, while every automated check passed
- Status: fixed, deployed to the live sheet, and verified there. **Not yet committed** —
  the change sits in the working tree on `draft-refactoring` for review.

## Symptom

Sorted by DURH, Victor Wembanyama's BMP DURH column read **`#5 3PM`**. He is BMP DURH
**`#2`**, and `3PM` is his dropped category. The rank was another player's; the category
was his.

## What was actually wrong

Not one cell. Pulling all 200 rows and comparing against `Data.gs`:

| | wrong |
|---|---|
| Rank tags | **1755 of 1800** — 195 of 200 rows in **every one** of the nine source × value columns |
| ▲ Strengths / ▼ Weaknesses | wrong wherever the two orderings disagreed |
| Category Tracker raw feed | wrong, invisibly — 0 players were ticked `Mine` |

Victor was shown `▲ FG%, FT%, PTS, AST, STL`. That is Shai Gilgeous-Alexander's profile.
Victor's own `REB` and `BLK` were missing — Wembanyama not listed as a rebounding or
blocking strength, on the tab you draft from.

Only the **rank half** of each tag was wrong. The dropped category was always right, which
is what made every tag look ordinary.

## Mechanism

The board's rows were in **BMP·DURH** order. The hidden block behind them — `AQ:BY`, the
raw feed, the profile values and the nine numeric rank columns — was in **HBP·DURH** order,
left over from an earlier build. Read live:

| board row 5 (Victor, calculation row 5) | formula | points at |
|---|---|---|
| `J5` value | `=BMP!$Q$5` | Victor |
| `AL5` best build | `…BMP!$R$5…` | Victor |
| `AP5` notes | `=Board!$AB$5` | Victor |
| `AQ5` raw FGM | `=BMP!$E$6` | **SGA** |
| `BI5` profile | `=BMP!$AG$6` | **SGA** |
| `BQ5` DURH rank | `=BMP!$R$6` | **SGA** |

The tag turned that misalignment into a plausible sentence, because it spliced two
different anchoring schemes into one string:

```js
var rc = '$' + a1col(dRank(s, k)) + r;                            // POSITIONAL
row[dTag(s, k)] = '="#"&' + rc + '&" "&'
                + cellRef(SOURCES[s].key, V[kind.drop], n);       // IDENTITY
```

`$BQ4` means "whatever helper cell sits in my row". `BMP!$S$4` is pinned to that player.
Let the block and the rows disagree and the tag pairs one player's rank with another's
dropped category — and still reads like a rank.

**Origin.** Re-running `Rebuild & re-sort` against the unmodified deployed code healed all
1800 tags, and the deployed `Code.gs` matched the repo on line count and on the block-write
code itself. So the writer was never wrong: the sheet had been left half-rebuilt by an
earlier run, with the visible columns in the new order and the hidden block still in the
old one. Nothing announced it.

## Why nothing caught it

- `pytest` — 182 passed. It never sees the sheet.
- `ruff` — clean.
- `harness.js` — "no problems found". It compares generated formula **strings** and never
  evaluates one. Its tag assertion checked only that the tag mentioned `$BQ4`, which is
  exactly what the broken formula did.
- `verify.py --sheet` — pulled three columns, `rank,name,value`. It never read a tag.
- The sheet's own guards — **dead**. `COUNTA(#REF!)`. See below.

Every gate was green while 97% of the tags were wrong. That is the finding worth keeping.

## Three further defects, found while fixing it

1. **The Settings sanity checks were dead** (pre-existing). "Board rows" read `1.0000`
   against a 200-row board and "ADP coverage" read `0 of 1`, because `sheetByName` deletes
   and recreates each tab, which turns every named range pointing into it into `#REF!`
   inside the formulas that used it. The one live guard against the calculation tabs
   drifting out of row-order had been reporting nothing at all.

2. **A rank could disagree with the value beside it** (23 rows). `Data.gs` shipped ranks
   computed at full precision and values rounded to four places, while the sheet's own `#`
   column ranks what it was given. Deep-tier pairs — Desmond Bane and Ryan Rollins traded
   56/57 — but the same defect class: a `#` that does not mean what it says.

3. **The board's sort dropdown was decorative.** It carried a dropdown, the cheat sheet
   pointed at it, picking a value changed the label — and `Rebuild & re-sort` read Settings'
   `SORT_BY` and sorted by that instead. A control that silently does nothing is worse than
   no control, because you believe it.

## Fix

- **Both halves of every tag now name the same calculation row.** A tag can only be wrong
  when the value beside it is wrong too, and that is checkable.
- **The board carries its own witness.** A hidden `row check` column resolves the player
  name from the same calculation row the hidden block reads; Settings compares it against
  `Player` on all 200 rows and says `MISALIGNED` if they ever differ.
- **The sanity checks reach other tabs through `INDIRECT` over R1C1**, which Sheets does
  not rewrite. Both live guards report again.
- **`rerank` ranks the rounded value** — what the sheet is given is what we rank.
- **The sort dropdown writes through to `SORT_BY`**, so the control on the board is the
  control.
- **The gates can now see it.** `verify.py --sheet` accepts a full `A4:AA203` pull and
  checks all 1800 tags plus that the `#` column equals exactly one source's rank on every
  row; the harness asserts each tag, its value and its rank helper name one row on one tab,
  and that no sanity check leans on a named range or an A1 cross-sheet reference.

Each new gate was run against the old code first: the harness fails 84 assertions on the
positional tag, 1 on the A1 sanity reference, and `verify.py` reports `1755 wrong` on the
pull taken before the fix.

## Verified

On the live sheet, both orderings, after deploying: 1800 of 1800 tags correct sorted by
BMP·DURH and again sorted by HBP·DURH; `# column agrees with BMP DURH on every row`; both
Settings guards read `aligned`; `Board rows 200`, `ADP coverage 162 of 200`. Victor
Wembanyama reads `#2 3PM`, `#5 AST`, `#4 AST`, and his ▲ includes `REB` and `BLK`.
