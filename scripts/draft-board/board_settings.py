"""The league and draft-day settings both boards are built from.

One Python source for the numbers the Google Sheet's Settings tab is seeded with and the
local board computes with. Build.gs cannot import this, so it carries the same values as
`var SETTINGS_DEFAULTS = {...};`, a one-line strict-JSON object literal, and
tests/test_board_settings.py parses that line and fails the moment the two disagree.

The league numbers are transcribed from config/league.yaml rather than parsed out of it:
pyyaml is not a declared dependency, and a runtime dependency needs an ADR. The same test
file holds the transcription to the YAML by regex.
"""

from __future__ import annotations

import json
import re

#: config/league.yaml `team_count`. Twelve play; Yahoo's "Max Teams: 14" is capacity.
TEAMS = 12
#: Starters plus bench, IL excluded -- the spots that compete for a draftable player.
ROSTER = 13
#: Everyone who gets drafted. Every pool, the tracker's benchmark cap and the export use it.
Q = TEAMS * ROSTER
#: config/league.yaml `season`.
SEASON = "2026-27"
#: Display only; the Settings dropdown offers this string.
SCORING = "Head-to-Head Categories"

#: A tier breaks where a value drop exceeds this multiple of the local median (ADR-0012).
TIER_MULT = 2.0
#: A category is a strength or weakness at +/- this many unweighted DURANT SDs (ADR-0018).
CAT_BAND = 1.0
#: Rank places a source must disagree by before its tag is painted.
DISAGREE_GAP = 15

#: Category Tracker win-rate cutoffs. WEAK and STRONG are ADR-0023's 40/60; BANKED is
#: ADR-0018's 75%, where the next unit of edge is down to 80% of its peak return.
WEAK_WIN = 0.40
STRONG_WIN = 0.60
BANK_WIN = 0.75

#: The keys Build.gs's SETTINGS_DEFAULTS carries: the ones the sheet has a cell for. `q` is a
#: formula on the sheet and `season` has no cell at all.
SHEET_KEYS = (
    "teams",
    "roster",
    "scoring",
    "tier_mult",
    "cat_band",
    "disagree_gap",
    "weak_win",
    "strong_win",
    "bank_win",
)

_BUILD_GS_DEFAULTS = re.compile(r"^var SETTINGS_DEFAULTS = (\{.*\});[ \t]*$", re.MULTILINE)


def as_dict() -> dict:
    """Every setting, keyed the way the local snapshot and the sheet pull name them."""
    return {
        "teams": TEAMS,
        "roster": ROSTER,
        "q": Q,
        "season": SEASON,
        "scoring": SCORING,
        "tier_mult": TIER_MULT,
        "cat_band": CAT_BAND,
        "disagree_gap": DISAGREE_GAP,
        "weak_win": WEAK_WIN,
        "strong_win": STRONG_WIN,
        "bank_win": BANK_WIN,
    }


def from_build_gs(text: str) -> dict:
    """Parse `var SETTINGS_DEFAULTS = {...};` out of Build.gs's text.

    Strict JSON on purpose: a regex over a JavaScript expression would pass an edit it could
    not read, and a comparison that silently compares nothing reads as agreement.
    """
    match = _BUILD_GS_DEFAULTS.search(text)
    if match is None:
        raise ValueError("Build.gs has no one-line `var SETTINGS_DEFAULTS = {...};`")
    return json.loads(match.group(1))
