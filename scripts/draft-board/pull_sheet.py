#!/usr/bin/env python3
"""Pull the live draft board into one JSON file, for `verify.py --local`.

    python3 scripts/draft-board/pull_sheet.py                               # the live sheet
    python3 scripts/draft-board/pull_sheet.py --sheet-id ID --label copy    # a scenario copy

The sheet is read through `playwright-cli -s=fantasy`, the owner's signed-in browser, and by
no other route (AGENTS.md). One `run-code` downloads the whole workbook as xlsx through the
browser's own request context (`page.request`, which carries the profile's cookies and follows
the export's redirect off docs.google.com), so a pull is one request of a few seconds. It
replaced ~94 sequential gviz range fetches that took about 1.5 minutes: an xlsx pull of the
live sheet matched the last gviz pull on every cell the ticks do not drive, and passed
`verify.py --local` on all of them.

xlsx carries each cell's stored value and type, so none of gviz's hazards apply: no per-column
type sniffing, no dropped all-empty rows, checkboxes as real booleans, errors as errors. The
workbook is read with the standard library only (`zipfile`, `xml.etree`). The planned ranges
from board_layout.json are what verify reads; each still states how many filled cells it must
hold, so a layout that no longer matches the sheet is refused rather than diffed.

The output is provider data. It is written under data/draft-board/pulls/, which is
gitignored and blocked by check-no-data.sh, and nothing is printed but a path and counts.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, date, datetime, timedelta
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
#: Each its own range. Sheets stores the stamped date as a date serial, converted to ISO, and
#: the digest is the one cell the whole comparison hangs on.
SETTINGS_ALONE = frozenset({"generated", "digest"})

TRACKER_TYPES = {"cat": STRING, "my_team": NUMBER, "avg_team": NUMBER, "z": NUMBER,
                 "win": NUMBER, "read": STRING, "punted": BOOLEAN}
TRACKER_FULL = {"cat", "punted"}
ROSTER_TYPES = {"rank": NUMBER, "name": STRING, "pos": STRING}
PUNT_TYPES = {"rank": NUMBER, "name": STRING, "score": NUMBER, "adp": NUMBER, "gap": NUMBER}
PUNT_FULL = {"rank", "name", "score"}

EXPORT = "https://docs.google.com/spreadsheets/d/{id}/export?format=xlsx"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
EPOCH = date(1899, 12, 30)
XLSX_SIG_DIGITS = 10


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
           min_cells: int) -> dict:
    """A planned range: the cells verify reads, their type, and how many must be filled."""
    a1 = f"{col_letter(c1)}{r1}" + ("" if (c1, r1) == (c2, r2) else f":{col_letter(c2)}{r2}")
    return {"name": f"{name_sheet}!{a1}", "sheet": name_sheet, "range": a1, "type": kind,
            "rows": r2 - r1 + 1, "cols": c2 - c1 + 1, "min_cells": min_cells}


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

    # Draft Board data, in runs of adjacent columns of one type.
    cols = []
    for key, c in tabs["Draft Board"]["columns"].items():
        least = 0 if key in DRAFT_OPTIONAL else rows - 1 if key in DRAFT_NOT_FIRST else rows
        cols.append((c["index"], column_type("Draft Board", key), least))
    for c1, c2, kind, least in _runs(cols):
        out.append(_range("Draft Board", c1, first, c2, last, kind, least))

    # Board: the name column, then the hand columns (human overrides, blank on most rows).
    bcols = [(tabs["Board"]["columns"][k]["index"], kind, rows if k in BOARD_FULL else 0)
             for k, kind in BOARD_TYPES.items()]
    for c1, c2, kind, least in _runs(bcols):
        out.append(_range("Board", c1, first, c2, last, kind, least))

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
    for c1, c2, kind, least in _runs(tcols):
        out.append(_range("Category Tracker", c1, cat_first, c2, cat_last, kind, least))
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


def build_code(sheet_id: str) -> str:
    """One async function for `playwright-cli run-code`: download the workbook as xlsx.

    `page.request` shares the signed-in profile's cookies and is not bound by the page's CORS,
    so it follows the export's redirect to googleusercontent. The bytes come back base64.
    """
    url = EXPORT.format(id=sheet_id)
    return ("async page => { const r = await page.request.get(" + json.dumps(url) + ");"
            " const b = await r.body();"
            " return JSON.stringify({status: r.status(),"
            " type: r.headers()['content-type'] || '', b64: b.toString('base64')}); }")


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
        raise PullError("the result is not a JSON object")
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


def read_xlsx(data: bytes) -> tuple[set[str], dict[tuple[str, int, int], dict | None]]:
    """(sheet names, every stored cell by (sheet, column, row)). Errors keep their text in `f`."""
    if not data.startswith(b"PK"):
        raise PullError("the download is not an xlsx file -- is the "
                        f"{SESSION} profile signed in? Open the sheet with "
                        f"`playwright-cli -s={SESSION} open --persistent` from the repo root")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(t.text or "" for t in si.iter(NS + "t"))
                      for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si")]
        rels = {r.get("Id"): r.get("Target", "") for r in
                ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(PKG + "Relationship")}
        parts = {}
        for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(NS + "sheet"):
            target = rels[sh.get(REL + "id")].lstrip("/")
            parts[sh.get("name")] = target if target.startswith("xl/") else "xl/" + target
        grid: dict[tuple[str, int, int], dict | None] = {}
        for name, part in parts.items():
            for c in ET.fromstring(z.read(part)).iter(NS + "c"):
                m = re.match(r"^([A-Z]+)(\d+)$", c.get("r", ""))
                if not m:
                    raise PullError(f"{name}: a cell with no A1 reference")
                t, v = c.get("t"), c.find(NS + "v")
                text = None if v is None else (v.text or "")
                if t == "inlineStr":
                    cell = {"v": "".join(x.text or "" for x in c.iter(NS + "t")), "f": None}
                elif text is None:
                    continue
                elif t == "s":
                    cell = {"v": shared[int(text)], "f": None}
                elif t == "b":
                    cell = {"v": text == "1", "f": None}
                elif t == "e":
                    cell = {"v": None, "f": text}
                elif t == "str":
                    cell = {"v": text, "f": None}
                else:
                    x = float(text)
                    whole = x.is_integer() and not any(ch in text for ch in ".eE")
                    cell = {"v": int(x) if whole else x, "f": None}
                if cell["v"] == "" and not cell["f"]:
                    cell = None
                grid[(name, col_number(m.group(1)), int(m.group(2)))] = cell
    except (zipfile.BadZipFile, KeyError, ValueError, IndexError, ET.ParseError) as e:
        raise PullError(f"the xlsx could not be read ({type(e).__name__}: {e})") from None
    return set(parts), grid


def assemble(sheets: set[str], grid: dict, ranges: list[dict], label: str, pulled_at: str,
             dates: frozenset[str] = frozenset()) -> dict:
    """Place every planned range from the workbook, or refuse the whole pull.

    `dates` names single-cell ranges Sheets stores as a date serial; they become ISO strings.
    """
    # Sheets writes every number into an xlsx export to 10 significant digits (a tracker
    # average of 155.58333333333331 arrives as 155.5833333), so verify compares at that.
    out: dict = {"pulled_at": pulled_at, "label": label, "sig_digits": XLSX_SIG_DIGITS,
                 "ranges": {}}
    for r in ranges:
        if r["sheet"] not in sheets:
            raise PullError(f"{r['name']}: the workbook has no {r['sheet']!r} tab")
        c1, r1, _, _ = parse_a1(r["range"])
        cells, filled = [], 0
        for i in range(r["rows"]):
            row = []
            for j in range(r["cols"]):
                cell = grid.get((r["sheet"], c1 + j, r1 + i))
                if r["type"] == BOOLEAN and cell is None:
                    cell = {"v": False, "f": None}
                if (r["name"] in dates and cell is not None
                        and isinstance(cell["v"], int | float) and not isinstance(cell["v"], bool)):
                    cell = {"v": (EPOCH + timedelta(days=int(cell["v"]))).isoformat(), "f": None}
                if cell is not None and cell["v"] is not None:
                    filled += 1
                row.append(cell)
            cells.append(row)
        if r["type"] != BOOLEAN and filled < r["min_cells"]:
            raise PullError(f"{r['name']}: {filled} filled cells, at least {r['min_cells']} "
                            "expected -- the range is not what this layout says")
        out["ranges"][r["name"]] = {"sheet": r["sheet"], "range": r["range"],
                                    "type": r["type"], "cells": cells}
    return out


def pull(sheet_id: str, label: str, layout: dict, root: Path = BS.ROOT) -> tuple[Path, dict]:
    """Download, read and write one pull. Raises PullError; no message carries the sheet id."""
    ranges = plan_ranges(layout)
    dates = frozenset({f"Settings!{layout['tabs']['Settings']['cells']['generated']}"})
    try:
        try:
            proc = subprocess.run(["playwright-cli", f"-s={SESSION}", "run-code",
                                   build_code(sheet_id)], cwd=REPO, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise PullError(f"playwright-cli not found: {e}") from None
        if proc.returncode != 0:
            raise PullError(f"playwright-cli exited {proc.returncode}:\n"
                            f"{proc.stderr.strip()[-600:]}")
        got = extract(proc.stdout)
        if got.get("status") != 200:
            raise PullError(f"the export answered HTTP {got.get('status')} -- is the {SESSION} "
                            "profile signed in?")
        sheets, grid = read_xlsx(base64.b64decode(got.get("b64") or ""))
        now = datetime.now(UTC)
        out = assemble(sheets, grid, ranges, label, now.isoformat(timespec="seconds"), dates)
    except PullError as e:
        raise PullError(str(e).replace(sheet_id, "<sheet id>")) from None
    path = root / "pulls" / f"{now.strftime('%Y-%m-%dT%H%M%SZ')} {label}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")
    return path, out


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
    started = time.monotonic()
    try:
        path, out = pull(sheet_id, args.label,
                         json.loads(args.layout.read_text(encoding="utf-8")), root)
    except (PullError, ValueError) as e:
        print(f"pull refused: {e}", file=sys.stderr)
        return 1
    cells = sum(1 for r in out["ranges"].values() for row in r["cells"] for c in row if c)
    print(f"wrote {path}\n  {len(out['ranges'])} ranges, {cells} filled cells, "
          f"{time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
