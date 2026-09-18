#!/usr/bin/env python3
"""The tick scenario on a copy of the draft board, as one command.

    python3 scripts/draft-board/tick_scenario.py --sheet-id ID --allow-consent

Ticks drive most of what board_engine.py re-implements, and the owner's sheet cannot be used to
exercise them, so this copies the live sheet, drives the copy through `playwright-cli -s=fantasy
run-code`, and after every step downloads the copy (pull_sheet.pull) and runs the full
`verify.py --local` comparison in process. Every cell is checked at every step. The copy is
deleted at the end, pass or fail.

Steps: copy; untick anything inherited (Space, never Delete); a. MINE 8 then 14 (the tracker's
cap); b. CMP on eight spread rows, two of them MINE, so Compare picks shows five of six and says
so; c. one punted category, then two; f. the Clear all box beside Compare picks, which must
untick every CMP and itself; g. CMP on three rows, then MINE on a fifteenth, which must clear
them (ADR-0028); d. a new
Sort by and Rebuild & re-sort (the copy's first script run, so Google asks to authorise it);
e. two swapped Board names on clean rows and a hand value (GP Y-1) on one of the swapped rows,
then Refresh data -- the reordering path. Verify compares My GP on every row, so its pass is the
C1 check. Refresh keys hand values by the name a row shows when it runs, so the value belongs to
the swapped-in player and must land on whichever row that player occupies afterwards; a value
kept by row position fails. It goes in GP Y-1 because the Name Box cannot reach My GP on this
sheet: Board W and Z sit in hidden columns, and the Name Box lands on the next visible one.

Two tiers, because steps d and e each cost a full Apps Script execution on the copy and that is
most of the wall-clock (ADR-0025):

  ticks  steps a-c, f and g. The default. No consent, no script run, no menu.
  full   adds d and e. `--full`, and it needs `--allow-consent`.

`--allow-consent` is the owner's approval, given before the run, to click Allow on the copy's
authorisation screen. Without it a full run stops at step d (exit 5).

**The gate reads the generated formulas, not the filenames.** `node harness.js
--tick-fingerprint` builds the workbook offline and hashes the formulas each tier can reach;
`tier_needed` compares those to the last passing run and returns "none", "ticks" or "full".
Gating on `Build.gs` having changed at all was the defect this replaced: it is one 2,600-line
file covering nine tabs, so editing a column width used to trip a four-minute browser run.
A width moves no formula, so it now moves no hash. `--force` runs the tick tier regardless.

Output is one line per step. Never a sheet id, a title or a player name: the pulls are provider
data and stay under data/draft-board/pulls/, gitignored.
Exit: 0 pass or not needed, 1 a step failed, 2 usage, 5 consent not allowed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_snapshot as BS  # noqa: E402
import pull_sheet as PS  # noqa: E402
import verify_local as VL  # noqa: E402

WATCHED = ("scripts/draft-board/Build.gs", "scripts/draft-board/board_engine.py")
ENGINE = "scripts/draft-board/board_engine.py"
LAST = BS.ROOT / "pulls" / "last-scenario"
CMP_ROWS = (5, 9, 25, 40, 60, 80, 100, 130)   # 5 and 9 are MINE too: six reach the panel
CLEAR_ROWS = (150, 160, 170)                   # CMP ticks a MINE tick must then clear
MINE_ROW = 190
NEW_SORT = "HBP · DURH"
OVERRIDE = 50


class StepFailed(Exception):
    pass


class NeedsConsent(Exception):
    pass


# ------------------------------------------------------------------ pure helpers (tested)

def needed(repo: Path, last: Path) -> bool:
    """True unless a passing run is recorded and nothing it covers changed since.

    The coarse, file-level gate. Superseded by `tier_needed` for deciding what to run and
    kept only for the `engine_changed` half of it (ADR-0025).
    """
    if not last.exists():
        return True
    sha = _stamp(last).get("sha", "")
    diff = subprocess.run(["git", "diff", "--name-only", sha, "--", *WATCHED], cwd=repo,
                          capture_output=True, text=True)
    return diff.returncode != 0 or bool(diff.stdout.strip())


def _stamp(last: Path) -> dict:
    """The recorded pass. A pre-fingerprint stamp was a bare sha and carries no hashes."""
    if not last.exists():
        return {}
    text = last.read_text(encoding="utf-8").strip()
    try:
        got = json.loads(text)
        return got if isinstance(got, dict) else {}
    except json.JSONDecodeError:
        return {"sha": text}


def fingerprint(repo: Path) -> dict:
    """The harness's two hashes over the GENERATED formulas. Offline, about two seconds."""
    proc = subprocess.run(["node", str(Path(__file__).with_name("harness.js")),
                           "--tick-fingerprint"], cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        raise StepFailed(f"harness --tick-fingerprint exited {proc.returncode}: "
                         f"{proc.stderr.strip()[-300:]}")
    return json.loads(proc.stdout.strip())


def engine_changed(repo: Path, last: Path) -> bool:
    """Has the Python mirror moved since the last pass? It is not in the sheet, so no hash
    covers it -- but it is what every step compares against."""
    sha = _stamp(last).get("sha")
    if not sha:
        return True
    diff = subprocess.run(["git", "diff", "--name-only", sha, "--", ENGINE], cwd=repo,
                          capture_output=True, text=True)
    return diff.returncode != 0 or bool(diff.stdout.strip())


def tier_needed(repo: Path, last: Path, fp: dict, engine_changed: bool) -> str:
    """How much of the scenario this change can affect: "none", "ticks" or "full".

    Gating on the generated formulas rather than on which file was edited is the point.
    `Build.gs` is one file covering nine tabs, so a column width used to trip a four-minute
    browser run; a width moves no formula, so it now moves no hash (ADR-0025).

    A stamp with no hashes -- never run, or written before the fingerprint existed -- proves
    everything, because "unknown" must never read as "unchanged".
    """
    stamp = _stamp(last)
    if not stamp.get("tick") or not stamp.get("rebuild"):
        return "full"
    if stamp["rebuild"] != fp["rebuild"]:
        return "full"
    if stamp["tick"] != fp["tick"] or engine_changed:
        return "ticks"
    return "none"


def counts(sheet: VL._Pull, layout: dict) -> dict:
    d, t = layout["tabs"]["Draft Board"]["columns"], layout["tabs"]["Category Tracker"]
    rows = range(layout["first_row"], layout["last_row"] + 1)
    ncat = len(layout["tabs"]["Settings"]["weights"])

    def ticked(sheet_name: str, col: int, row_numbers) -> int:
        return sum(VL._v(sheet.cell(sheet_name, col, r)) is True for r in row_numbers)

    cats = range(t["first_cat_row"], t["first_cat_row"] + ncat)
    c = t["compare"]
    col, row, _, _ = PS.parse_a1(c["clear"])
    return {"mine": ticked("Draft Board", d["mine"]["index"], rows),
            "cmp": ticked("Draft Board", d["cmp"]["index"], rows),
            "punted": ticked("Category Tracker", t["columns"]["punted"], cats),
            "slots": sum(1 for s in c["slots"]
                         if VL._text(sheet.cell("Category Tracker", s["index"], c["slot_row"]))),
            "clear": ticked("Category Tracker", col, (row,))}


def ticked_cells(sheet: VL._Pull, layout: dict) -> list[tuple[str, str]]:
    """(tab, A1) of every tick the copy inherited."""
    d, t = layout["tabs"]["Draft Board"]["columns"], layout["tabs"]["Category Tracker"]
    out = [("Draft Board", f"{d[k]['letter']}{r}")
           for k in ("cmp", "mine") for r in range(layout["first_row"], layout["last_row"] + 1)
           if VL._v(sheet.cell("Draft Board", d[k]["index"], r)) is True]
    col = t["columns"]["punted"]
    for i in range(len(layout["tabs"]["Settings"]["weights"])):
        if VL._v(sheet.cell("Category Tracker", col, t["first_cat_row"] + i)) is True:
            out.append(("Category Tracker", f"{PS.col_letter(col)}{t['first_cat_row'] + i}"))
    return out


def clean_rows(sheet: VL._Pull, layout: dict) -> tuple[int, str, int, str]:
    """Two Board rows to swap, neither carrying a tick, note or hand value.

    The Draft Board points at fixed Board rows (I1), so a swapped name beside a tick would move
    the tick onto another player and verify, which reads ticks back as truth, would still pass.
    """
    first, last = layout["first_row"], layout["last_row"]
    d, b = layout["tabs"]["Draft Board"]["columns"], layout["tabs"]["Board"]["columns"]
    draft = lambda k, r: sheet.cell("Draft Board", d[k]["index"], r)  # noqa: E731
    board = lambda k, r: sheet.cell("Board", b[k]["index"], r)  # noqa: E731
    touched = set()
    for r in range(first, last + 1):
        gp, my = VL._num(draft("projGp", r)), VL._num(draft("myGp", r))
        if (VL._v(draft("cmp", r)) is True or VL._v(draft("mine", r)) is True
                or VL._text(draft("notes", r)) or VL._v(draft("xrank", r)) is not None
                or gp is None or my is None or abs(gp - my) > 1e-9):
            touched.add(VL._text(draft("player", r)))
    clean = [(r, VL._text(board("player", r))) for r in range(first, last + 1)
             if VL._text(board("player", r)) and VL._text(board("player", r)) not in touched
             and not VL._text(board("notes", r))
             and all(VL._v(board(k, r)) is None for k in ("gp1", "gp2", "gp3", "xrank"))]
    if len(clean) < 2:
        raise StepFailed("fewer than two clean Board rows")
    (ra, na), (rb, nb) = clean[-1], clean[-2]
    return ra, na, rb, nb


def sort_applied(sheet: VL._Pull, layout: dict, lines: list[str], want: str) -> str | None:
    """None when Settings SORT_BY reads `want` and verify saw the board sorted by it, else why.

    Verify accepts whatever sort the board shows, and onEdit swallows its own errors, so a sort
    that never reached SORT_BY would otherwise pass as a re-sort.
    """
    label = VL._text(sheet.at("Settings", layout["tabs"]["Settings"]["cells"]["sort_by"]))
    if label != want:
        return f"Settings SORT_BY reads {label!r}, not {want!r}"
    if f"ok: the board is sorted by {want}" not in lines:
        return f"SORT_BY reads {want!r} but the board is not sorted by it"
    return None


def hand_value_followed(sheet: VL._Pull, layout: dict, owner: str, other: str,
                        value: float) -> str | None:
    """None when `value` sits in GP Y-1 on `owner`'s Board row and not on `other`'s, else why."""
    b = layout["tabs"]["Board"]["columns"]
    rows = {VL._text(sheet.cell("Board", b["player"]["index"], r)): r
            for r in range(layout["first_row"], layout["last_row"] + 1)}
    if owner not in rows or other not in rows:
        return "a swapped player is no longer on the Board"
    if VL._num(sheet.cell("Board", b["gp1"]["index"], rows[owner])) != value:
        return "the hand value did not follow its player to the player's new row"
    if VL._num(sheet.cell("Board", b["gp1"]["index"], rows[other])) is not None:
        return "the hand value was also left on the row it was typed on, under another player"
    return None


# ------------------------------------------------------------------ the browser

class Browser:
    """Runs one Playwright snippet at a time against the copy's tab, found by its id."""

    def __init__(self, sheet_id: str):
        self.live_id, self.copy_id, self.title = sheet_id, None, None

    def run(self, body: str, **args) -> dict:
        code = ("async page => { const A = " + json.dumps(args) + ";"
                " const pages = page.context().pages();"
                " const copy = A.copy ? pages.find(p => p.url().includes(A.copy)) : null;"
                # The live sheet has to be open for anything here to find it. Left implicit,
                # a session parked on another page died on `live.locator` -- an opaque
                # TypeError, thrown after the point where a copy can already exist in Drive.
                # Open it instead: the scenario is a standalone command and must not depend
                # on where a previous command happened to leave the browser.
                " let live = pages.find(p => p.url().includes(A.live));"
                " if (!live) {"
                "   live = await page.context().newPage();"
                "   await live.goto('https://docs.google.com/spreadsheets/d/' + A.live + '/edit');"
                "   await live.waitForSelector('#docs-menubar', {timeout: 60000});"
                "   await live.waitForTimeout(2000); }"
                " const nameBox = async (p, tab, a1) => {"
                "   await p.locator('.docs-sheet-tab-name',"
                "     {hasText: new RegExp('^' + tab + '$')}).first().click();"
                "   await p.waitForTimeout(800);"
                "   const nb = p.locator('#t-name-box'); await nb.click(); await nb.fill(a1);"
                "   await nb.press('Enter'); await p.waitForTimeout(500); };"
                " const menu = async (p, top, item) => {"
                "   await p.locator('#docs-menubar .menu-button',"
                "     {hasText: new RegExp('^' + top + '$')}).click();"
                "   await p.locator('.goog-menuitem:visible', {hasText: item}).first().click(); };"
                + body + " }")
        proc = subprocess.run(["playwright-cli", f"-s={PS.SESSION}", "run-code", code],
                              cwd=PS.REPO, capture_output=True, text=True)
        try:
            if proc.returncode:
                raise PS.PullError(proc.stderr.strip()[-300:] or proc.stdout.strip()[-300:])
            return PS.extract(proc.stdout)
        except PS.PullError as e:
            msg = str(e)
            typed = [x for v in args.values() if isinstance(v, list) for row in v
                     for x in (row if isinstance(row, list | tuple) else [row])
                     if isinstance(x, str) and len(x) > 2]
            for secret in filter(None, (self.live_id, self.copy_id, self.title, *typed)):
                msg = msg.replace(secret, "<redacted>")
            raise StepFailed(f"browser: {msg[-300:]}") from None

    def make_copy(self) -> None:
        """Copy the live sheet. Once the copy has an id it is recorded before anything else can
        fail, so main's cleanup deletes it; a failure before that says a copy may exist."""
        got = self.run(
            "await menu(live, 'File', 'Make a copy');"
            " const btn = live.getByRole('button', {name: 'Make a copy'});"
            " const [np] = await Promise.all(["
            " page.context().waitForEvent('page', {timeout: 60000}),"
            " btn.click()]);"
            " await np.waitForURL(/\\/spreadsheets\\/d\\//, {timeout: 60000});"
            " const id = np.url().split('/d/')[1].split('/')[0];"
            " try { await np.locator('#t-name-box').waitFor({timeout: 90000}); }"
            " catch (e) { return JSON.stringify({id, error: 'the copy never finished loading'}); }"
            " return JSON.stringify({id,"
            " title: (await np.title()).replace(/ - Google Sheets$/, '')});",
            live=self.live_id)
        if got.get("id") and got["id"] != self.live_id:
            self.copy_id, self.title = got["id"], got.get("title")
        if got.get("error"):
            raise StepFailed(got["error"])
        if not self.copy_id or not (self.title or "").startswith("Copy of "):
            raise StepFailed("the new tab is not a copy")

    def toggle(self, cells: list[tuple[str, str]]) -> None:
        """Space on each cell or range: ticks an unticked checkbox, unticks a ticked one."""
        self.run("for (const [tab, a1] of A.cells) { await nameBox(copy, tab, a1);"
                 " await copy.keyboard.press('Space'); await copy.waitForTimeout(200); }"
                 " return '{}';", copy=self.copy_id, live=self.live_id, cells=cells)

    def type_into(self, entries: list[tuple[str, str, str]]) -> None:
        self.run("for (const [tab, a1, text] of A.entries) { await nameBox(copy, tab, a1);"
                 " await copy.keyboard.type(text); await copy.keyboard.press('Enter');"
                 " await copy.waitForTimeout(300); } return '{}';",
                 copy=self.copy_id, live=self.live_id, entries=entries)

    def draft_menu(self, item: str, done: str, allow: bool) -> None:
        """Run a Draft Board menu item and wait for its completion toast, authorising once."""
        got = self.run(
            "const bar = () => copy.locator('#docs-menubar .menu-button',"
            " {hasText: /^Draft Board$/});"
            " try { await bar().waitFor({timeout: 60000}); } catch (e) {"
            "   await copy.reload(); await copy.locator('#t-name-box').waitFor({timeout: 90000});"
            "   await bar().waitFor({timeout: 90000}); }"
            " await menu(copy, 'Draft Board', A.item);"
            " const doneText = copy.getByText(new RegExp(A.done)).first();"
            " const auth = copy.getByText('Authorization required').first();"
            " const first = await Promise.race(["
            " doneText.waitFor({timeout: 300000}).then(() => 'done', () => 'timeout'),"
            " auth.waitFor({timeout: 300000}).then(() => 'auth', () => 'timeout')]);"
            " if (first === 'timeout') throw new Error('the menu action never finished');"
            " if (first === 'done') return JSON.stringify({ok: true});"
            " if (!A.allow) return JSON.stringify({consent: true});"
            " const [pop] = await Promise.all(["
            " page.context().waitForEvent('page', {timeout: 60000}),"
            " copy.getByRole('button', {name: /^(OK|Continue|Review permissions)$/})"
            ".first().click()]);"
            " await pop.waitForLoadState('domcontentloaded');"
            " const allow = pop.getByRole('button', {name: /^(Allow|Continue)$/}).first();"
            " const account = pop.locator('[data-identifier]').first();"
            " const advanced = pop.getByText('Advanced', {exact: true}).first();"
            " const seen = async (loc) => loc.isVisible().catch(() => false);"
            " for (let k = 0; k < 60 && !(await seen(allow)); k++) {"
            "   if (await seen(account)) { await account.click(); await pop.waitForTimeout(2000); }"
            "   else if (await seen(advanced)) { await advanced.click();"
            "     await pop.getByText(/^Go to .*\\(unsafe\\)$/).first().click();"
            "     await pop.waitForTimeout(2000); }"
            "   else await pop.waitForTimeout(1000); }"
            " const all = pop.getByText('Select all', {exact: true}).first();"
            " if (await seen(all)) { await all.click(); await pop.waitForTimeout(500); }"
            " await allow.click({timeout: 30000});"
            " await pop.waitForEvent('close', {timeout: 60000}).catch(() => {});"
            " await doneText.waitFor({timeout: 300000});"
            " return JSON.stringify({ok: true, authorised: true});",
            copy=self.copy_id, live=self.live_id, item=item, done=done, allow=allow)
        if got.get("consent"):
            raise NeedsConsent()

    def delete_copy(self) -> None:
        """Trash the copy, then Delete forever on that one id in Drive's Trash, proving each stage
        from the file's own page. By id, never by title: an older copy can share the title."""
        got = self.run(
            "for (const p of page.context().pages()) if (p.url().includes(A.copy)) await p.close();"
            " const edit = 'https://docs.google.com/spreadsheets/d/' + A.copy + '/edit';"
            " const state = async () => { const c = await page.context().newPage();"
            "   await c.goto(edit); await c.waitForTimeout(8000);"
            "   const trashed = await c.getByText('File is in trash').count();"
            "   const opens = await c.locator('#t-name-box').count();"
            "   return {c, trashed, opens}; };"
            " let s = await state();"
            " for (let k = 0; k < 3 && s.opens && !s.trashed; k++) {"
            "   await s.c.keyboard.press('Escape');"
            "   await menu(s.c, 'File', /Move to (trash|bin)/); await s.c.waitForTimeout(2500);"
            "   const ok = s.c.getByRole('button', {name: /^Move to (trash|bin)$/});"
            "   if (await ok.count()) await ok.first().click();"
            "   await s.c.waitForTimeout(5000); await s.c.close(); s = await state(); }"
            " await s.c.close();"
            " const t = await page.context().newPage();"
            " for (let k = 0; k < 2 && s.opens; k++) {"
            "   await t.goto('https://drive.google.com/drive/trash');"
            "   const row = t.locator('[data-id=\"' + A.copy + '\"]').first();"
            "   for (let w = 0; w < 18 && !(await row.count()); w++) {"
            "     await t.waitForTimeout(10000); if (!(await row.count())) await t.reload(); }"
            "   if (await row.count()) { await row.click({button: 'right'});"
            "     await t.getByRole('menuitem', {name: /^Delete forever$/}).first().click();"
            "     await t.waitForTimeout(1500);"
            "     const b = t.getByRole('button', {name: /^Delete forever$/});"
            "     if (await b.count()) await b.first().click();"
            "     await t.waitForTimeout(5000); }"
            "   s = await state(); await s.c.close(); }"
            " await t.close();"
            " return JSON.stringify({trashed: s.trashed, opens: s.opens});",
            copy=self.copy_id, live=self.live_id)
        if got.get("opens") or got.get("trashed"):
            raise StepFailed(f"the copy still exists after deletion ({got})")


# ------------------------------------------------------------------ the scenario

class Scenario:
    def __init__(self, browser: Browser, layout: dict, snapshot: dict):
        self.b, self.layout, self.snapshot = browser, layout, snapshot
        self.sheet: VL._Pull | None = None
        self.lines: list[str] = []

    def check(self, step: str, expect: dict | None = None, tries: int = 6,
              verify: bool = True) -> VL._Pull:
        """Pull and verify; retry while the copy has not saved the expected counts yet."""
        out: dict = {}
        got: dict = {}
        started = time.monotonic()
        for attempt in range(tries):
            started = time.monotonic()
            _, out = PS.pull(self.b.copy_id, "copy", self.layout)
            sheet = VL._Pull(out)
            got = counts(sheet, self.layout)
            if expect is None or all(got[k] == v for k, v in expect.items()):
                break
            if attempt == tries - 1:
                raise StepFailed(f"step {step}: counts {got}, expected {expect} -- "
                                 "a checkbox did not toggle (is its checkbox rule missing?)")
            time.sleep(1.5)
        # Mid-step e the Board's names are swapped on purpose, which the comparable check
        # refuses by design; that pull only proves the edits landed.
        code, lines = VL.diff_local(self.snapshot, out, self.layout) if verify else (0, [])
        print(f"step {step:<10} mine={got['mine']:<3} cmp={got['cmp']:<3} "
              f"punted={got['punted']} slots={got['slots']}  "
              f"pull {time.monotonic() - started:.1f}s  verify exit {code}", flush=True)
        if code != 0:
            raise StepFailed("\n".join(f"  {ln}" for ln in lines if not ln.startswith("ok"))[:1500])
        self.sheet, self.lines = sheet, lines
        return sheet

    def run(self, allow: bool, full: bool) -> None:
        L, d = self.layout, self.layout["tabs"]["Draft Board"]["columns"]
        t = L["tabs"]["Category Tracker"]
        punt = PS.col_letter(t["columns"]["punted"])
        first = L["first_row"]

        sheet = self.check("copy")
        inherited = ticked_cells(sheet, L)
        if inherited:
            # Only re-pull when something was actually toggled. A pull is one download
            # of the whole workbook, so re-proving a state this step just verified costs a
            # full download for nothing (ADR-0025).
            self.b.toggle(inherited)
            self.check("cleared", {"mine": 0, "cmp": 0, "punted": 0, "slots": 0})

        mine = d["mine"]["letter"]
        self.b.toggle([("Draft Board", f"{mine}{first}:{mine}{first + 7}")])
        self.check("a mine 8", {"mine": 8})
        self.b.toggle([("Draft Board", f"{mine}{first + 8}:{mine}{first + 13}")])
        self.check("a mine 14", {"mine": 14})

        cmp = d["cmp"]["letter"]
        self.b.toggle([("Draft Board", f"{cmp}{r}") for r in CMP_ROWS])
        self.check("b cmp 8", {"cmp": 8, "mine": 14, "slots": 5})

        self.b.toggle([("Category Tracker", f"{punt}{t['first_cat_row']}")])
        self.check("c punt 1", {"punted": 1})
        self.b.toggle([("Category Tracker", f"{punt}{t['first_cat_row'] + 3}")])
        self.check("c punt 2", {"punted": 2})

        # The two routes that clear CMP (ADR-0028), both through the simple onEdit trigger,
        # which runs on a copy with no authorisation. The Clear all box first; it has to
        # untick itself as well as every CMP.
        self.b.toggle([("Category Tracker", t["compare"]["clear"])])
        self.check("f clear all", {"cmp": 0, "slots": 0, "clear": 0, "mine": 14})
        # Then a MINE tick, which ends the comparison it was made from.
        self.b.toggle([("Draft Board", f"{cmp}{r}") for r in CLEAR_ROWS])
        self.check("g cmp 3", {"cmp": 3, "slots": 3})
        self.b.toggle([("Draft Board", f"{mine}{MINE_ROW}")])
        self.check("g mine", {"cmp": 0, "slots": 0, "mine": 15})

        if not full:
            # The tick tier ends here. Steps d and e each cost a full Apps Script run on the
            # copy, which is most of the wall-clock, and neither is reachable from a tick.
            return

        self.b.type_into([("Draft Board", f"{d['cmp']['letter']}1", NEW_SORT)])
        self.b.draft_menu("Rebuild & re-sort", "^Sorted by ", allow)
        sheet = self.check("d re-sort", {"mine": 15, "cmp": 0, "punted": 2})
        why = sort_applied(sheet, L, self.lines, NEW_SORT)
        if why:
            raise StepFailed(f"step d: {why}")

        # Row ra shows nb once swapped, so the hand value typed there belongs to nb.
        ra, na, rb, nb = clean_rows(sheet, L)
        b = L["tabs"]["Board"]["columns"]
        entries = [("Board", f"{b['player']['letter']}{ra}", nb),
                   ("Board", f"{b['player']['letter']}{rb}", na),
                   ("Board", f"{b['gp1']['letter']}{ra}", str(OVERRIDE))]
        self.b.type_into(entries)
        for attempt in (1, 2):
            typed = self.check("e typed", {"mine": 15, "cmp": 0, "punted": 2},
                               verify=False)
            landed = (VL._text(typed.cell("Board", b["player"]["index"], ra)) == nb,
                      VL._text(typed.cell("Board", b["player"]["index"], rb)) == na,
                      VL._num(typed.cell("Board", b["gp1"]["index"], ra)) == OVERRIDE)
            if all(landed):
                break
            if attempt == 2:
                raise StepFailed(f"step e: the Board edits did not land before Refresh "
                                 f"(swap a, swap b, override) = {landed}")
            self.b.type_into([e for e, ok in zip(entries, landed, strict=True) if not ok])
        self.b.draft_menu("Refresh data", "Calculation tabs rewritten", allow)
        sheet = self.check("e refresh", {"mine": 15, "cmp": 0, "punted": 2})
        why = hand_value_followed(sheet, L, nb, na, OVERRIDE)
        if why:
            raise StepFailed(f"step e: {why}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet-id", help="the live sheet to copy instead of .env DRAFT_SHEET_ID")
    ap.add_argument("--allow-consent", action="store_true",
                    help="the owner approved clicking Allow on the copy's authorisation screen")
    ap.add_argument("--force", action="store_true", help="run even if nothing covered changed")
    ap.add_argument("--full", action="store_true",
                    help="also run steps d and e (re-sort and Refresh); needs --allow-consent")
    args = ap.parse_args(argv)
    try:
        fp = fingerprint(PS.REPO)
    except (StepFailed, json.JSONDecodeError) as e:
        print(f"scenario: {e}", file=sys.stderr)
        return 2
    if args.force or args.full:
        tier = "full" if args.full else "ticks"
    else:
        tier = tier_needed(PS.REPO, LAST, fp, engine_changed(PS.REPO, LAST))
    if tier == "none":
        print("scenario not needed: no formula the ticks drive changed since the last pass")
        return 0
    if tier == "full" and not args.full:
        print("scenario: a rebuild-path formula changed, so steps d and e are included")
    try:
        sheet_id = args.sheet_id or PS.read_sheet_id(PS.ENV)
        layout = json.loads(PS.LAYOUT.read_text(encoding="utf-8"))
        snapshot = BS.load(BS.newest(BS.ROOT))
    except (ValueError, BS.SnapshotError, TypeError) as e:
        print(f"scenario: {e}", file=sys.stderr)
        return 2

    started, browser = time.monotonic(), Browser(sheet_id)
    code = 0
    try:
        browser.make_copy()
        Scenario(browser, layout, snapshot).run(args.allow_consent, tier == "full")
    except NeedsConsent:
        print("scenario stopped at step d: needs --allow-consent (ask the owner first)")
        code = 5
    except (StepFailed, PS.PullError) as e:
        print(f"scenario FAILED: {e}".replace(sheet_id, "<sheet id>"))
        code = 1
    finally:
        if not browser.copy_id and code:
            print("a copy may exist in Drive with no id recorded -- check for one and delete it "
                  "by hand before anything else")
        if browser.copy_id:
            for attempt in (1, 2):
                try:
                    browser.delete_copy()
                    break
                except StepFailed as e:
                    if attempt == 2:
                        print(f"copy NOT deleted: {e} -- delete it by hand before anything else")
                        code = code or 1
    if code == 0:
        LAST.parent.mkdir(parents=True, exist_ok=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PS.REPO, capture_output=True,
                              text=True).stdout.strip()
        # Record the hashes only for what this run actually proved: a tick-tier pass must
        # not stamp the rebuild hash, or the steps it skipped would never run again.
        stamped = {"sha": head, "tick": fp["tick"]}
        if tier == "full":
            stamped["rebuild"] = fp["rebuild"]
        else:
            stamped["rebuild"] = _stamp(LAST).get("rebuild", "")
        LAST.write_text(json.dumps(stamped) + "\n", encoding="utf-8")
        kept = "hand value kept, " if tier == "full" else ""
        print(f"scenario ok ({tier}): every step verify exit 0, {kept}copy deleted, "
              f"{time.monotonic() - started:.0f}s")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
