# ADR-0030: The Draft Board carries BMP's GP and Basketball Monster's comments, and its projection blocks collapse

- Status: Accepted
- Date: 2026-10-11
- Owner: Bryan
- Amends: ADR-0017 (which GP is shown), ADR-0014 (how a projection is hidden)

## Context

Four things about the Draft Board were not earning their place.

- **Three GP columns.** `Proj GP`, `My GP` and `Flag` sat under "GP · context only". The first
  was Hashtag's projected games, the second a hand override nobody had filled in, the third a
  flag comparing the two. The board ranks on Basketball Monster's projection by default, so the
  one GP shown was not the one behind the default ranking.
- **A TIERING block.** `Break`, with `Drop` and `Local med` collapsed beside it. The tier lines
  drawn across the board from those columns already say where each tier ends.
- **Projection checkboxes nobody could find.** Three checkboxes in row 1 hid and showed each
  projection's six columns. The owner did not know they existed.
- **An empty Notes column.** Basketball Monster publishes a comment on every player it projects.
  The owner was reading those on another site.

## Decision

**One `GP` column, and it is BMP's.** `build_data.py` reads the games Basketball Monster's own
source projects off the vendor row each board player already joined to, and writes it as a new
trailing `PLAYERS` field. The Board tab gains one appended column for it, `B.bmpGp`; the Draft
Board's `GP` is a formula into that cell at the player's own row, the same identity-anchored
shape as `INJ` ([ADR-0020](ADR-0020-identity-anchored-references.md)). Nothing scales by it
([ADR-0017](ADR-0017-no-games-played-adjustment.md) stands). The amber 68–74 rule is not carried
over: it marks Hashtag's generic haircut and means nothing on Basketball Monster's number.

**The Board tab keeps its own GP columns.** `GP Y-1/2/3`, `My GP Est` and `GP flag` stay where
they are, unread by the Draft Board. Removing them would move every Board column `Refresh data`
writes into.

**Notes shows Basketball Monster's comment.** The comments arrive as an optional seventh file in
the dated set, `BMP Comments - YYYY-MM-DD.csv`, keyed on the same normalised name the vendor join
uses. `Board!Notes` becomes a pipeline column and leaves `HAND_COLS`. The Draft Board cell is
still a formula into it, and still an input: type over it and the note is yours. `readCheckState`
carries only a typed-over cell through a re-sort, told apart by the cell having no formula. A
comment that opens with `=` or `+` is written with a leading space, because Sheets would store it
as a formula.

**Each projection's block is a column group, collapsed at build.** A narrow label column sits
ahead of each block. It keeps the three groups apart, since Sheets merges groups that touch, and
it stays on screen when its block is collapsed, with the group's `+` above it. The row-1
checkboxes, their `onEdit` branch and `Apply projection filter` are removed, so there is one way
to hide a projection.

**The tiering columns move into the hidden helpers.** `sel`, `Drop`, `Local med` and `Break`
keep their formulas. `TIER`, `RND`, the tier lines and the local engine still read them.

**The snapshot is schema 2.** Every player gains `bmp_gp` and `comment`. A schema-1 snapshot is
refused, not read with a hole in it.

## Consequences

- A refresh is seven same-dated files when the comments are exported, six when they are not. A
  set without them builds, says so in one line, and leaves Notes blank. Comments from another
  date are never borrowed.
- `Data.gs` grows by about 50KB, so pushing it takes about twenty chunks.
- `Rebuild & re-sort` collapses all three projection blocks again.
- The Draft Board no longer mirrors `My GP`, so `verify.py --local` no longer catches a Board
  `My GP Est` the pull lost. The tick scenario's reorder step still checks a hand value by
  reading `GP Y-1` on the Board.
- A note typed over a Draft Board cell is a literal a values pull cannot tell from the comment,
  so `verify.py --local` reports it as a mismatch on that row. Clear it, or accept the line.
- A draft state pinned to a schema-1 snapshot needs `board.py rebase`.
- The local engine's `gp` is BMP's. `my_gp` and `gp_flag` still mirror the Board tab and compare
  against Hashtag's `hbp_gp`; `gp_warn` is gone with the rule.
