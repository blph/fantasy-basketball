# How Basketball Monster ranks players, and what DURANT actually does

What we could establish about Josh Lloyd's DURANT metric, where each claim comes from, and
what it means for [our board](fantasy-basketball-draft-playbook.md).

Written 2026-08-29. Most of Basketball Monster's writing is behind a full-season
membership, so the mechanism below was recovered from podcast transcripts and from the
column tooltips on their public pages. That is hard to re-obtain — record it rather than
re-derive it.

---

## The short version

DURANT applies a **Yeo-Johnson power transformation** to each category to pull it toward
normality, standardises the transformed values, applies **fixed category weights**, and
**drops or half-weights each player's own worst category**. It is **per game** and has no
availability term.

It is **not** a percentile or rank transform, despite what the acronym suggests. That
distinction matters: a rank transform maps every category onto an identical Gaussian and
destroys the spacing between players; a power transform pulls in the skew while preserving
it.

**The coefficients are deliberately unpublished.** Lloyd, 2 Sep 2023: *"at the moment the
formula for Durant is something that I'm working on and going through and I'm not going to
tell you exactly what it is."* Nobody has replicated it publicly.

---

## What the name means

**DURANT — "Dynamic Unbiased Rankings Applying Normalised Transformations."** Confirmed in
Lloyd's own voice on three separate occasions (2 Sep 2023, 22 Jul 2025, 22 Apr 2026). He
glosses it himself: *"dynamic, meaning it changes every day when new data comes in;
unbiased, and… there's not a subjective part of this."* He also concedes the obvious —
*"just manipulating words to make it sound like Durant."*

## The mechanism

> "we try and transform the stats to become normally distributed so then we can apply
> standardization. And **I use a method called the Yeo-Johnson transformation**… Which
> adjusts the stats to normalize them so that standard scores appear to make more sense.
> **So that the right tail is eliminated**… Also, **Durant is a per game metric**."
> — Lloyd, 22 Apr 2026

The full component list, in his words (22 Jul 2025): a Yeo-Johnson transformation, plus
**category weighting**, the **availability of stats off waiver wires**, the **correlation
between numbers**, and a **minus-one component**.

Only the first and the last are documented well enough to reimplement. No public source
describes how waiver availability or inter-category correlation are quantified.

### The problem it targets

Lloyd's complaint is that z-scores assign impossible probabilities to routine events
(22 Jul 2025): a steals z of 4.94 is a 1-in-3.3-million event under a Normal, Wembanyama's
blocks z of 5.84 is 1 in a billion, and Giannis at a −6.07 FT% z is 1 in 10 billion —
*"Yet we see those numbers all the time and it leads to skewing of rankings."*

The premise is real. On our own pool, blocks skew **+1.53** with excess kurtosis **+3.31**,
and a zero-block player sits at z = −1.41 where a Normal says 7.95% of the pool should be
below him and **0%** is. FT% impact skews the other way, **−1.40** with kurtosis **+6.31**.

### The minus-one — a per-player automatic punt

Verbatim from the column tooltips on Basketball Monster's public Player Rankings and Trade
Analysis pages:

| Column | Worst-category handling |
|---|---|
| **DURANT**, league set to Roto | lowest category kept at **½ weight** |
| **DURANT**, league set to H2H | lowest category **removed entirely** |
| **DURANT H2H** | **turnovers removed**, then the **next-lowest also removed** |

This predates DURANT — BBM has long carried a separate "Minus 1 Value — the value with the
player's worst category removed", and Lloyd endorsed the idea before building DURANT:
*"taking away a player's worst category, which for head-to-head rankings I think is a
really good way of doing it."*

Sources that appear to contradict each other on this are usually quoting one row of the
table without the others.

---

## What DURANT does *not* do

**It does not fix FT%.** This is worth stating plainly because the opposite circulates:

> "I want to talk free throw percentage… I'm going to be honest with you, **Durant doesn't
> necessarily fix this problem**. I don't think it — actually it reduces some of the impact
> of free throw percentage but I don't think it fixes this problem and **I actually haven't
> found a way to do it yet**."
> — Lloyd, 2 Sep 2023

There are two separate FT% problems in his account. The first is the reversed skew — nearly
everyone shoots well, so the outliers sit at the bottom, which is what produces a −6 z for
one bad shooter. Yeo-Johnson addresses that one.

The second he presents as a new finding, and it is unsolved:

> "if you have a zed score of two in the points category and someone has a z score of 1.95,
> the person who gives you a z score of two… will outscore that player every single time.
> **With percentages it doesn't work that way**… **if your overall team's free throw
> percentage is higher than average, the player that you add onto that team, their
> percentage is more important than their volume. I did not expect to find this.**"
> — Lloyd, 2 Sep 2023

