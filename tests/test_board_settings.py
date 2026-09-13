"""board_settings.py against every other place a league setting is written down.

The Google Sheet and the local board have to compute with the same numbers. Before this
module each copy was transcribed separately -- Build.gs, build_data.py, calibrate_bbm.py,
the Yahoo exporter, bbm_reference.py -- and nothing noticed when one moved. Each test here
pins one copy to board_settings.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import bbm_reference
import board_settings as BSET
import build_data
import calibrate_bbm
import export_yahoo_rankings
import pytest

REPO = Path(__file__).resolve().parents[1]
BUILD_GS = REPO / "scripts" / "draft-board" / "Build.gs"
LEAGUE_YAML = REPO / "config" / "league.yaml"


def test_as_dict_carries_exactly_the_snapshot_keys():
    assert set(BSET.as_dict()) == {
        "teams",
        "roster",
        "q",
        "season",
        "scoring",
        "tier_mult",
        "cat_band",
        "disagree_gap",
        "weak_win",
        "strong_win",
        "bank_win",
    }


def test_q_is_teams_times_roster():
    assert BSET.Q == BSET.TEAMS * BSET.ROSTER
    assert BSET.as_dict()["q"] == BSET.Q


def test_sheet_keys_are_settings_keys():
    assert set(BSET.SHEET_KEYS) <= set(BSET.as_dict())
    assert "q" not in BSET.SHEET_KEYS and "season" not in BSET.SHEET_KEYS


def test_cutoffs_are_ordered():
    assert 0 < BSET.WEAK_WIN < 0.5 < BSET.STRONG_WIN < BSET.BANK_WIN < 1


def test_build_gs_defaults_equal_board_settings():
    got = BSET.from_build_gs(BUILD_GS.read_text(encoding="utf-8"))
    assert got == {k: BSET.as_dict()[k] for k in BSET.SHEET_KEYS}


def test_from_build_gs_compares_numbers_by_value():
    text = 'var X = 1;\nvar SETTINGS_DEFAULTS = {"tier_mult": 2, "weak_win": 0.4};\n'
    assert BSET.from_build_gs(text) == {"tier_mult": 2.0, "weak_win": 0.40}


def test_from_build_gs_refuses_text_without_the_literal():
    with pytest.raises(ValueError, match="SETTINGS_DEFAULTS"):
        BSET.from_build_gs("var TRACKER_TAB = 'Category Tracker';\n")


def test_from_build_gs_refuses_a_literal_that_is_not_json():
    with pytest.raises(ValueError):
        BSET.from_build_gs("var SETTINGS_DEFAULTS = {teams: 12};\n")


def test_bbm_reference_pool_matches():
    # Deliberately not repointed: the engine is validated against Basketball Monster on its
    # own constant. This is the line that notices if the league changes under it.
    assert bbm_reference.Q == BSET.Q


def test_pipeline_constants_come_from_board_settings():
    assert (build_data.TEAMS, build_data.ROSTER, build_data.Q) == (BSET.TEAMS, BSET.ROSTER, BSET.Q)
    assert calibrate_bbm.Q == BSET.Q
    assert export_yahoo_rankings.SEASON == BSET.SEASON
    assert export_yahoo_rankings.DRAFTED_POOL == BSET.Q


@pytest.mark.parametrize(
    ("module", "pattern"),
    [
        ("build_data.py", r"^(TEAMS|ROSTER|Q)\b[^\n]*=\s*\d"),
        ("calibrate_bbm.py", r"^Q\s*=\s*\d"),
        ("export_yahoo_rankings.py", r'^(SEASON\s*=\s*"|DRAFTED_POOL\s*=\s*\d)'),
    ],
)
def test_no_script_transcribes_a_league_number(module, pattern):
    # Equal values prove nothing about where they came from: a literal 156 passes the test
    # above until the day the league changes. Read the source instead.
    text = (REPO / "scripts" / "draft-board" / module).read_text(encoding="utf-8")
    assert re.search(pattern, text, re.MULTILINE) is None


def test_league_yaml_matches():
    text = LEAGUE_YAML.read_text(encoding="utf-8")
    team_count = re.search(r"^\s*team_count:\s*(\d+)", text, re.MULTILINE)
    season = re.search(r'^\s*season:\s*"([^"]+)"', text, re.MULTILINE)
    starters = re.search(r"^\s*starters:\s*\{([^}]*)\}", text, re.MULTILINE)
    bench = re.search(r"^\s*bench:\s*(\d+)", text, re.MULTILINE)
    assert team_count and season and starters and bench, "league.yaml layout changed"
    assert int(team_count.group(1)) == BSET.TEAMS
    assert season.group(1) == BSET.SEASON
    slots = sum(int(n) for n in re.findall(r":\s*(\d+)", starters.group(1)))
    assert slots + int(bench.group(1)) == BSET.ROSTER
