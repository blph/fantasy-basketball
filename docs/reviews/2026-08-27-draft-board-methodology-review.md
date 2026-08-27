# Draft board methodology review — 2026-27

- Date: 2026-08-27
- Reviewer: `nba-9cat-analyst`
- Scope: `scripts/draft-board/` (Build.gs, gen_data.py, harness.js, export_readme.js),
  `docs/references/fantasy-basketball-draft-playbook.md`, `docs/draft-board/`,
  `docs/decisions/`, `docs/database/schema.md`, `config/league.yaml`, `README.md`,
  `docs/roadmap.md`, `docs/api/data-providers.md`
- Method: read the playbook (provenance section first), the generated cheat sheet, then
  every formula string `Build.gs` writes; ran `node harness.js` to confirm the live
  formula text; checked every strategy claim against published sources.
- Constraint honoured: no player row, projection, ADP value, or export figure from
  `data/` or `Data.gs` appears below. Worked examples use invented players.

---

## Verdict

**Draftable, but not as it stands — three things must be fixed first, and they are all
cheap.** The valuation core is in better shape than most home-built boards: the nine
G-score multipliers reproduce Rosenof's Table 8 exactly, the percentage categories are
volume-weighted against an attempt-weighted aggregate rate (which makes the missing
mean-centring provably harmless, not merely tolerable), turnovers invert correctly, the
GP adjustment scales VOR rather than the G-score, and the Adjusted Value formula turns
out to be the exactly correct expected-season-VOR under replacement-level backfill —
better reasoned than the playbook itself claims. That layer I would not touch.

The failures are concentrated in the layers built *on top* of the valuation, and in the
settings underneath it. Underneath: `config/league.yaml` still carries `team_count`,
every roster slot, and the transaction cap as `TODO`, while the sheet hardcodes 12 × 13
and a scoring format that contradicts what `league.yaml` does say. Q = 156 is therefore
an assumption, not a measurement, and the punt-heavy posture rests on a format nobody
has confirmed. On top: the Punts tab and the "Best build" column silently drop the
games-played adjustment, so they systematically flag the least available players as
bargains; the Category Tracker's STRONG/EVEN/WEAK read is arithmetically incapable of
ever firing on FG% or FT% and is benchmarked against the wrong population for the first
ten rounds; and the six punt columns implement hard punts when the playbook's own cited
research prescribes soft ones. Downstream, `schema.md` specifies no G-score at all, so
Phase 2 would reimplement Z-score and inherit the loss permanently.

Twenty-one findings: 1 Critical, 5 High, 7 Medium, 5 Low, 3 Notes. None of the Critical
or High findings require touching the valuation math; four of the six are single-cell or
single-constant changes.

---

## Findings

### CRITICAL

---

#### F1. Q, the scoring format, and the churn-slot count are all unverified, and the sheet contradicts `league.yaml` on the one setting that decides the whole strategy

**Anchor.** `config/league.yaml:12` (`team_count: TODO`), `config/league.yaml:57-60`
(`starters`, `bench`, `injured_reserve` all `TODO`), `config/league.yaml:63`
(`max_acquisitions_per_week: TODO`), `config/league.yaml:8`
(`scoring_type: head_to_head_categories`) versus `scripts/draft-board/Build.gs:604-611`
(`['Teams', 12], ['Roster spots', 13], ['Pool size (Q)', '=B4*B5']`) and
`Build.gs:610` (`['Scoring format', 'Most Categories']`).

**What is wrong.** Two separate problems with one root.

*Q is an assumption.* Every mean, every SD, the aggregate FG%/FT%, `POOL_AVG_FGA`,
`POOL_AVG_FTA`, both impact SDs, and `REPLACEMENT` are computed over "the pool", and the
pool is defined by `Q = Teams × Roster spots`, hardcoded on the Settings tab as 12 × 13.
`league.yaml` — the file the repo names as the source of truth for exactly this, and
which `schema.md`'s "Open items" list flags as blocking `mart_replacement_level` — has
never been filled in. The playbook opens by saying "Confirm all four before building
anything" (`docs/references/fantasy-basketball-draft-playbook.md:29`). They were not
confirmed; they were assumed. If the league is 10 teams, or carries an IL slot that
makes the effective roster 14, Q moves and *every number on the board moves with it*.

*The scoring format is self-contradictory.* `league.yaml` records
`scoring_type: head_to_head_categories`. Yahoo's own help page defines "Head-to-Head
Categories" as the format where each category is a separate W/L, and defines
"Head-to-Head One Win" as the variant where the week resolves to a single W/L — which is
what the playbook calls "Most Categories". The Settings tab hardcodes `Most Categories`,
and `SCORING` drives the Punts tab headline (`Build.gs:1180-1184`). So the repo's config
says Each Category and the board says Most Categories, and the playbook is explicit that
this is the setting that "matters most": "Punting is far more effective in Most
Categories… In Each Category every category counts every week, so abandoning three of
them is expensive. If you are in Each Category, dial everything below back toward
balance" (playbook:43).

The research backs the playbook. Rosenof's H-score paper reports the algorithm winning
**37.7%** of Most Categories seasons but only **21.8%** of Each Category seasons against
a G-score field, and states outright that the Most Categories weight distribution "is
more skewed to the extremes… This tracks with the idea that punting is most effective
and worthwhile in Most Categories." The G-vs-Z static result splits the same way,
32.5% versus 21.4%.

**Failure scenario.** Suppose the league is actually Head-to-Head Categories (Yahoo's
each-category format) with a 14th IL slot. Two things go wrong at once. Q should be
168, not 156; the pool means rise, every z-score shifts, and the replacement level
moves roughly a dozen players down the board — most visibly re-ordering the round 9-13
range where the marginal picks live. And the Punts tab, sitting at the top of the
draft-day tab order, is telling you to build a strategy the research says is worth about
half as much in your format as in the one the sheet assumes. A manager who commits to
the FG%/FT%/TO triple punt in an each-category league is voluntarily conceding three
weekly losses every week for a category edge that no longer converts at the same rate.

**Fix.** Fifteen minutes in the Yahoo league settings page. Fill in `team_count`,
`starters`, `bench`, `injured_reserve`, `max_acquisitions_per_week`, `playoff_start_week`
and `draft_type` in `config/league.yaml`; set Settings `B4`, `B5` and `B10` from it; if
the format is Each Category, say so on the Punts tab and treat the six punt columns as
soft-punt guides rather than builds (see F5). Add a line to `build-and-maintenance.md`
naming `league.yaml` as the source for `B4`/`B5`/`B10`.

**Needs an ADR?** No for filling in the config — that is data entry, not a decision.
**Yes** if the answer turns out to be Each Category and the punt posture changes, since
that is a change to core strategy.

