# How we reach the draft sheet: four routes evaluated — 2026-09-12

- Date: 2026-09-12
- Scope: every available way to read and write the 2026-27 draft board — the **Google
  Sheets API v4**, the **`google-sheets` MCP** as configured on this machine, **Playwright**
  (`playwright-cli -s=fantasy`, the incumbent), and the **Claude Code Chrome extension** —
  scored against the twelve-step refresh in
  [build-and-maintenance.md](../draft-board/build-and-maintenance.md).
- Method: each option's capabilities were read from its **primary documentation**, not from
  memory or from what this repo previously asserted. The incumbent was checked against the
  code that actually calls it. Where a capability could not be confirmed, it is recorded as
  unconfirmed rather than guessed.
- Constraint honoured: no player row, projection, ADP value or export figure appears below
  ([ADR-0006](../decisions/ADR-0006-no-provider-data-redistribution.md)).
- Prompted by: a fair question — *wouldn't the Sheets API or the MCP be better?* — which
  turned out to expose a false claim in `AGENTS.md`. See [Correction of the
  record](#correction-of-the-record).

---

## Verdict

**Keep Playwright as the sole route. Nothing else can do the job, and the three
alternatives all fail for the same reason.**

The reason is not that the alternatives are crude. The Sheets API is a capable, well-built
interface that could draw a board very like ours. The reason is that **our board is not a
grid — it is an Apps Script program that happens to render as a grid.** `Refresh data` is
the thing that detects which cells changed and protects the hand-edited columns.
`Rebuild & re-sort` is what reattaches your checkboxes by player name. The projection
filter is an `onEdit` trigger. None of that is cell data, and no spreadsheet API can
install it or run it.

There is a second, quieter reason that rules out the Chrome extension specifically and is
easy to miss: **Playwright is not only Claude's tool — it is imported into the pipeline.**
`calibrate_bbm.py` shells out to it directly. Step 2 of the refresh is a Python script
driving a browser, and no conversational browser tool can be called from a `subprocess`.

One alternative earns a genuine, narrow place, and it is not the one the question started
with — see [Where a second route could still earn a place](#where-a-second-route-could-still-earn-a-place).

---

## How we update the board today

The twelve steps, each tagged with what it actually demands of a browser or an API. This
table is the yardstick every option below is measured against.

| # | Step | What it demands |
|---|---|---|
| 1 | Drop the three exports in `data/player_data/` | nothing — manual file placement |
| 2 | `calibrate_bbm.py --source BMP` / `--source BMP-ALT` | **a browser callable from Python** — scrapes the vendor, writes the constants and the injury table |
| 3 | `build_data.py --dry-run` | nothing — local |
| 4 | `build_data.py` writes `Data.gs` | nothing — local |
| 5 | `node harness.js` | nothing — local |
| 6 | `verify.py`, then `verify.py --published` | nothing — local |
| 7 | Push `Data.gs` (~185KB) into the bound `Code.gs` | **Apps Script deployment** — arbitrary JS against the editor, page state held across calls |
| 8 | `Draft Board ▸ Refresh data` | **custom menu execution** |
| 9 | Read the Settings sanity block | cell read |
| 10 | Re-do `My GP Est` overrides | cell write |
| 11 | `Draft Board ▸ Rebuild & re-sort` | **custom menu execution** |
| 12 | Screenshot the Draft Board and the Category Tracker | **visual capture** |

Steps 2, 7, 8 and 11 are the load-bearing ones. Steps 9, 10 and 12 are real work but any
route can do them.

Two things worth noticing about that table. First, **only three of the twelve steps touch
the sheet at all** — most of a refresh is Python running locally, and no choice of sheet
route changes that. Second, **the browser work is split across two consumers**: step 2 is a
script driving a browser unattended, steps 7–12 are Claude driving one interactively. An
option has to serve both, or it is an addition rather than a replacement.

## What the job demands

Stated once, so every option is judged on the same list:

1. **Callable from inside a Python script** — `calibrate_bbm.py` needs it at step 2
2. **Deploy ~185KB of source into a bound Apps Script project** — step 7
3. **Run a custom menu item** — steps 8 and 11
4. **Read back 200 rows × 27 columns** for `verify.py --sheet` — the `A4:AA203` pull
5. **Read cells inside a collapsed column group** — a known weak spot today
6. **Screenshot** — step 12, and the check that caught two tracker defects nothing else saw
7. **No new credential, no sharing change, no new runtime dependency** — the last of these
   would need an ADR under this repo's own rules

---

## Option 1 — Google Sheets API v4

**What it is.** Google's official REST interface to a spreadsheet. Two halves: a values API
for reading and writing cell contents, and `spreadsheets.batchUpdate`, which applies
structural and formatting changes as an atomic batch.

**What it can genuinely do — more than this repo used to claim.** The
[batchUpdate reference](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate)
lists roughly fifty request types, and every structural feature the board uses is among
them:

| Board feature | Request type |
|---|---|
| Named ranges (Settings constants) | `AddNamedRange` |
| Conditional formats (tier bands, risk colours) | `AddConditionalFormatRule` |
| Checkboxes (`GONE`, `MINE`, `Punted`) | `SetDataValidation`, boolean condition |
| The `Sort by` dropdown | `SetDataValidation`, one-of-list |
| Collapsible column groups | `AddDimensionGroup` |
| Merged block headers | `MergeCells` |
| Tier-break borders | `UpdateBorders` |
| Frozen panes | `UpdateSheetProperties` |
| Column widths, cell formats | `UpdateDimensionProperties`, `RepeatCell` |

So the claim that the API "cannot build this board at all" was wrong, and it is worth
being precise about that before explaining why the API still loses.

**Pros**

- Native, typed, atomic. A `batchUpdate` either applies or it does not; there is no
  half-written grid.
- No browser. Nothing to keep signed in, nothing to break when Google restyles its UI.
- Robust reads. A range read returns structured values directly, with no legacy endpoint
  and no CSV parsing in the middle.
- Callable from Python. It would serve step 2's consumer as well as Claude's.
- Well documented and stable, with a generous quota for a workload this size.

**Cons, and where it breaks against our steps**

- **It cannot run Apps Script. This is decisive.** The same reference confirms that no
  request type creates, modifies or executes Apps Script, a custom menu, or an `onEdit`
  trigger. That removes steps 7, 8 and 11 outright — which is to say, it removes the
  refresh.
- **The Apps Script API is not a cheap patch.** Reaching the bound script by API means
  `scripts.run`, which requires deploying the project as an API executable, a **standard**
  Cloud project shared between the script and the caller (the default project Apps Script
  creates is explicitly insufficient), and an OAuth token covering *every* scope the script
  uses — not just the called function's. It also cannot create triggers and passes only
  basic data types. That is a real infrastructure project, and a new runtime dependency
  needing an ADR.
- **Or we reimplement the program.** The alternative to running `refreshData` is rewriting
  it in Python: the changed-cell detection, the hand-edit preservation that reads *formulas*
  to distinguish an override from an untouched seeded cell, and the name-keyed reattachment
  in `refreshWithReorder`. That is the most subtly load-bearing logic in the project, and
  duplicating it puts two implementations of "don't destroy Bryan's typing" in play.
- **It would cost the menu.** Even a perfect API rewrite leaves the owner without
  `Rebuild & re-sort` on draft night, when the board must be re-sortable from inside the
  sheet with no terminal in the room.
- **New credential, new sharing.** Either a service account the sheet must be shared with,
  or an OAuth client and consent flow.
- No screenshot. Step 12 would still need a browser.

**Verdict: rejected.** Capable of drawing the board; incapable of operating it.

---

## Option 2 — the `google-sheets` MCP

**What it is.** An MCP server (`mcp-google-sheets`) already configured on this machine,
wrapping the Sheets API behind a fixed set of tools.

**What it can do here, specifically.** The configuration in `~/.claude.json` restricts it:

```
ENABLED_TOOLS = get_sheet_data, get_sheet_formulas, update_cells,
                batch_update_cells, list_sheets, add_rows, add_columns,
                find_in_spreadsheet
```

That is **values only**. No formatting, no named ranges, no data validation, no dimension
groups, no script call. It is a strict subset of Option 1, which already loses.

**Pros**

- Zero setup cost — installed and ready.
- Clean structured reads. `get_sheet_data` over `A4:AA203` would replace the gviz CSV pull
  behind `verify.py --sheet` with something typed and boring.
- **`get_sheet_formulas` solves a real, recorded Playwright weakness.** Formula-bar reads
  through the browser are unreliable for cells inside a *collapsed column group* — they
  return the previous selection's formula, which looks like data rather than like an error.
  That is a silent-wrong-answer failure mode, which this repo ranks as its worst class of
  bug. An API read has no such mode.
- `find_in_spreadsheet` is a convenient way to locate a row without pulling the tab.

**Cons, and where it breaks against our steps**

- **It cannot build or operate the board.** Values-only means it fails steps 7, 8 and 11
  for Option 1's reason, and additionally could not construct the board's checkboxes,
  conditional formats or named ranges even if asked to.
- **It authenticates as someone else.** The configured credential is the service account
  `claude-sheets-editor@…`, a different identity from the sheet's owner. The board is
  owned by Bryan's personal account and is not shared with that address, so **every call
  would currently fail**. Using it means deliberately sharing the draft board with a robot
  account — a permanent grant, easy to forget, and one more thing holding access to a
  personal Drive.
- **It cannot serve step 2.** `calibrate_bbm.py` needs a browser, not a spreadsheet client;
  the vendor's projections page is a scrape target, not a Google resource.
- Adds a second credential and a second failure mode alongside a route we would keep
  anyway.

**Verdict: rejected as a replacement.** But it has the strongest case of the three for a
*narrow supporting role* — see below.

---

## Option 3 — Playwright (`playwright-cli -s=fantasy`), the incumbent

**What it is.** A CLI driving a persistent Chrome profile named `fantasy`, already signed
in to the Google account that owns the sheet. Claude drives it for sheet operations; the
pipeline drives it directly.

**It is load-bearing in code, not only in docs.** This is the fact that decides the whole
evaluation, so it is worth pinning to lines:

- [`calibrate_bbm.py:175-193`](../../scripts/draft-board/calibrate_bbm.py) —
  `subprocess.run(["playwright-cli", f"-s={SESSION}", *args])`, with an `eval` wrapper and
  tab management on top
- `calibrate_bbm.py:240` — documents that it reuses "the same `playwright-cli -s=fantasy`
  profile the sheet workflow uses, so it needs" no extra credential
- [`review_mock_draft.py:8`](../../scripts/draft-board/review_mock_draft.py) and
  [`export_yahoo_rankings.py:17`](../../scripts/draft-board/export_yahoo_rankings.py) both
  take `playwright-cli` pulls as their input contract
- [`pull_sheet.py`](../../scripts/draft-board/pull_sheet.py) runs `playwright-cli` itself,
  so `verify.py --local` can hold the local board's engine to the live sheet
- `build-and-maintenance.md` lines 454, 463, 555 and 585 — the documented commands

Removing Playwright is therefore not a preference change. It is a rewrite of the
calibration step, the mock-draft review, the Yahoo export's input contract, and the local
board's parity check.

**Pros**

- **The only route that covers all seven demands.** Scriptable from Python, can deploy the
  script, can click the menu, can read any range, can screenshot.
- **No credential and no sharing change.** It is the owner's own signed-in browser, so it
  sees the sheet exactly as the owner does. Nothing is granted to a third identity.
- **Blast radius is scoped.** The `fantasy` profile is a purpose-built session, not the
  everyday browser holding email and banking.
- Unattended. Step 2 runs inside a script with nobody watching, which is what makes the
  calibration reproducible.
- Already documented, already exercised, already the thing every other procedure assumes.

**Cons — real ones, stated plainly**

- **The `gviz/tq?tqx=out:csv` read is a legacy endpoint.** It is undocumented for this use,
  could change without notice, and must be fetched from *inside* the sheet's page so the
  request carries its cookies. A `goto` to another origin breaks it. The JSON form,
  `tqx=out:json`, which `pull_sheet.py` uses to get raw values beside formatted ones,
  answers `access_denied` on this private sheet unless the fetch sends
  `X-DataSource-Auth: true`. Both forms sniff each column's type and silently drop
  minority-type cells, header labels included, so a pull must request single-type ranges
  and count what comes back.
- **The `Data.gs` push depends on editor internals.** It reaches into
  `monaco.editor.getModels()` and calls `setValue`. A Google redesign of the Apps Script
  editor breaks it, and the failure would arrive mid-deployment.
- **Synthetic `Cmd+V` silently does nothing.** Chromium does not treat it as a native
  paste, so the obvious clipboard approach fails without an error — a trap already paid
  for once.
- **Fifteen chunks.** Shipping 185KB through a page global is fragile by construction, and
  a truncated paste that saves cleanly is worse than no deployment. The procedure
  compensates with verify-before-save and verify-after-reload, which is correct but is
  overhead.
- **Collapsed column groups read back wrong.** The formula-bar route returns the previous
  selection's value. Silent, and exactly the class of bug this project cares most about.
- **The session is a thing to maintain.** If the `fantasy` profile signs out, step 2 fails
  with a postback bouncing off the projections page rather than an obvious auth error.

**Verdict: retained — not because it is elegant, but because it is the only one that
finishes the job.** Its weaknesses are real and two of them are addressable; see below.

---

## Option 4 — the Claude Code Chrome extension

**What it is.** Claude Code connects to the *Claude in Chrome* extension, giving browser
automation from this session. Enabled with `claude --chrome` or `/chrome`. It drives your
actual Chrome, sharing your login state, in a visible window in real time
([docs](https://code.claude.com/docs/en/chrome)).

**Pros**

- **No separate profile to keep alive.** It uses the browser Bryan is already signed into,
  so the `fantasy` session's maintenance burden disappears for the steps it covers.
- **Strong at the interactive steps.** Reading the Settings sanity block (step 9), typing
  a `My GP Est` override (step 10) and screenshotting (step 12) are exactly its shape, and
  it saves screenshots to disk on request.
- Visible and supervised. Actions run in a window you can watch, with per-site permission
  prompts, and it pauses and hands back on a login page or CAPTCHA.
- Integrated with this VS Code session; no extra tooling to install beyond the extension.
- In plan mode, read-only browser calls run without prompting while state-changing ones ask
  — a sensible default for inspection work.

**Cons, and where it breaks against our steps**

- **It cannot be called from a Python script. This removes step 2 outright.** The extension
  is driven conversationally by Claude; `calibrate_bbm.py` needs a subprocess. There is no
  arrangement in which the calibration keeps working without Playwright, so choosing this
  option means running **two** browser systems, not swapping one for another.
- **Whether it can deploy `Data.gs` at all is unconfirmed.** Step 7 needs arbitrary
  JavaScript evaluation *with page state persisting between calls* — accumulate chunks onto
  `window.__buf`, then drive the Monaco model. The official documentation lists
  `read_page`, `get_page_text`, `find`, console and network readers, screenshots, clicks,
  typing, navigation, tab management and `browser_batch`; it does **not** document a
  JavaScript-eval tool. A third-party writeup claims one exists among "40+ tools". This was
  not verifiable from the session that produced this report, because the extension is not
  connected here. **Check with `/mcp` → `claude-in-chrome` → View tools.** If eval with
  persistent page state exists, the extension could cover steps 7–12; if it does not, it
  cannot deploy the script at all and is limited to steps 9, 10 and 12.
- **It acts in the everyday profile.** That profile holds email, banking and everything
  else. Playwright's `fantasy` profile is scoped to this work. Widening the blast radius of
  an automated agent is a real cost even with permission prompts and a safety classifier in
  front of it, and browser-agent prompt injection is an active problem class.
- **The connection drops on long sessions.** The extension's service worker goes idle, and
  the documented fix is `/chrome` → Reconnect. A refresh is fifteen sequential chunk pushes
  followed by a build that runs close to the six-minute Apps Script cap — precisely the
  profile of work that idles a connection at the worst moment.
- **Plan and auth constraints.** It needs extension v1.0.36+, a direct Anthropic plan, and
  `/login`; sessions authenticated with an API key or a `setup-token` keep Chrome
  integration off entirely. Not available in WSL, nor through third-party model providers.
- It takes over a visible window, so the machine is not usable for anything else while a
  refresh runs.

**Verdict: rejected as a replacement, and weak as an addition.** It is genuinely good at
the cheapest three steps of the twelve, and cannot do the expensive ones.

---

## Capability matrix

| Demand | Sheets API | `google-sheets` MCP | **Playwright** | Chrome extension |
|---|:--:|:--:|:--:|:--:|
| 1. Callable from a Python script (step 2) | yes | yes¹ | **yes** | **no** |
| 2. Deploy `Data.gs` to the bound script (step 7) | no | no | **yes** | unconfirmed |
| 3. Run a custom menu item (steps 8, 11) | no | no | **yes** | yes |
| 4. Read back `A4:AA203` (verification) | yes | yes | **yes**² | yes |
| 5. Read inside a collapsed column group | yes | yes | **no**³ | unclear |
| 6. Screenshot (step 12) | no | no | **yes** | yes |
| 7. No new credential or sharing change | no | no | **yes** | yes⁴ |
| **Covers the whole refresh** | **no** | **no** | **yes** | **no** |

¹ But not for step 2's actual job, which is scraping a vendor site, not reading a Google
resource.
² Through the legacy gviz CSV endpoint rather than a supported API.
³ Returns the previous selection's formula — silently wrong, not an error.
⁴ No new credential, but it acts in the everyday profile rather than a scoped one.

---

## Correction of the record

`AGENTS.md` previously defended the Playwright rule like this:

> the Sheets API cannot create named ranges, conditional formats, checkboxes or data
> validation, so it cannot build this board at all

**That was false**, and this report's first table shows each of the four as a documented
`batchUpdate` request type. The line has been rewritten to give the true reason — the board
is an Apps Script program and no spreadsheet API can install or run one — and to name the
`google-sheets` MCP and the Apps Script API's requirements explicitly.

This is worth a section of its own rather than a quiet edit. A rule defended by a false
reason is a rule that collapses the first time someone checks it, and the correct
conclusion then goes down with the bad argument. The boundary is unchanged; only its
justification is, and it is now one that survives being looked up.

---

## Where a second route could still earn a place

One narrow case is genuinely open, and it is the MCP rather than the extension.

**Read-back verification only.** Two of Playwright's real weaknesses are read-side, and
both are the silent-wrong-answer kind this project ranks worst:

- the `A4:AA203` pull depends on an undocumented legacy endpoint
- cells inside a collapsed column group read back as the previous selection

`get_sheet_data` and `get_sheet_formulas` fix both, cleanly, with no browser in the path.
Playwright would keep every write and every menu action; the MCP would only ever read.

**What it would cost**, stated honestly, because it is not free:

1. Sharing the draft board with `claude-sheets-editor@…` — a standing grant to a robot
   identity on a personal Drive, which someone has to remember exists.
2. An ADR. A second route into the sheet contradicts a `DO NOT` in `AGENTS.md`, so the
   boundary would need rewriting to say "Playwright for everything; the MCP may read" —
   and a split rule is harder to follow correctly than an absolute one.
3. A second failure mode in the verification path, which is the path whose reliability
   matters most.

**Recommendation: not yet.** The gviz pull works today, `verify.py --sheet` already
catches misalignment, and `pull_sheet.py` asserts a cell count on every range it reads, so
a silently short gviz response now fails loudly. Revisit if the gviz endpoint breaks, or if a collapsed-group misread
ever produces a wrong conclusion in practice — at that point the trade flips, because the
cost of the alternative is a forgotten share and the cost of the status quo is a silent
wrong answer on draft night.

---

## Recommendation

1. **Keep Playwright as the sole route.** Re-affirmed on the evidence, not by default.
2. **Do not adopt the Sheets API or the Apps Script API.** The former cannot operate the
   board; the latter is an infrastructure project whose payoff is a worse draft-night
   experience.
3. **Do not adopt the Chrome extension for this workflow.** It cannot serve step 2, so it
   adds a system rather than replacing one, and it acts in the everyday profile.
4. **Hold the MCP read-only idea in reserve**, with the trigger conditions above.
5. **Leave the rule's corrected rationale in `AGENTS.md`** and point at this report from it.

## Open questions

- **Does the Chrome extension expose JavaScript evaluation with page state persisting
  across calls?** Unverified here. `/mcp` → `claude-in-chrome` → View tools answers it. It
  does not change the verdict — step 2 decides that — but it does determine whether the
  extension is a plausible fallback for steps 7–12 if the Playwright push ever breaks.
- **How brittle is the Monaco `setValue` route, really?** It has not failed yet. Worth
  knowing what the fallback is *before* it does, given step 7 sits in the middle of a
  deployment.
- **Should the Playwright rule become an ADR?** It is currently a `DO NOT` in `AGENTS.md`
  with its reasoning in this report. That is sufficient, but an ADR citing this evaluation
  would put it in the decision log where the other structural choices live.

## Addendum — the local board

The local-board branch
([ADR-0022](../decisions/ADR-0022-local-draft-board.md)) adds a consumer, not a route.
`pull_sheet.py` reads the sheet through the same `fantasy` profile, from the repo root
because the persistent profile is keyed by working directory, and `verify.py --local`
compares the pull with the local engine.

Its tick scenario runs on a **copy** of the spreadsheet, made through Playwright with
File ▸ Make a copy, which carries the bound script, named ranges and rules. The copy is a
new Apps Script project and asks for its own consent, the screen the 2026-09-01 deploy
declined. The scenario grants it for the copy alone and deletes the copy afterwards,
because the copy is provider data in Drive. No credential or sharing change is added, so
the verdict stands.

The refresh procedure tabulated above has since grown from twelve steps to fourteen: step 12
runs `pull_sheet.py` and `verify.py --local` after the re-sort, and step 14 rebases a local
draft state. Step 12 reaches the sheet through the same `fantasy` profile; step 14 never
touches it.
