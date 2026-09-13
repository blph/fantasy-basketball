"""Check the local engine against a pull of the live sheet. Run as `verify.py --local`.

The local board reproduces the sheet's draft-day formulas in Python (board_engine.py), and
two implementations of one formula drift apart silently -- nothing on either side errors.
This is the check that says whether they still agree, on real rows: it reads what the sheet
displays, feeds the sheet's own ticks, hand columns, settings and row order into the engine,
and compares every derived cell.

    1. Comparable? Header labels equal board_layout.json, the stamped digest equals the
       snapshot's, and both Settings alignment checks read `aligned`. Otherwise exit 3:
       a diff between two different builds is noise, and noise gets tolerances widened.
    2. Engine input, in memory only. Nothing is written to draft-state.json.
    3. Values, tags, INJ and the # column, on raw values rather than display rounding.
    4. Every other derived column, the tracker, My roster and the Punts blocks. Numbers
       compare on the raw `v` to 1e-9, text on its text. Tied values share their ranks as a
       set; the columns computed from a tied row's rank are checked against the rank shown.
    5. Reported Settings cells equal DERIV. Settings inputs that differ from the defaults
       the snapshot was built with are their own failure: drift to fix on one side.
    6. SORT_BY differing from the order actually shown is reported, not failed -- onEdit
       sets it without re-sorting.
    7. Output is aggregate: counts, columns and sheet row numbers, never a name or a value.

Triage: if the sheet evaluates differently from Build.gs's formula text, fix Build.gs; if the
engine differs from a sheet that evaluates correctly, fix the engine. Never widen TOL.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_engine as ENGINE  # noqa: E402
import board_settings as SETTINGS  # noqa: E402
import board_snapshot as BS  # noqa: E402
from pull_sheet import col_letter, parse_a1  # noqa: E402

LAYOUT = Path(__file__).resolve().parent / "board_layout.json"
TOL = 1e-9
PASS, MISMATCH, USAGE, NOT_COMPARABLE = 0, 1, 2, 3

DB, TRACKER, PUNTS, SET = "Draft Board", "Category Tracker", "Punts", "Settings"
PREFIX = {"bmp": "BMP", "hbp": "HBP", "alt": "BMP-ALT"}
KIND = {"Durh": "durh", "Zsh": "zsh", "Zsc": "zsc"}
FEEDS = {"hFgm": "fgm", "hFga": "fga", "hFtm": "ftm", "hFta": "fta", "h3": "tpm", "hPts": "pts",
         "hReb": "reb", "hAst": "ast", "hStl": "stl", "hBlk": "blk"}
INPUT_KEYS = (*SETTINGS.SHEET_KEYS, "q")
WHOLE = {"teams", "roster", "q", "disagree_gap"}
REPORTED = {"k": "k_rosenof", "w": "weights", "K": "k_tracker", "slope": "slopes"}

#: Draft Board columns read straight off an engine row: (how to compare, engine field).
DIRECT = {
    "tier": ("num", "tier"), "player": ("text", "name"), "team": ("text", "team"),
    "pos": ("text", "pos"), "inj": ("text", "inj"), "drafted": ("bool", "gone"),
    "mine": ("bool", "mine"), "drop": ("num", "drop"), "med": ("num", "med"),
    "brk": ("text", "brk"), "projGp": ("num", "gp"), "myGp": ("num", "my_gp"),
    "gpFlag": ("text", "gp_flag"), "adp": ("num", "adp"), "xrank": ("num", "xrank"),
    "best": ("text", "best_build"), "strengths": ("text", "strengths"),
    "weaknesses": ("text", "weaknesses"), "posLeft": ("num", "left_at_pos"),
    "notes": ("text", "notes"),
}
#: Compared by their own rule below.
RANK_DEPENDENT = ("rank", "round", "gap")


class NotComparable(Exception):
    """The sheet and the snapshot are not the same build, so a diff would be noise."""


def expected_draft_keys(cat_labels: list[str]) -> set[str]:
    """Every Draft Board column this check compares. A test holds it equal to the layout."""
    keys = set(DIRECT) | set(RANK_DEPENDENT) | set(FEEDS) | {"sel", "rowCheck"}
    for prefix in PREFIX:
        for kind in KIND:
            keys |= {prefix + kind, prefix + kind + "Tag"}
    for src in BS.SOURCES:
        keys |= {f"rank:{src}:{kind}" for kind in BS.KINDS}
    for cat in cat_labels:
        keys |= {f"dh:{cat}", f"d:{cat}"}
    return keys


# ------------------------------------------------------------------ reading the pull

class _Pull:
    """Every pulled cell by sheet, column and row. A cell the pull does not cover is fatal."""

    def __init__(self, pulls: dict):
        self.grid: dict[tuple[str, int, int], dict | None] = {}
        for rng in pulls["ranges"].values():
            c1, r1, _, _ = parse_a1(rng["range"])
            for i, row in enumerate(rng["cells"]):
                for j, cell in enumerate(row):
                    self.grid[(rng["sheet"], c1 + j, r1 + i)] = cell

    def cell(self, sheet: str, col: int, row: int) -> dict | None:
        try:
            return self.grid[(sheet, col, row)]
        except KeyError:
            raise NotComparable(f"the pull does not cover {sheet}!{col_letter(col)}{row} -- "
                                "pull again with this checkout's pull_sheet.py") from None

    def at(self, sheet: str, a1: str) -> dict | None:
        c, r, _, _ = parse_a1(a1)
        return self.cell(sheet, c, r)


def _v(cell):
    return None if cell is None else cell.get("v")


def _num(cell):
    v = _v(cell)
    return v if isinstance(v, int | float) and not isinstance(v, bool) else None


def _text(cell) -> str:
    """A string cell's text. gviz puts it in `v`; `f` carries the text of anything else."""
    if cell is None:
        return ""
    v, f = cell.get("v"), cell.get("f")
    if isinstance(v, str):
        return v
    if f is not None:
        return str(f)
    return "" if v is None else str(v)


