#!/usr/bin/env python3
"""Pull the live draft board into one JSON file, for `verify.py --local`.

    python3 scripts/draft-board/pull_sheet.py                               # the live sheet
    python3 scripts/draft-board/pull_sheet.py --sheet-id ID --label copy    # a scenario copy

The sheet is read through `playwright-cli -s=fantasy`, the owner's signed-in browser, and by
no other route (AGENTS.md). One `eval` fetches every range through gviz's JSON endpoint, one
range at a time -- never with `Promise.all`. Firing all ~94 fetches in parallel failed live on
5+ consecutive attempts: exactly one came back non-JSON each time, at a different index every
run, and the resulting `SyntaxError` killed the whole eval without saying which range had
failed. Fetched one at a time, the identical plan has succeeded 94 of 94 on every attempt. A
reply that is not JSON, or that gviz answers with `status: "error"`, stops the loop and comes
back as a structured error naming the range (never the sheet id); `main` reports it and exits
1. gviz answers a private sheet only when the request carries `X-DataSource-Auth: true`.

Every range is ONE type. gviz sniffs a type per column and silently drops the cells that do
not match it -- in CSV and JSON alike. Settings B4:B11, which mixes numbers with the sort
label and the scoring format, came back as 6 cells of 8 with nothing to say two were gone.
So the plan splits every block by type, and every range states how many filled cells it
must return -- except a boolean range, which never refuses on a blank cell: an un-ticked
checkbox is a genuinely empty cell, not an explicit FALSE, so "not enough filled cells" is
the normal case rather than a sign anything is missing. The types come from what each column
holds, keyed off board_layout.json, and a column the table below does not know is an error
rather than a guess.

gviz also omits every row whose fetched cells are all empty, wherever that falls in the
range, not only at the end. Confirmed live: a fetch of Break alone returned 45 of 200 rows
(only the rows carrying a tier break); ADP, XRank and GAP together returned 171 of 200 (the
29 players with no ADP have blank XRank and GAP too, so their rows vanished). Every cell
below a dropped row silently moves up one row, with nothing to say so. So every range whose
columns can legitimately all be blank on the same player row also asks gviz, via `tq=select`,
for an always-filled anchor column from board_layout.json -- Draft Board and Board: `player`;
Category Tracker's category rows: `cat` -- inside a wider bounding `range`; the anchor keeps
gviz from dropping the row at all, and its own cell is stripped back out once the reply is in
hand, so the pull file's shape never carries it. An anchored reply that still comes back short
is refused outright rather than padded: with the anchor guaranteed present on every row, a
short reply cannot be explained away as "the tail of the range was empty."

The output is provider data. It is written under data/draft-board/pulls/, which is
gitignored and blocked by check-no-data.sh, and nothing is printed but counts.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_snapshot as BS  # noqa: E402

REPO = BS.REPO
LAYOUT = Path(__file__).resolve().parent / "board_layout.json"
ENV = REPO / ".env"
SESSION = "fantasy"

STRING, NUMBER, BOOLEAN = "string", "number", "boolean"

#: What each Draft Board column holds. Keys not listed here are matched by the patterns in
#: `column_type`; anything else stops the plan.
DRAFT_TYPES = {
    "rank": NUMBER, "tier": NUMBER, "round": NUMBER,
    "player": STRING, "team": STRING, "pos": STRING, "inj": STRING,
    "drafted": BOOLEAN, "mine": BOOLEAN,
    "sel": NUMBER, "drop": NUMBER, "med": NUMBER, "brk": STRING,
    "projGp": NUMBER, "myGp": NUMBER, "gpFlag": STRING,
    "adp": NUMBER, "xrank": NUMBER, "gap": NUMBER,
    "best": STRING, "strengths": STRING, "weaknesses": STRING, "posLeft": NUMBER,
    "notes": STRING, "rowCheck": STRING,
    "hFgm": NUMBER, "hFga": NUMBER, "hFtm": NUMBER, "hFta": NUMBER, "h3": NUMBER,
    "hPts": NUMBER, "hReb": NUMBER, "hAst": NUMBER, "hStl": NUMBER, "hBlk": NUMBER,
}
DRAFT_VALUE = re.compile(r"^(bmp|hbp|alt)(Durh|Zsh|Zsc)$")
DRAFT_TAG = re.compile(r"^(bmp|hbp|alt)(Durh|Zsh|Zsc)Tag$")

#: Columns that may be empty on any row. Every other Draft Board column is filled on every
#: board row, except these two, which are blank on the first row by construction.
DRAFT_OPTIONAL = {"brk", "gpFlag", "myGp", "adp", "xrank", "gap", "notes", "team", "pos"}
DRAFT_NOT_FIRST = {"drop", "med"}

#: The Board is pulled only for its name column and the columns typed by hand.
BOARD_TYPES = {"player": STRING, "gp1": NUMBER, "gp2": NUMBER, "gp3": NUMBER,
               "myGp": NUMBER, "xrank": NUMBER, "notes": STRING}
BOARD_FULL = {"player"}

SETTINGS_TYPES = {
    "teams": NUMBER, "roster": NUMBER, "q": NUMBER, "sort_by": STRING, "scoring": STRING,
    "tier_mult": NUMBER, "cat_band": NUMBER, "disagree_gap": NUMBER,
    "weak_win": NUMBER, "strong_win": NUMBER, "bank_win": NUMBER,
    "names_aligned": STRING, "rows_aligned": STRING, "board_rows": NUMBER, "mine": NUMBER,
    "adp_coverage": STRING, "generated": STRING, "injuries": STRING, "digest": STRING,
}
#: Pulled alone. Sheets reads the stamped date as a DATE, which gviz types apart from every
#: string near it, and the digest is the one cell the whole comparison hangs on.
SETTINGS_ALONE = frozenset({"generated", "digest"})

TRACKER_TYPES = {"cat": STRING, "my_team": NUMBER, "avg_team": NUMBER, "z": NUMBER,
                 "win": NUMBER, "read": STRING, "punted": BOOLEAN}
TRACKER_FULL = {"cat", "punted"}
ROSTER_TYPES = {"rank": NUMBER, "name": STRING, "pos": STRING}
PUNT_TYPES = {"rank": NUMBER, "name": STRING, "score": NUMBER, "adp": NUMBER, "gap": NUMBER}
PUNT_FULL = {"rank", "name", "score"}

GVIZ = "https://docs.google.com/spreadsheets/d/{id}/gviz/tq?tqx=out:json&headers=0"
DATE = re.compile(r"^Date\((\d+),(\d+),(\d+)(?:,\d+)*\)$")


class PullError(Exception):
    """The pull cannot be trusted. Nothing is written."""


def col_number(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def col_letter(n: int) -> str:
    """Build.gs's a1col."""
    s = ""
    while n > 0:
        n, m = divmod(n - 1, 26)
        s = chr(65 + m) + s
    return s