Percentage value is not additive across a roster: whether a high-FT% player helps depends
on your existing team's attempt volume. An 80% shooter on four attempts and an 80% shooter
on ten both score zero, and they are not the same player. His stated workaround is to
hand-downweight FT%, not to model it.

**It has no availability term.**

> "Playing more games is better, but there's the concept of **replacement level** that has
> to be factored into that. **And that's not accounted for with any of this.**"
> — Lloyd, 22 Apr 2026

He chooses per-game deliberately: totals *"[don't] tell you if they missed 20 in November
or 20 in March and February in your fantasy playoffs… it also ignores the fact that when
somebody's hurt you can just drop them and add somebody else in."*

**Its weights are fixed and ignore yours.** Per BBM's admin: *"DURANT weights are fixed so
yours won't affect them."* User punt settings and category weights do not propagate into
DURANT. Only the standard nine categories are supported.

---

## How this compares to our board

| | DURANT | Our board |
|---|---|---|
| Distribution handling | Yeo-Johnson per category, then standardise | Plain z against the rostered pool |
| Category weighting | Fixed, unpublished | Rosenof Table 8 G-multipliers (3PM 0.96, STL 0.59, BLK 0.91) |
| Punting | **Automatic**, per player — worst category dropped or half-weighted | **Explicit**, nine fixed builds with a soft `PUNT_WEIGHT` |
| Games played | None — per game only | `VOR × GP / 72`, the replacement-backfill model |
| Correlation between categories | Claimed, undescribed | Not modelled (a known open gap) |
| Percentages | Volume-weighted; the roster-additivity problem acknowledged and unsolved | Volume-weighted impact, per [ADR-0012](../decisions/ADR-0012-tier-multiplier-and-percentage-denominator.md) |

Two of these are worth dwelling on.

**The punting philosophies are opposites.** DURANT decides for you which category each
player concedes; our board makes you choose a build and then values every player against
it. DURANT's approach flatters specialists automatically. Ours makes the punt a decision
you have to own, which is the point of the Punts tab.

**We do something DURANT does not.** Lloyd states outright that replacement level is not
accounted for. Our `Adjusted Value` is Basketball Monster's own recommended
total-value-with-added-replacement-games model, which their flagship H2H metric declines to
use.

### Their standard Value, reverse-engineered

Basketball Monster's free rankings page publishes the nine per-category z-scores
(`pV 3V rV aV sV bV fg%V ft%V toV`) alongside a `Value` column. **`Value` is their
arithmetic mean of the nine**, verified on multiple players to the displayed precision. Our
`G TOTAL` sums. A uniform ÷9 changes no ranking, but it means their per-category columns
sit on the same footing as our `z` block and can be compared directly.

---

## The case against adopting it

Recorded so that a future reader does not have to re-run the argument.

Lloyd normalises the **marginal** distribution — how one player's blocks are distributed
across the league. But a category is won by a **13-man team total**, and the central limit
theorem flattens skew long before it reaches a win probability. Simulated on our own pool,
blocks go from an individual skew of **+1.53** to a team-total skew of **+0.38**, with
excess kurtosis falling from +3.31 to +0.11. Team totals are near-normal even when players
are not.

This is not a contrarian reading. Rosenof cites Lloyd by name for the non-normality premise
in the H-scoring paper — and **still declines to transform**, resting on exactly this CLT
argument, which is also why his G-score treats team category totals as Normal.

There is also a cost. A transform that pulls in the right tail necessarily compresses the
gap between the best and second-best in a category, and in a category league you win blocks
with blocks, not with rank order. Rank-based transforms make this catastrophic — every
category leader lands on the same ceiling regardless of dominance — and Yeo-Johnson is
gentler, but it is the same trade.

A defensible alternative exists that does not require any distributional assumption:
saturate value by win probability rather than by normality, since the marginal value of
extra edge in an already-won category really does fall off. That is a decision for its own
ADR, not something to smuggle in here.

---

## Reproduction targets

Lloyd has published enough named rank movements to *score* a reproduction rather than
merely assert one.

**Set A — 2 Sep 2023, straight 9-cat rank → DURANT rank.** The cleanest target: both sides
are per-game, so the transform is the only thing moving.

- Up: Nurkić 101 → 52 · Şengün 103 → 71 · Zion 73 → 38 · Banchero 120 → 67 ·
  Scoot Henderson 155 → 95 · Beal 76 → 37 · Draymond Green 102 → 75
- Down: Walker Kessler 34 → 80 · Brunson 35 → 66 · Trey Murphy 68 → 107 ·
  Tyus Jones 65 → 103 · Chris Paul 60 → 85 · Jaren Jackson Jr. 13 → 27

**Set D — 2025, the oddities DURANT is marketed as fixing:** Trae Young in the 30s, Okongwu
above Giannis, Amen Thompson in the top seven.

