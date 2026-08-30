# ADR-0014: DURANT ships as a column, not as the ranking

- Status: Accepted
- Date: 2026-08-29
- Owner: Bryan

## Context

Basketball Monster is the reference tool in this hobby, and Josh Lloyd's DURANT
is its head-to-head valuation. We set out to find how it works and to cross-track
the board against it.

Two things came back.

**Their standard rankings are already ours.** Measured against Basketball
Monster's free rankings table, every counting category regresses on its per-game
stat at R² ≥ 0.9948 — a plain z-score with no transform. The pool that reproduces
their recovered means and SDs is N = 156, the same Q we use. Their `Value` is the
arithmetic mean of the nine category values where ours sums, which cannot reorder
anyone. Our own `valuation.py` reproduces their published ranking at **Spearman
0.9979**, mean 3.11 places. There is nothing to reconcile on that layer.

**DURANT is where they differ, and its mechanism is now known.** Lloyd names it
himself: a Yeo-Johnson power transform per category, then standardisation, plus
fixed weights and a "minus one" rule that drops or half-weights each player's own
worst category. It is per-game and has **no availability term** —
`docs/references/basketball-monster-durant.md` has the sourcing.

`scripts/draft-board/durant.py` reconstructs that structure. It behaves like the
real thing: of the nine players Lloyd named in 2023 as moving under DURANT that
appear on our board, **eight move in the direction he published**, and run over
Basketball Monster's own stat lines it reproduces the headline oddity DURANT is
marketed against — their z-score puts Okongwu 41st and Giannis 67th, the
reconstruction puts Giannis 7th.

So the question is not whether we can compute it. It is whether it should rank
the board.

## Decision

**DURANT ships as a column on the Board and the Draft Board. It does not drive
the ranking.**

The Draft Board carries `DURANT` (its rank) and `vs us` (our rank minus its
rank), so a disagreement is visible on the clock without changing the order you
draft in.

Three reasons.

**The premise does not survive our format.** DURANT normalises the *marginal*
distribution — how one player's blocks are spread across the league. But a
category is won by a **13-man team total**, and the central limit theorem
flattens that skew long before it reaches a win probability. On our own pool
blocks go from an individual skew of +1.53 to a team-total skew of **+0.38**,
with excess kurtosis falling from +3.31 to +0.11. Rosenof cites Lloyd by name for
the non-normality premise and **still declines to transform**, resting on exactly
this argument.

**The cost is not marginal.** Comparing per-game against per-game, so our GP
layer is not confounding it, adopting DURANT moves players a mean of **18.6
places**, with **135 of 200 moving ten or more**. Pulling in the right tail is
what removes a specialist's edge, and in a category league you win blocks with
blocks, not with rank order.

**Its punting philosophy contradicts ours.** DURANT decides for you which
category each player concedes. Our board makes you choose a build and values
everyone against it, which is the entire point of the Punts tab and of
`PUNT_WEIGHT`. Running both as the ranking would be incoherent.

Against all that, Lloyd is a serious analyst and the board should be able to hear
him. `docs/references/quant-vs-expert-reconciliation.md` already says how:
**take their information, never their rank.** A column is information.

## Consequences

**Good.** A cheap second opinion on every player, from the tool most of the room
is using, with the disagreement quantified rather than remembered. It is also the
first thing on the board that reads across to what leaguemates see on their
screens.

**Reversible and tunable.** `DUR_W` on Settings holds the nine weights, defaulted
to Lloyd's published pre-DURANT hand weights because DURANT's own are withheld.
Zeroing them or ignoring the column costs nothing.

**Lambda is a fit, not a setting.** The nine Yeo-Johnson lambdas live on Settings
but are produced by `Fit DURANT lambdas` in the menu, not typed. The means and
SDs beside them are formulas and follow the pool automatically; lambda does not.
**A stale lambda is a wrong transform, silently.** Re-run the fit after any
refresh that moves the pool.

The search bracket is [-15, 15], not the [-2, 2] most libraries default to. The
percentage impacts are small signed numbers clustered near zero and FG% impact
peaks near -6.9 on real data; a narrower bracket returns the edge of the search
instead of the fit, and nothing about the result looks wrong.

**Bad — it is a reconstruction, not a copy.** Lloyd withholds the coefficients
outright. The weights are a stand-in, and two components he names — waiver-wire
availability and inter-category correlation — are not modelled at all, because no
public description of either exists. The column is labelled as a reconstruction
on the sheet's own README for that reason, and it must not be quoted as "what
Basketball Monster says".

**The columns sit at the far right of both tabs**, after `Notes` on the Board and
after the hidden mirror block on the Draft Board. That is deliberate: inserting
them earlier would shift existing columns, and `Refresh data` writes by fixed
position while the Category Tracker bakes in column letters at write time. Placed
where they are, this change deploys with targeted menu steps and does not cost a
full rebuild.

**Not decided here.** Whether to adopt the bounded, win-probability-based
saturation that the same research suggests as a better-founded alternative to a
distributional transform. That needs its own ADR and its own measurement.