def parse_a1(a1: str) -> tuple[int, int, int, int]:
    """`B4:D11` -> (first col, first row, last col, last row). A single cell is 1x1."""
    m = re.match(r"^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$", a1)
    if not m:
        raise ValueError(f"not an A1 range: {a1!r}")
    c1, r1 = col_number(m.group(1)), int(m.group(2))
    c2 = col_number(m.group(3)) if m.group(3) else c1
    r2 = int(m.group(4)) if m.group(4) else r1
    return c1, r1, c2, r2


def column_type(tab: str, key: str) -> str:
    if tab == "Draft Board":
        if key in DRAFT_TYPES:
            return DRAFT_TYPES[key]
        if DRAFT_TAG.match(key):
            return STRING
        if DRAFT_VALUE.match(key) or key.startswith(("dh:", "d:", "rank:")):
            return NUMBER
    raise ValueError(f"pull_sheet.py does not know what {tab} column {key!r} holds -- "
                     "add it to the type table before pulling")


def _range(name_sheet: str, c1: int, r1: int, c2: int, r2: int, kind: str,
           min_cells: int, anchor: int | None = None) -> dict:
    """A range to fetch. `anchor`, when given, is an always-filled column index (never inside
    c1..c2) that rides along so gviz cannot drop a row where every *target* cell is blank.
    `range`/`name` stay the target's own address -- the contract verify_local reads -- while
    `fetch_range`/`select` carry what actually goes into the eval's request.
    """
    a1 = f"{col_letter(c1)}{r1}" + ("" if (c1, r1) == (c2, r2) else f":{col_letter(c2)}{r2}")
    out = {"name": f"{name_sheet}!{a1}", "sheet": name_sheet, "range": a1, "type": kind,
           "rows": r2 - r1 + 1, "cols": c2 - c1 + 1, "min_cells": min_cells}
    if anchor is not None:
        ac1, ac2 = min(c1, anchor), max(c2, anchor)
        out["fetch_range"] = (f"{col_letter(ac1)}{r1}"
                              + ("" if (ac1, r1) == (ac2, r2) else f":{col_letter(ac2)}{r2}"))
        out["anchor"] = anchor
        out["select"] = [col_letter(c) for c in range(c1, c2 + 1)] + [col_letter(anchor)]
    return out