def _same_num(cell, want) -> bool:
    got = _num(cell)
    if want is None:
        return _v(cell) is None
    return got is not None and abs(got - want) <= TOL


def _same(how: str, cell, want) -> bool:
    if how == "num":
        return _same_num(cell, want)
    if how == "bool":
        return (_v(cell) is True) == bool(want)
    return _text(cell) == ("" if want is None else str(want))


def _r9(x):
    return None if x is None else round(float(x), 9)


def _sort_label(sort: dict) -> str:
    return f"{sort['source']} · {sort['kind'].upper()}"


# ------------------------------------------------------------------ the report

class _Report:
    def __init__(self):
        self.oks: list[str] = []
        self.notes: list[str] = []
        self.fails: list[str] = []
        self.cells: dict[str, list] = {}

    def miss(self, where: str, at) -> None:
        self.cells.setdefault(where, []).append(at)

    def lines(self) -> list[str]:
        for where, at in self.cells.items():
            shown = ", ".join(str(a) for a in at[:5]) + (f" and {len(at) - 5} more"
                                                        if len(at) > 5 else "")
            self.fails.append(f"FAIL: {where}: {len(at)} cell(s) differ, at {shown}")
        self.cells = {}
        return self.oks + self.notes + self.fails


# ------------------------------------------------------------------ steps 1 and 2

