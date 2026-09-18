#!/usr/bin/env python3
"""Category scarcity by round: when does each category run out?

The board labels a player's categories as a primary strength (unweighted DURANT
`d >= CAT_BAND`), a secondary strength (`CAT_BAND_SEC <= d < CAT_BAND`), or a weakness.
Those labels answer "what is this player good at". They do not answer the question that
drives draft-day sequencing: how many players with a given strength are still on the board
by round 6, and which categories are gone by then.

This slices the drafted pool into rounds of `teams` and counts, per round and per category,
how many players carry that category as a primary or a secondary strength. Eight per-player
labels become eight scarcity curves.

Three decisions worth stating, because each one is a way to get a plausible wrong number:

  - **The pool is Q, not the board.** Ranks 1..q only -- 13 rounds of 12. Rows past Q are
    below replacement and the last group would be a partial round of 8, whose counts share
    no denominator with the other 16 and would dip for a purely arithmetic reason.

  - **The state is empty, always.** `_profile` drops a category ticked Punted from every
    list, and the applied sort decides which source's `d` is read. Reading the live
    `draft-state.json` would let a punt Bryan had ticked erase a category from all thirteen
    rounds, and the report would look entirely normal. `board_engine.empty_state()` is a
    draft nobody has started; `verify_local.py` reads the board the same way.

  - **Eight categories, not nine.** DURANT H2H prices turnovers at zero, so a TO column is
    identically 0.0 for every player and can never clear a band. `cat_labels` carries the
    eight the board actually profiles.

The bands come from `snapshot["settings"]`, never from a constant here, so a reband
re-measures instead of silently disagreeing with the board it claims to describe.

Output is aggregate: counts per round per category, no names, no values, no ranks. It lands
in `docs/studies/`, which is gitignored (ADR-0026) -- the committed, reproducible artifact
is this script.

    python3 scripts/draft-board/study_scarcity.py
    python3 scripts/draft-board/study_scarcity.py --source HBP --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_engine as E  # noqa: E402
import board_snapshot as BS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
#: Where the rendered report lands. Gitignored (ADR-0026).
STUDIES = REPO / "docs" / "studies"

#: The three bands a category can fall in. `None` is "neither", which includes every
#: weakness -- a weakness is not a strength and this study counts strengths.
PRIMARY = "primary"
SECONDARY = "secondary"


class StudyError(Exception):
    """A study that cannot be measured from the snapshot it was given."""


def classify(d: dict, labels: list[str], band: float, band_sec: float) -> dict[str, str | None]:
    """One player's categories, each `PRIMARY`, `SECONDARY` or None.

    The same two tests `board_engine._profile` applies, in the same order and on the same
    quantity -- the applied source's UNWEIGHTED `d`. The secondary interval is half-open,
    `[band_sec, band)`, so a primary strength is never also counted as a secondary one and
    `primary + secondary` can be summed without double-counting anybody.

    Weaknesses are deliberately not a third outcome here. `d <= -band` is simply not a
    strength, and collapsing it into None keeps the caller from having to know that.
    """
    out: dict[str, str | None] = {}
    for c in labels:
        v = d[c]
        if v >= band:
            out[c] = PRIMARY
        elif v >= band_sec:
            out[c] = SECONDARY
        else:
            out[c] = None
    return out


def scarcity_counts(snapshot: dict, source: str = "BMP", rounds: int | None = None) -> dict:
    """Counts of primary and secondary strengths per round, per category.

    `rounds` defaults to the league's own depth, `q / teams` -- 156 / 12 = 13. Every round
    is a full `teams` players, so each count shares one denominator and the curves compare
    honestly end to end.

    Ordering and the round each player falls in come from `board_engine.board_rows`, which
    already carries `rnd = ceil(rank / teams)`. Reproducing that here would be a second
    implementation of the board's displayed order, free to drift from it.
    """
    if source not in BS.SOURCES:
        raise StudyError(f"unknown source {source!r}: expected one of {BS.SOURCES}")

    settings = snapshot["settings"]
    teams, q = int(settings["teams"]), int(settings["q"])
    band, band_sec = float(settings["cat_band"]), float(settings["cat_band_sec"])
    labels = list(snapshot["cat_labels"])

    n_rounds: int = q // teams if rounds is None else int(rounds)
    if n_rounds < 1:
        raise StudyError(f"rounds must be at least 1, got {n_rounds}")
    limit = n_rounds * teams
    if limit > len(snapshot["players"]):
        raise StudyError(
            f"{n_rounds} rounds of {teams} needs {limit} players, "
            f"board has {len(snapshot['players'])}"
        )

    # An empty state, never the live one: no ticks, nothing conceded, the default sort.
    rows = E.board_rows(snapshot, E.empty_state(), settings,
                        {"source": source, "kind": "durh"})
    by_key = {p["key"]: p for p in snapshot["players"]}

    counts = {c: {PRIMARY: [0] * n_rounds, SECONDARY: [0] * n_rounds, "total": [0] * n_rounds}
              for c in labels}
    counted = 0
    for row in rows:
        if row["rank"] > limit:
            continue
        i = row["rnd"] - 1
        bands = classify(by_key[row["key"]]["values"][source]["d"], labels, band, band_sec)
        for c, verdict in bands.items():
            if verdict is not None:
                counts[c][verdict][i] += 1
                counts[c]["total"][i] += 1
        counted += 1

    if counted != limit:
        raise StudyError(f"expected {limit} players in the pool, counted {counted}")

    return {
        "meta": {
            "generated": snapshot["meta"]["generated"],
            "digest": snapshot["meta"]["digest"][:12],
            "source": source,
            "teams": teams,
            "rounds": n_rounds,
            "pool": limit,
            "band": band,
            "band_sec": band_sec,
        },
        "labels": labels,
        "rounds": list(range(1, n_rounds + 1)),
        "counts": counts,
    }


def totals_by_category(result: dict) -> list[tuple[str, int]]:
    """Each category's total strength count across the whole pool, scarcest last.

    The one-line summary of the whole study: which categories this player pool is deep in
    and which it is thin in, before any per-round shape is considered.
    """
    return sorted(((c, sum(v["total"])) for c, v in result["counts"].items()),
                  key=lambda kv: (-kv[1], kv[0]))


def last_round_with(result: dict, category: str, minimum: int = 1) -> int | None:
    """The deepest round still holding `minimum` players with `category` as a strength.

    "Runs out at round 7" is the actionable form of a scarcity curve, and it is not the
    same as the round the count first hits zero: a category can go quiet for a round and
    come back. This reads the last round that clears the bar, not the first that fails it.
    """
    hits = [r for r, n in zip(result["rounds"], result["counts"][category]["total"], strict=True)
            if n >= minimum]
    return hits[-1] if hits else None


def load_newest(root: Path = BS.ROOT) -> dict:
    """The newest local snapshot, by date in the filename."""
    path = BS.newest(root)
    if path is None:
        raise StudyError(f"no board snapshot under {root} -- run build_data.py first")
    return BS.load(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Category scarcity by round: when does each category run out?")
    ap.add_argument("--source", default="BMP", choices=list(BS.SOURCES),
                    help="projection source whose d the bands are applied to (default BMP)")
    ap.add_argument("--rounds", type=int, default=None,
                    help="rounds of `teams` to measure (default q / teams = 13)")
    ap.add_argument("--json", action="store_true", help="print the counts as JSON, write nothing")
    ap.add_argument("--out", type=Path, default=None,
                    help=f"report path (default {STUDIES}/<date>-category-scarcity.html)")
    args = ap.parse_args(argv)

    try:
        snapshot = load_newest()
        result = scarcity_counts(snapshot, args.source, args.rounds)
    except (StudyError, BS.SnapshotError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    import study_scarcity_render as R

    out = args.out or STUDIES / f"{result['meta']['generated']}-category-scarcity.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(R.render(result), encoding="utf-8")
    m = result["meta"]
    print(f"{out}  ({m['source']}, {m['rounds']} rounds of {m['teams']}, "
          f"{m['pool']} players, board {m['generated']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
