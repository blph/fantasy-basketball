"""The Google Sheet's draft-day formulas, run locally over a board snapshot.

Every function here mirrors a named function in Build.gs and says which. Nothing is valued
again: DURH, ZSH, ZSC, the per-category impacts and the punt scores all arrive in the
snapshot as the numbers `build_data.py` wrote into Data.gs, and this module only does what
the sheet's own formulas do with them -- rank, tier, round, the draft-state columns, the
Category Tracker and the Punts tab.

It reproduces the sheet's MEANING, not its colours. A conditional format becomes a named
flag (`gp_warn`, `disagree`), and a blank cell becomes None.

The arithmetic is kept in the sheet's operation order and never rounded, because the parity
check (`verify.py --local`) compares it to the sheet's raw cell values. Two places where
Python's obvious idiom would compute a different float:

  - A tier break compares `drop > tier_mult * med` on binary floats. A drop that is exactly
    twice the median in decimal can break here, and does on the sheet.
  - `sum()` on floats has been compensated (Neumaier) since Python 3.12. SUMIF and AVERAGE
    are modelled as a plain left-to-right sum down the displayed rows, so `_sheet_sum`.

Pure and stdlib-only: no I/O, no printing, and no import from the valuation modules --
a test holds that boundary, because an engine that could recompute a value would one day
disagree with the sheet about one.
"""

from __future__ import annotations

import math
import re

from board_snapshot import KINDS, SOURCES

DEFAULT_SORT = {"source": "BMP", "kind": "durh"}
READS = {"punted": "— PUNTED", "banked": "■ BANKED", "strong": "▲ STRONG",
         "weak": "▼ WEAK", "contested": "● CONTESTED"}

# What a player row looks like before anyone has touched it. `my_gp: None` means "equals
# projected GP" -- the seeding formula, not an override.
_PLAYER_DEFAULTS = {"name": "", "gone": False, "mine": False, "pick": None, "notes": "",
                    "my_gp": None, "xrank": None, "gp1": None, "gp2": None, "gp3": None}


def empty_state() -> dict:
    """A draft nobody has started: no ticks, nothing conceded, the default sort."""
    return {"players": {}, "conceded": [], "offboard": [], "applied_sort": dict(DEFAULT_SORT)}


def player_state(state: dict, key: str) -> dict:
    """One player's hand columns with the defaults filled in.

    Returns a copy and inserts nothing: a read must never grow the state file. A writer
    assigns the edited dict back into `state["players"][key]` itself.
    """
    return {**_PLAYER_DEFAULTS, **state.get("players", {}).get(key, {})}


def sort_key(sort: dict) -> str:
    """`{"source": "BMP", "kind": "durh"}` -> `"BMP:durh"`, the key of every per-value dict."""
    return f"{sort['source']}:{sort['kind']}"


def _check_sort(sort: dict) -> None:
    if sort.get("source") not in SOURCES or sort.get("kind") not in KINDS:
        raise ValueError(f"unknown sort {sort!r}: source must be one of {SOURCES}, "
                         f"kind one of {KINDS}")


def order(snapshot: dict, applied_sort: dict) -> list[int]:
    """boardOrder: the applied value, descending; ties break on the Board's own row order."""
    _check_sort(applied_sort)
    players = snapshot["players"]
    src, kind = applied_sort["source"], applied_sort["kind"]
    return sorted(range(len(players)),
                  key=lambda i: (-players[i]["values"][src][kind]["v"], players[i]["row"]))


def _displayed(snapshot: dict, applied_sort: dict, row_order: list[int] | None) -> list[int]:
    if row_order is None:
        return order(snapshot, applied_sort)
    shown = list(row_order)
    if sorted(shown) != list(range(len(snapshot["players"]))):
        raise ValueError("row_order must list every player index exactly once")
    return shown


