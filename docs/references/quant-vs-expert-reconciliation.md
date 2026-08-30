# When the board and the analysts disagree

What to do when the board says round three and the analysts say round six.
Companion to the [playbook](fantasy-basketball-draft-playbook.md), which specifies the math.

---

## The answer

**Take their information. Never take their rank.**

Analysts rank a generic category league. Our board ranks ours, on our pool, our format and
our punt weight. But the board reads one projected stat line and is blind to anything that
changed it. So an analyst's edge is always in the *input*, never in the ordering.

Every accepted override lands in `My GP Est` or the projection row. Never in a rank.

---

## The procedure

### 1. Check ADP first. Most splits die here.

| What GAP says | What it means | Do this |
|---|---|---|
| **Large positive** (ADP agrees with the analysts) | The room already prices him where they do. You will never pay round-three price | **Wait.** Take him a round before his ADP. Nothing to resolve |
| **Near zero or negative** (ADP agrees with you) | The analysts are a minority view, and it will cost you | Go to 2 |

Most of what feels like conflict is this. "He should go in round six" is usually a claim
about *price*, and the board already separates price from value: the board says who, ADP
says when.

### 2. Ask one question: games, or the stat line?

| They say | It is | Go to |
|---|---|---|
| "great when he plays", load management, injury history, age | **Games** | 3 |
| traded, new coach, lost the starting job, camp battle, usage, minutes | **Stat line** | 4 |
| "overrated", "I don't like him", or they are ranking points / roto / 8-cat | **Nothing** | Board wins. Stop |

### 3. Games: edit `My GP Est`, then check it was worth doing

How far a GP cut actually moves a player, measured on the current board:

| Games removed | Places he drops |
|---|---|
| 5 | 4 to 8 |
| 10 | 6 to 14 |
| 15 | 9 to 22 |
| 20 | 12 to 29 |

**A GP override cannot move a player three rounds.** Thirty-six places needs roughly
twenty-five games off, which is a claim that he plays under fifty. If the analysts are not
saying that, availability is not what the split is about and you have mis-diagnosed it.
Go to 4.

It also has to clear a tier to change any decision you will actually make. Tier sizes on
the current board:

| Where you are picking | Tier size |
|---|---|
| Rounds 1 to 2 | 2 |
| Round 3 | 5 |
| Round 5 | 10 |
| Round 8 and later | 17 |

So five games is a real move in round two and noise in round eight.

### 4. Stat line: only a named event counts

A three-round split needs the projected line to be wrong, not just the games. That means a
specific, checkable event: a trade, a signing, a departure, a new coach, a camp battle he
lost. Edit the projection row: minutes first, then the counting stats that scale with them.

**If you cannot name the event, you are in "nothing". Board wins.**

### 5. Still stuck

Board and two analysts disagree, you have run 1 to 4, and no cause is nameable. Coin flip.
Take whichever of the two candidates is cheaper against ADP.

---

## The rules

1. **Change the input, never the rank.** A typed rank desynchronises VOR, the tiers, the
   nine punt columns and the tracker. Change the input and they all move together.
2. **Two independent analysts, never one.** Independent excludes anyone echoing ADP and
   anyone working from the projection our board already reads.
3. **If it does not clear a tier, do not do it.** Small adjustments make things worse.
4. **Downgrades cheap, upgrades expensive.** A downgrade needs one sourced reason. An
   upgrade needs two, plus a named mechanism: whose minutes, whose shots.
5. **15 to 30 overrides, and no more.** Past thirty you have replaced the model with your
   own, unaudited.
6. **Write it in `Notes`, dated.** One line: what changed, who said it, why. It survives a
   re-sort. Without it you cannot tell next season whether your judgment is worth anything.
7. **On the clock, the board wins ties.** Overrides are homework. Mid-draft the only live
   judgment is about the draft, not the player: which tier is live, who runs out first,
   which category is slipping. Those are columns.

---

## Ignore them outright when

- They are ranking points, roto, 8-cat, or an unstated generic build.
- Their rank tracks ADP. They are reporting the market, not disagreeing with you.
- The objection is about category shape rather than total value. `Category profile` and
  the Punts tab answer that; the rank is not the instrument.
- No named reason. "Feels wrong" is not a broken leg.

---

## Why these rules

Four findings, all from outside fantasy. The transfer is mine and unreplicated here.