def _runs(cols: list[tuple[int, str, int]]) -> list[tuple[int, int, str, int]]:
    """Adjacent columns of one type -> (first, last, type, summed minimum)."""
    out: list[tuple[int, int, str, int]] = []
    for index, kind, least in sorted(cols):
        if out and out[-1][1] == index - 1 and out[-1][2] == kind:
            first, _, _, total = out[-1]
            out[-1] = (first, index, kind, total + least)
        else:
            out.append((index, index, kind, least))
    return out


def _header(sheet: str, row: int, labels: dict[int, str]) -> dict:
    return _range(sheet, min(labels), row, max(labels), row, STRING,
                  sum(1 for text in labels.values() if text))


def _cells_by_column(tab: str, cells: dict[str, str], types: dict[str, str],
                     alone: frozenset[str] = frozenset()) -> list[dict]:
    """Single cells -> vertical runs of one type in one column. `alone` never joins a run."""
    placed = []
    for key, a1 in cells.items():
        c, r, _, _ = parse_a1(a1)
        placed.append((c, r, types[key], key))
    placed.sort()
    out: list[dict] = []
    run: list[tuple[int, int, str, str]] = []

    def flush():
        if run:
            c, r1, kind = run[0][0], run[0][1], run[0][2]
            out.append(_range(tab, c, r1, c, run[-1][1], kind, len(run)))
            run.clear()

    for c, r, kind, key in placed:
        if run and (c != run[-1][0] or r != run[-1][1] + 1 or kind != run[-1][2]
                    or key in alone or run[-1][3] in alone):
            flush()
        run.append((c, r, kind, key))
    flush()
    return out


