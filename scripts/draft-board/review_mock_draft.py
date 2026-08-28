#!/usr/bin/env python3
"""Grade a mock draft against the board and the playbook.

The method is documented in `docs/draft-board/mock-draft-review.md`; this file
is its computation. Every artifact below maps to a step in that document, and
where the two disagree the document is the specification.

Inputs are the two `playwright-cli` pulls described in that document's Step 1 —
`Draft Board!A2:Z202` and `Board!A3:CA202` — plus a draft log. Those CSVs are
provider data and live outside the repo; nothing here holds player data, and
there is no I/O beyond the paths given on the command line, which is what makes
this file safe to commit (ADR-0006).

Two properties this file exists to protect, both of which a hand analysis got
wrong before it existed:

  - The shortlist at any pick is the player's own tier. Comparing across tiers
    produces recommendations that read well and reach three tiers down.
  - A one-player substitution is the wrong instrument. It reports no change on
    a roster whose deficits run deeper than one player, so the ceiling is
    hill-climbed instead.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass, field

# --- The nine categories ----------------------------------------------------
# `lower_is_better` inverts the comparison; turnovers are the only one.
# Keys match config/league.yaml. The two percentages are volume-weighted and
# never appear as bare rates — see docs/database/schema.md.
CATS = ["fgp", "ftp", "tpm", "pts", "reb", "ast", "stl", "blk", "to"]
LOWER_IS_BETTER = {"to"}
LABEL = {
    "fgp": "FG%",
    "ftp": "FT%",
    "tpm": "3PM",
    "pts": "PTS",
    "reb": "REB",
    "ast": "AST",
    "stl": "STL",
    "blk": "BLK",
    "to": "TO",
}
# The g-score block on the Board tab uses its own short keys, in column order.
GKEYS = ["fg", "ft", "tpm", "pts", "reb", "ast", "stl", "blk", "to"]
GKEY_FOR = dict(zip(CATS, GKEYS, strict=True))

# ADR-0010 ships nine builds. Order is the column order on the Board tab; the
# Draft Board MATCHes across the rank span as one range, so it must not drift.
PUNTS = ["FT%", "FG%", "AST", "3PM", "BLK", "FG%+REB", "AST+STL", "PTS+FT%", "FG/FT/TO"]

# Board!A3:CA202 column offsets. The header row spans merged blocks, so position
# is the only reliable handle. Mirrors the table in mock-draft-review.md.
COL_SEED, COL_NAME, COL_TEAM, COL_POS = 0, 1, 2, 3
COL_GP = 5
COL_RAW = {  # the per-game projection block
    "fgm": 7,
    "fga": 8,
    "fgp": 9,
    "ftm": 10,
    "fta": 11,
    "ftp": 12,
    "tpm": 13,
    "pts": 14,
    "reb": 15,
    "ast": 16,
    "stl": 17,
    "blk": 18,
    "to": 19,
}
COL_Z0, COL_ZTOT = 22, 31
COL_G0, COL_GTOT = 32, 41
COL_VOR = 42
COL_MYGP, COL_ADJVAL, COL_ADJRANK = 47, 49, 50
COL_ADP, COL_GAP = 51, 53
COL_PUNT0, COL_PUNTRANK0 = 54, 63
DETAIL_WIDTH = 73

# Draft Board!A2:Z202 offsets.
DB_RANK, DB_TIER, DB_NAME, DB_TEAM, DB_POS = 0, 1, 2, 3, 4
DB_ADJVAL, DB_PROJGP, DB_MYGP, DB_ADP, DB_GAP = 5, 11, 12, 13, 15
DB_BUILD, DB_PROFILE, DB_LEFT = 16, 17, 18

# Playbook s10, "marginal value of the same sliver of capital". Value peaks at
# the coin flip and collapses at both ends; this is the table the review uses to
# price where a pick went.
MARGINAL = [(0.05, 0.31), (0.30, 0.97), (0.50, 1.09), (0.85, 0.60), (0.95, 0.26)]

# Playbook s10's four simulated archetypes, for placing a roster's shape.
ARCHETYPES = [
    ("Balanced", [0.63] * 9, 0.794),
    ("Soft punt 2", [0.73] * 7 + [0.27] * 2, 0.805),
    ("Stack 3 hard", [0.92] * 3 + [0.42] * 6, 0.725),
    ("Stack 3 extreme", [0.96] * 3 + [0.34] * 6, 0.636),
]

GRADE_BANDS = [
    (9.5, "A+"),
    (8.8, "A"),
    (8.3, "A-"),
    (7.8, "B+"),
    (7.2, "B"),
    (6.7, "B-"),
    (6.2, "C+"),
    (5.5, "C"),
    (5.0, "C-"),
    (4.5, "D+"),
    (3.8, "D"),
]


class ReviewError(Exception):
    """The input does not look like a board pull or a draft log."""


# --- Parsing ----------------------------------------------------------------


def norm(name: str) -> str:
    """Fold a player name to a join key.

    Providers and draft logs disagree on diacritics and generational suffixes,
    and the two must join or a roster silently loses a player. Strips accents
    (Jokic, Doncic, Porzingis, Sengun) and Jr./III/II/Sr./IV.
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z ]", "", s.lower())
    s = re.sub(r"\b(jr|iii|ii|sr|iv)\b", "", s)
    return " ".join(s.split())