def _rank(sel: list[float]) -> list[int]:
    """buildDraftTab's `#`: RANK(sel, all sel) + COUNTIF(sel from the top to here, sel) - 1.

    Implemented as the formula rather than as the row position, because the two agree only
    while the displayed order is sorted -- and verification feeds this the sheet's displayed
    order, which need not be.
    """
    out = []
    for i, x in enumerate(sel):
        rank = 1 + sum(1 for y in sel if y > x)          # RANK, descending
        ties = sum(1 for y in sel[: i + 1] if y == x)    # the expanding COUNTIF
        out.append(rank + ties - 1)
    return out


def _median(values: list[float]) -> float:
    """MEDIAN: the middle value, or the mean of the middle two as (a + b) / 2."""
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _tiers(sel: list[float], tier_mult: float) -> tuple[list, list, list, list]:
    """buildDraftTab's Drop, Local med, Break and TIER, over every displayed row.

    The median formula is `MEDIAN(INDEX(drops, MAX(1, ROW()-10)):INDEX(drops, MIN(200,
    ROW()+4)))`. INDEX(range, k) is sheet row k + HDR, so the window is displayed rows i-7
    through i+7 clamped to the board. Row 0's Drop is a blank cell, which MEDIAN skips. The
    sheet clamps at POOL_ROWS; clamping at the last row is the same thing on a full board
    and the only meaning a short synthetic board can have.

    Independent of GONE: the tiers describe the board as built, not what is left of it.
    """
    n = len(sel)
    drop: list = [None] * n
    med: list = [None] * n
    brk = [""] * n
    tier = [1] * n
    for i in range(1, n):
        drop[i] = sel[i - 1] - sel[i]
    for i in range(1, n):
        window = [d for d in drop[max(0, i - 7): min(n - 1, i + 7) + 1] if d is not None]
        med[i] = _median(window)
        # IF(N(med)<=0,"",IF(drop>TIER_MULT*med,"BREAK",""))
        brk[i] = "" if med[i] <= 0 else ("BREAK" if drop[i] > tier_mult * med[i] else "")
        tier[i] = tier[i - 1] + 1 if brk[i] == "BREAK" else tier[i - 1]
    return drop, med, brk, tier


def _best_build(player: dict, builds: list[dict]) -> str:
    """bestBuildFormula: "AST+STL  +21", the build that ranks him furthest above his DURH rank.

    Always BMP, whatever the applied sort -- the punt builds ship for that source only.
    MATCH takes the FIRST minimum in PUNTS order. With no punt ranks at all, MIN over a blank
    span is 0, MATCH(0) finds nothing, and IFERROR renders the dash.
    """
    base = player["values"]["BMP"]["durh"]["rank"]
    punts = player.get("punts") or {}
    ranks = [(punts.get(b["key"]) or {}).get("rank") for b in builds]
    present = [r for r in ranks if r is not None]
    if not present:
        return "—"
    low = min(present)
    if low >= base:
        return "—"
    label = builds[ranks.index(low)]["label"].replace("Punt ", "", 1)
    return f"{label}  {base - low:+.0f}"          # TEXT(base - min, "+0")


def _profile(name: str, d: dict, labels: list[str], conceded: set, band: float) -> tuple:
    """profileFormulas: the categories the applied source's UNWEIGHTED d clears by a band.

    A category ticked Punted drops out of both lists.
    """
    if name == "":
        return "", ""
    strong = [c for c in labels if d[c] >= band and c not in conceded]
    weak = [c for c in labels if d[c] <= -band and c not in conceded]
    return ("▲ " + ", ".join(strong) if strong else "—",
            "▼ " + ", ".join(weak) if weak else "—")


