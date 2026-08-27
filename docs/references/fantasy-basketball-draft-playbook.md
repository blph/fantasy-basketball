# 9-Cat H2H Draft Playbook

Yahoo head-to-head, nine categories. Built from expert guidance and the published research on category-league valuation.

---

## Table of contents

1. [Open questions to settle first](#1-open-questions-to-settle-first)
2. [How to weight your inputs](#2-how-to-weight-your-inputs)
3. [Projections vs last season's actuals](#3-projections-vs-last-seasons-actuals)
4. [Z-score: the math](#4-z-score-the-math)
5. [G-score: the math](#5-g-score-the-math)
6. [The spreadsheet](#6-the-spreadsheet)
6a. [Estimating games played](#6a-estimating-games-played)
6b. [Punt re-ranking](#6b-punt-re-ranking)
7. [Pre-draft prep](#7-pre-draft-prep)
7a. [How to build tiers](#7a-how-to-build-tiers)
8. [In-draft decision rule](#8-in-draft-decision-rule)
8a. [Roster construction and streaming](#8a-roster-construction-and-streaming)
9. [Round-by-round plan](#9-round-by-round-plan)
10. [Punting, done correctly](#10-punting-done-correctly)
11. [Ideas tested and rejected](#11-ideas-tested-and-rejected)
12. [References and provenance](#12-references-and-provenance)

---

## 1. Open questions to settle first

Four league settings change the math. Confirm all four before building anything.

| Setting | Why it matters |
|---|---|
| Number of teams | Sets the player pool size |
| Roster size | Sets the player pool size |
| Roster slot structure (how many G, F, C, Util, bench) | Drives the scarcity tiebreak in section 8 and how much multi-position eligibility is worth |
| Most Categories or Each Category | Changes how aggressively to punt |
| Transaction limits and lineup frequency | Determines how many bench spots are real draft assets versus churn slots |
| Your draft slot | Determines which tiers survive to your picks, and whether an early lopsided star is available to you |

Pool size formula: `teams x roster spots`. A 12-team league with 13 roster spots gives a pool of 156. Every mean and standard deviation in this document is computed across that pool and nobody else.

The scoring format matters most. Punting is far more effective in Most Categories, because once you have won five of nine, a sixth win adds nothing. In Each Category every category counts every week, so abandoning three of them is expensive. If you are in Each Category, dial everything below back toward balance.

---

## 2. How to weight your inputs

### Where to get the projections

The board is only as good as its inputs, and the document leans on them for 50 to 60% of the answer.

| Source | Notes |
|---|---|
| **Hashtag Basketball** | Free tier lets you set your league's scoring and outputs z-scores directly, with a punt tool that unticks categories and re-ranks. The fastest way to sanity-check your own sheet. Paid tier adds a draft tracker |
| **Basketball Monster** | Paid. The long-standing reference for category leagues. Also publishes DURANT rankings, which apply scarcity and variance adjustments and relax the normality assumption |
| **RotoWire, FantasyPros** | Projections plus written context on role and injury risk |

Pull from more than one and compare. Where two sources disagree by a lot on a player's minutes, that player belongs on your homework list.

### The weighting

| Input | Weight | What it is for |
|---|---|---|
| Projections converted to league settings | 50-60% | The board |
| Games-played / durability adjustment | 15-20% | The most under-priced variable in fantasy |
| Roster fit / marginal category need | 15% | Changes at every pick |
| Yahoo ADP | 5-10% | Timing only |
| Yahoo XRank | ~5% | Reading the room |
| Last season's 9-cat finish | 0% direct | Feeds the projection, never the board |

### What each input actually is

**Yahoo "Rank"** is Yahoo's own board. They project each player's stats, squash his performance across all your categories into one number, and sort by it. "Total projected categories" in Yahoo's own help text means summed across categories, not season totals.

Two things follow. First, Rank is calculated for *your* league. Drop blocks from your settings and shot-blockers fall. Play 8-cat instead of 9-cat and turnover-prone players rise. Second, it ignores position entirely, so a center and a point guard with the same projected value get the same number. There is no scarcity bump. Yahoo puts positional context in a separate "Pos Rank" column, which requires Fantasy Plus.

**Yahoo "Expert Rank" (XRank)** is the average of Yahoo analysts and RotoWire, and it drives autopick order. Unlike Rank, XRank uses Yahoo's *default* scoring settings, not yours.

Neither is a value model you can audit. Yahoo does not publish how it aggregates categories, what pool it used, or whether any variance adjustment is applied. Your own board is auditable, which is the whole reason to build one. Use Rank and XRank to see what the room is looking at, not to decide who to take.

**ADP is market timing, not value.** It is also platform-specific. Yahoo ADP favors safe established names, Fantrax pushes younger breakouts earlier, ESPN lags on adjustments. Use Yahoo ADP only, because that is the room you are drafting in.

### The games-played gap

The difference between per-game value and total value is enormous, and the market prices it badly. In one recent season, only 2 of the top 20 players by per-game value reached 70 games, while 10 of the top 20 by total value did. Anthony Davis finished 6th per-game and 43rd in total value on 51 games. Kyrie Irving finished 18th per-game and 68th in total.

Keep games played in its own column. Never fold it into the projection, because you want to see the raw talent and the availability discount separately.

### Turnovers

Turnovers are the whole differentiator in 9-cat versus 8-cat. Rookies and rookie ball-handlers are turnover-prone. Catch-and-shoot specialists and non-passing bigs gain the most.

Do not punt turnovers *on their own*. Good players handle the ball, and streaming adds turnovers you cannot control. As a solo punt it is a bad trade.

Turnovers inside the FG%/FT%/TO triple punt are a different case, and section 10 lists that build for a reason. Those three are the categories where accumulating stats can hurt you. Drop all three together and you are free to chase counting stats without penalty, which is a coherent build rather than a lone concession.

Outside that build, treat turnovers as a tiebreaker.

---

## 3. Projections vs last season's actuals

**Projections drive the pick. Actuals audit the projection.**

Projections are the only input that knows about trades, free agency, coaching changes, and depth charts. Last season's finish knows none of that.

**Where actuals earn their keep:** as a sanity check. Pull three-year trends for points, rebounds, assists, and minutes to separate a real leap from an unsustainable one.

**Where actuals beat projections outright: games played.** Many projection systems hedge toward the mean on availability, applying a generic haircut instead of modeling the individual. Games-played history is honest. See [section 6a](#6a-estimating-games-played) for how to handle this in practice.

**Where actuals mislead:**

- Career years and small samples
- Percentage stats, which bounce year to year
- Anyone with an offseason role change
- Rookies and sophomores

RotoWire's framing is useful: projections are the raw statistical outlook, rankings add context like injury risk and positional scarcity. Use both in tandem.

---

## 4. Z-score: the math

A z-score puts every category on a common scale so you can add them up.

### Step 1: Define the pool (Q)

Not the whole NBA. The number of players who will actually get drafted. Twelve managers picking thirteen players gives 156.

Every mean and standard deviation below is computed across those 156 only. Using all 500 NBA players inflates everyone's score and distorts the shape of the distribution. This is the most common mistake.

### Step 2: Counting stats (PTS, REB, AST, STL, BLK, 3PM)

```
z = (player's per-game stat - pool mean) / pool standard deviation
```

Sheets formula:

```
=(B2 - AVERAGE(B$2:B$157)) / STDEV(B$2:B$157)
```

### Step 3: Turnovers

Same formula, numerator flipped, because fewer is better.

```
z_TO = (pool mean - player's TO) / pool standard deviation
```

### Step 4: Percentages

You cannot z-score FG% directly. A player shooting 65% on 4 attempts barely moves your team. A player shooting 65% on 18 attempts moves it a lot. Weight the rate by volume:

```
impact  = (player FGA / pool average FGA) x (player FG% - pool FG%)
z_FG%   = impact / STDEV(impact across pool)
```

Use aggregate pool FG% (total makes divided by total attempts), not the average of everyone's percentage. Repeat for FT% using FTA. Using the aggregate is what makes the impact column sum to exactly zero across the pool, which is why dividing by its standard deviation gives a proper z-score with no mean to subtract.

**An open question on that denominator.** Rosenof's Table 5(b) defines its sigma over the spread of players' raw success *rates*, not over the volume-weighted impact column this document divides by. The two differ by a per-category constant, and the difference is larger for FT% than FG% because free-throw attempts are more dispersed. Which he intends is unresolved, so the Settings tab prints both and their ratio and the board changes nothing until someone reads them. Do not attribute this exact formula to him; section 12E now carries it.

### Step 5: Sum all nine

That total is the player's z-score.

### The circularity fix

Your pool is "the top 156 by value," but you need values to know who those are. Iterate. Rank by a rough list, take the top 156, compute z-scores, re-take the top 156, recompute. Two or three passes and the set stops changing.

---

## 5. G-score: the math

### The concept

Z-score asks: how much better than average is this player in this category?

G-score asks: how much does that edge actually help me win the category in a given week?

Those differ because some categories are wildly noisy week to week. A player averaging 2.0 steals against a pool average of 0.8 looks like a huge edge on paper, but steals bounce around so much that the randomness often swamps the advantage. A player averaging 9 assists gives you roughly 9 assists most weeks, and that edge shows up on the scoreboard.

**An advantage in a stable category is worth more than the same-sized advantage in a volatile category.** Z-score treats them as equal. G-score discounts each category by how noisy it is.

### The formulas

Numerators are identical to z-score. Only the denominator changes.

```
Counting:    (player mean - pool mean) / sqrt(sigma^2 + kappa * tau^2)
Percentage:  [(FGA_p/avg FGA) x (FG%_p - pool FG%)] / sqrt(sigma_R^2 + kappa * tau_R^2)
```

- **sigma** is what z-score already uses: the spread of season averages across the pool (player-to-player variance).
- **tau** is new: each player's week-to-week standard deviation, root-mean-squared across the pool (period-to-period variance).
- **kappa** = 2N/(2N-1). For 12 or 13 players per team it lands between 1.040 and 1.043, so set it to 1.04 or drop it.

Z-score is the special case where tau equals zero.

### The practical shortcut

Computing tau requires weekly game logs for 156 players, which is a real project. Rosenof published the empirical result from 2022-23, so you can apply it as a per-category multiplier instead. Normalized to assists:

| Category | Multiplier |
|---|---|
| AST | 1.00 |
| 3PM | 0.96 |
| REB | 0.92 |
| BLK | 0.91 |
| PTS | 0.87 |
| TO | 0.83 |
| FT% | 0.77 |
| FG% | 0.75 |
| **STL** | **0.59** |

Multiply each category z-score by its factor, then sum. One extra column approximates a G-score.

**Headline effect: steals get cut roughly in half.** Steals specialists drop. Stable production rises.

Treat these as approximations. They come from a single season (2022-23), and the underlying variance ratios shift with the pool, the season, and league size. The ordering is reliable and steals being the biggest discount is robust. The second decimal place is not.

### Does it work

In simulated 12-team, 13-player head-to-head seasons:

| Matchup | Most Categories | Each Category |
|---|---|---|
| Lone Z-score drafter vs field of G-score | 0.4% | 0.5% |
| Lone G-score drafter vs field of Z-score | 32.5% | 21.4% |

Baseline is 8.33%. The setup is synthetic and assumption-heavy, but the direction is clear enough to act on.

### Caveat

This reasoning is built for head-to-head, where each week is a fresh coin flip. In roto, weekly noise averages out across a season and the gap between the two metrics narrows a lot.

---

## 6. The spreadsheet

One row per player, top 200. Columns in this order.

### Identity

- Player
- NBA team
- Yahoo position eligibility (multi-position players are worth a real bump in Yahoo's daily lineup format)

### Raw projection

- Projected MPG
- Projected PTS, REB, AST, 3PM, STL, BLK, FG%, FT%, TO
- Projected FGA and FTA (needed for the percentage impact formulas)

### Value

- Z-score total, computed on league settings and correct pool size
- G-score approximation (z-score with the multipliers above applied per category)
- **VOR** = `G-score - G-score of the last player in your pool`
- **My Rank**, derived from VOR

Why VOR and not the raw G-score: G-scores are centered on the pool mean, so roughly half your list is negative, and the availability formula below breaks on negative numbers. Subtracting the replacement-level player's score makes every player in the pool positive. It is also the more honest question. What you care about is value above the player you could take instead.

### Availability

Keep this separate. Never fold it into the projection.

- Projected GP (from your projection source)
- GP last season
- GP two seasons ago
- GP three seasons ago
- **My GP estimate** (starts as a copy of Projected GP, then hand-edited)
- Flag: `=IF(ABS(Projected_GP - My_GP_estimate) > 10, "CHECK", "")`
- **Adjusted Value** = `VOR x (My GP estimate / 72)`

Do not apply the GP ratio to the raw G-score. A negative score multiplied by a fraction moves toward zero, which moves that player *up* your board. A bad player who misses half the season would rank above the same player healthy. Scale VOR, not G-score.

See [section 6a](#6a-estimating-games-played) for how to fill in My GP estimate.

### Market

- Yahoo ADP
- Yahoo XRank
- **Gap** = `Yahoo ADP - My Rank`

Ranks are ordinal, so lower is better, and the subtraction has to run in this direction for the sign to mean anything useful. A player you rank 20th who goes 45th in ADP gives `45 - 20 = +25`. Positive means the room likes him less than you do, which is a target. Negative means the room likes him more than you do, which is someone to let go.

### Build fit

- **Punt value columns**, one per plausible build. See [section 6b](#6b-punt-re-ranking).
- **Punt Gap** per build: `Yahoo ADP - rank in that build`
- Notes: role change, injury history, age, contract year, whatever you actually believe

### Second tab: category tracker

Nine columns, one row per pick. Update after every pick so you can see at a glance where you are strong, average, and weak.

---

## 6a. Estimating games played

### The short version

**Use projected GP as your default. Hand-override the players you have an actual opinion about.**

Do not build a formula for all 200 rows. The GP column exists to catch the twenty or so players where the market is mispricing availability, and for those you need judgment, not arithmetic. Everyone else takes the projection as-is.

Practically: copy the projected GP column into your GP estimate column, then edit fifteen to thirty cells. Sort ascending by projected GP and the players needing attention will be sitting at the top.

### Check this first: per-game or season totals?

If your projections are **season totals**, games played is already baked into every number, and multiplying by a GP ratio double-counts it. The GP adjustment applies only to **per-game** projections.

Confirm this before building the column. Getting it wrong corrupts the entire board.

### Then run the spread test

Look at the range of the projected GP column.

| What you see | What it means | What to do |
|---|---|---|
| Almost everyone between 68 and 74 | The source is applying a generic durability haircut. The column carries no player-level information. | Override heavily, or use the fallback method below |
| Range from the 40s to the high 70s with real separation | Availability is modeled per player | Lean on it. Override lightly |

Ten seconds of looking, and it tells you how much work the rest of this section is.

### Who to override, and why

Adjust a cell when you know something the projection does not, or when you can see it hedging.

**Add games back for:**

- A lost season caused by a single freak injury. A broken hand from a collision says nothing about next year.
- A player returning from a full missed season who is healthy now. History says 25 games. History is wrong.
- Anyone the projection has parked at the pool average despite a long clean record.

**Take games away for:**

- Recurring soft-tissue or joint problems. Chronic issues are the part of injury history that actually predicts.
- Age past about 32. Two or three games per year beyond that.
- Announced load management for an older star.
- Anyone projected above roughly 76. Even iron men miss games.

Two things the research supports here: season-long durability is more predictable than week-to-week risk, and the signal lives in prior injury *type* combined with age and workload rather than in raw absence counts. Guards carry the highest injury ratios by position.

One league-context note: the 65-game rule, in effect since 2023-24, ties award and All-NBA eligibility to playing 65 games. That gives stars a real incentive to suit up and has firmed up availability at the top of the board relative to the load-management era.

### Why keep the three history columns

They are your audit, not your input. Put projected GP next to the last three actual seasons. When they agree, move on. When they are ten or more games apart, that player goes on your homework list.

This is the mirror image of how you treat everything else. For points, rebounds, and assists, the projection builds the number and history audits it. For games played, history audits the projection. Availability is the one place where the past is more honest than the forecast.

### Fallback method

If your projection source fails the spread test, build the estimate yourself:

1. **Weighted three-year average of actual GP.** Most recent completed season x3, the one before x2, the one before that x1, divided by 6.
2. **Regress toward your pool baseline.** 70% of that weighted average plus 30% of the average GP across your 156-player pool. Compute the baseline from your own pool rather than using a fixed number, because it drifts year to year.
3. **Age adjustment.** Nothing until about 32, then subtract two or three games per year past that.
4. **Override by hand** using the same criteria above.

### Two things not worth worrying about

**The 72 in the Adjusted Value formula is cosmetic.** It is a constant applied to every player, so it cannot change anyone's rank. Use 82, use your pool average, use whatever makes the numbers readable. Only the ratios between players matter.

**Do not over-penalize injury-prone stars.** Rosenof flags this as a known gap in his own model: real managers swap in healthy players when someone goes down, which mitigates the risk and makes injury-prone players more valuable than their expected performance implies.

**The linear form already handles that, exactly.** This document used to advise softening the discount for a deep bench, which is wrong and would double-count the mitigation. Work out what `VOR x GP / 72` actually computes. A player gives you `g_p - g_r` of value over replacement on each of the `GP_p` games he plays. On the remaining `72 - GP_p` you stream someone at replacement level, who by definition contributes `g_r - g_r = 0`. So your expected season value is:

```
GP_p x (g_p - g_r) / 72  +  (72 - GP_p) x 0  =  VOR x GP_p / 72
```

which is the formula. It is not a crude approximation that over-punishes the fragile — it is the exact expected value *given* that you replace an injured player at replacement level, which is precisely the mitigation Rosenof names as missing from his own model. The board already does it; the paper does not.

The one legitimate refinement runs the other way. In a deep league your bench replacement is *above* replacement level, so the honest discount is slightly **larger**, not smaller. A hard cap on weekly pickups pushes the other way again, since you cannot always stream the hole shut.

**Availability must never promote a player.** Below replacement VOR is negative, and a negative times a fraction moves toward zero — up the board. Switch the scaling off there, or the last forty names end up sorted by fragility.

---

## 6b. Punt re-ranking

This is the mechanic that makes section 10 usable. Without it, punting is a philosophy rather than a method.

### The idea

When you commit to punting a category, you **recompute the board with that category removed**. Nine per-category scores become eight, and you re-sort. The reordering is dramatic, not marginal.

Giannis is roughly 25th on a standard 9-cat board. On a punt-FT% board he is 2nd. That is not a note in a comments column. That is a different board.

Everything in section 10 depends on having these numbers. "Value only exists at market price" is a comparison between a player's rank *inside your build* and his ADP. You cannot make that comparison without the build rank.

### Building it

Cheap, because you already have the per-category scores. A punt column is your existing sum with terms dropped.

If your nine per-category G-score columns sit in K through S:

```
Standard:      =SUM(K2:S2)
Punt FT%:      =SUM(K2:S2) - FT_column
Punt FG%+REB:  =SUM(K2:S2) - FG_column - REB_column
```

Build four to six of these, covering the pairings in section 10 plus the single punts you are most likely to land in. Then for each, a rank column and a Punt Gap column:

```
Punt Gap = Yahoo ADP - rank in that build
```

Sort each Punt Gap descending. The top of each list is the players that build gets at a discount.

### One thing you do not need to recompute

Pool means and standard deviations stay as they are. You are dropping terms from a sum, not redefining the player pool. Do not rebuild the z-scores.

A purist would note that a punt build should arguably use a pool of the players *other punt drafters* would take, which shifts the means. Ignore this. The effect is small and the complexity is not worth it.

### Do the homework before draft day

Mid-draft is too late to be reading a spreadsheet. Before the draft, cycle through each build and memorize the ten biggest risers. Mamone's guide recommends exactly this: untick category combinations, watch who moves, reset, repeat, until you know by feel which players belong to which build.

Hashtag Basketball's free rankings tool does this natively. Set your league's scoring, untick the punted categories, and it re-ranks. Use it to check your own columns.

### Using it during the draft

Your standard board is live until you commit. Once your first four or five picks have revealed a build (section 9), switch to that build's column as your primary sort and keep the standard column visible as a sanity check.

Two guardrails:

- **A build rank is not a licence to reach.** The point of a punt is buying players near their normal ADP whose value to you is higher, not paying build price for them.
- **The later you switch, the more of your earlier capital you waste.** By the last third of the draft your earlier picks are sunk cost, so finish the build that fits what you have. This used to read "do not switch builds after round 7"; the instinct is right but the round number is invented, and it is listed in section 12E as such. Published punt guides lean the other way, treating a mid-draft pivot as normal when the early rounds do not cooperate — punt blocks especially. The thing that actually loses drafts is having no build at all and drifting into mediocrity everywhere.

---

## 7. Pre-draft prep

1. **Sort by Adjusted Value and cut tiers.** See [section 7a](#7a-how-to-build-tiers) below for the method.

2. **Sort by Gap descending.** With `Gap = Yahoo ADP - My Rank`, positive means the room rates a player lower than you do. The top of that list is your target list. The bottom is players to let someone else take.

3. **Sanity-check the extremes.** Anyone 40 or more spots off ADP is either a real find or a broken projection. Go look at their last three seasons and decide which.

4. **Set your Yahoo pre-rank list from your board.** It protects you if you lose connection, and it makes your queue surface the right names at the right moment.

5. **Build your punt columns and learn the risers.** See section 6b. Four to six builds, and the ten biggest movers in each. This is the highest-value prep work after the board itself.

6. **Pull the fantasy playoff schedule.** Note which NBA teams play the most games in your league's playoff weeks. This becomes a tiebreaker in the late rounds.

7. **Mock draft two or three times from your actual slot.** The only way to learn which tiers survive to your picks.

---

## 7a. How to build tiers

### What a tier is

A tier is a group of players who are close enough in value that you would be fine with any of them. Between tiers there is a real drop.

That distinction is the only thing tiers are for. Inside a tier, you can wait. Between tiers, waiting costs you something real. Tiers turn your board from a list of 200 names into roughly a dozen decisions.

### Why you cannot just cut every twelve players

Value does not decline at a steady rate. The gap between the 1st and 2nd player on your board might be as large as the gap between the 60th and 80th. Cutting every twelve players draws lines in places where nothing happens and misses the cliffs that matter.

### The method

Sort by Adjusted Value, descending. Then add three columns.

**Column 1: Drop.** How much value you lose going from the player above to this one.

```
=Adjusted_Value_above - Adjusted_Value_this_row
```

**Column 2: Local median drop.** The typical drop among nearby players. This matters because drops shrink as you go down the board. At the top, a 0.40 drop is routine. At pick 120, a 0.40 drop is a canyon. A fixed threshold would give you five tiers at the top and one enormous blob at the bottom.

Take the median of the fifteen drops centered on the current row:

```
=MEDIAN(OFFSET($D$2,ROW()-9,0,15,1))
```

Adjust the column reference to wherever your Drop column lives.

Two practical notes. `OFFSET` is a volatile function and will recalculate constantly on a 200-row sheet, so swap in `INDEX` if it feels sluggish. And the window is truncated for the first several rows, which means the local median at the very top of the board comes from a partial sample. **Set tier one by hand.** The top of the board is a judgment call anyway and the formula adds nothing there.

**Column 3: Break flag.** Fire when a drop is much larger than what is normal around it.

```
=IF(Drop > 2 * Local_median_drop, "BREAK", "")
```

**Tier number.** A running count of breaks:

```
=IF(Break_flag="BREAK", Tier_above + 1, Tier_above)
```

### Tuning it

The multiplier of 2 is a starting point, not a law. Turn it up if you get too many tiers, down if you get too few.

Aim for **12 to 15 tiers across 200 players**. Sanity checks:

- Tier 1 will be small, sometimes 1 to 3 players. That is correct. The top of the board is genuinely spread out.
- Tiers get larger as you go down. A tier of 25 players at pick 140 is normal, because those players really are interchangeable.
- If any tier has more than about 35 players, split it by hand somewhere sensible.

### Override the formula

The formula finds gaps in your numbers. It does not know anything else. Move a line by hand when you have a reason: a player whose role is genuinely uncertain, a rookie you do not trust, a guy coming off a major injury. The formula gives you a first draft.

### Positional counting

You do not need separate tiers per position. Keep one global tier column and filter by position when you need to count. "How many centers are left in tier 5" is a filter, not a second board. That count is what feeds the scarcity rule below.

---

## 8. In-draft decision rule

At every pick, in this order:

**1. Identify your live tier.** Everyone in it is roughly interchangeable by value. This is your shortlist.

**2. Count the picks until your next turn.** Twelve-team snake at slot 5: from 3.05 your next pick is 4.08, so fifteen players come off the board in between. That number is the whole basis for the next step.

**3. Break ties on scarcity.** When two options in the tier are close in value, take the one from the group that will not survive until your next pick.

The comparison is between **parallel groups at similar value**, not between one tier and the tier below it. Positions, or sources of a category you need. For example:

> You need a center and a point guard. Your board says the best available at each is worth about the same. Centers left in that tier: **2**. Point guards left in that tier: **9**. Fifteen picks until your next turn.
>
> Take the center. Both groups have someone you want right now. Only one of them will still have someone in fifteen picks. Take the point guard and you come back to a center cliff and reach a full tier down.

Two conditions on this rule:

- **Count live, not from your prep sheet.** A group with nine names in round 3 can have two by round 4.
- **Count slots, not labels.** "How many centers are left" means how many players can fill a roster slot you still need, which depends on your league's slot structure and on multi-position eligibility. A player listed PF/C counts toward both.
- **Only fires when value is close.** If the scarce player is a full tier worse, take the better player and accept the positional pain.

**4. Break remaining ties on category need.** Check your running totals and take the player who fixes your weakest live category.

**5. Break anything still tied on turnovers.** Free value nobody else is pricing.

**6. Check ADP before confirming.** If the player you want is going two rounds later on average, take the other name first and come back for him.

### What this is not

It is not "take the top name on the list." A static ranking list used that way cannot adapt, cannot punt, and can leave you with five players who are all strong in the same three categories. The list narrows your choice to a handful. Steps 3 through 6 make the choice.

In rounds 1 and 2 the top of the board usually is the right answer anyway. The overrides start earning their keep around round 3, once your roster has a shape.

### The rule that ties it together

Your board tells you **who** is good. ADP tells you **when** you can have him.

Never take a player at his board rank if his ADP says he will last two more rounds. Never let a top-tier player slide because his ADP says he "should" go later. The Gap column is where you make your money.

---

## 8a. Roster construction and streaming

Yahoo runs daily lineups. That changes what the back of your roster is for, and most draft guidance ignores it.

### Not every roster spot is a draft asset

Your last two or three bench spots are **churn slots**. You are not drafting a player to hold there for six months. You are drafting a placeholder you will drop in week two for whoever has four games and a hot role.

This means the marginal value of your final picks is lower than your board says, and you should spend them differently: on upside swings that might break out, or on players with immediate schedule advantages, rather than on the safest available veteran.

How many spots are churn depends on two settings from section 1. Free transactions and daily lineups means three or more. A weekly lineup lock or a cap on moves per week means one, or none.

### Streaming interacts with your punt choice

This is the connection most guides miss. If you punt both shooting percentages, streaming gets much easier, because a pickup cannot wreck your FG% or FT% for the week. You add whoever is playing tonight and take the counting stats.

That is a real argument for the FG%/FT%/TO triple punt beyond its draft-day appeal, and it is why that build shows up as a favourite among analysts who play in high-transaction leagues.

The reverse also holds. If you are competing in both percentages, every streamer is a risk, and you should plan on fewer churn slots and more held depth.

### What to do with this

- Decide how many churn slots you have **before** the draft, and subtract them from the number of players you are actually drafting.
- If you are leaning toward a percentage punt, you can afford more churn slots. Factor that into the build decision.
- In the last two rounds, stop optimizing for value and start optimizing for upside and schedule.

---

## 9. Round-by-round plan

| Rounds | What to do |
|---|---|
| 1-2 | Best available, adjusted for games played. Commit to nothing. |
| 3-6 | Your build reveals itself. Look at what your first four picks are collectively bad at and stop fighting it. |
| 7-10 | Deliberately fill your two weakest non-punted categories. This is where balanced teams get made. |
| 11+ | Upside swings, specialists, and one or two players with good schedules you can churn. |

**Rookies.** Let someone else take the risk. For every rookie who hits, several disappoint relative to cost, and 9-cat punishes them twice: they turn the ball over and they shoot inefficiently while learning. The exception is a rookie with a guaranteed large role on a bad team, and even then, wait a round past his ADP.

**Late-round tiebreaker.** When two players are close, take the one whose team plays more games in your fantasy playoff weeks. Head-to-head is won in specific weeks, and by round 11 the value difference between candidates is usually smaller than the schedule difference.

---

## 10. Punting, done correctly

### Timing

Do not pick a punt before the draft. Have paths after pick one and an idea before pick two. Avoid early double or triple punts.

Your first-round pick should still be a first-round-caliber player. Taking a specialist early to force a build wastes draft capital, even if that player has top-ten value inside the build.

### Value only exists at market price

Gobert projecting 28th in a punt-FT% build is worthless at the end of round two. He is real value at his round-five ADP. The point of punting is that some players' values are inflated inside your build, so you can take them near their normal ADP and get surplus. Reaching too far erases the surplus.

### The single punts

The four most commonly played, and the four worth having pre-computed: **FT%, FG%, AST, 3PM**. Add **BLK**, which is less popular but is the build you are most likely to fall into rather than plan — a guard-heavy start puts you there whether or not you meant it, and published guides describe it as the easiest build to pivot into mid-draft.

### Working pairings

- FG% + REB
- AST + STL
- PTS + FT%
- The triple punt: FG% / FT% / TO

**Not BLK + FG%.** An earlier version of this document listed that pairing. It is wrong, and the sheet was right not to ship it. Punt-blocks and punt-FG% are competing routes to the same small-ball roster, not complements — you pick one. And a punt-blocks build is specifically trying to *protect* FG%, because it is rostering guards and wings who do not get free rim points. Conceding both is not a pairing, it is the three-category "punt big-man stats" build (REB / BLK / FG%), which is a different and much harder thing.

Punt TO is not a build on its own either. It rides along with FG% and usage builds; nobody publishes a standalone punt-turnovers guide.

### Punting is subtraction, not addition

Punting a category does not mean avoiding players who help there. Elite rebounders are usually also top FG% players. You are not drafting bad free-throw shooters to lose FT%. You are ignoring FT% so that players with a weakness there become cheap.

Giannis is roughly 25th in per-game 9-cat and 2nd in a punt-FT% build. That is the shape of the effect.

### Do not over-invest in categories you already win

This is the counter-intuitive part, and it is the biggest correction to make.

Winning a category 60 to 30 pays exactly the same as winning it 46 to 45. Every point of margin past "win" is wasted capital.

Rosenof's H-scoring algorithm learned this on its own. It rarely invested enough in a category to nearly guarantee wins. When a category was already above average, it invested less and kept it slightly above 50%, then spent elsewhere.

**Simulation, fixed budget of draft capital, Most Categories scoring.** Categories are modelled as independent, which they are not: points and threes move together, field goal percentage and rebounds move together through position. Real correlation makes both stacking and punting somewhat easier than this model implies. Read the ordering, not the decimals.

| Strategy | Per-category win rates | Match win % |
|---|---|---|
| Balanced | 63 across the board | 79.4% |
| **Soft punt 2** | 73 x7, 27 x2 | **80.5%** |
| Stack 3 hard | 92, 92, 92, then 42 x6 | 72.5% |
| Stack 3 extreme | 96, 96, 96, then 34 x6 | 63.6% |

**Marginal value of the same sliver of capital:**

| Category currently at | Gain in match win probability |
|---|---|
| 5% win rate | +0.31 pts |
| 30% win rate | +0.97 pts |
| **50% win rate** | **+1.09 pts** |
| 85% win rate | +0.60 pts |
| 95% win rate | +0.26 pts |

Value peaks at the coin flip. Capital spent on a category you already dominate is nearly as wasted as capital spent on one you have abandoned.

### Targets

- Aim for roughly 60% in your live categories, not 90%.
- Soft-punt rather than hard-punt. Rosenof's dynamic algorithm did not zero a punted category: it "took a more subtle 'soft-punting' approach," with the punted tail "peaking around 75% or so" of the baseline weight, because a small chance of winning is never no chance. Read that as direction, not as a coefficient to copy — the 75% is a first-round figure from a weight vector constrained to sum to one, and the paper says explicitly that those weights forecast your own later picks rather than score the player in front of you. It also argues that a static list cannot execute punting properly at all. The board's Punt weight constant is our own tuning choice, informed by that finding rather than prescribed by it. See ADR-0009.
- Aim to win six or seven, not exactly five. Five leaves no margin for an injury or a cold week.

---

## 11. Ideas tested and rejected

### Chunking the pool into groups of 50 for z-scores

**Verdict: do not do this.**

A z-score means "how far above this pool's average." Chunking creates four different averages. Each chunk gets re-centered so its own mean is zero and its own standard deviation is one, which deletes the only thing you care about: how much better chunk one is than chunk four. The best player in chunk two and the best player in chunk one both land near +3.

**Simulation on a synthetic 156-player pool, chunked into groups of 50:**

- Spearman correlation with the full-pool ranking: **0.28**
- 57 of 156 players moved 50 or more spots
- The player ranked 151st came out 4th overall
- The player ranked 8th fell to 60th

**Precedent:** nobody in fantasy basketball does this. Fantasy baseball does the positional version, and the z-score community argues against it, on the grounds that a home run from a catcher counts the same as a home run from a shortstop. Same objection applies here. A rebound from your 90th-ranked player counts the same as a rebound from Jokic.

Value over replacement is the legitimate cousin, and note the difference in operation: it **subtracts** a constant, which preserves gaps between players. Chunking **rescales**, which destroys them.

**The valid instincts underneath, and their real fixes:**

| Concern | Fix |
|---|---|
| Superstars inflate the SD and compress everyone else | Winsorize (cap outliers at the 99th percentile before computing SD), or fit a non-normal distribution |
| NBA stats are not normally distributed, especially blocks | Fit an exponential or similar. Basketball Monster's DURANT rankings exist for this reason |
| The gap between rank 40 and 60 is tiny | Tiers, drawn at real score drops. Apply after one global calculation, never as the basis for it |
| 156 feels arbitrary | Legitimate. Run the board at 156 and at 200 and see whose rank moves. This is the one knob worth turning |

If you want a version of the chunking idea that gains something, add a column showing each player's rank **within his tier** alongside his global score. Tier-relative view, uncorrupted numbers.

### Stacking your first-round pick's strengths

**Verdict: right instinct, wrong direction. See section 10.**

Two specific problems:

1. **Over-investment.** Stacking three categories to 92% loses to doing nothing special, at equal capital. See the table above.
2. **Pick one is the wrong anchor.** Round-one players are round-one players because they are well-rounded. Building around Jokic's strengths tells you almost nothing, since he is good at seven categories. The real read comes around picks three to five, from the shape of what actually fell to you.

The correct version is negative space. Decide what you are giving up, then take best available among everyone who does not hurt you there.

### Static ranking lists in general

Worth knowing the limitation you are living with. Rosenof, the author of both the G-score and H-score papers, says plainly that static ranking lists are fundamentally sub-optimal. They cannot adapt to draft circumstances, cannot punt optimally (you do not know in advance whether Giannis will be available), and can produce unbalanced teams when the best players available all happen to be strong in the same category.

His dynamic algorithm, H-scoring, won 37.7% of Most Categories seasons and 21.8% of Each Category seasons against a field of G-score drafters, versus an 8.33% baseline. That is a larger edge than G-score gave over Z-score.

Building H-score is a real project. The practical substitute is what this document describes: a G-score board as your baseline, overridden live by tier logic and category need.

---

## 12. References and provenance

This section maps each piece of guidance to where it came from, so you can check anything yourself. It is organised by how much weight the source can carry.

### A. Published research

Zach Rosenof, three papers on arXiv. These are the mathematical backbone of the whole document. Everything in sections 4, 5, and 10 traces here.

| Paper | Link | What this document uses it for |
|---|---|---|
| Static quantification of player value for fantasy basketball (2023) | https://arxiv.org/abs/2307.02188 | Z-score derivation, G-score derivation, the percentage-impact formula, the empirical per-category multiplier table, the Z vs G simulation win rates, the author's own caveat about static lists |
| Dynamic quantification of player value for fantasy basketball (2024) | https://arxiv.org/abs/2409.09884 | H-scoring, the 37.7% / 21.8% win rates, the finding that the optimal algorithm stops investing in categories it already wins, soft-punting, punting being more effective in Most Categories, the streaming caveat on injury risk |
| Optimizing for Rotisserie fantasy basketball (2025) | https://arxiv.org/abs/2501.00933 | Why this document's punting guidance is head-to-head specific, and why roto managers should punt minimally |

Note on standing: these are arXiv preprints, not peer-reviewed journal articles. The derivations are shown in full and the simulation code and assumptions are described, so they are auditable, which is more than can be said for most fantasy content. But the simulation results rest on a simplified model of fantasy basketball, and the author says so himself.

### B. Fantasy basketball analysts

| Source | What this document uses it for |
|---|---|
| Hashtag Basketball, An Introduction to Punting in Fantasy Basketball (https://hashtagbasketball.com/introduction-punting-fantasy-basketball) | Punt timing (paths after pick one, an idea before pick two), avoiding early double punts, the working punt pairings, "value only exists at market price," the Gobert and Giannis examples |
| SportsEthos, Fantasy Basketball Draft Guide, punt strategy section | Punting as subtraction rather than addition. The line about not drafting bad free-throw shooters to lose FT% |
| RotoBaller, How to Punt Categories in Fantasy Basketball | Your first-round pick should still be a first-round-caliber player. The DeAndre Jordan example |
| Basketball Monster (Josh Lloyd), DURANT rankings | NBA stats are not normally distributed. Scarcity and variance adjustments. "Don't draft by the top name showing," and the gap between rank 40 and 60 being small |
| RotoWire, category league strategy content | Projections as raw statistical outlook versus rankings as context. Per-game vs total value gap. The Anthony Davis and Kyrie Irving examples |
| Yahoo Sports fantasy analysts | Rookie caution. Platform-specific ADP behaviour |
| FanGraphs, z-score primer and its comment thread | The objection to computing z-scores within position groups, which is the fantasy baseball version of the chunking idea rejected in section 11 |
| Giora Omer, min-max normalization for NBA player valuation | Alternative to z-scores mentioned in section 11 |
| George Berry, pseudo z-scores for counting stats | The exponential-fit approach to non-normal categories, mentioned in section 11 |

### C. Product documentation

- Yahoo Fantasy help pages, for the definitions of Rank, Expert Rank, and Pos Rank in section 2. Quoted from Yahoo's own wording.

### D. Sports science and news reporting

Used only in section 6a, on games played.

- Peer-reviewed injury forecasting literature, including Cohan, Schuster and Fernandez (Journal of Sports Analytics, 2021) and NBA injury epidemiology work in PLOS ONE, for: season-long durability being more predictable than week-to-week risk, prior injury type and age carrying more signal than raw absence counts, and guards showing the highest injury ratios by position.
- General NBA reporting on the 65-game rule, in effect since 2023-24, for the availability-incentive note.

### E. My own contributions, not sourced to any expert

You asked specifically about this, so here it is plainly. The following are my synthesis or my own work. They are reasoned, but nobody published them and you should weigh them accordingly.

| Item | Where it appears | What it actually is |
|---|---|---|
| The input weighting table (50-60%, 15-20%, 15%, and so on) | Section 2 | My judgment call on how to balance inputs. No analyst publishes percentages like these. Treat the ordering as sound and the exact numbers as illustrative |
| The tier construction formula (Drop, local median, 2x threshold) | Section 7a | Mine. Analysts universally recommend tiers but nobody publishes a cutting rule, so I built one. The multiplier of 2 is a starting point, not a finding |
| The scarcity tiebreak and pick-counting procedure | Section 8 | Mine. Standard practice in fantasy generally, but the specific procedure is my formulation |
| The chunked z-score simulation (correlation 0.28, 57 players moving 50+ spots) | Section 11 | I ran this during our conversation on **synthetic** data, not real NBA projections. It demonstrates a mathematical property that holds regardless, but the specific numbers are from made-up players |
| The stacking vs punting simulation (79.4%, 80.5%, 72.5%, 63.6%) | Section 10 | Also mine, also synthetic. A simplified model with independent categories and a fixed capital budget. It illustrates Rosenof's finding rather than independently proving it |
| "Aim for 60%, not 90%" and "win six or seven, not five" | Section 10 | My translation of Rosenof's results into a usable rule of thumb. He does not state these targets |
| The GP estimation procedure (weighted 3-year, 70/30 regression, age adjustment) | Section 6a | Mine, informed by the injury literature but not a published method |
| The spreadsheet column schema | Section 6 | Mine |
| "The later you switch, the more you waste" | Section 6b | Mine. Previously stated as a hard "not after round 7", which read as sourced and was not. The instinct holds; the round number was invented, and published guides are more relaxed about mid-draft pivots than it implied |
| Dividing the percentage impact by the SD of the impact column | Section 4 | Mine, or at least not Rosenof's. His Table 5(b) defines that sigma over the raw rate. My derivation favours the impact SD — if a team's category outcome is the mean of its members' impacts, dividing by SD(impact) puts the percentages on the same "share of a team standard deviation" footing the counting categories get — but that reasoning is mine and the question is open |
| The punt weight of 0.25 | Section 6b, ADR-0009 | Mine. Rosenof's soft-punting finding gives the direction; the specific retention is a tuning choice, and his ~75% figure does not transfer to a static board unmodified |
| The rate bands on the Category Tracker (0.005 FG%, 0.010 FT%) | Category Tracker | Mine, and explicitly uncalibrated. Starting guesses pending a season of real standings |

### Corrections applied after review

The document was reviewed against the sources above and two formula errors were found and fixed. Recorded here so the history is visible:

- **Adjusted Value** originally scaled the raw G-score by the games-played ratio. Because G-scores are centered on the pool mean, roughly half were negative, and scaling a negative number by a fraction moved that player *up* the board. Now scales VOR instead, which is positive across the pool.
- **The Gap column** was originally defined as `My Rank - Yahoo ADP` with an instruction to sort descending, which put the avoid list on top. Definition flipped to `Yahoo ADP - My Rank`.

A second review, recorded in `docs/reviews/2026-08-27-draft-board-methodology-review.md`, found four more:

- **`BLK + FG%` was listed as a working pairing.** It is not one. The two are competing routes to the same roster, and a punt-blocks build is trying to protect FG%. Removed from section 10; the sheet had never implemented it.
- **"Soften the GP discount for a deep bench"** would have double-counted the replacement-level backfill the linear form already assumes. The correct refinement runs the opposite way. Section 6a now derives it.
- **The percentage-impact formula was attributed to Rosenof.** It does not match his Table 5(b). Moved to section 12E above.
- **The tier local-median window in the spreadsheet was described as centred and was not** — nine rows above, five below, which inflated the median and made breaks fire late. This document's `OFFSET($D$2,ROW()-9,0,15,1)` is correct and resolves to rows `r-7` through `r+7`; the sheet's `INDEX` translation of it was off by two in each direction and has been fixed to match. The review that surfaced this initially blamed the formula here as well, which was wrong.

Also added after review: section 6b on punt re-ranking (the mechanic section 10 depends on and previously assumed), section 8a on roster construction and streaming, projection sources in section 2, playoff schedule as a late-round tiebreaker, and the reconciliation of the turnover guidance between sections 2 and 10.

### What this means in practice

The valuation math is on solid ground: derived, published, and auditable. The punting principles are backed by both the research and by analysts who agree with each other. The operational layer, meaning how to cut tiers, how to weight inputs, and how to run each pick, is my construction. It is internally consistent and follows from the research, but it is not received wisdom, and you should feel free to change any of it.

---

## Quick reference card

**Before the draft**

- [ ] Confirm teams, roster size, slot structure, scoring format, transaction limits, draft slot
- [ ] Pull projections into the sheet
- [ ] Compute z-scores on the correct pool, iterate the pool twice
- [ ] Apply G-score multipliers
- [ ] Confirm projections are per-game, not season totals
- [ ] Run the spread test on projected GP
- [ ] Copy projected GP into My GP estimate, then override 15-30 cells by hand
- [ ] Convert G-score to VOR, then apply the GP adjustment
- [ ] Cut tiers using the Drop / local-median method (section 7a)
- [ ] Build the Gap column (ADP minus My Rank) and sort descending
- [ ] Build 4-6 punt columns and learn the top risers in each
- [ ] Note fantasy playoff week schedules
- [ ] Decide how many bench spots are churn slots
- [ ] Load your pre-rank list into Yahoo
- [ ] Mock draft from your slot two or three times

**During the draft**

1. Identify your live tier
2. Count picks until your next turn
3. Tiebreak on scarcity: which parallel group runs out first?
4. Tiebreak on weakest live category
5. Tiebreak on turnovers
6. Check ADP before confirming

**Never forget**

- The board says who. ADP says when.
- Steals are worth half what the raw z-score claims.
- Games played is the most under-priced variable on the board.
- Once you commit to a punt, switch to that build's column.
- Stop investing in categories you already win.
- Win six or seven, not exactly five.
- The last two picks are churn slots. Draft upside, not safety.
