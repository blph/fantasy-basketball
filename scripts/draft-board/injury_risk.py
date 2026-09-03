#!/usr/bin/env python3
"""Turn researched injury histories into the board's HIGH / MED / LOW risk tier.

The board scales nothing by games played (ADR-0017). This column is the other half of
that decision: the GP columns give you the number, and this gives you the reason to
distrust it. It is context for a judgement call, never a multiplier.

Two halves, deliberately split:

    the research   one JSON record per player, gathered by an agent and committed to
                   `injury_risk.json`. It holds *evidence* -- dated, cited injury events
                   and season games-played -- and never a verdict.
    the rubric     `tier()`, here. It reads that evidence and returns the tier.

The split is ADR-0016 applied to a new column: the sheet holds the result, Python owns the
derivation. It also buys the thing 200 independently-run research agents cannot give you
on their own -- comparability. Agent 7's MED and agent 180's MED are the same MED because
neither of them decided it. And a rubric change costs a `pytest` run rather than 200
re-runs, which is the difference between a tunable model and a frozen one.

Recency is weighted because the playbook says the signal lives there: a lost season from
one freak injury "says nothing about next year", while "recurring soft-tissue or joint
problems" are "the part of injury history that actually predicts".
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

#: Roughly a 1.3-season half-life. Last season is the only one that counts in full.
SEASON_WEIGHTS = {
    "2025-26": 1.00,
    "2024-25": 0.55,
    "2023-24": 0.30,
    "2022-23": 0.15,
    "older": 0.05,
}

#: The two most recent seasons, for the surgery term's "recent" test.
RECENT = ("2025-26", "2024-25")
OLDER_SCORED = ("2023-24", "2022-23")

FULL_SEASON = 82

#: What a `freak` event keeps. A broken hand from a collision is not a durability signal,
#: but it is not nothing either -- it still cost you the games.
FREAK_WEIGHT = 0.25

#: Weighted games missed -> points. Bands rather than a slope: the column is a three-way
#: sort, and a continuous term would imply a precision the underlying reporting lacks.
MISSED_BANDS = ((6, 0), (14, 1), (25, 2), (40, 3))
MISSED_MAX = 4

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
#: nothing about him changed.
CUT_HIGH = 6
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


def _season_weight(season: str) -> float:
    return SEASON_WEIGHTS.get(season, SEASON_WEIGHTS["older"])


def _body_part(raw: str) -> str:
    """Normalise a body part so both sides of one joint group together."""
    return re.sub(r"[^a-z ]", "", SIDE.sub("", (raw or "").lower())).strip()


def _season_missed(season: str, gp: dict, events: list) -> float | None:
    """Games missed in one season, or None if the season cannot be scored.

    Two routes, preferring the precise one. When every event in the season carries a
    games-missed count, sum them -- that isolates injury from rest and from a role change.
    Otherwise fall back to `82 - GP`, which is blunter but honest: the playbook's whole
    argument for the GP column is that games-played history does not hedge.

    The event route is capped at the season's real absence, because two overlapping
    injuries cannot cost more games than the player actually missed.
    """
    in_season = [e for e in events if e.get("season") == season]
    played = gp.get(season)
    from_gp = None if played is None else max(0.0, FULL_SEASON - float(played))

    counted = [e for e in in_season if e.get("games_missed") is not None]
    if in_season and len(counted) == len(in_season):
        total = sum(
            float(e["games_missed"]) * (FREAK_WEIGHT if e.get("mechanism") == "freak" else 1.0)
            for e in in_season
        )
        return total if from_gp is None else min(total, from_gp)

    if from_gp is None:
        return None

    # No usable event breakdown. Discount the part of the absence a known freak event
    # explains, so one broken hand does not read as fragility.
    freak = sum(
        float(e["games_missed"])
        for e in in_season
        if e.get("mechanism") == "freak" and e.get("games_missed") is not None
    )
    return max(0.0, from_gp - freak * (1.0 - FREAK_WEIGHT))


def availability_points(record: dict) -> tuple[int, float | None]:
    """Recency-weighted games missed, banded. Returns (points, weighted average)."""
    gp = record.get("gp") or {}
    events = record.get("events") or []
    seasons = [s for s in SEASON_WEIGHTS if s != "older" and s in gp]
    if not seasons:
        return 0, None

    num = den = 0.0
    for s in seasons:
        missed = _season_missed(s, gp, events)
        if missed is None:
            continue
        w = _season_weight(s)
        num += w * missed
        den += w
    if den == 0:
        return 0, None

    avg = num / den
    for ceiling, pts in MISSED_BANDS:
        if avg <= ceiling:
            return pts, avg
    return MISSED_MAX, avg


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
        if surgery == "major":
            if season in RECENT:
                best = max(best, MAJOR_LOWER if lower else MAJOR_UPPER)
            elif season in OLDER_SCORED:
                best = max(best, MAJOR_LOWER_OLD if lower else 0)
        elif surgery == "minor" and season in RECENT:
            best = max(best, MINOR_RECENT)
    return min(best, SURGERY_MAX)


def chronic_points(record: dict) -> tuple[int, str | None]:
    """The same body part failing across seasons -- the term that actually predicts.

    Freak events are excluded outright rather than discounted: a facial fracture and a
    hamstring strain are not evidence of one recurring problem just because both happened.
    """
    by_part: dict[str, set] = {}
    soft: dict[str, bool] = {}
    for e in record.get("events") or []:
        if e.get("mechanism") == "freak":
            continue
        part = _body_part(e.get("body_part", ""))
        if not part:
            continue
        by_part.setdefault(part, set()).add(e.get("season"))
        if e.get("kind") == "soft_tissue":
            soft[part] = True

    best, worst_part = 0, None
    for part, seasons in by_part.items():
        n = len(seasons)
        pts = CHRONIC_THREE if n >= 3 else CHRONIC_TWO if n >= 2 else 0
        if pts and soft.get(part):
            pts += SOFT_TISSUE_BONUS
        if pts > best:
            best, worst_part = pts, part
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
    """The full breakdown behind one tier. `tier()` is the thin wrapper over this."""
    avail, avg = availability_points(record)
    surg = surgery_points(record)
    chronic, part = chronic_points(record)
    age = age_points(record)
    pos = position_points(record)
    total = avail + surg + chronic + age + pos

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
        "availability": avail,
        "weighted_missed": None if avg is None else round(avg, 1),
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
        # Every asserted fact must be traceable. An uncited event is a guess, and a guess
        # that looks like a citation is the failure this whole column has to avoid.
        srcs = e.get("sources")
        _require(
            bool(isinstance(srcs, list) and srcs and all(s.get("url") for s in srcs)),
            f"{at}: no source URL",
        )
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
        f"(≥{CUT_HIGH} HIGH, {CUT_MED}–{CUT_HIGH - 1} MED, ≤{CUT_MED - 1} LOW). Recent "
        "seasons weigh more: "
        + ", ".join(f"{s} ×{w:g}" for s, w in SEASON_WEIGHTS.items() if s != "older")
        + ". `?` means the research found nothing to go on, not that the player is clean.",
        "",
        "The board scales nothing by games played (ADR-0017). This is context for a "
        "judgement call, not a multiplier.",
        "",
    ]

    for group in (*TIERS[::-1], UNKNOWN):
        rows = [(k, r, s) for k, r, s in scored if s["tier"] == group]
        if not rows:
            continue
        out += [f"## {group} ({len(rows)})", ""]
        for _, rec, s in rows:
            bits = []
            if s["availability"]:
                bits.append(f"availability {s['availability']}")
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
            gp = rec.get("gp") or {}
            if gp:
                out.append(
                    "- GP: " + ", ".join(f"{s2} {int(gp[s2])}" for s2 in SEASON_WEIGHTS if s2 in gp)
                )
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
