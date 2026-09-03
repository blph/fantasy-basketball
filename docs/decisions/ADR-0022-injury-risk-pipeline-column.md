# ADR-0022: Injury risk is a researched pipeline column

- Status: Accepted
- Date: 2026-09-02
- Owner: Bryan
- Amends: ADR-0008 (in part — the hand-edited-columns contract)

## Context

The board has carried an `Injuries` column since it was built: `Board!AA`, mirrored to the
Draft Board as `INJ`. It was designed for a *current status* — its only two conditional
formats matched `OUT` exactly and `GTD` as a substring — and it was listed in `HAND_COLS`
so a refresh would never touch what you typed there.

Nothing was ever typed there. A pull of the live sheet before this change found
`Board!AA4:AA203` and `Draft Board!G4:G203` empty on all 200 rows, alongside `GP Y-1/2/3`,
`XRank` and `Notes`. The same audit that retired the games-played adjustment
([ADR-0017](ADR-0017-no-games-played-adjustment.md)) found the availability override
machinery unused on 0 of 200 rows. This column was the same story: a place to record a
judgement, with no judgement recorded.

That is the wrong shape for the question. A current-status note goes stale in a day and is
worthless in September. What a draft actually needs is the durable version of the question
— *how likely is this player to miss time this season* — and the playbook already calls
availability "the most under-priced variable in fantasy" while identifying exactly which
part of an injury history carries signal:

> A lost season caused by a single freak injury. A broken hand from a collision says
> nothing about next year. […] Recurring soft-tissue or joint problems. Chronic issues are
> the part of injury history that actually predicts.

Answering that for 200 players is real research — dated injuries, surgeries, games missed,
and what the small number of genuine injury analysts have said. It is not something to
hand-type into a spreadsheet cell at 2am.

## Decision

**The `INJ` column carries a computed durability tier — `HIGH` / `MED` / `LOW` — and is a
pipeline column, not a hand-edited one.** `B.injuries` moves out of `HAND_COLS` and into
`REFRESH_MAP` as the 21st `PLAYERS` field. The old `OUT` / `GTD` conditional formats are
replaced.

**The research is committed; the tier is not.** `scripts/draft-board/injury_risk.json`
holds *evidence* — dated injury events with body part, mechanism, surgery, games missed and
at least one source URL per player, plus any expert read. It holds no tier.
`injury_risk.py` computes the tier from that evidence at build time.

This is [ADR-0016](ADR-0016-values-computed-in-python.md) applied to a new column: the
sheet holds the result, Python owns the derivation. Two things follow that would not
otherwise. Two hundred independently-run research agents produce *comparable* tiers,
because none of them decided one — agent 7's MED and agent 180's MED are the same MED. And
retuning the rubric costs a `pytest` run instead of 200 re-runs.

**Keyed on `sources.normalise()`, a superset of the board, alphabetical.** The same key the
projection join already uses, so it costs nothing to match and it survives a refresh that
swaps players in and out of Hashtag's top 200. A player who leaves the board in September
is back in October, and deleting his record would mean re-running an agent. Alphabetical
order carrying no rank, no ADP and no stat line keeps the file public injury reporting
rather than a thin derivative of a provider export
([ADR-0006](ADR-0006-no-provider-data-redistribution.md)).

**A board player with no record renders `?`. Never blank, never fatal.** `AGENTS.md`'s rule
is that a hole must not *read as data*, and a blank cell in a risk column reads as `LOW` —
the one reading that would actually cost a pick. `?` cannot be mistaken for a tier. A hard
failure is wrong in the other direction: this column scales nothing (ADR-0017), so refusing
to build the whole board on draft eve because one player entered the top 200 trades a real
loss for a cosmetic one. Coverage is reported loudly by `build_data.py` and on the Settings
sanity block, and `--require-injuries` makes it fatal when you want that gate.

**The rubric scores injury history, never durability.** Four terms sum: the worst
surgery rather than the sum of them (0–3, weighted toward a recent lower-body repair), the
same body part failing across seasons (0–4, with a soft-tissue bonus), age (0–2), and
guard (0–1). A `freak` mechanism (a broken hand from a collision, an illness) never counts
toward recurrence. Max score is 10.

Games played or missed play no part in the score, in either direction. A `games_missed`
count on an event is kept only as descriptive detail for the report — how long one injury
cost a player is not the same question as how injury-prone he is, and the board already
has a GP column for the durability question that deliberately scales nothing
([ADR-0017](ADR-0017-no-games-played-adjustment.md)). An earlier draft of this rubric
included a recency-weighted "games missed" term; it was removed before any board player
saw it, because it re-derived the durability signal ADR-0017 already deliberately excludes
from the board's values, inside a column meant to answer a different question.

**Cuts are absolute — `≥5` HIGH, `3–4` MED, `≤2` LOW — not percentile.** A percentile cut
would make `LOW` mean "low relative to this year's field", so a player's tier would drift
every refresh while nothing about him changed. Two overrides: a major lower-body surgery
inside 12 months is `HIGH` regardless of the score, and thin research coverage caps a
scored `HIGH` at `MED`.

**`D.inj` leaves `restoreCheckState`, `readCheckState` and `draftHeaderCols`.** The Board
owns the column now and the Draft Board cell is `='Board'!AA<row>`, which follows the
player through a re-sort by construction. Restoring it by name would write a literal over
that formula — see Consequences.

**Nothing is scaled by the tier.** ADR-0017 stands unchanged. This is the reason to
distrust a GP number, not a discount applied to one.

## Consequences