def _check_comparable(snapshot: dict, sheet: _Pull, layout: dict) -> None:
    tabs, bad = layout["tabs"], []
    for tab in (DB, "Board", *BS.SOURCES):
        t = tabs[tab]
        for c in t["columns"].values():
            if _text(sheet.cell(tab, c["index"], t["header_row"])) != c["label"]:
                bad.append(f"{tab}!{c['letter']}{t['header_row']}")
    t = tabs[TRACKER]
    for key, col in t["columns"].items():
        if _text(sheet.cell(TRACKER, col, t["header_row"])) != t["column_labels"][key]:
            bad.append(f"{TRACKER}!{col_letter(col)}{t['header_row']}")
    for key, col in t["roster_columns"].items():
        if _text(sheet.cell(TRACKER, col, t["roster_header_row"])) != t["roster_labels"][key]:
            bad.append(f"{TRACKER}!{col_letter(col)}{t['roster_header_row']}")
    p = tabs[PUNTS]
    for b in p["blocks"]:
        for col in p["columns"].values():
            c = b["first_col"] + col["offset"]
            if _text(sheet.cell(PUNTS, c, p["header_row"])) != col["label"]:
                bad.append(f"{PUNTS}!{col_letter(c)}{p['header_row']}")
    s = tabs[SET]
    labels = [(lab["cell"], lab["text"]) for lab in s["cell_labels"].values()]
    labels += [(a1, cat) for cat, a1 in s["weight_labels"].items()]
    labels += [(a1, cat) for cat, a1 in s["tracker_labels"].items()]
    bad += [f"{SET}!{a1}" for a1, text in labels if _text(sheet.at(SET, a1)) != text]
    if bad:
        raise NotComparable(f"{len(bad)} header or label cell(s) differ from board_layout.json, "
                            f"first {', '.join(bad[:5])} -- the sheet is not running this "
                            "Build.gs")

    stamped = _text(sheet.at(SET, s["cells"]["digest"]))
    want = snapshot["meta"]["digest"]
    if stamped != want:
        raise NotComparable(f"the sheet is stamped with digest {stamped[:12] or '(blank)'} and "
                            f"the snapshot carries {want[:12] or '(blank)'} -- they did not come "
                            "from one build_data.py run")
    for key in ("names_aligned", "rows_aligned"):
        if _text(sheet.at(SET, s["cells"][key])) != "aligned":
            raise NotComparable(f"Settings {s['cells'][key]} "
                                f"({s['cell_labels'][key]['text']}) does not read 'aligned'")


def _engine_inputs(snapshot: dict, sheet: _Pull, layout: dict) -> dict:
    tabs, players = layout["tabs"], snapshot["players"]
    first, last, n = layout["first_row"], layout["last_row"], len(snapshot["players"])
    if n > last - first + 1:
        raise NotComparable(f"the snapshot has {n} players and the board {last - first + 1} rows")
    by_name: dict[str, int] = {}
    for i, p in enumerate(players):
        if p["name"] in by_name:
            raise NotComparable(f"snapshot rows {by_name[p['name']]} and {i} share a name")
        by_name[p["name"]] = i

    dcols, bcols = tabs[DB]["columns"], tabs["Board"]["columns"]
    order = []
    for r in range(first, last + 1):
        name = _text(sheet.cell(DB, dcols["player"]["index"], r))
        if r - first >= n:
            if name:
                raise NotComparable(f"Draft Board row {r} holds a player past the snapshot's {n}")
            continue
        if name not in by_name:
            raise NotComparable(f"Draft Board row {r} holds a player that is not in the snapshot")
        order.append(by_name[name])
    if len(set(order)) != n:
        raise NotComparable("the Draft Board shows a player on two rows")

    state = ENGINE.empty_state()
    for i, p in enumerate(players):
        r = first + i
        if _text(sheet.cell("Board", bcols["player"]["index"], r)) != p["name"]:
            raise NotComparable(f"Board row {r} is not snapshot row {i} -- the Board was not "
                                "refreshed from the Data.gs this snapshot was built with")
        st = dict(ENGINE.player_state(state, p["key"]))
        st["name"] = p["name"]
        for field, key in (("my_gp", "myGp"), ("xrank", "xrank"), ("gp1", "gp1"),
                           ("gp2", "gp2"), ("gp3", "gp3")):
            st[field] = _num(sheet.cell("Board", bcols[key]["index"], r))
        st["notes"] = _text(sheet.cell("Board", bcols["notes"]["index"], r))
        state["players"][p["key"]] = st
    for i, idx in enumerate(order):
        st = state["players"][players[idx]["key"]]
        st["gone"] = _v(sheet.cell(DB, dcols["drafted"]["index"], first + i)) is True
        st["mine"] = _v(sheet.cell(DB, dcols["mine"]["index"], first + i)) is True

    t = tabs[TRACKER]
    state["conceded"] = [
        cat for i, cat in enumerate(snapshot["cat_labels"])
        if _v(sheet.cell(TRACKER, t["columns"]["punted"], t["first_cat_row"] + i)) is True]

    cells, settings = tabs[SET]["cells"], dict(snapshot["settings"])
    for key in INPUT_KEYS:
        cell = sheet.at(SET, cells[key])
        if key == "scoring":
            settings[key] = _text(cell)
            continue
        v = _num(cell)
        if v is None:
            raise NotComparable(f"Settings {cells[key]} ({key}) is not a number")
        settings[key] = int(v) if key in WHOLE and float(v).is_integer() else v
    return {"state": state, "settings": settings, "order": order}