**Set C — 19 Aug 2026, DURANT vs Yahoo's rank:** Jalen Johnson 15 (Yahoo 10) · Donovan
Mitchell 8 (11) · Chet Holmgren 47 (19) · Kon Knueppel 66 (37).

**Set B is weaker and should not be used as a primary target.** Lloyd's 2025-26 comparison
runs DURANT *per-game* against 9-cat *totals*, so the per-game switch confounds the
transform.

---

## Sources

### Primary — Lloyd's own words

- **2 Sep 2023**, Locked On Fantasy Basketball, *"Assessing the Good, Bad, and Ugly of
  Fantasy Basketball Rankings"* / *"Are We Ranking Players the Right Way In Fantasy
  Basketball? A Deep Dive"* — https://www.youtube.com/watch?v=aOT2csO579A — the origin
  episode. Acronym, the FT% findings, Set A, and the refusal to publish the formula.
- **22 Jul 2025** — https://www.youtube.com/watch?v=KHGF0EU_9ZM — the component list and
  the impossible-probability argument.
- **22 Apr 2026** — https://www.youtube.com/watch?v=ss2gHYRgiWs — names Yeo-Johnson, "per
  game metric", and the replacement-level omission.
- **16 Mar 2025**, @redrock_bball — https://x.com/redrock_bball/status/1901159454013575655
  — "DURANT H2H per game rankings" (comparison is in an image; not recoverable).
- **Article 1831**, *Welcome*, 15 Aug 2022 —
  https://basketballmonster.com/article.aspx?article=1831 — the only article still public.
  His pre-DURANT manual method: punt turnovers, weight threes/steals/blocks to 0.8. Also
  the replacement-player button, and *"predicting injuries is impossible. It cannot be
  done. The correlation year over year for games played ranges from low to non-existent."*

Transcripts are YouTube auto-captions (the `timedtext` endpoint returns empty; recovered
via a third-party extractor). Proper nouns are mangled — "Yo Johnson", "Zed scores" — but
the acronym and the numbers read cleanly and recur across episodes.

### Primary — Basketball Monster itself

- Column tooltips on https://basketballmonster.com/PlayerRankings.aspx and
  https://basketballmonster.com/TradeAnalysis.aspx — the DURANT and DURANT H2H definitions
  quoted above. Public HTML, no login.
- Forum topic 24603 — https://basketballmonster.com/MessageTopic.aspx?topic=24603 —
  admin confirming DURANT is per-game, that its weights are built in, and that it will
  become selectable "instead of the standard z-score Value".
- Forum topic 23394 — the BAZEMORE description.
- Article 2185 (via the Wayback Machine, 14 Aug 2025) — *"Use DURANT (or DURANT H2H) for
  category leagues… DURANT adjusts for scarcity and variance and relaxes strict z-score
  assumptions—NBA stats aren't normally distributed."*

### Secondary

- Rosenof, [2307.02188](https://arxiv.org/abs/2307.02188) (G-score) and
  [2409.09884](https://arxiv.org/abs/2409.09884) (H-scoring). The latter **cites Lloyd's
  2023 podcast** for the heavy-tailed-blocks premise — independent confirmation of when the
  argument was first made — and declines to act on it.
- https://georgeberry.substack.com/p/pseudo-z-scores-for-basketball-counting (Sep 2023) —
  written in response to the same podcast; an exponential-CDF transform for blocks only.
  Both code links are dead.

### Not found

The formula. The per-category Yeo-Johnson lambdas. The category weight values. How waiver
availability and inter-category correlation are quantified. What BAZEMORE stands for, or
its math beyond a 0.7–1.5 rebuilding/contending slider. What specifically changed in
"DURANT 2.0". Any third-party replication, on GitHub or elsewhere.

---

## Corrections to claims that circulate

- **"DURANT fixes the FT% problem."** False, and Lloyd says so directly. Show notes say the
  episode *highlights* FT%'s peculiarities; that has been paraphrased into *fixes*.
- **"DURANT 2.0 is a new method."** The article dated 27 Aug 2026 carries the **same ID
  (1957)** as the original DURANT article. It is a redated in-place edit, not a new
  release. No podcast or video covers a 2.0. The only public signal of change is BBM's note
  that DURANT can now be set as the default value, and that more categories are supported.
- **"DURANT is a percentile/rank transform."** The acronym implies it; Lloyd names
  Yeo-Johnson, which is a parametric power transform.
- **Specific z-score figures attributed to Lloyd vary by season and by retelling.** His own
  Giannis FT% figures range from −4.5 to −6.07 across episodes. Treat any single quoted
  number as illustrative.

---

## If we ever want certainty

DURANT's per-category outputs are exposed as `DpV`, `D3V`, `DaV` and so on, and **members
can export them to CSV**. One month of membership would convert everything above from a
structural reconstruction into a fitted, checkable one — enough to solve for the withheld
weights directly.