def _left_at_pos(rows: list[dict]) -> None:
    """posLeftFormula: same tier, GONE false, and REGEXMATCH(candidate pos, this pos as A|B).

    Counts the row itself and any MINE row not also ticked GONE -- the formula reads GONE
    only. `re.search` is REGEXMATCH's partial match, so a bare "G" counts every guard and a
    bare "F" every forward. A blank Pos becomes an empty pattern, which matches every
    candidate; that is RE2's behaviour and is what the sheet is taken to do until the
    parity check has seen a blank Pos live.
    """
    for row in rows:
        pattern = re.compile(row["pos"].replace(",", "|"))
        row["left_at_pos"] = sum(
            1 for c in rows
            if c["tier"] == row["tier"] and not c["gone"] and pattern.search(c["pos"])
        )


def board_rows(snapshot: dict, state: dict, settings: dict, applied_sort: dict,
               row_order: list[int] | None = None) -> list[dict]:
    """buildDraftTab, evaluated: one dict per Draft Board row, in displayed order.

    `row_order`, when given, replaces `order()` -- verification passes the sheet's own
    displayed order. Settings and sort are explicit so the parity check can vary them
    without touching a state file.

    `in_pool` mirrors writeCalcSheet's In pool on the BMP tab, against `settings["q"]`; the
    sheet reads DERIV.q, which build_data takes from the same board_settings.Q.
    `disagree` mirrors addDraftRules' two rules, the "higher" rule first because a
    conditional format resolves on first match. The sheet bakes the gap into its rules at
    build time; this reads the gap it is given.
    """
    _check_sort(applied_sort)
    players = snapshot["players"]
    src, kind = applied_sort["source"], applied_sort["kind"]
    shown = _displayed(snapshot, applied_sort, row_order)
    sel = [players[p]["values"][src][kind]["v"] for p in shown]
    rank = _rank(sel)
    drop, med, brk, tier = _tiers(sel, settings["tier_mult"])
    conceded = set(state.get("conceded", []))
    labels = snapshot["cat_labels"]
    builds = snapshot["punt_builds"]
    gap_limit = settings["disagree_gap"]

    rows = []
    for i, p in enumerate(shown):
        pl = players[p]
        ps = player_state(state, pl["key"])
        values, ranks, tags, disagree = {}, {}, {}, {}
        for s in SOURCES:
            for k in KINDS:
                cell = pl["values"][s][k]
                sk = f"{s}:{k}"
                values[sk] = cell["v"]
                ranks[sk] = cell["rank"]
                # "#4 REB"; ZSC drops nothing, so its tag is the rank alone.
                tags[sk] = f"#{cell['rank']}" if k == "zsc" else f"#{cell['rank']} {cell['drop']}"
                if rank[i] - cell["rank"] >= gap_limit:
                    disagree[sk] = "higher"
                elif cell["rank"] - rank[i] >= gap_limit:
                    disagree[sk] = "lower"
                else:
                    disagree[sk] = None
        gp = pl["hbp_raw"]["gp"]
        my_gp = gp if ps["my_gp"] is None else ps["my_gp"]
        strengths, weaknesses = _profile(pl["name"], pl["values"][src]["d"], labels,
                                         conceded, settings["cat_band"])
        rows.append({
            "row": pl["row"], "key": pl["key"], "name": pl["name"], "team": pl["team"],
            "pos": pl["pos"], "inj": pl["inj"], "gone": ps["gone"], "mine": ps["mine"],
            "rank": rank[i], "tier": tier[i], "rnd": math.ceil(rank[i] / settings["teams"]),
            "sel": sel[i], "drop": drop[i], "med": med[i], "brk": brk[i],
            "gap": None if pl["adp"] is None else pl["adp"] - rank[i],
            "adp": pl["adp"], "xrank": ps["xrank"], "notes": ps["notes"],
            "gp": gp, "my_gp": my_gp,
            # writeBoardFormulas: IF(ABS(GP - My GP) > 10, "CHECK", "")
            "gp_flag": "CHECK" if abs(gp - my_gp) > 10 else "",
            "gp_warn": 68 <= gp <= 74,                  # addDraftRules' Proj GP warning
            "best_build": _best_build(pl, builds),
            "strengths": strengths, "weaknesses": weaknesses,
            "left_at_pos": 0,
            "in_pool": pl["values"]["BMP"]["durh"]["rank"] <= settings["q"],
            "values": values, "ranks": ranks, "tags": tags, "disagree": disagree,
        })
    _left_at_pos(rows)
    return rows