def plan_ranges(layout: dict) -> list[dict]:
    """Every range to fetch, each of a single type, with the cells it must return."""
    tabs, first, last = layout["tabs"], layout["first_row"], layout["last_row"]
    rows = last - first + 1
    out: list[dict] = []

    # Header rows: the comparable check reads these before anything else.
    for tab in ("Draft Board", "Board", *BS.SOURCES):
        t = tabs[tab]
        out.append(_header(tab, t["header_row"],
                           {c["index"]: c["label"] for c in t["columns"].values()}))

    # Draft Board data, in runs of adjacent columns of one type. Break, the Flag, ADP/XRank/GAP,
    # Notes and GONE/MINE (before anyone touches a checkbox) can each be blank on a row, and
    # more than one of them can be blank on the SAME row -- exactly the shape gviz drops. Every
    # run but the one already holding `player` asks for it as an anchor; a run that can never
    # go fully blank pays one harmless extra column rather than needing its own case here.
    cols = []
    for key, c in tabs["Draft Board"]["columns"].items():
        least = 0 if key in DRAFT_OPTIONAL else rows - 1 if key in DRAFT_NOT_FIRST else rows
        cols.append((c["index"], column_type("Draft Board", key), least))
    anchor_col = tabs["Draft Board"]["columns"]["player"]["index"]
    for c1, c2, kind, least in _runs(cols):
        anchor = None if c1 <= anchor_col <= c2 else anchor_col
        out.append(_range("Draft Board", c1, first, c2, last, kind, least, anchor=anchor))

    # Board: the name column, then the hand columns. Every hand column is a human override,
    # blank on most rows, so every run but `player`'s own asks for `player` as an anchor.
    bcols = [(tabs["Board"]["columns"][k]["index"], kind, rows if k in BOARD_FULL else 0)
             for k, kind in BOARD_TYPES.items()]
    anchor_col_b = tabs["Board"]["columns"]["player"]["index"]
    for c1, c2, kind, least in _runs(bcols):
        anchor = None if c1 <= anchor_col_b <= c2 else anchor_col_b
        out.append(_range("Board", c1, first, c2, last, kind, least, anchor=anchor))

    # Settings: inputs and sanity cells, their labels, the reported weights and constants.
    s = tabs["Settings"]
    out += _cells_by_column("Settings", s["cells"], SETTINGS_TYPES, SETTINGS_ALONE)
    out += _cells_by_column("Settings", {k: v["cell"] for k, v in s["cell_labels"].items()},
                            dict.fromkeys(s["cell_labels"], STRING))
    out += _cells_by_column("Settings", s["weights"], dict.fromkeys(s["weights"], NUMBER))
    out += _cells_by_column("Settings", s["weight_labels"],
                            dict.fromkeys(s["weight_labels"], STRING))
    out += _cells_by_column("Settings", s["tracker_labels"],
                            dict.fromkeys(s["tracker_labels"], STRING))
    grid = [parse_a1(a) for block in s["tracker_constants"].values() for a in block.values()]
    out.append(_range("Settings", min(g[0] for g in grid), min(g[1] for g in grid),
                      max(g[0] for g in grid), max(g[1] for g in grid), NUMBER, len(grid)))

    # Category Tracker.
    t = tabs["Category Tracker"]
    c, r, _, _ = parse_a1(t["players_ticked"])
    out.append(_range("Category Tracker", c, r, c, r, NUMBER, 1))
    labels = {t["columns"][k]: t["column_labels"][k] for k in t["columns"]}
    out.append(_header("Category Tracker", t["header_row"], labels))
    ncat = len(s["weights"])
    cat_first, cat_last = t["first_cat_row"], t["first_cat_row"] + ncat - 1
    tcols = [(t["columns"][k], kind, ncat if k in TRACKER_FULL else 0)
             for k, kind in TRACKER_TYPES.items()]
    # Only eight rows here, and Punted especially can be blank on every one of them -- nobody
    # has to concede a category. `cat` (the category name) is always filled, so every run but
    # its own asks for it as an anchor. The roster block below is left as it was: MINE players
    # are listed from the top, so a short reply there can only be the natural tail, never a
    # gap in the middle.
    anchor_col_t = t["columns"]["cat"]
    for c1, c2, kind, least in _runs(tcols):
        anchor = None if c1 <= anchor_col_t <= c2 else anchor_col_t
        out.append(_range("Category Tracker", c1, cat_first, c2, cat_last, kind, least,
                          anchor=anchor))
    roster = {t["roster_columns"][k]: t["roster_labels"][k] for k in t["roster_columns"]}
    out.append(_header("Category Tracker", t["roster_header_row"], roster))
    r1, r2 = t["roster_first_row"], t["roster_first_row"] + t["roster_rows"] - 1
    rcols = [(t["roster_columns"][k], kind, 0) for k, kind in ROSTER_TYPES.items()]
    for c1, c2, kind, least in _runs(rcols):
        out.append(_range("Category Tracker", c1, r1, c2, r2, kind, least))

    # Punts: one header row across every block, then each block by type.
    p = tabs["Punts"]
    heads = {b["first_col"] + col["offset"]: col["label"]
             for b in p["blocks"] for col in p["columns"].values()}
    out.append(_header("Punts", p["header_row"], heads))
    r1, r2 = p["first_row"], p["first_row"] + p["rows"] - 1
    for b in p["blocks"]:
        pcols = [(b["first_col"] + col["offset"], PUNT_TYPES[k],
                  p["rows"] if k in PUNT_FULL else 0) for k, col in p["columns"].items()]
        for c1, c2, kind, least in _runs(pcols):
            out.append(_range("Punts", c1, r1, c2, r2, kind, least))
    return out


