#!/usr/bin/env python3
"""Turn researched injury histories into the board's HIGH / MED / LOW risk tier.

This is a judgement about injury history -- surgeries, recurring problems, age, position
-- never about games played. The board already has a GP column for durability and
deliberately scales nothing by it (ADR-0017); this rubric does not touch games played or
games missed either, in either direction. Two players with an identical injury history are
tiered identically no matter how many games either of them happened to play.

Two halves, deliberately split:

    the research   one JSON record per player, gathered by an agent and committed to
                   `injury_risk.json`. It holds *evidence* -- dated, cited injury events --
                   and never a verdict.
    the rubric     `tier()`, here. It reads that evidence and returns the tier.

The split is ADR-0016 applied to a new column: the sheet holds the result, Python owns the
derivation. It also buys the thing 200 independently-run research agents cannot give you
on their own -- comparability. Agent 7's MED and agent 180's MED are the same MED because
neither of them decided it. And a rubric change costs a `pytest` run rather than 200
re-runs, which is the difference between a tunable model and a frozen one.

Recency still matters -- a freak injury or an old surgery weighs less than a fresh,
recurring one -- but it is read off the injury events themselves (their `season`,
`mechanism`, how many seasons the same body part has failed), never off a season's games
count.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: Bump when the record shape changes. An old file is refused, not guessed at.
SCHEMA = 1

DEFAULT_PATH = Path(__file__).resolve().parent / "injury_risk.json"
DEFAULT_CHECKPOINTS = Path(__file__).resolve().parents[2] / "data" / "injury_research"

#: The seasons a research agent is asked to cover, most recent first. Not a decay curve --
#: nothing here is weighted by games, so there is no games-derived number to decay. Recency
#: shows up instead in the surgery term (a recent major repair outweighs an old one) and
#: implicitly in the chronic term (only a problem recorded in more than one of these
#: seasons counts as recurring).
RECENT = ("2025-26", "2024-25")
OLDER_SCORED = ("2023-24", "2022-23")

#: A season's games, for validating a `games_missed` count -- descriptive only. It is never
#: read into the score: two players with the same injury history tier identically no
#: matter how many games either of them played.
FULL_SEASON = 82

#: Procedures with a multi-month timeline and a documented recurrence profile.
MAJOR_LOWER = 3
MAJOR_LOWER_OLD = 1
MAJOR_UPPER = 1
MINOR_RECENT = 1
SURGERY_MAX = 3

CHRONIC_TWO = 2
CHRONIC_THREE = 3
SOFT_TISSUE_BONUS = 1
CHRONIC_MAX = 4

#: Cuts are absolute, not percentile. A percentile cut would make LOW mean "low relative
#: to this year's field", so the same player's tier would drift every refresh while
#: nothing about him changed. Max score is surgery(3) + chronic(4) + age(2) + guard(1) = 10.
CUT_HIGH = 5
CUT_MED = 3

TIERS = ("LOW", "MED", "HIGH")
UNKNOWN = "?"
VALID_CELL = frozenset(TIERS) | {UNKNOWN}

VALID_COVERAGE = frozenset({"full", "thin", "none"})
VALID_MECHANISM = frozenset({"chronic", "acute", "freak"})
VALID_SURGERY = frozenset({"none", "minor", "major"})
VALID_POS_GROUP = frozenset({"guard", "wing", "big"})
VALID_KIND = frozenset({"soft_tissue", "joint", "bone", "tendon", "other"})

#: Sides and qualifiers are stripped so a left knee and a right knee are still "the knee".
#: Both sides of one joint recurring is the same signal as one side recurring twice.
SIDE = re.compile(r"\b(left|right|l|r|lower|upper|non-?shooting|shooting)\b", re.I)


class InjuryDataError(Exception):
    """A researched injury record is not what the board requires."""


# ------------------------------------------------------------------ the rubric


def _body_part_tokens(raw: str) -> frozenset[str]:
    """Words describing a body part, side- and qualifier-stripped.

    A compound description ("leg/ankle", "ankle/calf/knee") becomes a set of words rather
    than one joined string, so it can overlap with a plain "ankle" or "knee" entry from
    another event. A single joined string treats every differently-phrased mention of the
    same joint as an unrelated body part -- which is how a player with three separate
    lower-body surgeries across a career scored zero recurrence.
    """
    cleaned = re.sub(r"[^a-z ]", " ", SIDE.sub("", (raw or "").lower()))
    return frozenset(t for t in cleaned.split() if t)


def _clean_label(raw: str) -> str:
    """Side-stripped, human-readable body part text -- for display only."""
    cleaned = re.sub(r"[^a-z ]", " ", SIDE.sub("", (raw or "").lower()))
    return re.sub(r"\s+", " ", cleaned).strip()


def surgery_points(record: dict) -> int:
    """The worst surgery on the record, not the sum of them.

    Summing would double-count one deteriorating joint: a meniscus repair and the
    arthroscopic clean-up that follows it are one problem, and a player is not twice as
    fragile for having had both.
    """
    best = 0
    for e in record.get("events") or []:
        season, surgery = e.get("season"), e.get("surgery")
        lower = bool(e.get("lower_body"))
        # "older" scores at the same discounted rate as the two named older seasons, not
        # zero. The schema tells an agent to report an event that old only when it is a
        # major surgery or an established pattern (see the schema docstring) -- precisely
        # the case this term exists to catch, and zero-crediting it contradicted that.
        if surgery == "major":
            if season in RECENT:
                best = max(best, MAJOR_LOWER if lower else MAJOR_UPPER)
            elif season in OLDER_SCORED or season == "older":
                best = max(best, MAJOR_LOWER_OLD if lower else 0)
        elif surgery == "minor" and season in RECENT:
            best = max(best, MINOR_RECENT)
    return min(best, SURGERY_MAX)


def chronic_points(record: dict) -> tuple[int, str | None]:
    """The same body part failing across seasons -- the term that actually predicts.

    Freak events are excluded outright rather than discounted: a facial fracture and a
    hamstring strain are not evidence of one recurring problem just because both happened.

    Two events group as "the same body part" when their word sets overlap at all, via
    union-find over every pair -- so "right knee" and "knee soreness" join, and so does a
    third event bridging through either. Distinct occurrences within one group are counted
    by (season, date), not season alone: two hamstring strains ten weeks apart in the same
    season are two occurrences, not one, and using season alone missed the single most
    literal case of "recurring" this term exists to catch. Two events with no date fall
    back to their position in the list, so an undated multi-surgery career still counts as
    more than one occurrence rather than collapsing into a single bucket.
    """
    events = record.get("events") or []
    idxs = [
        i
        for i, e in enumerate(events)
        if e.get("mechanism") != "freak" and _body_part_tokens(e.get("body_part", ""))
    ]
    tokens = {i: _body_part_tokens(events[i].get("body_part", "")) for i in idxs}

    parent = {i: i for i in idxs}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in range(len(idxs)):
        for b in range(a + 1, len(idxs)):
            if tokens[idxs[a]] & tokens[idxs[b]]:
                ra, rb = find(idxs[a]), find(idxs[b])
                if ra != rb:
                    parent[ra] = rb

    groups: dict[int, list[int]] = {}
    for i in idxs:
        groups.setdefault(find(i), []).append(i)

    best, worst_part = 0, None
    for members in groups.values():
        occurrences: set[tuple] = set()
        soft = False
        for i in members:
            e = events[i]
            occurrences.add((e.get("season"), e.get("date") or f"__idx{i}"))
            soft = soft or e.get("kind") == "soft_tissue"
        n = len(occurrences)
        pts = CHRONIC_THREE if n >= 3 else CHRONIC_TWO if n >= 2 else 0
        if pts and soft:
            pts += SOFT_TISSUE_BONUS
        if pts > best:
            # The most specific description in the group, not just the first-seen one --
            # "knee" reads better than "ankle/calf/knee" when both are in the cluster.
            raw = min(
                (events[i].get("body_part", "") for i in members),
                key=lambda s: len(_body_part_tokens(s)),
            )
            best, worst_part = pts, _clean_label(raw) or None
    return min(best, CHRONIC_MAX), worst_part


def age_points(record: dict) -> int:
    age = record.get("age")
    if age is None:
        return 0
    if age >= 34:
        return 2
    if age >= 31:
        return 1
    return 0


def position_points(record: dict) -> int:
    """Guards carry the highest injury ratios by position (playbook, section 6a)."""
    return 1 if record.get("pos_group") == "guard" else 0


def _recent_major_lower(record: dict) -> bool:
    """A major lower-body surgery inside the last 12 months, by event date."""
    as_of = record.get("as_of") or ""
    for e in record.get("events") or []:
        if e.get("surgery") != "major" or not e.get("lower_body"):
            continue
        date = e.get("date")
        if not date or not as_of:
            continue
        try:
            years = int(as_of[:4]) - int(date[:4])
            months = years * 12 + (int(as_of[5:7]) - int(date[5:7]))
        except (ValueError, IndexError):
            continue
        if 0 <= months <= 12:
            return True
    return False


def score(record: dict) -> dict:
    """The full breakdown behind one tier. `tier()` is the thin wrapper over this.

    Games played or missed never appear here, in either direction -- this is a judgement
    about injury history, not durability. Two players with the same surgeries, the same
    recurring problem, the same age and position tier identically no matter how many games
    either of them happened to play.
    """
    surg = surgery_points(record)
    chronic, part = chronic_points(record)
    age = age_points(record)
    pos = position_points(record)
    total = surg + chronic + age + pos

    coverage = record.get("coverage")
    if coverage == "none":
        tier, reason = UNKNOWN, "no findable history"
    elif total >= CUT_HIGH:
        tier, reason = "HIGH", "score"
    elif total >= CUT_MED:
        tier, reason = "MED", "score"
    else:
        tier, reason = "LOW", "score"

    if tier != UNKNOWN and _recent_major_lower(record):
        tier, reason = "HIGH", "major lower-body surgery within 12 months"
    if tier == "HIGH" and coverage == "thin" and reason == "score":
        tier, reason = "MED", "capped: thin coverage"

    return {
        "tier": tier,
        "total": total,
        "reason": reason,
        "surgery": surg,
        "chronic": chronic,
        "chronic_part": part,
        "age": age,
        "position": pos,
    }


def tier(record: dict) -> str:
    """HIGH, MED, LOW, or `?` when the research found nothing to go on."""
    return score(record)["tier"]


# ------------------------------------------------------------------ the file


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise InjuryDataError(msg)


def validate_record(rec: object, key: str | None = None) -> dict:
    """Reject a record the rubric would otherwise score wrongly and silently."""
    _require(isinstance(rec, dict), f"{key}: record is not an object")
    assert isinstance(rec, dict)
    where = key or rec.get("key") or "<unkeyed>"

    _require(bool(rec.get("key")), f"{where}: missing key")
    if key is not None:
        _require(rec["key"] == key, f"{where}: key does not match its filename")
    _require(bool(rec.get("name")), f"{where}: missing name")
    _require(
        rec.get("coverage") in VALID_COVERAGE,
        f"{where}: coverage {rec.get('coverage')!r} not one of {sorted(VALID_COVERAGE)}",
    )
    _require(
        rec.get("suggested_tier") in TIERS,
        f"{where}: suggested_tier {rec.get('suggested_tier')!r} not one of {list(TIERS)}",
    )
    pos = rec.get("pos_group")
    _require(
        pos is None or pos in VALID_POS_GROUP,
        f"{where}: pos_group {pos!r} not one of {sorted(VALID_POS_GROUP)}",
    )

    gp = rec.get("gp")
    _require(gp is None or isinstance(gp, dict), f"{where}: gp is not an object")
    for season, played in (gp or {}).items():
        _require(
            isinstance(played, (int, float)) and 0 <= played <= FULL_SEASON,
            f"{where}: gp[{season}] = {played!r} is not a games count",
        )

    events = rec.get("events")
    _require(events is None or isinstance(events, list), f"{where}: events is not a list")
    for i, e in enumerate(events or []):
        at = f"{where}: event {i}"
        _require(isinstance(e, dict), f"{at} is not an object")
        _require(
            e.get("mechanism") in VALID_MECHANISM,
            f"{at}: mechanism {e.get('mechanism')!r} not one of {sorted(VALID_MECHANISM)}",
        )
        _require(
            e.get("surgery") in VALID_SURGERY,
            f"{at}: surgery {e.get('surgery')!r} not one of {sorted(VALID_SURGERY)}",
        )
        _require(
            e.get("kind") in VALID_KIND,
            f"{at}: kind {e.get('kind')!r} not one of {sorted(VALID_KIND)}",
        )
        _require(bool(e.get("body_part")), f"{at}: missing body_part")
        gm = e.get("games_missed")
        _require(
            gm is None or (isinstance(gm, (int, float)) and 0 <= gm <= FULL_SEASON),
            f"{at}: games_missed {gm!r} is neither null nor a games count",
        )
        # A per-event source is no longer required -- see the record-level check below --
        # but one that IS given still has to carry a real URL. A citation that names no
        # page is worse than no citation, because it looks verified and is not.
        srcs = e.get("sources")
        _require(
            srcs is None or (isinstance(srcs, list) and all(s.get("url") for s in srcs)),
            f"{at}: sources present but missing a url",
        )

    # Every asserted FACT must be traceable to something, but not to one thing per event --
    # a player's injury history is usually covered by one page, and demanding a citation
    # per incident was the single largest cost driver in this pipeline for no accuracy
    # gain a rubric consuming aggregates could use. So the bar is one real URL anywhere on
    # the record with events: its own `sources`, or any event's. A record with none is a
    # guess, and a guess that looks like a citation is the failure this column must avoid.
    #
    # A record with ZERO events needs no citation. "No injuries found" asserts nothing
    # about an event to fabricate -- the citation requirement exists to keep event facts
    # honest, not to prove a negative was searched for. `coverage` already carries that
    # signal (`full` = verified clean, `none` = unknown) without a source to back it.
    top_srcs = rec.get("sources")
    _require(
        top_srcs is None or (isinstance(top_srcs, list) and all(s.get("url") for s in top_srcs)),
        f"{where}: sources present but missing a url",
    )
    if events:
        any_url = any(s.get("url") for s in (top_srcs or [])) or any(
            s.get("url") for e in events for s in (e.get("sources") or [])
        )
        _require(any_url, f"{where}: no source URL anywhere on the record")
    return rec


def load(path: Path = DEFAULT_PATH) -> dict:
    """Read and validate the committed research file."""
    if not path.exists():
        raise InjuryDataError(f"no injury research at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InjuryDataError(f"{path.name} is not valid JSON: {exc}") from exc

    _require(isinstance(data, dict), f"{path.name}: top level is not an object")
    _require(
        data.get("schema") == SCHEMA,
        f"{path.name}: schema {data.get('schema')!r}, expected {SCHEMA}",
    )
    players = data.get("players")
    _require(isinstance(players, dict), f"{path.name}: players is not an object")
    for key, rec in players.items():
        validate_record(rec, key)
    return data


def tiers_for(board: list, data: dict) -> tuple[list, list, list]:
    """Tier every board row. Returns (tiers, unresearched names, unused keys).

    A board player with no record renders `?`, never blank. AGENTS.md's rule is that a
    hole must not read as data -- and a blank cell in a risk column reads as LOW, which is
    the one reading that would actually cost a pick.
    """
    players = data.get("players", {})
    out, missing = [], []
    for row in board:
        rec = players.get(row["key"])
        if rec is None:
            out.append(UNKNOWN)
            missing.append(row["name"])
        else:
            out.append(tier(rec))
    seen = {row["key"] for row in board}
    unused = sorted(k for k in players if k not in seen)
    return out, missing, unused


def merge(checkpoints: Path = DEFAULT_CHECKPOINTS, generated: str = "") -> tuple:
    """Fold the per-player agent checkpoints into one committed file.

    Returns (data, bad) where `bad` names every checkpoint that failed validation. A
    half-written checkpoint is worse than none, so a caller re-dispatches those rather
    than merging them.
    """
    players, bad = {}, []
    for f in sorted(checkpoints.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            validate_record(rec, f.stem)
        except (json.JSONDecodeError, InjuryDataError) as exc:
            bad.append(f"{f.stem}: {exc}")
            continue
        players[f.stem] = rec
    data = {
        "schema": SCHEMA,
        "generated": generated,
        "players": dict(sorted(players.items())),
    }
    return data, bad


# ------------------------------------------------------------------ the report


def _event_line(e: dict) -> str:
    bits = [e.get("season", "?"), e.get("diagnosis") or e.get("body_part", "")]
    gm = e.get("games_missed")
    if gm is not None:
        bits.append(f"{int(gm)} game" + ("" if int(gm) == 1 else "s"))
    if e.get("surgery") in ("minor", "major"):
        bits.append(f"{e['surgery']} surgery")
    if e.get("mechanism") in ("chronic", "freak"):
        bits.append(e["mechanism"])
    return " — ".join(b for b in bits if b)


def render_report(data: dict, order: list | None = None) -> str:
    """The committed per-player report. Bullets only; nobody reads an essay on the clock."""
    players = data.get("players", {})
    keys = (
        [r["key"] for r in order if r["key"] in players]
        if order
        else sorted(players, key=lambda k: players[k].get("name", k))
    )
    scored = [(k, players[k], score(players[k])) for k in keys]
    counts = {t: sum(1 for _, _, s in scored if s["tier"] == t) for t in TIERS}
    counts[UNKNOWN] = sum(1 for _, _, s in scored if s["tier"] == UNKNOWN)

    out = [
        "# Injury risk",
        "",
        "<!-- Generated by scripts/draft-board/injury_risk.py. Do not hand-edit. -->",
        "",
        f"Research as of {data.get('generated') or 'unknown'}. "
        f"{len(scored)} players — "
        + ", ".join(f"{counts[t]} {t}" for t in (*TIERS, UNKNOWN))
        + ".",
        "",
        "Tiers are computed, not typed: each player's cited injury history is scored by "
        "the rubric in `injury_risk.py` and cut at fixed thresholds "
        f"(≥{CUT_HIGH} HIGH, {CUT_MED}–{CUT_HIGH - 1} MED, ≤{CUT_MED - 1} LOW) on surgery, "
        "the same body part recurring across seasons, age and position. `?` means the "
        "research found nothing to go on, not that the player is clean.",
        "",
        "Never games played, in either direction: two players with the same injury "
        "history tier identically no matter how many games either of them played. The "
        "board's own GP columns are a separate signal, and neither scales the other "
        "(ADR-0017).",
        "",
    ]

    for group in (*TIERS[::-1], UNKNOWN):
        rows = [(k, r, s) for k, r, s in scored if s["tier"] == group]
        if not rows:
            continue
        out += [f"## {group} ({len(rows)})", ""]
        for _, rec, s in rows:
            bits = []
            if s["surgery"]:
                bits.append(f"surgery {s['surgery']}")
            if s["chronic"]:
                bits.append(f"chronic {s['chronic']} ({s['chronic_part']})")
            if s["age"]:
                bits.append(f"age {s['age']}")
            if s["position"]:
                bits.append("guard 1")
            head = f"**{rec.get('name')}** — score {s['total']}"
            if bits:
                head += " (" + " + ".join(bits) + ")"
            if s["reason"] != "score":
                head += f" · {s['reason']}"
            out.append(head)
            for e in rec.get("events") or []:
                out.append(f"- {_event_line(e)}")
            for x in rec.get("expert_reads") or []:
                out.append(
                    f"- *{x.get('analyst')} ({x.get('outlet')}, {x.get('date')}):* {x.get('read')}"
                )
            if rec.get("load_management"):
                out.append("- Routinely rested on healthy nights")
            if rec.get("open_status"):
                out.append(f"- Now: {rec['open_status']}")
            if rec.get("coverage") != "full":
                out.append(f"- Coverage: {rec.get('coverage')}")
            if rec.get("suggested_tier") and rec["suggested_tier"] != s["tier"]:
                out.append(f"- Researcher said {rec['suggested_tier']}, rubric says {s['tier']}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


# ------------------------------------------------------------------ the CLI


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Turn researched injury histories into the board's risk tier."
    )
    ap.add_argument("--merge", action="store_true", help="fold checkpoints into the file")
    ap.add_argument("--report", action="store_true", help="write the markdown report")
    ap.add_argument("--checkpoints", type=Path, default=DEFAULT_CHECKPOINTS)
    ap.add_argument("--path", type=Path, default=DEFAULT_PATH)
    ap.add_argument("--date", default="", help="research date stamped into the file")
    ap.add_argument("--out", type=Path, help="report destination (default: stdout)")
    args = ap.parse_args(argv)

    if args.merge:
        data, bad = merge(args.checkpoints, args.date)
        for b in bad:
            print(f"  rejected {b}", file=sys.stderr)
        args.path.write_text(
            json.dumps(data, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        counts: dict = {}
        for rec in data["players"].values():
            t = tier(rec)
            counts[t] = counts.get(t, 0) + 1
        print(f"merged {len(data['players'])} records into {args.path.name}")
        print("  " + ", ".join(f"{counts.get(t, 0)} {t}" for t in (*TIERS, UNKNOWN)))
        if bad:
            print(f"  {len(bad)} rejected — re-run those players", file=sys.stderr)
            return 1

    if args.report:
        data = load(args.path)
        text = render_report(data)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