# The tracker's feed columns. Makes over attempts for the two rates, never a mean of rates.
_RATES = {"FG%": ("fgm", "fga"), "FT%": ("ftm", "fta")}
_COUNTS = {"3PM": "tpm", "PTS": "pts", "REB": "reb", "AST": "ast", "STL": "stl", "BLK": "blk"}


def normal_cdf(x: float) -> float:
    """NORMSDIST."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _sheet_sum(values) -> float:
    """SUM / SUMIF as a plain left-to-right accumulation, not Python's compensated sum()."""
    total = 0
    for v in values:
        total += v
    return total


def _read(conceded: bool, win: float | None, settings: dict) -> str:
    """The tracker's Read cell. Punted is tested FIRST, so it shows before any pick is made."""
    if conceded:
        return READS["punted"]
    if win is None:
        return ""
    if win >= settings["bank_win"]:
        return READS["banked"]
    if win >= settings["strong_win"]:
        return READS["strong"]
    if win <= settings["weak_win"]:
        return READS["weak"]
    return READS["contested"]


def tracker(snapshot: dict, state: dict, settings: dict, applied_sort: dict,
            rows: list[dict] | None = None) -> dict:
    """buildTrackerTab, evaluated.

    `n` counts MINE ticks on board rows; an off-board pick is reported, never counted --
    the sheet has the same blind spot. The benchmark is every row whose `#` is within
    MIN(Q, TEAMS * n): by rank, not by GONE. Raw totals are HBP's line whatever the
    projection, because every calculation tab carries HBP's raw columns (writeCalcSheet);
    the Z uses the applied source's weighted `dh`.

    A zero attempt total is a #DIV/0! on the sheet; here the value is None and the category
    carries `flag: "no_attempts"`.
    """
    _check_sort(applied_sort)
    if rows is None:
        rows = board_rows(snapshot, state, settings, applied_sort)
    by_row = {p["row"]: p for p in snapshot["players"]}
    src = applied_sort["source"]
    mine = [r for r in rows if r["mine"]]
    n = len(mine)
    cutoff = min(settings["q"], settings["teams"] * n)
    drafted = [r for r in rows if r["rank"] <= cutoff]
    conceded = set(state.get("conceded", []))
    raw_mine = [by_row[r["row"]]["hbp_raw"] for r in mine]
    raw_bench = [by_row[r["row"]]["hbp_raw"] for r in drafted]

    cats = []
    for cat in snapshot["cat_labels"]:
        entry = {"cat": cat, "my_team": None, "avg_team": None, "z": None, "win": None,
                 "read": "", "conceded": cat in conceded, "flag": None}
        if n > 0:
            if cat in _RATES:
                made, att = _RATES[cat]
                mine_att = _sheet_sum(x[att] for x in raw_mine)
                bench_att = _sheet_sum(x[att] for x in raw_bench)
                if mine_att == 0 or bench_att == 0:
                    entry["flag"] = "no_attempts"
                if mine_att != 0:
                    entry["my_team"] = _sheet_sum(x[made] for x in raw_mine) / mine_att
                if bench_att != 0:
                    entry["avg_team"] = _sheet_sum(x[made] for x in raw_bench) / bench_att
            else:
                col = _COUNTS[cat]
                entry["my_team"] = _sheet_sum(x[col] for x in raw_mine)
                entry["avg_team"] = _sheet_sum(x[col] for x in raw_bench) / len(raw_bench) * n
            dh_mine = _sheet_sum(by_row[r["row"]]["values"][src]["dh"][cat] for r in mine)
            dh_bench = [by_row[r["row"]]["values"][src]["dh"][cat] for r in drafted]
            z = (dh_mine - n * (_sheet_sum(dh_bench) / len(dh_bench))) / math.sqrt(n)
            entry["z"] = z
            entry["win"] = normal_cdf(z * snapshot["deriv"]["k_tracker"][cat])
        entry["read"] = _read(entry["conceded"], entry["win"], settings)
        cats.append(entry)

    roster = [{"rank": r["rank"], "name": r["name"], "pos": r["pos"]}
              for r in sorted(mine, key=lambda r: r["rank"])]
    offboard_mine = sum(1 for o in state.get("offboard", []) if o.get("mine"))
    return {"n": n, "benchmark": "by_rank", "cutoff": cutoff, "cats": cats,
            "roster": roster, "offboard_mine": offboard_mine}