# ------------------------------------------------------------------ steps 3 to 6

def _applied_sort(snapshot: dict, sheet: _Pull, layout: dict, order: list[int],
                  rep: _Report) -> dict | None:
    """The sort the board is actually showing: whose values `sel` copies and whose rank `#` is."""
    players, first = snapshot["players"], layout["first_row"]
    dcols = layout["tabs"][DB]["columns"]
    sel = [_num(sheet.cell(DB, dcols["sel"]["index"], first + i)) for i in range(len(order))]
    shown = [_num(sheet.cell(DB, dcols["rank"]["index"], first + i)) for i in range(len(order))]
    by_value, exact = [], []
    for src in BS.SOURCES:
        for kind in BS.KINDS:
            vals = [players[i]["values"][src][kind]["v"] for i in order]
            if all(a is not None and abs(a - b) <= TOL for a, b in zip(sel, vals, strict=True)):
                sort = {"source": src, "kind": kind}
                by_value.append(sort)
                ranks = [players[i]["values"][src][kind]["rank"] for i in order]
                if shown == ranks:
                    exact.append(sort)
    label = _text(sheet.at(SET, layout["tabs"][SET]["cells"]["sort_by"]))
    pool = exact or by_value
    if not pool:
        rep.fails.append("FAIL: the Draft Board's sorted-by column copies none of the nine value "
                         "columns -- it is not showing this snapshot's values")
        return None
    chosen = next((s for s in pool if _sort_label(s) == label), pool[0])
    if not exact:
        rep.notes.append(f"NOTE: the # column matches no source's rank on every row; ranks are "
                         f"compared against {_sort_label(chosen)} below")
    if _sort_label(chosen) != label:
        rep.notes.append(f"NOTE: Settings SORT_BY reads {label!r} but the board is sorted by "
                         f"{_sort_label(chosen)!r} -- onEdit sets SORT_BY without re-sorting; "
                         "run Rebuild & re-sort to apply it")
    rep.oks.append(f"ok: the board is sorted by {_sort_label(chosen)}")
    return chosen


def _draft_expected(key: str, er: dict, p: dict, applied: dict):
    """(how to compare, expected value) for a Draft Board column not in RANK_DEPENDENT."""
    src = applied["source"]
    if key in DIRECT:
        how, field = DIRECT[key]
        return how, er[field]
    if key == "sel":
        return "num", er["values"][ENGINE.sort_key(applied)]
    if key == "rowCheck":
        return "text", p["name"]
    if key in FEEDS:
        return "num", p["hbp_raw"][FEEDS[key]]
    if key.startswith("dh:") or key.startswith("d:"):
        block, cat = key.split(":", 1)
        return "num", p["values"][src][block][cat]
    if key.startswith("rank:"):
        _, s, kind = key.split(":")
        return "num", p["values"][s][kind]["rank"]
    tag = key.endswith("Tag")
    stem = key[:-3] if tag else key
    s = ENGINE.sort_key({"source": PREFIX[stem[:3]], "kind": KIND[stem[3:]]})
    return ("text", er["tags"][s]) if tag else ("num", er["values"][s])