def build_eval(sheet_id: str, ranges: list[dict]) -> str:
    """One async function for `playwright-cli eval`: every range, fetched one at a time.

    The page has to be on docs.google.com for the request to carry the owner's cookies, which
    is why this runs inside the browser rather than from Python. Each table is cut down to its
    column ids and cells before it comes back, because the tool prints the result on stdout.

    Ranges are awaited in turn, never with `Promise.all`: firing all ~94 at once made exactly
    one non-JSON on every one of 5+ consecutive live attempts, at a different index each time,
    and the resulting SyntaxError killed the whole eval without saying which range had failed.
    So `one()` never lets a parse failure escape -- a bad reply becomes a same-shaped error
    result -- and the loop stops at the first one, returning a small object naming the range
    (never the sheet id) instead of throwing.
    """
    plan = []
    for r in ranges:
        entry = {"name": r["name"], "sheet": r["sheet"], "range": r.get("fetch_range", r["range"])}
        if "select" in r:
            # Backtick-quoted: gviz's query language is case-insensitive and a plain `BY`
            # parses as the `by` keyword (as in `group by`), not a column -- confirmed live,
            # `select BY` refuses `invalid_query` while `select \`BY\`` returns the column.
            # Every letter is quoted, not only the ones that happen to collide today.
            entry["select"] = ",".join(f"`{c}`" for c in r["select"])
        plan.append(entry)
    base = GVIZ.format(id=sheet_id)
    return (
        "async () => {\n"
        f"  const base = {json.dumps(base)};\n"
        f"  const plan = {json.dumps(plan, ensure_ascii=False)};\n"
        "  const one = async (p) => {\n"
        "    let url = base + '&sheet=' + encodeURIComponent(p.sheet)"
        " + '&range=' + encodeURIComponent(p.range);\n"
        "    if (p.select) url += '&tq=' + encodeURIComponent('select ' + p.select);\n"
        "    let status = 0, text;\n"
        "    try {\n"
        "      const res = await fetch(url, {credentials: 'include',"
        " headers: {'X-DataSource-Auth': 'true'}});\n"
        "      status = res.status;\n"
        "      text = await res.text();\n"
        "    } catch (e) {\n"
        "      return [p.name, {status: 'error', errors: [{reason: 'fetch_failed'}]}];\n"
        "    }\n"
        "    const i = text.indexOf('{'), j = text.lastIndexOf('}');\n"
        "    if (i < 0 || j < i) return [p.name, {status: 'error', errors:"
        " [{reason: 'http_' + status}]}];\n"
        "    let g;\n"
        "    try {\n"
        "      g = JSON.parse(text.slice(i, j + 1));\n"
        "    } catch (e) {\n"
        "      return [p.name, {status: 'error', errors: [{reason: 'invalid_json'}]}];\n"
        "    }\n"
        "    if (g.status === 'error' || !g.table) return [p.name, {status: 'error',"
        " errors: g.errors || []}];\n"
        "    return [p.name, {status: g.status, cols: g.table.cols.map(c => c.id),\n"
        "      rows: g.table.rows.map(r => (r.c || []).map(c => c == null ? null :\n"
        "        {v: c.v === undefined ? null : c.v, f: c.f === undefined ? null : c.f}))}];\n"
        "  };\n"
        "  const out = [];\n"
        "  for (const p of plan) {\n"
        "    const [name, result] = await one(p);\n"
        "    if (result.status === 'error') {\n"
        "      const reason = (result.errors && result.errors[0] &&"
        " result.errors[0].reason) || 'unknown';\n"
        "      return JSON.stringify({error: true, range: name, reason: reason});\n"
        "    }\n"
        "    out.push([name, result]);\n"
        "  }\n"
        "  return JSON.stringify(Object.fromEntries(out));\n"
        "}"
    )