def num(cell: str | None) -> float | None:
    """Read a sheet cell as a number, or None if it is blank.

    The sheet renders negatives with U+2212 MINUS SIGN and signs its z and g
    columns explicitly, neither of which float() accepts.
    """
    if cell is None:
        return None
    s = cell.strip().replace("−", "-").replace("+", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class Player:
    """One board row, joined across the Draft Board and Board tabs."""

    name: str
    rank: int
    tier: int
    pos: str = ""
    adjval: float = 0.0
    mygp: float = 0.0
    adp: float | None = None
    gap: float | None = None
    build: str = ""
    gtot: float | None = None
    vor: float | None = None
    raw: dict[str, float] = field(default_factory=dict)
    g: dict[str, float] = field(default_factory=dict)
    punt: dict[str, float] = field(default_factory=dict)


def parse_draft_board(rows) -> dict[str, Player]:
    """Read `Draft Board!A2:Z202`. Carries TIER, which nothing else does."""
    out: dict[str, Player] = {}
    for row in rows:
        if len(row) <= DB_LEFT or not row[DB_RANK].strip().isdigit():
            continue  # the merged header rows, and the trailing blanks
        name = row[DB_NAME].strip()
        tier = num(row[DB_TIER])
        if not name or tier is None:
            raise ReviewError(f"row {row[DB_RANK]!r}: missing player name or tier")
        out[norm(name)] = Player(
            name=name,
            rank=int(row[DB_RANK]),
            tier=int(tier),
            pos=row[DB_POS].strip(),
            adjval=num(row[DB_ADJVAL]) or 0.0,
            mygp=num(row[DB_MYGP]) or 0.0,
            adp=num(row[DB_ADP]),
            gap=num(row[DB_GAP]),
            build=row[DB_BUILD].strip(),
        )
    if not out:
        raise ReviewError("no player rows in the Draft Board range")
    return out


def parse_board_detail(rows, players: dict[str, Player]) -> dict[str, Player]:
    """Merge `Board!A3:CA202` into the players from `parse_draft_board`."""
    seen = 0
    for row in rows:
        if len(row) < DETAIL_WIDTH or not row[COL_NAME].strip():
            continue
        key = norm(row[COL_NAME])
        p = players.get(key)
        if p is None:
            continue  # on the Board tab but past the Draft Board's export cut
        p.raw = {k: num(row[c]) or 0.0 for k, c in COL_RAW.items()}
        p.raw["gp"] = num(row[COL_GP]) or 0.0
        p.g = {k: num(row[COL_G0 + i]) or 0.0 for i, k in enumerate(GKEYS)}
        p.gtot = num(row[COL_GTOT])
        p.vor = num(row[COL_VOR])
        p.punt = {b: num(row[COL_PUNT0 + i]) or 0.0 for i, b in enumerate(PUNTS)}
        seen += 1
    if not seen:
        raise ReviewError("no Board rows joined onto the Draft Board — check the range")
    return players


def check_replacement(players: dict[str, Player], expected: float, tol: float = 0.01) -> float:
    """Stop-the-line check: `G TOTAL - VOR` must be the replacement level.

    Every value on the board is measured against it, so a mismatch means the
    pull is stale or a range has shifted, and nothing computed after this point
    would mean anything.
    """
    for p in players.values():
        if p.gtot is None or p.vor is None:
            continue
        implied = p.gtot - p.vor
        if abs(implied - expected) > tol:
            raise ReviewError(
                f"{p.name}: implied replacement {implied:.4f} != Settings {expected:.4f}. "
                "The pull is stale or a range has shifted."
            )
        return implied
    raise ReviewError("no row carried both G TOTAL and VOR")


def parse_draft_log(rows) -> list[tuple[int, int, str, str]]:
    """Read `round,pick,manager,player`, one line per pick."""
    out = []
    for lineno, row in enumerate(rows, start=1):
        if not row or not row[0].strip() or row[0].strip().lower() == "round":
            continue
        if len(row) < 4:
            raise ReviewError(f"draft log line {lineno}: expected 4 fields, got {len(row)}")
        try:
            rnd, pick = int(row[0]), int(row[1])
        except ValueError as exc:
            raise ReviewError(f"draft log line {lineno}: round and pick must be integers") from exc
        out.append((rnd, pick, row[2].strip(), row[3].strip()))
    if not out:
        raise ReviewError("draft log is empty")
    return out


# --- Draft reconstruction ---------------------------------------------------


def snake_slots(teams: int, rounds: int, slot: int) -> list[int]:
    """Overall pick numbers for one seat in a snake draft.

    Odd rounds run 1..T, even rounds run back T..1, so an even round's seat is
    T - slot + 1. Slot 10 of 14 gives 10, 19, 38, 47, ...
    """
    if not 1 <= slot <= teams:
        raise ReviewError(f"slot {slot} is outside 1..{teams}")
    out = []
    for r in range(rounds):
        within = slot if r % 2 == 0 else teams - slot + 1
        out.append(r * teams + within)
    return out


def rosters_from_log(log) -> dict[str, list[str]]:
    """Group a draft log into one normalised roster per manager, in pick order."""
    out: dict[str, list[str]] = {}
    for _, _, manager, player in log:
        out.setdefault(manager, []).append(norm(player))
    return out


def taken_before_each_pick(log) -> list[set[str]]:
    """For every pick in the log, the set of players already off the board."""
    out, seen = [], set()
    for _, _, _, player in log:
        out.append(set(seen))
        seen.add(norm(player))
    return out


# --- Artifact A/B: totals, standings, gap-to-flip ---------------------------


def team_totals(names, players, divisor: float, size: int) -> dict[str, float]:
    """The nine category aggregates for one roster.

    Each player contributes his per-game line scaled by `My GP Est / divisor`.
    Playbook s6a: that is the exact expected season value under replacement-
    level backfill, not an approximation.

    Percentages are team makes over team attempts. Averaging individual rates
    counts a 3-shot night the same as an 18-shot one and is the single most
    common way to get a 9-cat board wrong.

    Rosters short of `size` are scaled up so teams of different lengths — some
    drafted players fall outside the board's rows — remain comparable.
    """
    known = [players[n] for n in names if n in players and players[n].raw]
    if not known:
        raise ReviewError("roster joined to no board rows")
    scale = size / len(known)
    acc = dict.fromkeys(["fgm", "fga", "ftm", "fta", *CATS], 0.0)
    for p in known:
        w = (p.mygp or p.raw.get("gp", 0.0)) / divisor
        for k in ("fgm", "fga", "ftm", "fta"):
            acc[k] += p.raw[k] * w
        for c in CATS:
            if c not in ("fgp", "ftp"):
                acc[c] += p.raw[c] * w
    out = {c: acc[c] * scale for c in CATS if c not in ("fgp", "ftp")}
    out["fgp"] = acc["fgm"] / acc["fga"] if acc["fga"] else 0.0
    out["ftp"] = acc["ftm"] / acc["fta"] if acc["fta"] else 0.0
    return out


def beats(mine: dict[str, float], theirs: dict[str, float], cat: str) -> bool:
    """Does `mine` win this category? Turnovers run the other way."""
    return mine[cat] < theirs[cat] if cat in LOWER_IS_BETTER else mine[cat] > theirs[cat]


def record(mine, opponents) -> tuple[int, dict[str, int]]:
    """Category record over a round robin: wins, and wins per category."""
    per = dict.fromkeys(CATS, 0)
    for opp in opponents:
        for c in CATS:
            if beats(mine, opp, c):
                per[c] += 1
    return sum(per.values()), per


def standings(totals: dict[str, dict[str, float]]) -> list[tuple[str, int, int]]:
    """Every manager's category record against every other. Best first."""
    out = []
    for me, mine in totals.items():
        others = [t for k, t in totals.items() if k != me]
        won, _ = record(mine, others)
        out.append((me, won, len(others) * len(CATS) - won))
    return sorted(out, key=lambda r: -r[1])


def gap_to_flip(mine, opponents) -> dict[str, dict]:
    """Per category: the record, and how far from changing it.

    The distance to the next flip is what makes wasted margin legible. A
    category lost 0-13 by half a percent and one won 13-0 by fifteen are the
    same mistake seen from two sides.
    """
    out = {}
    for c in CATS:
        lost = [o[c] for o in opponents if not beats(mine, o, c)]
        won = [o[c] for o in opponents if beats(mine, o, c)]
        row = {"mine": mine[c], "won": len(won), "lost": len(lost)}
        if lost:
            # The cheapest flip is the weakest opponent still beating me: the
            # smallest total I must clear, or the largest turnover count I must
            # get under. Taking the extreme the other way measures the distance
            # to sweeping the category, which is not a decision anyone makes.
            nearest = max(lost) if c in LOWER_IS_BETTER else min(lost)
            row["next_flip"] = abs(nearest - mine[c])
            row["next_flip_pct"] = abs(nearest - mine[c]) / abs(mine[c]) * 100 if mine[c] else 0.0
        if won and not lost:
            # Symmetrically, surplus is measured against the closest rival I
            # still beat — the margin I could give up and keep the category.
            hardest = min(won) if c in LOWER_IS_BETTER else max(won)
            row["surplus"] = abs(mine[c] - hardest)
            row["surplus_pct"] = abs(mine[c] - hardest) / abs(mine[c]) * 100 if mine[c] else 0.0
        out[c] = row
    return out


# --- Artifact C: the Category Tracker trace ---------------------------------


def tracker_trace(my_picks, players, teams, bands) -> list[dict[str, str]]:
    """Reproduce the Category Tracker after each pick.

    Benchmark is what an average team holds *at the current roster size*: the
    mean of the top `teams x n` by Adj Rank, times n. Measuring against the
    whole pool instead reads STRONG on everything through about round ten,
    which is exactly when the tracker needs to say something (finding F4).
    """
    by_rank = sorted((p for p in players.values() if p.raw), key=lambda p: p.rank)
    rows = []
    for n in range(1, len(my_picks) + 1):
        mine = [players[k] for k in my_picks[:n] if k in players and players[k].raw]
        pool = by_rank[: teams * n]
        row = {}
        for c in CATS:
            if c in ("fgp", "ftp"):
                mk, at = ("fgm", "fga") if c == "fgp" else ("ftm", "fta")
                mv = sum(p.raw[mk] for p in mine) / max(sum(p.raw[at] for p in mine), 1e-9)
                bv = sum(p.raw[mk] for p in pool) / max(sum(p.raw[at] for p in pool), 1e-9)
                band = bands[c]
            else:
                mv = sum(p.raw[c] for p in mine)
                bv = sum(p.raw[c] for p in pool) / len(pool) * n
                band = bands["counting"] * abs(bv)
            diff = (bv - mv) if c in LOWER_IS_BETTER else (mv - bv)
            row[c] = "STRONG" if diff > band else ("WEAK" if diff < -band else "EVEN")
        rows.append(row)
    return rows


def needs_from_trace(trace_row: dict[str, str]) -> list[str]:
    """The categories a pick should be spent on: anything not already STRONG.

    Playbook s10, printed on the tracker itself: spend the next pick on an EVEN
    category, not a STRONG one.
    """
    return [c for c in CATS if trace_row[c] != "STRONG"]


# --- Artifact D: which build was actually drafted ---------------------------


def detect_build(names, players) -> list[tuple[str, float]]:
    """Rank the nine punt builds by how well the roster fits each.

    A roster has a build whether or not its manager declared one. When a punt
    column beats the standard total by a wide margin, playbook s6b applies: the
    primary sort should have switched once the build revealed itself.
    """
    known = [players[n] for n in names if n in players and players[n].punt]
    if not known:
        raise ReviewError("roster joined to no punt columns")
    return sorted(((b, sum(p.punt[b] for p in known)) for b in PUNTS), key=lambda r: -r[1])


# --- Artifact E: playbook s10 marginal value --------------------------------


def marginal_value(rate: float) -> float:
    """Price the next slice of capital in a category at this win rate.

    Linear interpolation of playbook s10's table. Value peaks at the coin flip
    (+1.09) and collapses at both ends, so capital in a category already won is
    nearly as wasted as capital in one abandoned.
    """
    if rate <= MARGINAL[0][0]:
        return MARGINAL[0][1]
    if rate >= MARGINAL[-1][0]:
        return MARGINAL[-1][1]
    for (x0, y0), (x1, y1) in zip(MARGINAL, MARGINAL[1:], strict=False):
        if x0 <= rate <= x1:
            return y0 + (y1 - y0) * (rate - x0) / (x1 - x0)
    return MARGINAL[-1][1]


def closest_archetype(rates: list[float]) -> tuple[str, float, float]:
    """Which of s10's four shapes a roster most resembles.

    Compares sorted profiles, so it matches on shape rather than on which
    particular categories are strong. Returns the name, its simulated match-win
    rate, and the L1 distance — a large distance means the roster is more
    extreme than anything s10 simulated, which is itself the finding.
    """
    mine = sorted(rates, reverse=True)
    best = ARCHETYPES[0]
    dist = float("inf")
    for arch in ARCHETYPES:
        d = sum(abs(a - b) for a, b in zip(mine, sorted(arch[1], reverse=True), strict=True))
        if d < dist:
            best, dist = arch, d
    return best[0], best[2], dist


# --- Artifact F: tier-legal alternatives and the ceiling --------------------


def need_fit(player: Player, needs: list[str]) -> float:
    """Sum of a player's g-scores across the categories still needing help."""
    return sum(player.g.get(GKEY_FOR[c], 0.0) for c in needs)


def tier_alternatives(pick: str, players, taken: set[str]) -> list[Player]:
    """The shortlist at a pick: same tier, still on the board.

    Playbook s8 step 1 makes the live tier the shortlist. Anything outside it
    is a reach and does not belong in the comparison — comparing across tiers
    is what produced a Tier 7 recommendation over a Tier 4 player the first
    time this review was run by hand.
    """
    me = players[pick]
    return [
        p for k, p in players.items() if p.tier == me.tier and p.g and (k == pick or k not in taken)
    ]


def s8_violated(pick: Player, shortlist, needs, close=0.25, margin=1.0) -> bool:
    """Did a same-tier player, at essentially the same value, fit better?

    Playbook s8 step 4 makes category need the tiebreak, and step 3's proviso
    is that it "only fires when value is close". Both conditions have to hold:
    a materially better fit a full tier down is not a violation, and a better
    fit at much lower value is the tiebreak being correctly declined.
    """
    mine = need_fit(pick, needs)
    return any(
        other is not pick
        and abs(other.adjval - pick.adjval) <= close
        and need_fit(other, needs) - mine >= margin
        for other in shortlist
    )


def tier_legal_ceiling(my_picks, candidates, players, opponents, divisor, size, rounds=8):
    """Hill-climb to the best roster reachable with same-tier swaps only.

    Single substitutions understate everything: one player is a small share of
    a roster, so a swap that fixes nothing on its own can be part of a set that
    fixes three categories. Climbing finds those; testing one at a time does
    not.
    """

    def score_of(roster):
        return record(team_totals(roster, players, divisor, size), opponents)[0]

    def climb(start):
        cur = list(start)
        cur_score = score_of(cur)
        for _ in range(rounds):
            improved = False
            for i in range(len(cur)):
                for cand in candidates[i]:
                    if cand in cur and cand != cur[i]:
                        continue
                    trial = list(cur)
                    trial[i] = cand
                    if len(set(trial)) < len(trial):
                        continue
                    score = score_of(trial)
                    if score > cur_score:
                        cur, cur_score, improved = trial, score, True
            if not improved:
                break
        return cur, cur_score

    # Hill-climbing from one start lands in a local optimum, and on this shape
    # it lands well short. Three deterministic starts — as drafted, best value
    # in each tier, best fit in each tier — approach the true ceiling without
    # the non-reproducibility of random restarts.
    starts = [list(my_picks)]
    for key in ("adjval", "fit"):
        seed, used = [], set()
        for i, slot in enumerate(candidates):
            pool = [c for c in slot if c in players and c not in used] or [my_picks[i]]
            if key == "adjval":
                pick = max(pool, key=lambda c: players[c].adjval)
            else:
                pick = max(pool, key=lambda c: sum(players[c].g.values()))
            seed.append(pick)
            used.add(pick)
        starts.append(seed)

    best, best_score = list(my_picks), score_of(my_picks)
    for start in starts:
        if len(set(start)) < len(start):
            continue
        cand_roster, cand_score = climb(start)
        if cand_score > best_score:
            best, best_score = cand_roster, cand_score
    return best, best_score


# --- Step 4: grading --------------------------------------------------------


@dataclass
class Grade:
    """One pick's score, with every component itemised so it can be argued."""

    score: float
    letter: str
    forced: bool
    components: dict[str, float]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def letter_for(score: float) -> str:
    for cut, letter in GRADE_BANDS:
        if score >= cut:
            return letter
    return "F"


# A pick that captures the top of its tier, fits the roster, and carries no
# market edge lands here. Market timing earns the last point; it cannot buy back
# a fit failure, which an earlier version of this rubric let it do.
BASE_SCORE = 9.0


def grade_pick(
    *,
    round_no: int,
    adjv_rank: int,
    n_tier: int,
    my_need: float,
    best_need: float,
    gap: float | None,
    mygp: float,
    pool_avg_gp: float,
    dominated: bool = False,
    s8_violation: bool = False,
    s9_violation: bool = False,
) -> Grade:
    """Score one pick. See mock-draft-review.md Step 4.

    Two exemptions, both from the playbook rather than from charity:

    A tier holding one player is a forced pick, so the value and fit terms are
    zeroed — a manager cannot be graded on a choice the board did not give him.
    Roughly half the picks in a real mock come out forced.

    Rounds 1-2 are exempt from the fit term. Playbook s9 says to take best
    available and commit to nothing, and s8 adds that the overrides "start
    earning their keep around round 3". A lopsided first-round pick is the plan
    working. The s8 tiebreak still applies, because that rule is not
    round-dependent.
    """
    forced = n_tier <= 1
    early = round_no <= 2
    comp = {}
    comp["value"] = 0.0 if forced else -clamp(2.5 * (adjv_rank - 1) / (n_tier - 1), 0.0, 2.5)
    comp["fit"] = 0.0 if (forced or early) else -clamp(0.6 * (best_need - my_need), 0.0, 3.5)
    comp["market"] = clamp(gap / 25.0, -1.0, 1.0) if gap is not None else 0.0
    comp["availability"] = -clamp((pool_avg_gp - mygp) / 10.0, 0.0, 1.5)
    comp["dominated"] = -2.0 if (dominated and not forced) else 0.0
    comp["s8"] = -1.5 if s8_violation else 0.0
    comp["s9"] = -1.0 if s9_violation else 0.0
    score = clamp(BASE_SCORE + sum(comp.values()), 1.0, 10.0)
    return Grade(score=score, letter=letter_for(score), forced=forced, components=comp)


def dominated_by_tier_mate(pick: Player, shortlist, needs) -> bool:
    """Was someone in the same tier strictly better on both axes?

    Higher Adjusted Value *and* better need-fit leaves no reading under which
    the pick was right: the board preferred the other player and so did the
    roster. This is the sharpest signal in the rubric and the one that separates
    a defensible tier choice from a careless one.
    """
    mine = need_fit(pick, needs)
    return any(
        other is not pick and other.adjval > pick.adjval and need_fit(other, needs) > mine
        for other in shortlist
    )


def round_band(rnd: int) -> str:
    """Playbook s9's expectation for this round."""
    if rnd <= 2:
        return "best available, commit to nothing"
    if rnd <= 6:
        return "the build reveals itself"
    if rnd <= 10:
        return "fill the two weakest non-punted categories"
    return "upside, specialists, schedule"


def s9_violated(rnd: int, player: Player, trace_row: dict[str, str]) -> bool:
    """Does this pick contradict its round band?

    Rounds 1-2 cannot violate: s9 says commit to nothing, so a poor need-fit
    there is the plan working, not a mistake.
    """
    if rnd <= 2 or not player.g:
        return False
    strongest = max(CATS, key=lambda c: player.g.get(GKEY_FOR[c], 0.0))
    if rnd <= 6:
        weak = [c for c in CATS if trace_row[c] == "WEAK"]
        return bool(weak) and all(player.g.get(GKEY_FOR[c], 0.0) <= 0 for c in weak)
    if rnd <= 10:
        return trace_row[strongest] == "STRONG"
    return False


# --- Rendering --------------------------------------------------------------


def md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Grade a mock draft against the board. "
        "Method: docs/draft-board/mock-draft-review.md."
    )
    ap.add_argument("--board", required=True, help="saved Draft Board!A2:Z202 CSV")
    ap.add_argument("--detail", required=True, help="saved Board!A3:CA202 CSV")
    ap.add_argument("--draft", required=True, help="draft log CSV: round,pick,manager,player")
    ap.add_argument("--me", required=True, help="your manager name, as the log spells it")
    ap.add_argument("--teams", type=int, required=True, help="teams in the mock (not the league)")
    ap.add_argument("--roster", type=int, default=13, help="roster spots (default: 13)")
    ap.add_argument("--divisor", type=float, default=72.0, help="GP divisor (default: 72)")
    ap.add_argument(
        "--replacement",
        type=float,
        default=None,
        help="Settings 'Replacement G-score', to run the stop-the-line check",
    )
    ap.add_argument("--fg-band", type=float, default=0.0050)
    ap.add_argument("--ft-band", type=float, default=0.0100)
    ap.add_argument("--counting-band", type=float, default=0.08)
    args = ap.parse_args(argv)

    def read(path):
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.reader(fh))

    players = parse_draft_board(read(args.board))
    players = parse_board_detail(read(args.detail), players)
    if args.replacement is not None:
        check_replacement(players, args.replacement)

    log = parse_draft_log(read(args.draft))
    rosters = rosters_from_log(log)
    if args.me not in rosters:
        raise ReviewError(f"{args.me!r} not in the draft log; saw {sorted(rosters)}")

    size = args.roster
    totals = {m: team_totals(r, players, args.divisor, size) for m, r in rosters.items()}
    mine = totals[args.me]
    opponents = [t for m, t in totals.items() if m != args.me]
    my_picks = rosters[args.me]
    unmatched = [n for n in my_picks if n not in players or not players[n].raw]

    print("## Caveats\n")
    print(f"- Mock had {args.teams} teams; Q for this mock is {args.teams * size}.")
    all_names = {n for r in rosters.values() for n in r}
    missing = [n for n in all_names if n not in players or not players[n].raw]
    print(f"- {len(missing)} of {len(all_names)} drafted players are outside the board's rows;")
    print("  opponent totals are scaled up from those that matched.")
    if unmatched:
        print(f"- {len(unmatched)} of your own picks did not match.")
    print("- ADP is the export provider's, not Yahoo's. Read GAP as 'cheap somewhere'.\n")

    won, per = record(mine, opponents)
    total = len(opponents) * len(CATS)
    print(f"## Result: {won}-{total - won} ({won / total * 100:.0f}%)\n")
    print(
        md_table(
            ["#", "Team", "Record"],
            [(i, m, f"{w}-{ll}") for i, (m, w, ll) in enumerate(standings(totals), 1)],
        )
    )

    print("\n## Gap to flip\n")
    g2f = gap_to_flip(mine, opponents)
    rows = []
    for c in CATS:
        r = g2f[c]
        nxt = f"{r['next_flip']:.3f} ({r['next_flip_pct']:.1f}%)" if "next_flip" in r else "—"
        sur = f"{r['surplus']:.3f} ({r['surplus_pct']:.1f}%)" if "surplus" in r else "—"
        rows.append((LABEL[c], f"{r['mine']:.3f}", f"{r['won']}-{r['lost']}", nxt, sur))
    print(md_table(["Cat", "Mine", "Record", "To next flip", "Surplus"], rows))

    bands = {"fgp": args.fg_band, "ftp": args.ft_band, "counting": args.counting_band}
    trace = tracker_trace(my_picks, players, args.teams, bands)
    print("\n## Category Tracker trace\n")
    print(
        md_table(
            ["After", "Pick"] + [LABEL[c] for c in CATS],
            [
                (
                    i + 1,
                    players[my_picks[i]].name if my_picks[i] in players else my_picks[i],
                    *[trace[i][c] for c in CATS],
                )
                for i in range(len(trace))
            ],
        )
    )

    print("\n## Build actually drafted\n")
    print(
        md_table(
            ["Build", "Score"],
            [(f"Punt {b}", f"{v:.2f}") for b, v in detect_build(my_picks, players)],
        )
    )

    print("\n## Marginal value (playbook s10)\n")
    rates = [per[c] / len(opponents) for c in CATS]
    print(
        md_table(
            ["Cat", "Win rate", "Value of next slice"],
            [
                (
                    LABEL[c],
                    f"{per[c] / len(opponents) * 100:.0f}%",
                    f"{marginal_value(per[c] / len(opponents)):.2f}",
                )
                for c in sorted(CATS, key=lambda c: -per[c])
            ],
        )
    )
    name, winpct, dist = closest_archetype(rates)
    print(
        f"\nClosest s10 archetype: **{name}** ({winpct * 100:.1f}% match win), "
        f"L1 distance {dist:.2f}"
    )

    print("\n## Round by round\n")
    # Where each of my picks sits in the log, so the board state at that moment
    # is the players actually gone — not the whole roster.
    taken_before = taken_before_each_pick(log)
    log_index = {norm(player): i for i, (_, _, mgr, player) in enumerate(log) if mgr == args.me}

    rated = [p for p in players.values() if p.raw]
    pool_avg_gp = sum(p.mygp for p in rated) / max(len(rated), 1)

    rows, candidates = [], []
    for i, key in enumerate(my_picks):
        if key not in players or not players[key].g:
            candidates.append([key])  # unmatched: no shortlist, and not graded
            continue
        p = players[key]
        # Needs are read from the tracker *before* this pick, which is what the
        # manager could actually see. Round 1 has no prior state.
        needs = needs_from_trace(trace[i - 1]) if i else list(CATS)
        taken = taken_before[log_index[key]] | set(my_picks[:i]) | set(my_picks[i + 1 :])
        shortlist = tier_alternatives(key, players, taken)
        candidates.append([norm(x.name) for x in shortlist])
        by_val = sorted(shortlist, key=lambda x: -x.adjval)
        gr = grade_pick(
            round_no=i + 1,
            adjv_rank=by_val.index(p) + 1,
            n_tier=len(shortlist),
            my_need=need_fit(p, needs),
            best_need=max(need_fit(x, needs) for x in shortlist),
            gap=p.gap,
            mygp=p.mygp,
            pool_avg_gp=pool_avg_gp,
            dominated=dominated_by_tier_mate(p, shortlist, needs),
            s8_violation=s8_violated(p, shortlist, needs),
            s9_violation=s9_violated(i + 1, p, trace[i]),
        )
        rows.append(
            (
                i + 1,
                p.name,
                f"T{p.tier}",
                f"#{p.rank}",
                f"{p.adjval:.2f}",
                int(p.mygp),
                p.gap if p.gap is not None else "—",
                len(shortlist),
                f"{gr.score:.1f}",
                gr.letter,
                "forced" if gr.forced else round_band(i + 1),
            )
        )
    print(
        md_table(
            ["Rd", "Player", "Tier", "#", "AdjV", "GP", "GAP", "Tier n", "Score", "Grade", "Note"],
            rows,
        )
    )

    best, best_score = tier_legal_ceiling(
        my_picks, candidates, players, opponents, args.divisor, size
    )
    print(f"\n## Tier-legal ceiling: {best_score}-{total - best_score}")
    print(f"You captured {won / best_score * 100:.0f}% of it.\n")
    for i, k in enumerate(best):
        if k != my_picks[i]:
            was = players[my_picks[i]].name if my_picks[i] in players else my_picks[i]
            print(f"- R{i + 1}: {was} -> {players[k].name if k in players else k}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ReviewError as exc:
        sys.exit(f"review_mock_draft: {exc}")
