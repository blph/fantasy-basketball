# ADR-0026: Studies are generated, gitignored, and reproduced by a committed script

- Status: Accepted
- Date: 2026-09-17
- Owner: Bryan

## Context

The local draft board ([ADR-0022](ADR-0022-local-draft-board.md)) holds every number the
sheet does, answerable in one local call. That makes a class of question cheap to ask that
was previously not worth the browser round trip: not "what is this player worth", which the
board already answers, but "what does the *pool* look like" — how a category thins out by
round, where the sources disagree, which shapes the eye misses when reading 200 rows one at
a time.

The first of these is the category-scarcity study: the drafted pool sliced into rounds of
12, counting per round how many players carry each category as a primary or secondary
strength ([ADR-0024](ADR-0024-secondary-strength-band.md)). There will be more.

A study is an awkward artifact for this repository, for two reasons that pull in opposite
directions.

**It is derived from provider data.** The repository is public and publishes none
([ADR-0006](ADR-0006-no-provider-data-redistribution.md)). A study's *aggregates* — "round 3
holds five players with REB as a strength" — are not provider data in any useful sense: they
carry no name, no value, no rank, and nothing in them reconstructs a projection. But the
line between an aggregate and a derivation that recovers the underlying figure is a judgement
call, and this repository has already been caught on the wrong side of one: mock-draft
reviews were ignored wholesale after `GAP + Adj Rank` turned out to recover ADP exactly.
`scripts/check-no-data.sh` would not catch a bad study — it does not scan `.md` or `.html`
under `docs/` — so the guard has to be the directory, not the check.

**It is also a rendered artifact, not prose.** A study is a chart-heavy HTML page, generated
in full from a snapshot. Committing it means committing a large generated file that no one
diffs, that goes stale the moment the board is rebuilt, and whose staleness is invisible.

## Decision

**`docs/studies/` is gitignored. The committed, reproducible artifact is the script.**

- A study is a committed Python module under `scripts/draft-board/`, with tests over
  synthetic fixtures, that reads a snapshot through `board_snapshot.load()` and writes its
  report into `docs/studies/`.
- The rendered report is local. It carries the board date and the snapshot digest in its
  header, so a reader can always tell which board it describes.
- Reproducibility comes from re-running the script against a dated snapshot, exactly as it
  does for the borrowed pool constants ([ADR-0021](ADR-0021-borrowed-bbm-pool-constants.md)),
  which are likewise refitted rather than stored.
- A study reads the pool through `board_engine.empty_state()`, never the live draft state.
- Where a study's *argument* is worth keeping — the finding, not the figures — it is written
  as ordinary committed prose under `docs/reviews/`, aggregate-only.

## Consequences

- Positive: the question "may I put this number in the report?" stops being a judgement call
  made per study. The directory is ignored, so the answer is always yes, and the review
  burden moves to the one place it belongs — the prose that gets committed.
- Positive: a study is rebuilt rather than refreshed, so it cannot silently describe a board
  that no longer exists. The digest in the header makes the pairing checkable.
- Positive: no generated HTML in the diff.
- Negative: a study is invisible to anyone reading the repository, including CI and a future
  agent. Mitigated by the script and its tests being committed, and by the command being
  listed in `AGENTS.md` where the other board commands are.
- Negative: two people running the same study on different snapshots get different numbers
  and nothing in git reconciles them. Accepted: the board itself already works this way.
- Follow-up: if a study's finding proves durable enough to cite, write it up as prose in
  `docs/reviews/` rather than pointing at a file only one machine has.

## Links

- Provider-data policy: [ADR-0006](ADR-0006-no-provider-data-redistribution.md).
- The snapshot a study reads: [ADR-0022](ADR-0022-local-draft-board.md).
- The bands the first study counts: [ADR-0024](ADR-0024-secondary-strength-band.md).
- Precedent for the split: the `.gitignore` entries for `docs/mock-drafts/` and
  `docs/reviews/mock-drafts/`.