def extract(stdout: str) -> dict:
    """The payload under `### Result`: a JSON-quoted string holding the JSON the eval built."""
    lines = stdout.splitlines()
    if any(ln.strip() == "### Error" for ln in lines):
        raise PullError("playwright-cli reported an error:\n" + stdout.strip()[-600:])
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "### Result")
    except StopIteration:
        raise PullError("no '### Result' section in the playwright-cli output") from None
    body = []
    for ln in lines[start + 1:]:
        if ln.startswith("### "):
            break
        body.append(ln)
    text = "\n".join(body).strip()
    if not text:
        raise PullError("the '### Result' section is empty")
    try:
        value = json.loads(text)
        if isinstance(value, str):
            value = json.loads(value)
    except json.JSONDecodeError as e:
        raise PullError(f"the result is not JSON: {e}") from None
    if not isinstance(value, dict):
        raise PullError("the result is not an object keyed by range")
    return value


def read_sheet_id(env_path: Path) -> str:
    """DRAFT_SHEET_ID from .env. The id stays out of every committed file."""
    key = "DRAFT_SHEET_ID"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == key:
                value = value.strip().strip("'\"")
                if value:
                    return value
    raise ValueError(f"{key} is not set in {env_path} -- add it, or pass --sheet-id")


def _cell(cell):
    """A gviz cell as the pull file stores it. Dates become ISO strings; "" is empty."""
    if cell is None:
        return None
    v, f = cell.get("v"), cell.get("f")
    if isinstance(v, str):
        m = DATE.match(v)
        if m:
            v = f"{int(m.group(1)):04d}-{int(m.group(2)) + 1:02d}-{int(m.group(3)):02d}"
    if v is None or v == "":
        return None if f in (None, "") else {"v": None, "f": f}
    return {"v": v, "f": f}


