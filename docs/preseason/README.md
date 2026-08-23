# Pre-season Context

Roadmap Phase 1. **Not yet started.**

## Why this is first

Rankings and projections are backward-looking. They extrapolate last season and adjust, which means they systematically lag situational change: a trade that vacates 20 shots a game, a coach who plays rookies, a starter who quietly had off-season surgery.

That lag is where the edge is. Consensus rankings are available to everyone in the league; nobody has an advantage from ECR alone. Knowing that a player's role is about to change, before the rankings catch up, is the kind of thing a draft is won on. It is also the one part of this project that no API supplies.

## What to capture

One file per topic. Keep entries dated and sourced, and separate what happened from what it implies.

- `trades.md` — trades and the usage each one vacates or absorbs
- `signings-and-departures.md` — free agency, waivers, contract situations
- `injuries.md` — off-season surgeries, recovery timelines, expected minutes limits
- `depth-charts.md` — projected rotations and role changes by team
- `rookies.md` — landing spots and realistic first-year roles
- `coaching-changes.md` — new systems, pace changes, rotation tendencies

## Entry format

```md
## [Date] — [Team] — [Headline]

**What happened:** the fact, with a source link.

**Fantasy implication:** who gains or loses usage, minutes, or role. Be specific
about the category effect — "absorbs ~6 FGA/game, helps PTS and FG%" beats
"should be better this year."

**Confidence:** high | medium | speculation.
```

Keep the fact and the inference separate, and mark speculation as such. In March it needs to be possible to tell what was known from what was guessed, or reviewing our own decisions honestly becomes impossible.

## Feeding this into the draft

Where these notes disagree with consensus rankings, that disagreement is the actionable part. Phase 3 should surface it: a manual note or adjustment on a player's row, so the reasoning is visible on the clock rather than half-remembered.