def _compare_draft(snapshot, sheet, layout, inputs, applied, rows, rep) -> None:
    players, first = snapshot["players"], layout["first_row"]
    dcols, settings, order = layout["tabs"][DB]["columns"], inputs["settings"], inputs["order"]
    by_key = {r["key"]: r for r in rows}
    n = len(order)

    # Out of order means a row whose sorted value is not the value the engine's order puts
    # there. Two rows that trade places inside a group of equal values are still in order:
    # which tied player the sheet shows first is compared as a set, like their ranks, until
    # it is proven live to match the engine's tie-break on Board row.
    src, kind = applied["source"], applied["kind"]

    def value(idx: int) -> float:
        return players[idx]["values"][src][kind]["v"]

    moved = [first + i for i, (a, b) in
             enumerate(zip(order, ENGINE.order(snapshot, applied), strict=True))
             if value(a) != value(b)]
    if moved:
        rep.fails.append(f"FAIL: the Draft Board is out of {_sort_label(applied)} order on "
                         f"{len(moved)} rows, first at row {moved[0]} -- run Rebuild & re-sort")

    group, g = [0] * n, 0
    for i in range(1, n):
        if value(order[i]) != value(order[i - 1]):
            g += 1
        group[i] = g
    size = Counter(group)
    shown = [_num(sheet.cell(DB, dcols["rank"]["index"], first + i)) for i in range(n)]

    checked = 0
    for i, idx in enumerate(order):
        r, p = first + i, players[idx]
        er, tied = by_key[p["key"]], size[group[i]] > 1
        for key, col in dcols.items():
            cell = sheet.cell(DB, col["index"], r)
            if key == "rank":
                if tied:
                    continue
                ok = _same_num(cell, er["rank"])
            elif key == "round":
                want = er["rnd"]
                if tied:
                    want = None if shown[i] is None else math.ceil(shown[i] / settings["teams"])
                ok = _same_num(cell, want)
            elif key == "gap":
                want = er["gap"]
                if tied:
                    want = None if p["adp"] is None or shown[i] is None else p["adp"] - shown[i]
                ok = _same_num(cell, want)
            else:
                how, want = _draft_expected(key, er, p, applied)
                ok = _same(how, cell, want)
            checked += 1
            if not ok:
                rep.miss(f"Draft Board {col['letter']} ({key})", f"row {r}")

    # A tie group shares its ranks. Which tied row the sheet gives the lower one to is compared
    # as a set until it is proven to match the engine's row order live.
    for gid in [k for k, c in size.items() if c > 1]:
        members = [i for i in range(n) if group[i] == gid]
        got = Counter(_r9(shown[i]) for i in members)
        want = Counter(_r9(by_key[players[order[i]]["key"]]["rank"]) for i in members)
        if got != want:
            for i in members:
                rep.miss(f"Draft Board {dcols['rank']['letter']} (rank, tied values)",
                         f"row {first + i}")

    # The disagreement highlight is a conditional format, so its colour cannot be pulled. Its
    # condition can: recompute it from the ranks shown and compare with the engine's flag.
    gap = settings["disagree_gap"]
    for i, idx in enumerate(order):
        if size[group[i]] > 1 or shown[i] is None:
            continue
        er = by_key[players[idx]["key"]]
        for src in BS.SOURCES:
            for k in BS.KINDS:
                helper = _num(sheet.cell(DB, dcols[f"rank:{src}:{k}"]["index"], first + i))
                flag = None
                if helper is not None:
                    flag = ("higher" if shown[i] - helper >= gap
                            else "lower" if helper - shown[i] >= gap else None)
                if flag != er["disagree"][f"{src}:{k}"]:
                    rep.miss(f"disagreement {src} {k.upper()}", f"row {first + i}")
    tied_rows = sum(c for c in size.values() if c > 1)
    rep.oks.append(f"ok: compared {checked} Draft Board cells on {n} rows "
                   f"({tied_rows} rows in tie groups)")


def _compare_tracker(snapshot, sheet, layout, inputs, trk, rep) -> None:
    t, first = layout["tabs"][TRACKER], layout["first_row"]
    dcols, order = layout["tabs"][DB]["columns"], inputs["order"]
    c = t["columns"]
    if not _same_num(sheet.at(TRACKER, t["players_ticked"]), trk["n"]):
        rep.miss("Category Tracker players ticked", t["players_ticked"])
    for i, cat in enumerate(trk["cats"]):
        r = t["first_cat_row"] + i
        for key, how, want in (("cat", "text", cat["cat"]), ("my_team", "num", cat["my_team"]),
                               ("avg_team", "num", cat["avg_team"]), ("z", "num", cat["z"]),
                               ("win", "num", cat["win"]), ("read", "text", cat["read"]),
                               ("punted", "bool", cat["conceded"])):
            if not _same(how, sheet.cell(TRACKER, c[key], r), want):
                rep.miss(f"Category Tracker {col_letter(c[key])} ({key})", f"row {r}")

    # My roster: the MINE rows, in the order of the ranks the Draft Board shows for them.
    expected = []
    for i, idx in enumerate(order):
        if _v(sheet.cell(DB, dcols["mine"]["index"], first + i)) is True:
            p = snapshot["players"][idx]
            expected.append((_num(sheet.cell(DB, dcols["rank"]["index"], first + i)),
                             p["name"], p["pos"]))
    expected.sort(key=lambda e: (e[0] is None, e[0] or 0))
    rc, got = t["roster_columns"], []
    for j in range(t["roster_rows"]):
        r = t["roster_first_row"] + j
        name = _text(sheet.cell(TRACKER, rc["name"], r))
        if name:
            got.append((_num(sheet.cell(TRACKER, rc["rank"], r)), name,
                        _text(sheet.cell(TRACKER, rc["pos"], r))))
    if got != expected:
        at = next((j for j, (a, b) in enumerate(zip(got, expected, strict=False)) if a != b),
                  min(len(got), len(expected)))
        rep.miss("Category Tracker My roster", f"row {t['roster_first_row'] + at}")
    if sorted(e["name"] for e in trk["roster"]) != sorted(e[1] for e in expected):
        rep.fails.append("FAIL: the engine's My roster is not the Draft Board's MINE ticks")
    rep.oks.append(f"ok: compared {len(trk['cats'])} tracker rows and a roster of {len(got)}")