def assemble(raw: dict, ranges: list[dict], label: str, pulled_at: str) -> dict:
    """Place every returned table into its planned grid, or refuse the whole pull."""
    out: dict = {"pulled_at": pulled_at, "label": label, "ranges": {}}
    for r in ranges:
        got = raw.get(r["name"])
        if got is None:
            raise PullError(f"{r['name']}: missing from the result")
        if got.get("status") == "error":
            reasons = ", ".join(e.get("reason", "?") for e in got.get("errors", [])) or "?"
            raise PullError(f"{r['name']}: gviz refused ({reasons}) -- is the {SESSION} "
                            "profile signed in? Open the sheet with "
                            f"`playwright-cli -s={SESSION} open --persistent` from the repo root")
        c1 = parse_a1(r["range"])[0]
        ids = list(got.get("cols") or [])
        rows = [list(row) for row in (got.get("rows") or [])]

        anchor = r.get("anchor")
        if anchor is not None:
            # The anchor rides along so gviz cannot see an all-blank row in the target columns
            # -- it is always present, so a short reply here cannot be the tail of the range;
            # refuse rather than guess which row is missing. Its own cell never reaches the
            # pull file: it exists only to keep every planned row in the reply.
            try:
                anchor_pos = next(i for i, cid in enumerate(ids) if col_number(cid) == anchor)
            except StopIteration:
                raise PullError(f"{r['name']}: the anchor column is missing from the reply -- "
                                "gviz did not return what was asked for") from None
            if len(rows) != r["rows"]:
                raise PullError(f"{r['name']}: {len(rows)} of {r['rows']} rows came back with "
                                "the anchor present -- refusing rather than guessing which "
                                "row is missing")
            ids = [cid for i, cid in enumerate(ids) if i != anchor_pos]
            rows = [[cell for i, cell in enumerate(row) if i != anchor_pos] for row in rows]

        if len(ids) == r["cols"]:
            where = list(range(r["cols"]))
        else:
            # gviz left a column out. Place the rest by their ids: absolute letters when they
            # all fall inside the range, relative ones otherwise.
            nums = [col_number(i) for i in ids]
            if all(c1 <= n < c1 + r["cols"] for n in nums):
                where = [n - c1 for n in nums]
            elif all(1 <= n <= r["cols"] for n in nums):
                where = [n - 1 for n in nums]
            else:
                raise PullError(f"{r['name']}: returned columns {ids} do not fit the range")
        if len(rows) > r["rows"]:
            raise PullError(f"{r['name']}: {len(rows)} rows returned for {r['rows']} planned")
        # Without an anchor, gviz leaves off only TRAILING rows that are entirely empty, so the
        # last row it does return always holds something. A short reply that ends on an empty
        # row was cut off some other way, and nothing can be assumed about the rows after it --
        # refuse it rather than pad a truncation into blanks the engine would read as "no
        # value". An anchored range never reaches this check: it was already required to
        # return every planned row above.
        if (anchor is None and 0 < len(rows) < r["rows"]
                and all(_cell(c) is None for c in rows[-1])):
            raise PullError(f"{r['name']}: {len(rows)} of {r['rows']} rows came back and the "
                            "last one is empty -- gviz omits only trailing empty rows, so the "
                            "reply was truncated")
        grid = [[None] * r["cols"] for _ in range(r["rows"])]
        filled = 0
        for i, row in enumerate(rows):
            for j, cell in enumerate(row[: len(where)]):
                value = _cell(cell)
                if value is None and r["type"] == BOOLEAN:
                    # Sheets leaves an un-ticked checkbox with no value at all, not an explicit
                    # FALSE. verify_local already reads a missing boolean cell as false; this
                    # just makes the pull file say so plainly instead of leaving it implicit.
                    value = {"v": False, "f": None}
                grid[i][where[j]] = value
                if value is not None and value.get("v") is not None:
                    filled += 1
        if r["type"] != BOOLEAN and filled < r["min_cells"]:
            raise PullError(f"{r['name']}: {filled} filled cells, at least {r['min_cells']} "
                            f"expected -- gviz dropped cells of another type, or the range "
                            "is not what this layout says")
        out["ranges"][r["name"]] = {"sheet": r["sheet"], "range": r["range"],
                                    "type": r["type"], "cells": grid}
    return out


def main(argv: list[str] | None = None, root: Path = BS.ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet-id", help="pull this spreadsheet instead of .env DRAFT_SHEET_ID")
    ap.add_argument("--label", choices=("live", "copy"), default="live")
    ap.add_argument("--layout", type=Path, default=LAYOUT)
    args = ap.parse_args(argv)

    try:
        sheet_id = args.sheet_id or read_sheet_id(ENV)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    try:
        ranges = plan_ranges(json.loads(args.layout.read_text(encoding="utf-8")))
    except ValueError as e:
        print(f"pull refused: {e}", file=sys.stderr)
        return 1
    try:
        proc = subprocess.run(
            ["playwright-cli", f"-s={SESSION}", "eval", build_eval(sheet_id, ranges)],
            cwd=REPO, capture_output=True, text=True)
    except FileNotFoundError as e:
        print(f"playwright-cli not found: {e}", file=sys.stderr)
        return 1
    if proc.returncode != 0:
        print(f"playwright-cli exited {proc.returncode}:\n{proc.stderr.strip()[-600:]}",
              file=sys.stderr)
        return 1
    now = datetime.now(UTC)
    try:
        raw = extract(proc.stdout)
        if isinstance(raw, dict) and raw.get("error"):
            raise PullError(f"{raw.get('range', '?')}: {raw.get('reason', '?')}")
        pull = assemble(raw, ranges, args.label, now.isoformat(timespec="seconds"))
    except PullError as e:
        print(f"pull refused: {e}", file=sys.stderr)
        return 1
    out = root / "pulls" / f"{now.strftime('%Y-%m-%dT%H%M%SZ')} {args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pull, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    cells = sum(1 for r in pull["ranges"].values() for row in r["cells"] for c in row if c)
    print(f"wrote {out}\n  {len(ranges)} ranges, {cells} filled cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