**Known limitation: the chronic term only credits the same body part recurring.** A
player hurt in a different place almost every season — an ankle one year, a hip the next,
a back the year after — reads as `LOW` under this rubric even when several research
agents independently called him `HIGH` for exactly that pattern. That is a real signal the
current design does not capture, not a bug: the term is deliberately scoped to "the same
body part failing across seasons", per the playbook's own framing of what predicts. A
general injury-frequency term (count of distinct dated events regardless of body part)
would catch it, and is a reasonable next revision, but is deliberately not added here —
scope was already corrected once in this branch (below), and a second unrequested
addition to the rubric is not this session's call to make alone.

**GP was removed from the rubric mid-branch.** An earlier revision of `score()` included
an "availability" term — recency-weighted games missed, falling back to `82 - GP` — worth
up to 4 of what was then a 14-point scale. It was removed before any board player saw it:
the whole point of this column is a judgement about injury *history*, and games played is
the durability question the board's own GP columns already own and ADR-0017 already
excludes from scaling. Re-deriving it inside a different column would have answered a
question nobody asked with it. `CUT_HIGH`/`CUT_MED` were rescaled from `6`/`3` (of 14) to
`5`/`3` (of the resulting 10-point max) when the term was removed.

**Two scoring bugs surfaced by full-scale research, fixed before any tier shipped:**
recurrence grouped events by an exact string match on body part, so "right leg/ankle" and
"ankle/calf/knee" never joined "knee" even though they describe overlapping anatomy — a
three-surgery career scored zero recurrence. And recurrence counted *distinct season
labels*, so two hamstring strains ten weeks apart in the same season — the single most
literal case of "recurring" — also scored zero, and two different old surgeries both
merely dated "older" collapsed into one occurrence. Both are fixed: `chronic_points`
clusters body parts by word-overlap (via union-find, so a third event can bridge two that
never directly overlap) and counts distinct `(season, date)` occurrences rather than
distinct seasons. `surgery_points` also stopped zero-crediting an `"older"`-dated major
surgery, since the schema tells an agent to report one that old only when it is
significant enough to matter.

**A latent bug had to be fixed to make this safe.** `restoreCheckState` wrote `D.inj` back
as a static value, gated on `if (any)`. With the column empty that gate never fired, so the
bug was invisible. It would have fired on the first `Rebuild & re-sort` after tiers landed
and then been permanent: the mirror formula replaced by a literal, the tier frozen at
whatever it was that day, with no `#REF!`, no error, and a value that reads as current.
Exactly the failure class [ADR-0020](ADR-0020-identity-anchored-references.md) exists to
prevent. `verify.py --sheet` now compares all 200 rendered `INJ` cells against `Data.gs`,
so a recurrence is caught mechanically rather than by eye.

**This change required a full rebuild.** `clearConditionalFormatRules()` is called in
exactly one place, inside `sheetByName`, which `rebuildAndResort` bypasses — so nothing
short of `Full rebuild` could remove the stale `OUT` / `GTD` rules. That was cheap here
only because every Board hand column was empty; it would not be next time. The related
rule-duplication bug is recorded in
[docs/bugs/2026-09-02-conditional-format-duplication.md](../bugs/2026-09-02-conditional-format-duplication.md).

**A refresh now has two clocks.** The projections and the injury research are dated
separately, and `META.injuries.generated` keeps that visible. Re-exporting projections does
not refresh the research, and a player who enters the board between research runs shows `?`
until someone researches him.

**The research is a snapshot with a shelf life.** It is accurate as of its stamped date and
degrades through the season as players get hurt. It is built for draft day, not for
in-season roster management.

**Sourcing is constrained on purpose.** Only three analysts may be quoted as risk
assessment — Jeff Stotts (ATC, *In Street Clothes*), Stephania Bell (ESPN; PT, ATC, OCS,
CSCS), and Dr. Jesse Morse (*Fantasy Doctors*). Beat reporters supply facts, never risk
reads; aggregators and social media are used only to locate a primary source. A record
must carry at least one real source URL — either its own `sources` or an event's — and
validation rejects one with none anywhere; a record with zero events (a genuinely clean
player) needs no citation, since there is no event fact to back. `expert_reads` is
opportunistic: an agent records a quote only if one turns up in something it already
read, and is never sent looking for one.

The citation rule was tightened and then loosened once already. The first 61 players were
researched under a stricter draft that demanded a source per *event* and a dedicated
search for a named analyst; it averaged 12.6 cited sources and 30–70 tool calls per
player, on the more expensive model, for research a rubric consuming aggregates does not
need at that resolution. The rule settled on one real source per player (an event-level
source still counts, so the first 61 records needed no rework), the expert search dropped
to opportunistic-only, and the research model moved from Opus to Sonnet — a
retrieval-and-extraction task the rubric, not the agent, turns into a verdict.

## Alternatives considered

**Leave it hand-edited and paste the tiers in once.** Less code. But nothing in the repo
would reproduce the column, the research would live only in a spreadsheet cell, and the
next refresh would depend on the name-rekeying path holding. Rejected: the whole reason the
column was empty is that hand-maintenance does not happen.

**Let each research agent decide the tier.** Closer to how the work was described, and
better on cases a rubric mishandles. Rejected because 200 independent judgements do not
mean the same thing, and re-tiering would mean re-researching. The agent's own read is kept
as `suggested_tier` and every disagreement with the rubric is counted and reviewed.

**Put the reason in the cell** (`HIGH knee`). Rejected: the Draft Board column is 56px in
the frozen identity block, and the tier has to be readable in the second you have. The
reasons live in [docs/draft-board/injury-risk.md](../draft-board/injury-risk.md).