**Sources.** [Yahoo, Head-to-Head scoring in Yahoo
Fantasy](https://help.yahoo.com/kb/SLN6447.html) · [Rosenof, *Dynamic quantification of
player value for fantasy basketball*](https://arxiv.org/abs/2409.09884) · [Rosenof,
*Static quantification of player value for fantasy
basketball*](https://arxiv.org/abs/2307.02188)

---

### HIGH

---

#### F2. The entire Punts tab and the "Best build" column drop the games-played adjustment, so they systematically promote the least available players

**Anchor.** `scripts/draft-board/Build.gs:250-257` — punt scores are built from
`$AP` (G TOTAL), never from `$AX` (Adjusted Value):

```
row[B[PUNTS[q].key]] = '=$AP' + r + ' - <dropped g terms>';
row[B[PUNTS[q].rank]] = '=RANK($<pc>' + r + ', $<pc>$3:$<pc>$202)';
```

and `Build.gs:975-978`, where **Best build** compares those un-adjusted punt ranks
against the GP-*adjusted* rank:

```
=IF(MIN(Board!$BG$n:$BL$n) >= Board!$AY$n, "—",
    INDEX({...}, MATCH(MIN(...), ..., 0)) & "  " & TEXT(Board!$AY$n - MIN(...), "+0"))
```

`$AY` is Adj Rank (`B.adjRank = 51`), which includes `My GP Est / 72`. The punt ranks do
not. The Punts tab's GAP column (`Build.gs:1196-1204`) is `ADP − punt rank`, also
un-adjusted, while the standard Gap on the Board is `ADP − Adj Rank` and *is* adjusted.

**What is wrong.** Two rankings on the same sheet answer different questions and are
then subtracted from one another. Availability is not a punt-specific consideration —
a player who misses a third of the season misses it in every build — so removing the GP
term from the punt columns is not a modelling choice, it is an omission. The
consequence is not noise: it is a *directional bias*, because the difference between the
two ranks is monotone in projected games.

**Failure scenario.** Invent "Marcus Delaine", a centre with a strong 9-cat line and a
poor free-throw stroke, projected for 48 games. On the standard board his Adjusted Value
puts him at Adj Rank 78. His Punt FT% score, computed from raw G TOTAL, puts him at punt
rank 31. **Best build** reads `FT% +47`. Roughly thirty of those forty-seven places are
nothing but the availability discount being deleted; only the remainder is the punt
genuinely helping him. On the Punts tab the same distortion inflates his Punt Gap by the
same thirty places, floating him toward the top of the "who this build gets at a
discount" list. The tab that the cheat sheet calls "Homework before draft day" is
handing you a list ordered partly by fragility. Every injury-prone player on the board
gets the same free promotion; every iron man gets a matching demotion. Systematically,
the punt lists are the standard board with the single most under-priced variable in
fantasy (the playbook's own words, at playbook:112) removed.

**Verdict.** CONFIRMED. Traced through the formula strings and reproduced in the harness
output.

**Fix.** One-line change per punt column: multiply the punt score by the same
availability ratio the main board uses.

```
Punt FT%  =($AP{r} - $AH{r}) * $AV{r} / GP_DIVISOR
```

Then **Best build** compares like with like and the Punts tab's GAP becomes a real
market comparison. Note the punt columns currently carry no `IF($AV{r}="","",…)` guard;
add one to match `B.adj`. If you would rather keep a raw-talent punt view, keep both and
label them, but sort the Punts tab on the adjusted one.

**Needs an ADR?** No. This is bringing the punt columns into line with a rule the
playbook already states and the main board already implements — a defect fix, not a new
decision.

**Sources.** playbook:110-116 ("Keep games played in its own column"); [RotoWire,
*Fantasy Basketball Durability: Top 10 Iron
Men*](https://www.rotowire.com/basketball/article/fantasy-basketball-iron-men-2025-availability-105630);
[CBS Sports, *Fantasy basketball's most reliable
stars*](https://www.cbssports.com/fantasy/basketball/news/fantasy-basketball-ironmen-mikal-bridges-more/)

---

#### F3. The Category Tracker's STRONG/EVEN/WEAK read can never fire on FG% or FT%

**Anchor.** `scripts/draft-board/Build.gs:1258-1260`:

```
=IF($B{r}="","", IF($D{r} > ABS($C{r})*0.08, "STRONG",
                 IF($D{r} < -ABS($C{r})*0.08, "WEAK", "EVEN")))
```

applied uniformly to all nine rows, including the two rate rows whose benchmark `$C` is
`=POOL_FG_PCT` and `=POOL_FT_PCT` (`Build.gs:1236-1237`).

**What is wrong.** The threshold is 8% *of the benchmark*. For a counting category the
benchmark is `MEAN_PTS × roster count` — a total — and 8% above an average team's point
total is a plausible, achievable edge. For a rate category the benchmark is the rate
itself. Eight percent of a field-goal percentage in the mid-forties is roughly **3.8
percentage points**; eight percent of a free-throw percentage near .780 is roughly
**6.2 percentage points**. Team-level FG% and FT% in a 12-team category league do not
spread anything like that far. The test is not merely conservative; it is unreachable in
both directions.

The same 8% number is transcribed into the cheat sheet
(`docs/draft-board/cheat-sheet.md:130`, "at a threshold of 8%") with no note that it
means something entirely different on two of the nine rows.

**Failure scenario.** You are at pick 8.04. You have taken three high-usage, poor-FT
bigs and a volume guard. Your roster is on track to lose FT% by a wide margin every
single week. You glance at the Category Tracker — the tab built precisely so you can
"see at a glance where you are strong, average, and weak" — and it reads **EVEN**. It
will read EVEN in round 3 and it will still read EVEN in round 13. The two categories
where a 9-cat roster most often quietly falls apart, and the two that decide whether you
are in a punt build at all, are the two the indicator is blind to. Worse, the Edge column
right beside it is formatted to three decimals precisely so the rate edge is visible
(`Build.gs:1255`), so the number is correct and only the verdict is wrong — the failure
mode this repo's own priority list names first: "A wrong number that looks right is worse
than no number."

**Verdict.** CONFIRMED. Pure arithmetic; no data needed.

**Fix.** Give the rate rows their own threshold. The cheapest correct version is an
absolute band in rate units, tuned once against a season of real category standings —
something on the order of half a percentage point for FG% and one point for FT% would be
my starting guess, explicitly labelled as a guess until it is calibrated. A better
version normalises every row by the SD of the *team-level* total rather than by the
benchmark's magnitude, which makes all nine rows comparable for the first time and
removes the arbitrary 8% entirely. Put the constants on Settings as named ranges.

**Needs an ADR?** Yes, if you take the SD-normalised version — that changes how roster
strength is judged, which is core strategy. No, for the minimal absolute-band patch.

**Sources.** playbook:290 (the tracker's stated purpose) ·
`docs/draft-board/cheat-sheet.md:124-131`

---

#### F4. The Category Tracker benchmarks against the whole 156-player pool, so every category reads STRONG for the first ten rounds

**Anchor.** `scripts/draft-board/Build.gs:1238-1246` — `'=MEAN_3PM*' + count`, and the
same pattern for the other six counting rows, where `count` is
`COUNTIF('Draft Board'!$S$3:$S$202, TRUE)` — the number of players you have ticked as
Mine. `MEAN_3PM` and its siblings are `AVERAGEIF(B_POOL, 1, …)` over all 156 pool
members (`Build.gs:626-631`). The tab's own header claims the opposite:
"Benchmark is what an average team from the pool would post over the same number of
players, **so the comparison holds at any roster size**" (`Build.gs:1204-1206`, mirrored
at `cheat-sheet.md:127`).

**What is wrong.** The claim is false everywhere except at the end of the draft. After
round *k* of a 12-team draft, all twelve managers hold *k* players each, and those
12*k* players are the **top 12*k* of the pool** — not a random sample of it. The right
benchmark for "what an average team has right now" is *k* × mean(top 12*k*), not *k* ×
mean(all 156). Because the pool mean is dragged down by the entire back half of the
board, the benchmark is far too low in the early rounds and converges to correct only at
round 13.

**Failure scenario.** Invent a pool whose mean rebounds across all 156 is 4.6 and whose
mean across the top 60 is 6.9 — a spread of that shape is what a value curve steepening
toward the top produces, and you can read yours directly off the Settings tab by
re-pointing `AVERAGEIF` at the top 60 rows. After five picks the tracker benchmarks your
five players against 5 × 4.6 = 23.0 when the honest benchmark is 5 × 6.9 = 34.5. You are
50% above a benchmark that is 33% too low, and the read is STRONG. It will be STRONG on
all seven counting rows simultaneously, because the same bias applies to all of them
equally. The tracker's one job is to tell you which category to spend your next pick on;
in rounds 3 through 6 — exactly the window where playbook section 9 says "Your build
reveals itself" — it tells you that all of them are fine. Combined with F3, in those
rounds the tab reads STRONG on seven rows and EVEN on two, regardless of what you have
actually drafted.

**Verdict.** CONFIRMED. Structural; follows from the definition of the benchmark.

**Fix.** Make the benchmark scale with the draft, not with the pool. Replace
`MEAN_3PM * count` with the mean over the top `TEAMS * count` rows by Adj Rank:

```
= AVERAGE(FILTER(B_3PM, B_ADJRANK <= TEAMS * count)) * count
```

(requires exporting `B_ADJRANK` as a named range — one line in `defineNames`). This is
correct at every roster size and reduces to the current formula at count = 13. Then fix
the header claim on `Build.gs:1204-1206` and regenerate the cheat sheet.

**Needs an ADR?** No — it makes the tab do what it already documents itself as doing.

**Sources.** playbook:288-290 · `Build.gs:1204-1206` · `cheat-sheet.md:127`

---

#### F5. The six punt columns are hard punts; the playbook and its own cited source both prescribe soft punts

**Anchor.** `scripts/draft-board/Build.gs:250-254` — a punt column is
`G TOTAL − <dropped term>`, i.e. the punted category is weighted **zero**. Confirmed in
the harness output: `Punt FT%  BC3 = =$AP3-$AH3`,
`Punt triple  BH3 = =$AP3-$AG3-$AH3-$AO3`. The cheat sheet describes it as "The entire
board recalculated as if that category did not exist" (`cheat-sheet.md:118`).

**What is wrong.** The playbook's section 10 says, under **Targets**: "Soft-punt rather
than hard-punt. The algorithm's punted-category weights peaked around 75% of normal, not
zero, because a small chance of winning is never no chance" (playbook:641). I verified
that against the source. Rosenof's H-score paper says: "the algorithm did not bifurcate
weights to an extreme degree between punting and not-punting. Instead, it took a more
subtle 'soft-punting' approach… It weighed most categories a bit above 100% and
compensated with a long tail below for punted categories, **peaking around 75% or so**."

So the sheet implements 0% where the playbook says 75% and the cited research says 75%.
This is a code-versus-playbook divergence, not a playbook error, and `ADR-0008` does not
declare it among its four deliberate deviations.

**Failure scenario.** Invent "Kwame Bristol", a wing who is unremarkable everywhere but
shoots free throws at a high rate and high volume. On a hard punt-FT% board his FT
contribution is worth exactly nothing, and he falls out of the top 60 of that column. On
a 75% board he keeps a quarter of it and stays around 45. If you have committed to punt
FT% and are choosing between Bristol and an equivalent player with no FT edge, the hard
board says they are identical and the soft board says Bristol is meaningfully better —
correctly, because you will still win FT% in some weeks by accident, and the weeks you
win it for free are pure profit. The error direction is consistent: **hard punting
systematically over-rewards players who are actively bad in the punted category** over
players who are merely neutral in it, and those are not the same bet. It also encourages
exactly the "Stack 3 extreme" behaviour that the playbook's own section 10 table rates
worst of the four strategies.

**Verdict.** CONFIRMED against the playbook and against the cited paper.

**Fix.** One constant and one edit. Add `PUNT_WEIGHT = 0.25` to Settings as a named
range (0.25 = retain 25%, i.e. the 75% discount), then change the generated punt formula
from `terms += '-$' + col + r` to `terms += '-(1-PUNT_WEIGHT)*$' + col + r`. Setting
`PUNT_WEIGHT` to 0 reproduces today's behaviour exactly, so the change is reversible from
the Settings tab with no code edit — which is the property ADR-0008 says the Settings tab
exists to provide.

**Needs an ADR?** **Yes.** It changes the valuation method for six of the board's
columns. Record it with the change, per the repo's convention.

**Sources.** [Rosenof, *Dynamic quantification of player value for fantasy
basketball*](https://arxiv.org/abs/2409.09884) · playbook:641 ·
`docs/decisions/ADR-0008-google-sheet-draft-board.md:60-77`

---

#### F6. `schema.md` specifies no G-score, so Phase 2 would reimplement Z-score and inherit the loss permanently

**Anchor.** `docs/database/schema.md` — `mart_player_zscores` ("Per-player,
per-`as_of_date` z-score for each of the 9 categories, plus a composite total"),
`mart_player_value` ("Composite value, positional rank, tier, and value over
replacement"). The words "G-score", "variance", "week-to-week" and "multiplier" do not
appear anywhere in the file. Two further defects in the same document:

- The layer diagram is headed **`FantasyPros API`**, the dimension carries
  `fp_player_id` as the first provider key, and `dim_expert` sources from
  `/nba/{season}/rankings/experts` — all of which `ADR-0007` superseded on 2026-08-23,
  four days before the board shipped.
- The impact formula is given as `(player_fg_pct − league_fg_pct) × player_fga`,
  "normalized". The sheet and the playbook use `(FGA / POOL_AVG_FGA) × (FG% − POOL_FG%)`.
  These differ by the constant `1 / POOL_AVG_FGA`, which cancels **only if** you then
  divide by the SD of that same column. `schema.md` does not say which SD it normalises
  by, so the formula as written is under-specified rather than wrong — and given F7
  below, the choice of SD is precisely the thing that needs pinning down.

**What is wrong.** `AGENTS.md` names the playbook, not either implementation, as the
specification — but Phase 2 will be built from `schema.md`, and `schema.md` describes a
Z-score system. The entire premise of this board is that Z-score is the wrong metric for
head-to-head, and the repo has a published simulation result to that effect sitting in
the playbook: a lone Z-score drafter against a field of G-score drafters wins **0.4%** of
Most Categories seasons against an 8.33% baseline. I verified that number against the
paper.

**Failure scenario.** Phase 2 lands. `mart_player_zscores` is built to spec. The Draft
Assistant reads it. The 2027-28 board is a Z-score board, the steals discount is gone,
steals specialists rise back to where the market already has them, and the one
defensible edge this project has over a free ranking site is silently deleted — silently,
because the numbers still compute and still look reasonable. Meanwhile the ingestion
layer is written against FantasyPros endpoints that ADR-0007 already rejected as unable
to carry the project.

**Verdict.** CONFIRMED.

**Fix.** Three edits to `schema.md`, none large. (1) Add `mart_player_gscores`, or a
`g_total` column and nine `g_*` columns on `mart_player_zscores`, with the multipliers
sourced from `config/league.yaml` rather than hardcoded — and note in the file that they
are 2022-23 estimates (see F7). (2) Replace FantasyPros with ESPN/Yahoo/Sleeper
throughout and repoint the endpoint reference. (3) Pin the percentage normalisation
explicitly: state whether the divisor is the SD of the impact column or the SD of the
rate, and cite the reason.

**Needs an ADR?** No for the provider correction (ADR-0007 already decided it; this is
the doc catching up). No for adding G-score either — the playbook and ADR-0008 already
establish it as the method, and `schema.md` is design-only with no DDL executed.

**Sources.** [Rosenof, *Static quantification of player value for fantasy
basketball*](https://arxiv.org/abs/2307.02188) ·
`docs/decisions/ADR-0007-espn-primary-data-source.md` · playbook:210-215

---

### MEDIUM

---

#### F7. The percentage z-scores are divided by the SD of the impact column, but the G-multipliers applied to them were derived from the variance of the raw rate

**Anchor.** `scripts/draft-board/Build.gs:186-192`:

```
row[B.ifg] = '=($I{r}/POOL_AVG_FGA)*($J{r}-POOL_FG_PCT)';
row[B.zfg] = '=$U{r}/SD_FG_IMPACT';
```

with `SD_FG_IMPACT = STDEV(FILTER(B_IFG, B_POOL=1))` (`Build.gs:635`). The playbook
specifies the same thing (playbook:186-189: `z_FG% = impact / STDEV(impact across pool)`)
and attributes "the percentage-impact formula" to Rosenof (playbook:735).

**What is wrong.** Rosenof's Table 5(b) defines the percentage denominator's σ_R as the
"Standard deviation of μ_R(q) across Q" — the spread of players' **success rates**, with
the formula `Σ(μ_R(q) − μ_R)² / |Q|`. That is not the SD of the volume-weighted impact
column. The two differ by a per-category constant: under independence of volume and rate
deviation, `SD(impact) ≈ σ_R · √(1 + CV²)` where CV is the coefficient of variation of
the attempt column. At CV = 0.40 that factor is 1.08; at CV = 0.65 it is 1.19. Because
free-throw attempts are far more dispersed across a player pool than field-goal attempts
are, the factor is materially larger for FT% than for FG% — you can read both CVs off
your own Settings tab in a minute.

The consequence is that the board's `z FG%` and `z FT%` are each a fixed fraction of
Rosenof's, so the two percentage categories carry *less* than their intended weight
relative to the seven counting categories, and FT% carries less than FG%. Then the
`MULT_FG = 0.75` and `MULT_FT = 0.77` multipliers, which were derived from the ratio of
**rate-based** variances in Table 8, are applied on top of an impact-based
standardisation. That composition is only clean if the volume weighting inflates σ and τ
by the same factor — plausible, since a player's attempt volume is fairly stable
week to week, but not established.

I could not settle which denominator is correct. Rosenof's own description of the
*conventional* Z-score procedure says to take the volume-weighted quantity and then
"subtract out the mean and divide by the standard deviation", which points at
SD(impact); Table 5(b)'s definition of σ_R points at the rate. My own derivation favours
SD(impact): if a team's category outcome is the mean of its members' impacts, the SD of
the team outcome is `SD(impact)/√N`, so dividing the player's impact by `SD(impact)` puts
the percentage categories on the same "share of a team standard deviation" footing that
`(μ_M(q) − μ_M)/σ_M` gives the counting categories. That is my reasoning, not a source.

**Failure scenario.** Invent "Terrell Osei", a high-usage guard taking 7 free throws a
game at 90%, and "Marcus Delaine" again, a centre taking 6 at 52%. If the board
under-weights FT% by ~19% relative to the intended metric, Osei loses and Delaine gains
roughly 0.19 × |z_FT| G-points each. For a z_FT near ±2.5 that is about 0.48 of a
G-point — enough to move a player several places in the dense middle of the board, and
enough to make the standard board understate how much a punt-FT% build actually buys you.
The direction is consistent: **bad-FT bigs sit a little too high on the standard board,
and elite-FT guards a little too low.**

**Verdict.** PLAUSIBLE, not confirmed. What would settle it: read Section 3 of arXiv
2307.02188 in full and determine whether the percentage G-score's denominator is
intended as the rate SD or as the SD of the volume-weighted contribution, and whether
there is a `|Q|` or `N` factor absorbed elsewhere. Whichever way it resolves, the
practical action is the same and is cheap: compute both `SD(impact)` and `STDEV(rate)`
on the Settings tab, print their ratio for FG% and FT%, and decide with the two numbers
in front of you.

**Fix.** Add two rows to the Settings POOL CONSTANTS block —
`=STDEV(FILTER(B_FGP, B_POOL=1))` and the FT equivalent — and a ratio cell. Then either
leave the board alone with the ratio documented, or switch `SD_FG_IMPACT` /
`SD_FT_IMPACT` to the rate SDs. Do not change it without the numbers.

**Needs an ADR?** Yes if you change the denominator. The ADR should also record which
reading of the paper you adopted and why, because the playbook currently attributes a
formula to Rosenof that does not match his Table 5(b), and that attribution should be
corrected either way.

**Sources.** [Rosenof, *Static quantification of player value for fantasy
basketball*](https://arxiv.org/abs/2307.02188), Tables 5(b) and 8 ·
[arXiv HTML v5](https://arxiv.org/html/2307.02188v5)

---

#### F8. The `MIN_GP` pool gate is undeclared, makes the pool smaller than Q, and breaks the maintenance doc's own check

**Anchor.** `scripts/draft-board/Build.gs:184`:

```
row[B.inPool] = '=IF(AND($A{r}<=Q, $F{r}>=MIN_GP), 1, 0)'
```

with `MIN_GP = 25` (`Build.gs:608`). Column `$F` is **projected** GP, not historical GP
(`REFRESH_MAP` maps `B.gp ← PLAYERS[5]`, `Build.gs:238`, which `gen_data.py:62` fills
from the export's GP column).

**What is wrong.** Three things.

*It is undeclared.* The playbook defines the pool as "the top 156 by value" and nothing
else (playbook:150-155). `ADR-0008` lists four deliberate deviations; this is not among
them. It is a change to what "average" means for every number on the board, which is
exactly the class of decision ADR-0008 exists to record.

*It desynchronises the pool from Q.* Every mean, SD and aggregate rate is now computed
over `COUNTIF(B_POOL,1)` players, which is **at most** Q and generally fewer, while
`REPLACEMENT = LARGE(B_GTOT, Q)` still uses Q = 156 (`Build.gs:640`). So the statistics
that define the value scale and the point that defines zero on that scale are drawn from
two different sets. The gap is small in practice — a projection source rarely projects
anyone below 25 games — but "small" is not "zero", and nothing on the sheet surfaces the
discrepancy.

*It makes the maintenance doc's check wrong.* `build-and-maintenance.md:102` instructs:
"Check the sanity block on Settings: the per-game gate, the GP spread test, **pool count
156**, Z-total ≈ 0, and ADP coverage." Under `MIN_GP`, a pool count below 156 is the
*correct* result, not a fault. An operator following the doc will either raise a false
alarm or, worse, learn to ignore that check.

*Directional bias.* The gate excludes low-projected-GP players from the mean and SD
computation. Those players skew toward the bottom of the value curve, so removing them
raises the pool means slightly and shrinks the SDs slightly. The net effect is to make
every remaining player's z-scores marginally less extreme and to push replacement level
up. It does not bias against high-value injury risks the way one might fear — a star
projected for 55 games clears the gate comfortably — but it does mean the board's notion
of "average" is quietly conditioned on availability, which nothing documents.

**Failure scenario.** Not a mispriced player so much as a mispriced audit: the operator
runs a refresh, sees the pool count read 153 instead of 156, and either wastes ten
minutes on draft eve or dismisses the sanity block entirely. The second is the dangerous
outcome, because the same block carries the per-game/season-totals gate that
`build-and-maintenance.md:104` correctly identifies as a stop-the-line failure.

**Verdict.** CONFIRMED.

**Fix.** Pick one. Either (a) delete the gate — with 200 rows seeded from a provider
rank, the deep-bench contamination it guards against is already excluded by
`Seed Rank <= Q`; or (b) keep it, declare it in an ADR-0008 amendment, add a Settings row
`Pool shortfall = Q - COUNTIF(B_POOL,1)` that reads 0 in the normal case, and change
`build-and-maintenance.md:102` from "pool count 156" to "pool count 156 minus the
shortfall shown". Also decide whether `REPLACEMENT` should use `Q` or the live pool
count; I would keep `Q`, since replacement level is about how many players get drafted,
not about who votes on the mean.

**Needs an ADR?** Yes — it is a change to how the valuation pool is defined, whichever
way you go.

**Sources.** playbook:150-155 · `ADR-0008:60-77` · `build-and-maintenance.md:102`

---

#### F9. Below replacement level, Adjusted Value inverts: the board ranks the *less* available of two equal players higher

**Anchor.** `scripts/draft-board/Build.gs:214`:

```
row[B.adj] = '=IF($AV{r}="","", $AQ{r} * $AV{r} / GP_DIVISOR)'
```

`$AQ` is VOR. For rows below replacement, VOR is negative, and multiplying a negative
number by `GP/72 < 1` moves it *toward zero*, i.e. *up* the board. `boardOrder`
(`Build.gs:917-926`) sorts the Draft Board on this column descending.

**What is wrong.** This is the exact sign error the playbook records as already fixed —
"Adjusted Value originally scaled the raw G-score by the games-played ratio… scaling a
negative number by a fraction moved that player *up* the board. Now scales VOR instead,
**which is positive across the pool**" (playbook:772-775). The premise holds for the
pool. It does not hold for the board, which carries 200 rows while the pool is 156. Rows
157-200 have negative VOR by construction, and for all of them the GP adjustment runs
backwards.

The good news is that the damage is **bounded and does not leak upward**. The most a
sub-replacement player can be promoted to is Adjusted Value approaching 0 from below,
and any player with positive VOR has positive Adjusted Value, so no below-replacement
player can cross above an above-replacement one. The corruption is confined to the
ordering *within* rows ~157-200.

**Failure scenario.** Invent two fringe bigs with identical VOR of −0.35: "Ivo Karras"
projected for 74 games and "Deshawn Pike" projected for 41. Karras gets
−0.35 × 74/72 = −0.360; Pike gets −0.35 × 41/72 = −0.199. Pike sorts well above Karras.
On a board that carries 200 names in a league that drafts 156, that tail is your
late-round waiver reference and your churn-slot shortlist — and section 8a says
explicitly that the last two or three bench spots are where you spend picks on upside and
schedule. The board is ordering that region by *fragility, ascending*. Tiering breaks
down there too: `Drop` is computed off a scrambled order, and the `IF(N($J{r})<=0,"",…)`
guard on the break test (`Build.gs:970`) means tiers simply stop being cut wherever the
local median collapses.

**Verdict.** CONFIRMED. Arithmetic, reproducible with two numbers.

**Fix.** Floor the multiplier at 1 for negative VOR, so availability can only ever
discount and never reward:

```
=IF($AV{r}="","", $AQ{r} * IF($AQ{r}<0, 1, $AV{r}/GP_DIVISOR))
```

or, if you prefer symmetry, apply the discount to the magnitude:
`SIGN($AQ{r}) * ABS($AQ{r}) * $AV{r}/GP_DIVISOR` — but that penalises a bad player for
being available, which is also wrong. The floor is the right shape. Alternatively cut the
board to 156 rows, which removes the region entirely; I would not, because the extra 44
rows are genuinely useful in-season.

**Needs an ADR?** No. The playbook already states the intended behaviour; this closes a
gap between the stated rule and the implementation.

**Sources.** playbook:270-274, playbook:772-775

---

#### F10. Position does not exist anywhere in the model — no positional replacement, no scarcity count, no multi-eligibility bump

**Anchor.** `scripts/draft-board/Build.gs:51` (`pos: 4`), `:506` (written from the
export), `:955` (`row[D.pos] = ref(B.pos)`), `:802` and `:1083` (column widths). That is
the complete list. Position is displayed and never computed with. `REPLACEMENT` is
`LARGE(B_GTOT, Q)` — the 156th-best G-total **globally** (`Build.gs:640`).

**What is wrong.** The playbook asks for two things the sheet does not provide.
Section 6 says Yahoo position eligibility matters because "multi-position players are
worth a real bump in Yahoo's daily lineup format" (playbook:248) — there is no bump.
Section 8 step 3 is an entire in-draft decision rule built on counting how many players
at each position remain in your live tier (playbook:526-542) — there is nothing on the
Draft Board that counts anything by position, no filter, no per-position tier count.
`ADR-0008` does not declare either omission.

The literature genuinely splits here, which is why this is Medium and not High.
**For:** Rosenof addresses it directly in Section 4.1.3 — "Most leagues have position
requirements, which do not factor into the justification for G-scores" — and judges the
omission tolerable: "the omission is not enormously problematic because there are often
many flex spots, players are eligible for many positions, and value tends to be spread
out fairly evenly between positions anyway." The playbook's own section 11 argues the
same way, rejecting positional chunking on the grounds that "a rebound from your
90th-ranked player counts the same as a rebound from Jokic." **Against:** essentially
every practitioner writing about category leagues treats centre scarcity as real and
category-linked — RotoWire and Athlon/Yahoo both frame it as showing up specifically in
rebounds and blocks, "two categories that are very difficult to fix on the fly."
Basketball Monster ships a Positional Value column for exactly this.

My read: the *valuation* is fine without position — Rosenof's argument is sound and
positional z-scores are a known mistake. What is missing is the **tiebreak**, which the
playbook specifies and which is not a valuation change at all. Pricing centre scarcity
into the G-score would be wrong; failing to tell you that two centres remain in your live
tier while nine guards do is just an unbuilt feature.

**Failure scenario.** Pick 5.08, fifteen picks until your next turn. Your live tier holds
two centres and nine guards at indistinguishable Adjusted Value. The board offers no way
to see that. You take the guard — his Gap is a little greener — and come back at 6.05 to
find both centres gone and the next one a full tier down. You have spent a full tier of
value to gain nothing, and it shows up as a season-long rebounds-and-blocks deficit,
which is the hardest kind to stream your way out of. The playbook anticipated this
exactly and the sheet cannot execute it.

**Verdict.** CONFIRMED as a code-versus-playbook gap. The underlying strategy question is
genuinely contested; I am siding with implementing the tiebreak, not with positional
valuation.

**Fix.** Two columns on the Draft Board, both cheap and both live:

- `Left in tier @ pos` — `=COUNTIFS(tier range, this tier, pos range, "*"&"C"&"*", gone range, FALSE)`,
  using a wildcard so a `PF/C` counts toward both, which is what "count slots, not
  labels" (playbook:539) requires.
- A small block on the Category Tracker showing, for each of C / F / G, how many
  un-`Gone` players remain in the current live tier.

Neither touches the valuation. Note also that `schema.md`'s `mart_replacement_level`
plans **per-position** replacement — so Phase 2 is currently designed to diverge from
both the sheet and from Rosenof's advice. Resolve that in `schema.md` before it is built.

**Needs an ADR?** No for the tiebreak columns. **Yes** if you ever move to positional
replacement level, which would be a real change of method.

**Sources.** [Rosenof, *Static quantification*, §4.1.3](https://arxiv.org/abs/2307.02188)
· [RotoWire, *Mastering Positional Scarcity*](https://www.rotowire.com/basketball/article/fantasy-basketball-draft-strategy-mastering-positional-scarcity-for-2025-97045)
· [Athlon/Yahoo, *Fantasy Basketball Position Scarcity
2026-27*](https://sports.yahoo.com/articles/fantasy-basketball-position-scarcity-2026-005609909.html)
· [Basketball Monster, Questions
Answered](https://basketballmonster.com/questionsanswered.aspx) · playbook:248, 526-542

---

#### F11. The shipped punt builds substitute two single punts for a pairing the playbook lists, and the most commonly published build in the category world is absent entirely

**Anchor.** `scripts/draft-board/Build.gs:64-71`:

```
Punt FT%   drop: [gft]
Punt FG%   drop: [gfg]
Punt FG%+REB
Punt AST+STL
Punt PTS+FT%
Punt FG/FT/TO
```

The playbook's working pairings (playbook:614-620) are: FG% + REB, AST + STL,
**BLK + FG%**, PTS + FT%, and the FG%/FT%/TO triple.

**What is wrong.** Four of the five playbook pairings ship. `BLK + FG%` does not, and two
single punts appear in its place. `ADR-0008` declares four deviations; this substitution
is not one of them.

Shipping single punt FT% and single punt FG% is defensible on its own — they are the two
most common real builds, the playbook's own Giannis and Gobert examples are both
FT%-punt examples, and section 6b explicitly invites "the single punts you are most
likely to land in" (playbook:441). The problem is what is missing rather than what was
added. **Nothing on the board covers punt BLK, punt AST, or punt 3PM**, and those are
precisely the builds that published guides treat as staples: SportsEthos and Elite
Fantasy Basketball both run standing punt-blocks guides, and the guard-heavy build that
concedes REB/BLK/FG% to dominate PTS/AST/3PM/STL/FT% is one of the two canonical shapes
described in general 9-cat strategy writing. Punt-blocks is also, per RotoBaller, "one of
the easier builds to switch to after the first few rounds because there are not a lot of
early-round options that make a switch to the strategy inadvisable" — which makes it the
single most valuable build to have pre-computed, since it is the one you are most likely
to fall into rather than plan.

**Failure scenario.** Rounds 1-3 hand you three high-usage guards. Your live shape is a
punt-BLK build and the board has no column for it. You are now reading the standard board
for the rest of the draft while executing a build it does not model, which is exactly the
state playbook section 6b says makes punting "a philosophy rather than a method". You
will systematically overpay for the shot-blocking bigs the standard column still likes,
and you will miss the guards whose value is inflated inside your actual build.

**Verdict.** CONFIRMED as an undeclared divergence from the playbook.

**Fix.** `PUNTS` is a data structure; adding builds is three lines each and costs six
columns of board width per build. Add `Punt BLK` (`drop: ['gblk']`), `Punt AST`
(`drop: ['gast']`), and either restore `Punt BLK+FG%` or record in ADR-0008 why the
single punts replaced it. Six builds is the playbook's own target (playbook:441, "Build
four to six of these"), so if width is the constraint, drop `Punt PTS+FT%` — punting
points is the rarest of the shipped builds — rather than leaving blocks uncovered.

**Needs an ADR?** Yes — an ADR-0008 amendment recording which builds ship and why, since
the current set diverges from the playbook without a record.

**Sources.** [SportsEthos, *Fantasy Basketball Draft Guide 2026: Punt
Strategy*](https://sportsethos.com/top-posts/fantasy-basketball-draft-guide-2026-punt-strategy/)
· [RotoBaller, *Fantasy Basketball Punting Guide
2025-2026*](https://www.rotoballer.com/fantasy-basketball-punting-guide-strategies-values-sleepers-2025-2026/1712272)
· [Elite Fantasy Basketball, punt-blocks
guides](https://elitefantasybasketball.com/25-26-punt-blocks-guides-free/) ·
[RotoWire, *9-Cat Fantasy Basketball Winning Strategy
Guide*](https://www.rotowire.com/basketball/article/master-9-cat-fantasy-basketball-strategies-for-a-winning-season-96454)
· playbook:614-620

---

#### F12. ADP is the export provider's, not Yahoo's; a fifth of the board carries none; and the Punts tab silently deletes those players

**Anchor.** `scripts/draft-board/gen_data.py:56` (`adp = c[2]` — the export's own ADP
column), `Build.gs:242` (`[B.adp, 4]`), `Build.gs:1431` (the README tab's own admission:
"Hashtag's, not confirmed Yahoo"), and `Build.gs:1196-1198` — the Punts tab's array
formula wraps every build in
`FILTER(…, Board!$AZ$3:$AZ$202 <> "")`.

**What is wrong.** The playbook is unusually emphatic on this point: "**ADP is market
timing, not value.** It is also platform-specific. Yahoo ADP favors safe established
names, Fantrax pushes younger breakouts earlier, ESPN lags on adjustments. **Use Yahoo
ADP only, because that is the room you are drafting in**" (playbook:106). The board uses
neither Yahoo's nor ESPN's. `ADR-0008` records this honestly under "Known limitation",
which is to its credit — but recording a known error is not the same as costing it, and
the cost compounds in three places.

*Gap.* `Gap = ADP − Adj Rank` is the column the playbook calls "where you make your
money" (playbook:558). Every value in it is measured against a room you are not sitting
in.

*Every Punt Gap.* Same error, six more times.

*The Punts tab drops the ADP-less.* The README tab reports that a meaningful minority of
the 200 rows have no ADP, and the Board handles that correctly — blank Gap, never zero,
"a zero would read as 'fairly priced', which is a different claim entirely"
(`Build.gs:1430`). Good. But the Punts tab's `FILTER` removes those rows from all six
build lists entirely. A player with no ADP is, almost by definition, a player the market
has not priced — a late-breaking role change, a returning injury, a rookie whose
situation just changed. Those are exactly the names a punt build most wants to find
cheap, and the Punts tab is structurally incapable of showing them. The comment says
"Rows without ADP are excluded: there is no market read to compare against", which is
true of the GAP column and not true of the player.

**Failure scenario.** The board says a mid-round wing is a target with Gap +22. In the
provider's ADP he goes at 62; in your Yahoo room, where ADP skews toward established
names, he goes at 44. You pass at 4.03 planning to get him at 5.10, and he is gone. The
Gap column pointed you at a discount that does not exist in your league. Separately, the
sleeper with a fresh starting job and no ADP never appears on any of the six punt lists
you spent your prep time memorising.

**Verdict.** CONFIRMED. Both the provenance error and the filter behaviour are visible
in the code.

**Fix.** Two parts, and the first is nearly free.

1. **Get a better ADP.** `docs/api/data-providers.md:17` records ESPN as publishing ADP
   on 1,095 players, free, unauthenticated, uncapped — more than five times the board's
   200 rows. It is not Yahoo's, but ESPN's is a large public draft room and is strictly
   closer to one than a ranking site's aggregate. Yahoo's own ADP is not exposed in the
   comparison table (the Yahoo ADP cell reads "—"), so if you want Yahoo's specifically,
   the path is the Yahoo OAuth integration that Phase 2 needs anyway — worth scoping now
   given the draft date. In the meantime, add an `ADP source` cell on Settings and print
   it on the Draft Board header, so the column is never read as Yahoo's by accident.
2. **Stop hiding the unpriced.** Change the Punts tab filter to keep every row and sort
   ADP-less players into a labelled block at the bottom of each build, sorted by punt
   rank. They have no Gap; they still have a build rank, and that is the thing the tab
   exists to surface.

**Needs an ADR?** No for the filter change. Yes if you add Yahoo OAuth ahead of Phase 2
purely to source ADP, since that is an integration decision.

**Sources.** playbook:106, 558 · `ADR-0008` "Known limitation" ·
`docs/api/data-providers.md:17`

---

#### F13. The tier local-median window is asymmetric while three documents call it "centred"

**Anchor.** `scripts/draft-board/Build.gs:966-968`, confirmed verbatim in the harness
output:

```
=MEDIAN(INDEX($I$3:$I$202, MAX(1, ROW()-11)) : INDEX($I$3:$I$202, MIN(200, ROW()+3)))
```

`INDEX(range, n)` resolves to sheet row `n + 2`, so at sheet row *r* the window spans
rows **r−9 to r+5** — fifteen rows, with the current row tenth of fifteen. A centred
window would be r−7 to r+7.

The playbook's own formula *is* centred: `=MEDIAN(OFFSET($D$2, ROW()-9, 0, 15, 1))`
resolves at row *r* to `D(r−7):D(r+7)` (playbook:472-476). Three places describe the
implementation as centred: `Build.gs:965` ("Fifteen drops centred here"),
`Build.gs:1405` and its generated copy `cheat-sheet.md:102` ("the fifteen drops centred
on this row").

**What is wrong.** The window is skewed nine rows up the board and five down. Because
value drops shrink monotonically as you descend — which is the entire reason the local
median exists (`cheat-sheet.md:102`: "a gap that is a canyon at pick 120 is completely
routine at pick 5") — a window weighted toward the rows above systematically returns a
**larger** median than a centred one. A larger median makes `Drop > TIER_MULT × median`
harder to satisfy, so breaks fire later and tiers run longer than the playbook's method
intends. The bias is consistent down the whole board, so it does not cancel.

This also gives a partial explanation for F14-adjacent behaviour: the shipped
`TIER_MULT = 4.0` is doing work that a centred window would have needed less of. Whether
2 would still produce an unusable number of tiers under a centred window is worth
checking before treating 4.0 as settled.

**Failure scenario.** A real cliff at pick 63 — say the last genuinely startable centre
before a run of interchangeable ones — is measured against a median that includes the
larger drops from picks 54-62. The break does not fire, the tier runs on, and the board
tells you that you can wait. You wait; the cliff was real; you take the pick-71 version
of the player. The failure is specifically at the *steepening* parts of the curve, which
is where tiers matter most.

**Verdict.** CONFIRMED. Index arithmetic, verified against the harness output.

**Fix.** One character each: `ROW()-11` → `ROW()-9` and `ROW()+3` → `ROW()+5`. Then
re-tune `TIER_MULT` from a centred baseline and see whether it still needs to be 4.0.
Alternatively, if the upward skew was deliberate — there is an argument for it, since the
"normal drop around here" you care about is the one you are about to pay, which is
above you — then say so in the comment and fix the three "centred" claims instead. What
is not acceptable is the current state, where the code and the docs disagree and neither
flags it.

**Needs an ADR?** No. Either resolution is a correction, not a decision — unless you keep
the asymmetry deliberately, in which case record it as a fifth deviation in ADR-0008.

**Sources.** playbook:472-476 · `cheat-sheet.md:102` · harness output

---

### LOW

---

#### F14. `ADR-0008`'s central verification claim is not reproducible

**Anchor.** `docs/decisions/ADR-0008-google-sheet-draft-board.md:47-50`: "The output was
verified against an independent Python implementation of the same playbook: all 200 rows
agree on Z and G totals, and all eight pool constants agree to four decimal places."

**What is wrong.** No such implementation exists in the repo. `find . -name "*.py"`
returns `gen_data.py` — a markdown-table parser with no valuation logic — and six empty
`__init__.py` files. The claim is the strongest evidence ADR-0008 offers that the board
is correct, and it cannot be re-run by anyone, including the author in six months. Under
this repo's own priority order ("data correctness first"), an unreproducible correctness
claim is worth close to nothing.

**Fix.** Either commit the verifier — it holds no provider data, it reads `Data.gs`
which is already gitignored, and it would fit comfortably in `scripts/draft-board/` next
to `harness.js` — or amend ADR-0008 to say the verification was performed once against a
throwaway script and is not reproducible. The first is better and is maybe an hour's
work; it also gives Phase 2 a reference implementation to test against, which addresses
part of F6 for free.

**Needs an ADR?** No — an amendment to ADR-0008, or a commit of the script.

---

#### F15. The harness pins formula strings as literals, so it cannot detect column-map drift

**Anchor.** `scripts/draft-board/harness.js:205-217`, e.g.

```js
expect('FG impact', cell('Board',3,21), '=($I3/POOL_AVG_FGA)*($J3-POOL_FG_PCT)');
```

against `Build.gs:187`, which emits `'$I'` and `'$J'` as hardcoded letters rather than
`a1col(B.fga)` and `a1col(B.fgp)`.

**What is wrong.** `build-and-maintenance.md:187` says the harness "checks that generated
formula strings land in the right cells", and it does — for the *destination*. It does
not check that `$I` still means FGA. If a column is inserted into the `B` map, every
hardcoded source letter in `writeBoardFormulas` silently shifts by one relative to the
data, and the assertion, being a string literal on both sides, still passes. Sheets would
compute happily. The board would be wrong and nothing would say so.

The harness does get two things right that are worth keeping: it derives the z and g
block boundaries from the indices (`if (L(zc[0]) !== 'W' || L(zc[8]) !== 'AE')`), and it
checks that each named range sits beside its expected Settings label. Extend that
approach to the source references.

**Fix.** Build the expectations from the map rather than from literals:

```js
const C = n => a1colFromBuild(n);   // Build.gs already exports a1col into scope
expect('FG impact', cell('Board',3,B.ifg),
       `=($${C(B.fga)}3/POOL_AVG_FGA)*($${C(B.fgp)}3-POOL_FG_PCT)`);
```

Better still, change `writeBoardFormulas` itself to use `a1col(B.fga)` instead of `'$I'`
throughout, which removes the failure mode rather than testing for it. That is a
mechanical edit to about thirty string concatenations and would be worth doing while the
board is quiet, not on draft eve.

**Needs an ADR?** No.

---

#### F16. `README.md` and `roadmap.md` both say nothing is built, while the board is in use

**Anchor.** `README.md:7` ("**Status: Phase 0 — project setup.** Documentation and
structure only; nothing is built yet."), `docs/roadmap.md:3` ("Current position:
**Phase 0 complete.** Nothing is built."), against `docs/roadmap.md:57` ("**Shipped in
the interim:** a Google Sheet draft board…") in the same file, and `CLAUDE.md`, which
gets it right ("One exception: the **2026-27 draft board** is built and in use").

**Fix.** One sentence in each. `README.md`: "Phase 0, plus one shipped exception — the
2026-27 draft board." `roadmap.md:3`: same. Also add the draft board's two docs to the
`README.md` "Where things are" table entry so the shipped artefact is discoverable from
the top of the repo.

**Needs an ADR?** No.

---

#### F17. Hashtag Basketball is the actual data source of the only shipped artefact and appears nowhere in `docs/api/data-providers.md`

**Anchor.** `docs/api/data-providers.md` — the comparison table covers ESPN, Sleeper,
Yahoo and FantasyPros. The provider actually feeding the live board is named only in
`ADR-0008` and in `gen_data.py`'s docstring. `README.md`'s canonical data statement reads
"No FantasyPros or Yahoo data… is committed" — which is true but enumerates the wrong
providers, since the data the repo is actually careful not to publish is Hashtag's.

**Fix.** Add a short "Hashtag Basketball — manual export, interim" row and paragraph to
`data-providers.md` recording what it supplies (per-game projections with makes and
attempts, its own ADP, its own rank used as the pool seed), that it is a manual markdown
export rather than an API, and that it is interim per ADR-0008. Generalise the
`README.md` sentence to "no provider data", which is what `ADR-0006` and
`check-no-data.sh` actually enforce.

**Needs an ADR?** No — documenting a source already chosen in ADR-0008.

---

#### F18. MPG is parsed, refreshed, stored, formatted and displayed, and enters no formula

**Anchor.** `gen_data.py:63` parses it, `Build.gs:238` (`[B.mpg, 6]`) refreshes it,
`Build.gs:794` formats it. No formula in `writeBoardFormulas` references column `$G`.

**What is wrong.** Nothing, arithmetically — it is a display column and does no harm.
But it is the strongest single predictor of category production, and it is sitting there
unused while the board has no other check on whether a projection's stat line is
consistent with the role it implies. Practitioner writing consistently lists minutes
alongside games played as the volume signal to draft for.

**Fix.** Cheapest useful version: a conditional format or a flag column that fires when a
player's `PTS + REB + AST` per minute sits far outside the pool's normal range — a
projection-sanity check, not a valuation input. Do **not** fold minutes into the
valuation; per-game projections already embed it, and multiplying by it would
double-count exactly the way section 6a warns about for games played.

**Needs an ADR?** No, for a flag column. Yes, if minutes ever enters the valuation.

**Sources.** [Athlon Sports, *Overrated vs Underrated Fantasy Basketball
Stats*](https://athlonsports.com/fantasy/overrated-underrated-fantasy-basketball-stats-guide)
· [ESPN, *Best draft tips for fantasy
managers*](https://africa.espn.com/fantasy/basketball/story/_/id/38697861/fantasy-basketball-best-draft-tips-fantasy-managers)

---

### NOTES

---

#### N1. "Do not switch builds after round 7" has no source and published guidance leans the other way

**Anchor.** playbook:466. Section 12E does not list this among the author's own
contributions, which implies it was sourced; I could not find a source for it, and it is
not implemented in code, so nothing on the board enforces it.

Published punt guides say close to the opposite. RotoBaller frames punting as "a strategy
that works very nicely as a mid-draft pivot, since the early rounds don't always go your
way", and specifically identifies punt blocks as "one of the easier builds to switch to
after the first few rounds". The nearest thing to agreement is the warning that
"drifting mid-draft leads to mediocrity across too many categories" — which is an
argument against having *no* build, not against changing one.

The underlying instinct is right — by round 8 your first seven picks are sunk cost and a
switch wastes them. The specific round number is arbitrary. Either soften it to "the
later you switch, the more of your earlier capital you waste; by the last third of the
draft, finish what you have", or move it into section 12E where the author's own
inventions are listed. Given F11, the more useful response is to make sure the build you
might pivot *into* actually has a column.

**Sources.** [RotoBaller punting
guide](https://www.rotoballer.com/fantasy-basketball-punting-guide-strategies-values-sleepers-2025-2026/1712272)
· [SportsEthos punt
strategy](https://sportsethos.com/top-posts/fantasy-basketball-draft-guide-2026-punt-strategy/)

---

#### N2. The playbook's advice to "soften the GP discount" for deep benches would double-count, because the linear form already assumes replacement-level backfill

**Anchor.** playbook:388-393: "A straight linear GP discount assumes you are stuck with
the hole in your lineup. Deep bench, free waiver moves: soften the discount."

This is worth writing down because it is the one place the playbook under-sells its own
formula. Work out what `Adjusted Value = VOR × GP/72` actually computes. If a player
gives you `g_p − g_r` of value over replacement on each of `GP_p` games, and on the
remaining `72 − GP_p` games you stream a replacement-level player who by definition
contributes `g_r − g_r = 0` of value over replacement, then your expected season value
over a fully replacement-level team is:

```
GP_p·(g_p − g_r)/72  +  (72 − GP_p)·0  =  VOR × GP_p / 72
```

which is the board's formula exactly. So the linear form is not a crude approximation
that over-penalises the fragile — **it is the exact expected value under the assumption
that you replace an injured player at replacement level**, which is precisely the
mitigation Rosenof names as missing from his own model: "real fantasy basketball managers
can ameliorate injury risk by swapping in un-injured players. This mitigates the risk of
players prone to injuries, and makes them more value than their expected performances
would indicate." The board already does this; the paper does not.

Softening the discount on top would therefore double-count the mitigation. The one
legitimate refinement is that in a deep league your bench replacement is *above*
replacement level, which makes the correct discount slightly *larger*, not smaller —
the opposite of the playbook's advice.

I would edit playbook:388-393 to say this, and note it in the cheat sheet's ADJUSTED
VALUE row, which currently explains the formula's sign logic well but does not explain
why linear is the right shape. This is the strongest single piece of reasoning in the
board and it is currently undocumented.

**Sources.** [Rosenof, *Dynamic quantification*](https://arxiv.org/abs/2409.09884) ·
playbook:388-393 · derivation above is mine

---

#### N3. The G-multipliers are frozen 2022-23 estimates and the two percentage rows rest on one significant figure

I verified all nine multipliers against Table 8 of arXiv 2307.02188, computed from the
2022-23 season over a pool defined as "the top 156 players by base Z-score". Every one
reproduces:

| Category | Paper G/Z | ÷ 0.75 (AST) | Settings tab |
|---|---|---|---|
| AST | 75% | 1.000 | 1.00 |
| 3PM | 72% | 0.960 | 0.96 |
| REB | 69% | 0.920 | 0.92 |
| BLK | 68% | 0.907 | 0.91 |
| PTS | 65% | 0.867 | 0.87 |
| TO | 62% | 0.827 | 0.83 |
| FT% | 58% | 0.773 | 0.77 |
| FG% | 56% | 0.747 | 0.75 |
| STL | 44% | 0.587 | 0.59 |

Two observations, neither a defect.

*Normalising to AST = 1.00 is free.* It rescales all nine G-scores by the same 1/0.75,
which is a uniform multiplicative constant. VOR subtracts a constant *after* the scaling,
and Adjusted Value divides by another constant, so every rank on the board is identical
to what the un-normalised multipliers would produce. No action needed; worth knowing so
nobody "fixes" it.

*The percentage rows are less precise than two decimals suggest.* Table 8 reports FG%
σ² as 0.003 and τ² as 0.007 — one significant figure each. Propagating the plausible
rounding band (σ² anywhere in 0.0025-0.0035) puts the normalised FG% multiplier anywhere
from about 0.68 to 0.77. The shipped 0.75 is inside that band, but the second decimal is
not meaningful. The playbook already says this in general terms — "The ordering is
reliable and steals being the biggest discount is robust. The second decimal place is
not" (playbook:214) — and it is specifically true of FG% and FT%, less so of the counting
categories whose variances are reported to four significant figures.

*On the vintage.* Freezing 2022-23 estimates is defensible. τ is a property of
week-to-week NBA variance, which moves slowly, and the paper's own caveat is about
within-season distribution changes rather than year-to-year drift. Re-deriving them
requires weekly game logs for 156 players — which `fact_player_game` in `schema.md` is
designed to hold, and which ESPN supplies per ADR-0007. That makes re-deriving the
multipliers a natural Phase 4 deliverable, not a draft-day concern. Until then, put the
season and the source in a comment cell next to the multiplier block on Settings, so the
vintage is visible to whoever next wonders whether to change one.

**Sources.** [Rosenof, *Static quantification*, Table
8](https://arxiv.org/abs/2307.02188) · [arXiv HTML v5](https://arxiv.org/html/2307.02188v5)

---

## What is sound

Specific things I traced and confirmed correct. Do not touch these.

**The G-score multipliers.** All nine reproduce Rosenof's Table 8 exactly under
normalisation to AST = 1.00 (table in N3). The normalisation itself is rank-preserving.
The headline claim — steals discounted to roughly half — is the paper's, not folklore.

**The missing mean-centring of the impact columns is provably harmless, and it is harmless
*because of* a choice the sheet gets right.** The impact term is
`(a_q/μ_A)(R_q − μ_R)` with `μ_R = Σ FGM / Σ FGA` over the same in-pool set
(`Build.gs:632-633`). Summing over the pool:

```
Σ (a_q/μ_A)(R_q − μ_R) = (1/μ_A)[Σ a_q R_q − μ_R Σ a_q]
                       = (1/μ_A)[Σ FGM − (Σ FGM/Σ FGA)·Σ FGA]
                       = 0
```

The mean of the impact column over the pool is **identically zero**, not approximately
zero, so `impact / SD(impact)` is already a proper z-score. This holds *only* because the
aggregate attempt-weighted rate was used. Had the sheet used `AVERAGE(FG%)` — the trap
the cheat sheet correctly warns about at line 68 — the mean would be non-zero and the
omission would matter. The one residual is that it depends on the export's FG% equalling
FGM/FGA to full precision; if the provider rounds them independently the residual is
non-zero but negligible. This is the best-reasoned piece of arithmetic on the sheet.

**Aggregate rather than average pool percentages.** `SUM(FILTER(B_FGM,…)) /
SUM(FILTER(B_FGA,…))`, correctly, in both the pool constants and the Category Tracker's
team rows (`Build.gs:1236-1237`). The playbook, `schema.md`, `league.yaml`'s
`volume_weighted: true`, and `AGENTS.md`'s boundary list all agree and all four are
implemented.

**Turnovers invert, once, in the right place.** `=(MEAN_TO - $T{r})/SD_TO`, and the
Category Tracker's Edge row flips sign for TO alone (`Build.gs:1252-1254`). No
double-inversion anywhere.

**`STDEV` versus population SD does not matter here.** The sample-SD correction
`√(n/(n−1))` uses the same `n` for all nine categories, so it is a uniform scaling and
rank-preserving. Not worth changing.

**Adjusted Value scales VOR, not the G-score**, and the divisor 72 is genuinely cosmetic
— dividing every row by the same constant cannot reorder anything. Both facts are stated
in the playbook and both are true of the code. And, per N2, the linear shape is not a
crude approximation but the exact expected-season-VOR under replacement-level backfill.

**Gap runs in the direction that makes its sign useful.** `= ADP − Adj Rank`, positive
means the room rates him lower than you do. The playbook records this as a
post-review correction and the code implements the corrected version.

**Blank ADP is blank, not zero.** `=IF($AZ{r}="","",…)` on both Gap and Adjusted Value.
The reasoning in the README tab — "a zero would read as 'fairly priced', which is a
different claim entirely" — is exactly right. (The Punts tab handles the same case badly;
see F12. The Board does not.)

**The per-game versus season-totals guard.** `=IF(AVERAGEIF(B_POOL,1,B_PTS)>100,
"SEASON TOTALS — the GP adjustment would double-count. Stop.", …)`. Section 6a names this
as the error that "corrupts the entire board", and it is the only failure mode on the
sheet with a hard stop attached. Good.

**The formula-versus-value trick that protects GP overrides.** `refreshWithReorder`
reads `getFormulas()` alongside `getValues()` and treats a `My GP Est` cell as an
override only when it no longer holds its `=$F{r}` seeding formula
(`Build.gs:354-360`). An untouched cell re-seeds from the new projection, which is
correct; a typed one survives. No bookkeeping column, no state to get out of sync. This
is a genuinely elegant solution to the hardest part of the refresh path.

**Hand-column preservation across a roster reorder.** Captured by player name, restored
by player name, blank for new arrivals, with added/dropped names written to
`Settings!A44`/`A45` so the operator can see what moved. `HAND_COLS` covers all six
yellow columns.

**The minimal-diff refresh.** `refreshInPlace` groups differing rows into contiguous runs
and issues one write per run, touching nothing else. This directly serves the repo's
stated third priority and makes frequent refreshes free, which is the behaviour you want.

**Data hygiene.** `data/**` and `scripts/draft-board/Data.gs` are both gitignored;
`git ls-files scripts/draft-board/` returns only `Build.gs`, `README.md`,
`export_readme.js`, `gen_data.py`, `harness.js`. The harness synthesises its own
deterministic 200-player pool so it runs on a clean clone, and I confirmed it does — it
ran and passed with no `Data.gs` present. `Build.gs` contains no player data.

**`gen_data.py`'s integrity assertions.** Contiguous ranks, no duplicate names, no
unparsed rows, and it raises rather than skipping. "A silently dropped player is a wrong
board" is the right instinct and it is enforced, not just written down.

**The generated cheat sheet.** `export_readme.js` regenerating `cheat-sheet.md` from
`README_ROWS` means the plain-English documentation cannot drift from the sheet's own
README tab. It is a real structural advantage and it worked as advertised — the three
"centred" claims in F13 are wrong *consistently*, in code and docs together, which made
the divergence easy to find rather than easy to miss.

---

## Structural gaps

What the board does not model at all, and whether it matters before the draft or only
after it.

**Games per week, off-nights, and streaming.** The board optimises *season* games played.
Head-to-head is won on games in a specific week. A player on a team with four games in
week 12 is worth more that week than one with two, and the schedule is knowable in
advance — ESPN publishes it (`data-providers.md:35`, `proTeamSchedules_wl`). Rosenof
names this as a limitation of his own model: "players don't always have the same number
of games each week, leading to changes in expected weekly performances." **Matters at
draft time, but only in the last three rounds**, where the playbook already says to use
it as a tiebreaker (playbook:596) — and where the board offers no column to do so. A
single "games in fantasy playoff weeks" column, hand-filled for the last forty rows,
would close it. Everything else about streaming is an in-season problem.

**Category correlation.** The nine z-scores are summed as though independent. They are
not: blocks travel with rebounds, assists travel with turnovers, points travel with field
goal attempts. The playbook is honest about this in its own simulation caveat
("Categories are modelled as independent, which they are not… Read the ordering, not the
decimals", playbook:625) but nothing downstream acts on it. The practical consequence is
that a roster can double-count a strength it believes it is diversifying: taking a second
elite shot-blocker adds less marginal win probability in BLK than the G-score implies,
because you were already winning it, while adding correlated turnovers. **Matters at
draft time, from round 4 onward**, and it is the gap that a working Category Tracker
would paper over most cheaply — which is why F3 and F4 matter more than their individual
severities suggest.

**Win probability per category against a specific opponent.** The tracker measures a
margin over a pool average. Head-to-head is won against one named team per week, and the
decision-relevant quantity is P(win this category), which peaks in marginal value at the
coin flip — the whole basis of the playbook's section 10. A margin over the pool mean is
a monotone proxy for that probability but not a calibrated one, and it cannot tell you
where on the curve you are. **Matters at draft time**; the honest fix is to express the
Edge in SDs of the team-level distribution rather than in raw units, which is the same
change F3 needs.

**Consensus dispersion.** One projection source, no spread, no best/worst, no
`rank_std_dev`. `ADR-0007` already names this as a known negative of the ESPN choice, and
`schema.md`'s `fact_consensus_ranking` is designed for it. For a draft board the cost is
that you cannot distinguish "everyone agrees he is the 40th best player" from "opinions
range from 22nd to 71st" — and the second is a materially different pick, especially in
the middle rounds where a role change has not yet resolved. The playbook's own advice to
"pull from more than one and compare" (playbook:64) is not implemented. **Matters at
draft time**, and is the largest gap that cannot be closed cheaply.

**The punt build does not reach the Category Tracker.** Once you commit to punt FT%, the
tracker still reports FT% as a live category and will still (in principle) tell you to
spend a pick fixing it. There is no way to mark a category punted. **Matters at draft
time, from round 5.** A row of nine checkboxes above the tracker, greying out punted
rows and excluding them from the read, is an afternoon's work.

**Yahoo's daily-lineup structure and churn slots.** Section 8a argues that the last two
or three roster spots are churn slots whose marginal value is lower than the board says,
and that the number of them depends on `max_acquisitions_per_week` — which is `TODO`.
The board treats pick 13 exactly like pick 1. **Matters at draft time only in the last
two rounds**, and the right response is judgment rather than a formula, which is what
section 8a already says.

**No auction support.** `draft_type` is `TODO`. If the draft is an auction, the board's
ordinal Adj Rank, its Gap column, and the entire tier mechanic are the wrong shape and
you would need dollar values instead. Worth confirming alongside F1.

---

## Docs vs code divergences

| # | Claim | Where the claim is made | What the code does | Anchor | Declared in ADR-0008? |
|---|---|---|---|---|---|
| 1 | Scoring is Head-to-Head Categories | `config/league.yaml:8` | Settings hardcodes `Most Categories`, and it drives the Punts tab | `Build.gs:610`, `:1180` | No |
| 2 | Pool is "the top 156 by value" | playbook:150 | Also requires `Projected GP >= MIN_GP` (25) | `Build.gs:184`, `:608` | No |
| 3 | "Pool count 156" is a sanity check | `build-and-maintenance.md:102` | `MIN_GP` makes it legitimately ≤ 156 | `Build.gs:633` | No |
| 4 | Local median is "the fifteen drops centred on this row" | `Build.gs:965`, `:1405`, `cheat-sheet.md:102` | Window is r−9 to r+5, ten of fifteen | `Build.gs:966-968` | No |
| 5 | Playbook's centred window formula | playbook:472 | Code's is asymmetric | `Build.gs:966` | No |
| 6 | Working pairings include BLK + FG% | playbook:618 | Not shipped; two single punts shipped instead | `Build.gs:64-71` | No |
| 7 | "Soft-punt rather than hard-punt", punted weight ≈ 75% | playbook:641 | Punt columns drop the term entirely (0%) | `Build.gs:250-254` | No |
| 8 | Multi-position eligibility is "worth a real bump" | playbook:248 | Position is displayed and never computed with | `Build.gs:955` | No |
| 9 | Scarcity tiebreak: count parallel groups in your live tier | playbook:526-542 | No positional count anywhere on any tab | — | No |
| 10 | Benchmark "holds at any roster size" | `Build.gs:1204`, `cheat-sheet.md:127` | Pool-mean benchmark; only correct at 13 players | `Build.gs:1238-1246` | No |
| 11 | Tracker threshold is "8%" | `cheat-sheet.md:130` | 8% of a rate on two rows, 8% of a total on seven | `Build.gs:1258` | No |
| 12 | Adjusted Value scales VOR "which is positive across the pool" | playbook:774 | True for 156 rows; the board carries 200 | `Build.gs:214` | No |
| 13 | GP adjustment applies to the board | playbook:270-276 | Punt columns and Punt Gap omit it | `Build.gs:250-257`, `:1196` | No |
| 14 | Impact = `(fg_pct − league_fg_pct) × fga` | `schema.md`, `mart_player_zscores` | Sheet uses the FGA *ratio*; equivalent only under matching normalisation | `Build.gs:187` | n/a |
| 15 | Valuation is G-score | playbook §5, ADR-0008 | `schema.md` specifies Z-score only | `schema.md`, marts | n/a |
| 16 | ESPN is the primary source | `ADR-0007` | `schema.md` still headed FantasyPros throughout | `schema.md` | n/a |
| 17 | Verified against an independent Python implementation | `ADR-0008:47` | No such file in the repo | — | n/a |
| 18 | "Nothing is built" | `README.md:7`, `roadmap.md:3` | The board is built and in use | `roadmap.md:57`, `CLAUDE.md` | n/a |
| 19 | Yahoo ADP only | playbook:106 | Export provider's ADP | `gen_data.py:56` | **Yes** |
| 20 | Tier multiplier 2 | playbook:493 | Ships at 4.0 | `Build.gs:609` | **Yes** |
| 21 | Gap against My Rank (VOR-derived) | playbook:280 | Gap against Adj Rank | `Build.gs:220` | **Yes** |
| 22 | Tracker typed in after each pick | playbook:288 | Automated from checkboxes | `Build.gs:1210` | **Yes** |
| 23 | Pool iteration converges by recomputation | playbook:198 | Manual menu action, one iteration per run | `Build.gs:1507` | **Yes** |

Five of twenty-three are declared. The eighteen undeclared ones are the report.

---

## Prioritized recommendations

Ordered by draft-day impact per unit of work. Stop reading anywhere and you will have
done the valuable things.

**1. Fill in `config/league.yaml` and reconcile the scoring format. (F1)**
Fifteen minutes, no code. Confirm team count, roster slots, IL slots, transaction cap,
draft type and — above all — whether the league is Head-to-Head Categories or
Head-to-Head One Win. Set Settings `B4`, `B5`, `B10` from the answer. Everything below
assumes Q is right; nothing else on this list is worth doing until it is. If the answer
is Each Category, treat the whole punt tab as advisory and dial toward balance, per the
playbook's own instruction and the H-score result.

**2. GP-adjust the punt columns. (F2)**
One edit to a generated string, plus the `IF($AV{r}="","",…)` guard. It fixes six punt
columns, six Punt Gaps, the entire Punts tab ordering, and the "Best build" indicator in
one change — and it stops the board pointing you at fragile players as bargains.
Highest ratio of correctness gained to characters typed on this list.

**3. Fix the Category Tracker: rate thresholds and a draft-scaled benchmark. (F3, F4)**
Two formula edits on the tab you look at most. Until they are done the tracker is
actively misleading in rounds 3-10, which is where it is supposed to earn its keep.
Do F4 (`AVERAGE(FILTER(…, adj rank <= TEAMS*count))`) first — it is the larger error and
it needs one new named range.

**4. Add `PUNT_WEIGHT` and soft-punt the six builds. (F5)**
One Settings row, one string change, default 0.25. Setting it to 0 reproduces today's
board exactly, so it is risk-free to ship and tune. Aligns the sheet with both the
playbook and the research it cites.

**5. Add punt BLK and punt AST columns. (F11)**
Three lines each in the `PUNTS` array. Punt blocks is the build you are most likely to
fall into unintentionally and the one you currently cannot see.

**6. Floor the GP multiplier for negative VOR. (F9)**
One `IF`. Fixes the ordering of the bottom forty rows of the board, which is your
late-round and waiver reference.

**7. Add the positional scarcity count to the Draft Board. (F10)**
Two `COUNTIFS` columns with a wildcard position match. Implements the playbook's step 3,
which is currently a rule with no instrument.

**8. Fix the tier window and re-tune `TIER_MULT` from a centred baseline. (F13)**
Two characters, then re-check whether 4.0 is still the right number. Also settles whether
the ADR-0008 deviation on the multiplier was really about the data or partly about the
window.

**9. Resolve `MIN_GP`: declare it or delete it, and fix the maintenance doc's check. (F8)**
Either way, add the pool-shortfall cell so the sanity block stops producing a false
alarm on draft eve.

**10. Replace or at least label the ADP source, and stop the Punts tab hiding unpriced
players. (F12)**
ESPN's ADP is free, unauthenticated, and covers five times the board. Label the source on
the Draft Board header regardless.

**11. Add the two Settings rows that would settle the percentage denominator question.
(F7)**
`STDEV(FILTER(B_FGP, B_POOL=1))`, the FT equivalent, and the ratio to `SD_FG_IMPACT` /
`SD_FT_IMPACT`. Do not change the denominator until you have looked at the two numbers.
This is diagnostic work, not a fix, and it is cheap.

**12. Fix `schema.md` before Phase 2 starts. (F6)**
Add G-score, repoint the provider, pin the percentage normalisation. Nothing here is
urgent for the draft and everything here is permanent afterwards. Doing it while the
reasoning is fresh costs an hour; doing it after Phase 2 is built costs a migration.

**13. Housekeeping. (F14, F15, F16, F17, F18, N1, N2, N3)**
Commit or retract the Python verifier; derive the harness expectations from the column
map; fix the two "nothing is built" status lines; add Hashtag Basketball to
`data-providers.md`; annotate the multiplier block with its 2022-23 vintage; correct the
playbook's "soften the discount" advice and its Rosenof attribution for the percentage
formula. None of these change a number. All of them change whether the next person to
read this repo — including you in a year — can trust what it says.

---

## Sources

**Published research**

- Zach Rosenof, *Static quantification of player value for fantasy basketball* (also
  circulated as *Improving Algorithms for Fantasy Basketball*), arXiv:2307.02188 —
  https://arxiv.org/abs/2307.02188 · HTML: https://arxiv.org/html/2307.02188v5 ·
  used for: the G-score derivation, the κ = 2N/(2N−1) definition, Table 5(b)'s definition
  of σ_R, Table 8's nine-category empirical variances and G/Z ratios (2022-23 season,
  pool = top 156 by base Z-score), the Z-vs-G simulation win rates (0.4% / 0.5% and
  32.5% / 21.4%), the |Q| = 12 × 13 = 156 pool definition, and §4.1.3 on position
  requirements.
- Zach Rosenof, *Dynamic quantification of player value for fantasy basketball*,
  arXiv:2409.09884 — https://arxiv.org/abs/2409.09884 · HTML:
  https://arxiv.org/html/2409.09884v1 · used for: the H-score win rates (37.7% Most
  Categories, 21.8% Each Category, 8.3% baseline), the soft-punting finding and the
  ~75% punted-category weight, the statement that static ranking systems are inherently
  limited, the injury-replacement limitation, the games-per-week limitation, and the
  finding that punting is most effective in Most Categories.
- Zach Rosenof, *Optimizing for Rotisserie fantasy basketball*, arXiv:2501.00933 —
  https://arxiv.org/abs/2501.00933 · cited by the playbook for the head-to-head/roto
  distinction; not independently examined for this review.

**Platform documentation**

- Yahoo, *Head-to-Head scoring in Yahoo Fantasy* —
  https://help.yahoo.com/kb/SLN6447.html · Head-to-Head Categories, Head-to-Head One Win,
  and Head-to-Head Points as the three H2H formats.
- Basketball Monster, *Questions Answered* —
  https://basketballmonster.com/questionsanswered.aspx · Positional Value column;
  punt instructions exist but the calculation method is not published.
- Basketball Monster, *Welcome and FAQ* — https://basketballmonster.com/help.aspx ·
  LeagV / PuntV / Punt+ columns; punted categories are excluded from Values.

**Analysts and practitioner writing**

- RotoBaller, *Fantasy Basketball Punting Guide, Strategies, Values, Sleepers
  (2025-2026)* —
  https://www.rotoballer.com/fantasy-basketball-punting-guide-strategies-values-sleepers-2025-2026/1712272
  · punting as a mid-draft pivot; punt blocks as the easiest late switch; the warning
  against drifting.
- SportsEthos, *Fantasy Basketball Draft Guide 2026: Punt Strategy* —
  https://sportsethos.com/top-posts/fantasy-basketball-draft-guide-2026-punt-strategy/
- Elite Fantasy Basketball, punt-blocks build guides —
  https://elitefantasybasketball.com/25-26-punt-blocks-guides-free/
- RotoWire, *9-Cat Fantasy Basketball Winning Strategy Guide* —
  https://www.rotowire.com/basketball/article/master-9-cat-fantasy-basketball-strategies-for-a-winning-season-96454
  · the two canonical build shapes (punt AST/3PM/FT% versus punt REB/BLK/FG%).
- RotoWire, *Fantasy Basketball Draft Strategy: Mastering Positional Scarcity* —
  https://www.rotowire.com/basketball/article/fantasy-basketball-draft-strategy-mastering-positional-scarcity-for-2025-97045
- Athlon Sports / Yahoo Sports, *Fantasy Basketball Position Scarcity 2026-27* —
  https://sports.yahoo.com/articles/fantasy-basketball-position-scarcity-2026-005609909.html
  · centre scarcity showing up in rebounds and blocks specifically.
- Athlon Sports, *Overrated vs Underrated Fantasy Basketball Stats* —
  https://athlonsports.com/fantasy/overrated-underrated-fantasy-basketball-stats-guide
  · minutes, usage and assist-to-turnover as the signals behind production.
- RotoWire, *Fantasy Basketball Durability: Top 10 Iron Men* —
  https://www.rotowire.com/basketball/article/fantasy-basketball-iron-men-2025-availability-105630
  · availability as the most underrated draft input.
- CBS Sports, *Fantasy basketball's most reliable stars* —
  https://www.cbssports.com/fantasy/basketball/news/fantasy-basketball-ironmen-mikal-bridges-more/
- NBC Sports, *Numbers Game: Fantasy Stat Correlations* —
  https://www.nbcsports.com/fantasy/basketball/news/article-numbers-game-fantasy-stat-correlations
  · turnovers correlating positively with points and assists through usage.
- ESPN, *Best draft tips for fantasy managers* —
  https://africa.espn.com/fantasy/basketball/story/_/id/38697861/fantasy-basketball-best-draft-tips-fantasy-managers

**Could not source**

- The "do not switch builds after round 7" rule (playbook:466). No published source
  found; published guidance leans toward mid-draft flexibility. Labelled as the
  playbook's own judgment in N1.
- Hashtag Basketball's published punt methodology. Its introduction-to-punting article
  (cited in playbook §12B) returned HTTP 403 to automated fetch, so I could not verify
  the playbook's attributions to it — including the working-pairings list, the "value
  only exists at market price" framing, and the claim that its rankings tool
  re-standardises when a category is unticked. The last of those is directly relevant to
  F5 and F11 and is worth checking by hand.
- Whether re-standardising pool means and SDs within a punt build materially reorders a
  board. The playbook asserts the effect is small (playbook:454) and I found no published
  measurement either way. My own view is that the playbook is probably right for single
  punts and probably understates it for the triple punt, where dropping three of nine
  categories changes which players are in the pool at all — but that is judgment, not
  evidence, and it is testable directly on this sheet by re-pointing the `AVERAGEIF` and
  `STDEV` ranges once.

*My own arithmetic and reasoning, not sourced to anyone:* the proof that the impact
column's pool mean is identically zero; the derivation that `VOR × GP/72` is the exact
expected season VOR under replacement-level backfill; the `√(1 + CV²)` relationship
between `SD(impact)` and `σ_R`; the index arithmetic showing the tier window spans r−9 to
r+5; the observation that the sub-replacement sign inversion cannot promote a player
above rank 156; and every worked example, all of which use invented players.