- **Dawes, Faust & Meehl (1989).** Formulas beat expert judgment in nearly every
  comparison. Meehl allowed one exception, the "broken leg": a rare decisive fact outside
  the model's inputs. But accuracy is *higher* when judges defer anyway, because they find
  far too many broken legs. Hence rule: name the fact or do not override.
- **Fildes, Goodwin, Lawrence & Nikolopoulos (2009),** 60,000+ forecasts. *Small*
  adjustments damaged accuracy while larger ones helped, and *upward* adjustments were
  less likely to help and more often plain wrong. Hence rules 3 and 4.
- **FantasyPros.** Consensus beat every individual expert over the back half of a season,
  top five across all of it. It ranked tenth over the first four weeks, and it is football
  start/sit rather than basketball drafting, so read the direction not the margin.
  Hence rule 2.
- **Dietvorst, Simmons & Massey.** People abandon a model after seeing it err, even when it
  beats them. Letting them modify it within limits made them both more willing to use it
  and more accurate. Hence a budget rather than either extreme.

---

## The board has no expert input at all right now

Read from the live sheet, 2026-08-28:

| Column | Purpose | Filled, of 200 |
|---|---|---|
| `GP Y-1/2/3` | audit availability against three real seasons | 0 |
| `My GP Est` differing from `Projected GP` | the override playbook 6a asks for 15 to 30 times | 0 |
| `Notes` | why you did what you did | 0 |
| `XRank` | market read | 0 |

`ADP` is the only external input, covering about four rows in five, and it is the export
provider's aggregate rather than Yahoo's.

So the board today is one projection, transformed correctly and touched by nobody. Filling
the three GP history columns is prerequisite to step 3 meaning anything, and is the highest
value hour of prep available.

---

## Not decided here

A consensus-rank column and a dispersion measure would turn step 1 into a flag instead of a
manual check. The decision log already names the missing second projection source. `XRank`
is tempting and wrong: it is computed on Yahoo's *default* scoring, not ours. Each needs its
own ADR.

---

## Sources

**Research.** [Dawes, Faust & Meehl, *Clinical versus actuarial judgment*, Science 1989](https://meehl.umn.edu/sites/meehl.umn.edu/files/files/138cstixdawesfaustmeehl.pdf) ·
[Fildes, Goodwin, Lawrence & Nikolopoulos, *Effective forecasting and judgmental adjustments*, IJF 2009](https://researchportal.bath.ac.uk/en/publications/effective-forecasting-and-judgmental-adjustments-an-empirical-eva/) ·
[Dietvorst, Simmons & Massey, *Algorithm Aversion*](https://marketing.wharton.upenn.edu/wp-content/uploads/2016/10/Dietvorst-Simmons-Massey-2014.pdf) and [*Overcoming Algorithm Aversion*](https://pubsonline.informs.org/doi/10.1287/mnsc.2016.2643) ·
Rosenof [2307.02188](https://arxiv.org/abs/2307.02188), [2409.09884](https://arxiv.org/abs/2409.09884)

**Industry.** [RotoWire, Rankings vs. Projections](https://www.rotowire.com/basketball/article/fantasy-basketball-rankings-vs-projections-96956) ("Rankings apply context, factoring in injury risk, positional scarcity, and real-world circumstances") ·
[Draft Day Authority](https://draftdayauthority.com/projections-vs-rankings/) ("projections ask how much, rankings ask who first") ·
[RotoWire, Projected Minutes](https://www.rotowire.com/basketball/article/nba-projected-minutes-explained-fantasy-basketball-97473) ·
[Snellings, ESPN](https://www.espn.com/fantasy/basketball/story/_/id/25816913/fantasy-basketball-updated-fantasy-hoops-points-ranks-impact-injury-risks) (prices injury history as a small input factor, not a large rank penalty) ·
[FantasyPros ECR accuracy](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/)

**Worth reading in-season, for the news channel this board cannot see.** Josh Lloyd
(Basketball Monster, Locked On Fantasy Basketball) · Adam King and Aaron Bruski
(SportsEthos) · Dan Titus (Yahoo, publishes 9-cat) · Hashtag Basketball · RotoWire, NBC and
Athlon role and minutes coverage.

**Mine, not sourced.** The step 1 to 5 procedure; reading the playbook's 15-to-30 as a
ceiling as well as a floor; the coin-flip-on-price tiebreak; the transfer of supply-chain
forecasting results to a draft. The GP and tier tables are measured off the current board.