def _compare_punts(snapshot, sheet, layout, rep) -> None:
    p = layout["tabs"][PUNTS]
    full = ENGINE.punts(snapshot, top=len(snapshot["players"]))
    labels = {b["key"]: b["label"] for b in snapshot["punt_builds"]}

    def key_of(entry):
        return entry[4] if entry[4] is not None else -1e9

    for b in p["blocks"]:
        where = f"Punts {labels[b['key']]}"

        def at(name, r, b=b):
            return sheet.cell(PUNTS, b["first_col"] + p["columns"][name]["offset"], r)

        got, got_rows = [], []
        for j in range(p["rows"]):
            r = p["first_row"] + j
            if _text(at("name", r)):
                got.append((_r9(_num(at("rank", r))), _text(at("name", r)),
                            _r9(_num(at("score", r))), _r9(_num(at("adp", r))),
                            _r9(_num(at("gap", r)))))
                got_rows.append(r)
        entries = [(_r9(e["rank"]), e["name"], _r9(e["score"]), _r9(e["adp"]), _r9(e["gap"]))
                   for e in full[b["key"]]]
        window = entries[: p["rows"]]
        if len(got) != len(window):
            rep.fails.append(f"FAIL: {where}: {len(got)} rows shown, the engine lists "
                             f"{len(window)}")
            continue
        keys = [key_of(e) for e in got]
        if any(a < b for a, b in zip(keys, keys[1:], strict=False)):
            rep.fails.append(f"FAIL: {where}: the block is not sorted by GAP")
        # Rows sharing a GAP are one group, compared as a set. A group cut by the row limit
        # may show any of its members, so long as it shows as many as the engine does.
        for k in set(keys) | {key_of(e) for e in window}:
            shown = Counter(e for e in got if key_of(e) == k)
            want = Counter(e for e in window if key_of(e) == k)
            if shown == want:
                continue
            whole = Counter(e for e in entries if key_of(e) == k)
            cut = whole.total() > want.total()
            if cut and shown.total() == want.total() and not (shown - whole):
                continue
            for r, e in zip(got_rows, got, strict=True):
                if key_of(e) == k:
                    rep.miss(where, f"row {r}")
            if not shown:
                rep.miss(where, f"row {p['first_row']}")
    rep.oks.append(f"ok: compared {len(p['blocks'])} punt blocks")


def _compare_settings(snapshot, sheet, layout, inputs, rep) -> None:
    s, deriv = layout["tabs"][SET], snapshot["deriv"]
    for cat, a1 in s["weights"].items():
        if not _same_num(sheet.at(SET, a1), deriv.get("weights", {}).get(cat)):
            rep.miss("Settings reported weights", a1)
    for cat, cells in s["tracker_constants"].items():
        for name, a1 in cells.items():
            if not _same_num(sheet.at(SET, a1), deriv.get(REPORTED[name], {}).get(cat)):
                rep.miss("Settings reported tracker constants", a1)

    chk, cells = ENGINE.checks(snapshot, inputs["state"]), s["cells"]
    for key, how in (("board_rows", "num"), ("mine", "num"), ("adp_coverage", "text"),
                     ("generated", "text"), ("injuries", "text")):
        if not _same(how, sheet.at(SET, cells[key]), chk[key]):
            rep.miss("Settings sanity checks", f"{cells[key]} ({key})")

    drift = []
    for key in INPUT_KEYS:
        cell, want = sheet.at(SET, cells[key]), snapshot["settings"][key]
        if not _same("text" if key == "scoring" else "num", cell, want):
            drift.append(f"{cells[key]} ({key})")
    if drift:
        rep.fails.append(f"FAIL: Settings inputs differ from the defaults this snapshot was built "
                         f"with: {', '.join(drift)} -- drift; change the sheet or "
                         "board_settings.py so they agree, never the tolerance")
    rep.oks.append(f"ok: compared {len(INPUT_KEYS)} Settings inputs and the reported constants")