def punts(snapshot: dict, top: int = 40) -> dict[str, list[dict]]:
    """buildPuntsTab: per build, SORT(FILTER(rank <> ""), gap descending), first `top` rows.

    A player with no ADP sorts last on a -1E9 key and keeps a blank gap rather than zero.
    Ties keep Board row order, which is what a stable sort of the filtered rows gives.
    """
    players = sorted(snapshot["players"], key=lambda p: p["row"])
    out = {}
    for build in snapshot["punt_builds"]:
        keyed = []
        for p in players:
            cell = (p.get("punts") or {}).get(build["key"])
            if cell is None or cell.get("rank") is None:
                continue
            adp, rank = p["adp"], cell["rank"]
            gap = None if adp is None else adp - rank
            keyed.append((-1e9 if adp is None else gap,
                          {"rank": rank, "name": p["name"], "score": cell["score"],
                           "adp": adp, "gap": gap}))
        keyed.sort(key=lambda e: -e[0])
        out[build["key"]] = [entry for _, entry in keyed[:top]]
    return out


# writeSanityBlock's two failure strings, verbatim.
_MISALIGNED_NAMES = "MISALIGNED — the calculation tabs are out of step with the Board. Stop."
_MISALIGNED_ROWS = ("MISALIGNED — the Draft Board's hidden block is out of step with its rows. "
                    "Run Rebuild & re-sort.")


def checks(snapshot: dict, state: dict) -> dict:
    """writeSanityBlock, evaluated.

    The sheet's two alignment guards compare columns across tabs. Locally there are no tabs,
    so each becomes the structural fact its failure would break: `names_aligned` that every
    player sits at his own Board row and carries all three sources, `rows_aligned` that the
    board has the row count META claims and no two rows share a key a tick could land on.
    """
    players = snapshot["players"]
    meta = snapshot["meta"]
    names_ok = all(p["row"] == i and all(s in p["values"] for s in SOURCES)
                   for i, p in enumerate(players))
    keys = [p["key"] for p in players]
    rows_ok = len(players) == meta["board_rows"] and len(set(keys)) == len(keys)
    board_rows_n = sum(1 for p in players if p["name"] != "")
    inj = [p["inj"] for p in players]
    ungraded = inj.count("?")
    injuries = (f"{inj.count('EXTREME')} EXTREME / {inj.count('HIGH')} HIGH / "
                f"{inj.count('MED')} MED / {inj.count('LOW')} LOW"
                + (f" — {ungraded} UNGRADED" if ungraded else ""))
    return {
        "names_aligned": "aligned" if names_ok else _MISALIGNED_NAMES,
        "rows_aligned": "aligned" if rows_ok else _MISALIGNED_ROWS,
        "board_rows": board_rows_n,
        "mine": sum(1 for p in players if player_state(state, p["key"])["mine"]),
        "adp_coverage": f"{sum(1 for p in players if p['adp'] is not None)} of {board_rows_n}",
        "generated": meta["generated"],
        "digest": meta["digest"],
        "injuries": injuries,
    }