# ------------------------------------------------------------------ entry points

def diff_local(snapshot: dict, pulls: dict, layout: dict) -> tuple[int, list[str]]:
    """(0 pass | 1 mismatch | 3 not comparable, aggregate messages). Never names a player."""
    try:
        sheet = _Pull(pulls)
        _check_comparable(snapshot, sheet, layout)
        inputs = _engine_inputs(snapshot, sheet, layout)
        rep = _Report()
        applied = _applied_sort(snapshot, sheet, layout, inputs["order"], rep)
        if applied is None:
            return MISMATCH, rep.lines()
        state, settings = inputs["state"], inputs["settings"]
        state["applied_sort"] = dict(applied)
        rows = ENGINE.board_rows(snapshot, state, settings, applied, row_order=inputs["order"])
        trk = ENGINE.tracker(snapshot, state, settings, applied, rows=rows)
        _compare_draft(snapshot, sheet, layout, inputs, applied, rows, rep)
        _compare_tracker(snapshot, sheet, layout, inputs, trk, rep)
        _compare_punts(snapshot, sheet, layout, rep)
        _compare_settings(snapshot, sheet, layout, inputs, rep)
    except NotComparable as e:
        return NOT_COMPARABLE, [f"NOT COMPARABLE: {e}"]
    lines = rep.lines()
    return (MISMATCH if rep.fails else PASS), lines


def run_local(pulls_path: Path, snapshot_path: Path | None = None,
              layout_path: Path = LAYOUT) -> int:
    """`verify.py --local`: load, diff, print the aggregate report, return the exit code.

    With no snapshot named, the newest under data/draft-board/ is the one compared.
    """
    if not pulls_path.exists():
        print(f"{pulls_path} not found. Pull the sheet first:\n"
              "  python3 scripts/draft-board/pull_sheet.py", file=sys.stderr)
        return USAGE
    if snapshot_path is None:
        snapshot_path = BS.newest(BS.ROOT)
    if snapshot_path is None or not snapshot_path.exists():
        print("no local board snapshot found. Build one:\n"
              "  python3 scripts/draft-board/build_data.py", file=sys.stderr)
        return USAGE
    try:
        snapshot = BS.load(snapshot_path)
    except BS.SnapshotError as e:
        print(f"NOT COMPARABLE: {e}", file=sys.stderr)
        return NOT_COMPARABLE
    pulls = json.loads(pulls_path.read_text(encoding="utf-8"))
    layout = json.loads(layout_path.read_text(encoding="utf-8"))

    print(f"\nDIFF vs SHEET, LOCAL ENGINE   pull {pulls.get('label')} {pulls.get('pulled_at')}   "
          f"snapshot {snapshot['meta']['generated']} {snapshot['meta']['digest'][:12]}")
    code, lines = diff_local(snapshot, pulls, layout)
    defaults = SETTINGS.as_dict()
    stale = [k for k in INPUT_KEYS if snapshot["settings"].get(k) != defaults[k]]
    if stale and code != NOT_COMPARABLE:
        lines.append(f"FAIL: the snapshot was built with settings board_settings.py no longer "
                     f"holds ({', '.join(stale)}) -- rebuild it with build_data.py")
        code = MISMATCH
    for line in lines:
        print(f"  {line}")
    print({PASS: "  the local engine agrees with the sheet",
           MISMATCH: "  the local engine and the sheet DISAGREE",
           NOT_COMPARABLE: "  not comparable: nothing was diffed"}[code])
    return code
