"""The category-scarcity study: band classification, round bucketing, and the invariants.

Every snapshot here is synthetic (ADR-0006). The board under test is a full-size one --
156 players, 12 teams of 13 -- because the study's whole job is to slice a pool into
rounds, and a scaled-down fixture cannot exercise the boundary between round 12 and
round 13.

The test that matters most is `test_classify_matches_profile`: the study re-implements the
band test rather than refactoring it out of `board_engine._profile`, so that the board's
own engine stays untouched and no sheet deployment is dragged into a read-only study. That
choice is only safe while the two agree, and this is what holds them together.
"""

import board_engine as E
import pytest
import study_scarcity as SS

import board_fixtures as F

CATS = ["FG%", "FT%", "3PM", "PTS", "REB", "AST", "STL", "BLK"]
LEAGUE = {"teams": 12, "roster": 13}


def league_snapshot(n=156, **overrides):
    """A 156-row board on the league's own 12x13 settings, so q = 156 and depth = 13."""
    settings = {**LEAGUE, **overrides.pop("settings", {})}
    return F.make_snapshot(n=n, settings=settings, **overrides)


def set_d(snap, i, values):
    """Overwrite player `i`'s unweighted d on every source. `values` maps label -> float."""
    for src in ("BMP", "HBP", "BMP-ALT"):
        snap["players"][i]["values"][src]["d"].update(values)


def flat_d(snap, value=0.0):
    """Silence every category on every player, so a test only sees what it sets."""
    for i in range(len(snap["players"])):
        set_d(snap, i, dict.fromkeys(CATS, value))


# --- classify: the two bands ------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (2.50, SS.PRIMARY),      # comfortably over
    (1.00, SS.PRIMARY),      # exactly the band -- >= , so primary
    (0.9999, SS.SECONDARY),  # a hair under the primary band
    (0.50, SS.SECONDARY),    # exactly the secondary floor -- >= , so secondary
    (0.4999, None),          # a hair under the floor: no label at all
    (0.0, None),
    (-1.00, None),           # a weakness is not a strength
    (-3.00, None),
])
def test_classify_bands(value, expected):
    d = dict.fromkeys(CATS, 0.0)
    d["BLK"] = value
    assert SS.classify(d, CATS, 1.0, 0.5)["BLK"] == expected


def test_classify_is_half_open_so_bands_never_overlap():
    """A primary strength must never also be counted as a secondary one."""
    d = {c: v for c, v in zip(CATS, [2.0, 1.0, 0.99, 0.5, 0.49, 0.0, -1.0, -2.0], strict=True)}
    out = SS.classify(d, CATS, 1.0, 0.5)
    assert sum(v == SS.PRIMARY for v in out.values()) == 2
    assert sum(v == SS.SECONDARY for v in out.values()) == 2
    assert sum(v is None for v in out.values()) == 4


def test_classify_matches_profile():
    """The study's classifier and the board's `_profile` name the same categories.

    `_profile` emits display strings ("- REB, BLK"); this parses them back to sets and
    compares. If this ever fails, the study is describing a board that no longer exists.
    """
    snap = league_snapshot()
    for player in snap["players"]:
        d = player["values"]["BMP"]["d"]
        strengths, secondary, _weak = E._profile(player["name"], d, CATS, set(), 1.0, 0.5)
        bands = SS.classify(d, CATS, 1.0, 0.5)

        def named(s):
            return set() if s == "—" else {p.strip() for p in s[2:].split(",")}

        assert named(strengths) == {c for c, v in bands.items() if v == SS.PRIMARY}
        assert named(secondary) == {c for c, v in bands.items() if v == SS.SECONDARY}


# --- round bucketing --------------------------------------------------------------------

def test_rounds_default_to_q_over_teams():
    result = SS.scarcity_counts(league_snapshot())
    assert result["meta"]["rounds"] == 13
    assert result["meta"]["pool"] == 156
    assert result["rounds"] == list(range(1, 14))


@pytest.mark.parametrize("row,expected_round", [
    (0, 1),      # rank 1
    (11, 1),     # rank 12  -- last of round 1
    (12, 2),     # rank 13  -- first of round 2
    (23, 2),
    (144, 13),   # rank 145 -- first of round 13
    (155, 13),   # rank 156 -- last player in the pool
])
def test_player_lands_in_the_right_round(row, expected_round):
    """The fixture ranks row i at i+1, so the round is ceil((i+1)/12)."""
    snap = league_snapshot()
    flat_d(snap)
    set_d(snap, row, {"BLK": 1.5})

    result = SS.scarcity_counts(snap)
    blk = result["counts"]["BLK"]["total"]
    assert blk[expected_round - 1] == 1
    assert sum(blk) == 1


def test_players_past_q_are_excluded():
    """A 200-row board still measures only the 156 the league drafts."""
    snap = league_snapshot(n=200)
    flat_d(snap)
    set_d(snap, 155, {"BLK": 1.5})   # rank 156, the last player in the pool
    set_d(snap, 156, {"BLK": 1.5})   # rank 157, the first one past it
    set_d(snap, 199, {"BLK": 1.5})   # rank 200

    result = SS.scarcity_counts(snap)
    assert result["meta"]["pool"] == 156
    assert sum(result["counts"]["BLK"]["total"]) == 1


# --- invariants -------------------------------------------------------------------------

def test_primary_and_secondary_sum_to_total():
    result = SS.scarcity_counts(league_snapshot())
    for cat, series in result["counts"].items():
        for i, total in enumerate(series["total"]):
            assert series[SS.PRIMARY][i] + series[SS.SECONDARY][i] == total, cat


def test_no_round_exceeds_its_twelve_players():
    """A round holds 12 players, so no category can name more than 12 of them."""
    result = SS.scarcity_counts(league_snapshot())
    for cat, series in result["counts"].items():
        assert max(series["total"]) <= 12, cat


def test_every_category_is_measured():
    result = SS.scarcity_counts(league_snapshot())
    assert set(result["counts"]) == set(CATS)
    assert result["labels"] == CATS


def test_turnovers_are_absent():
    """DURANT H2H prices TO at zero, so it can never clear a band and has no column."""
    result = SS.scarcity_counts(league_snapshot())
    assert "TO" not in result["counts"]
    assert len(result["labels"]) == 8


def test_all_twelve_can_share_a_strength():
    snap = league_snapshot()
    flat_d(snap)
    for i in range(12):
        set_d(snap, i, {"AST": 1.2})
    result = SS.scarcity_counts(snap)
    assert result["counts"]["AST"]["total"][0] == 12
    assert result["counts"]["AST"][SS.PRIMARY][0] == 12


# --- the neutral baseline ---------------------------------------------------------------

def test_counts_ignore_conceded_categories():
    """The study reads an empty state, so a punt ticked in a live draft cannot erase a row.

    `_profile` drops a conceded category from every list. That is right for the board and
    wrong for a scarcity study, which is measuring the pool rather than one team's plan.
    This pins the difference: the same snapshot, read through a conceding state, loses BLK
    from the board's own labels while the study still counts it.
    """
    snap = league_snapshot()
    flat_d(snap)
    for i in range(12):
        set_d(snap, i, {"BLK": 1.5})

    conceding = {**E.empty_state(), "conceded": ["BLK"]}
    rows = E.board_rows(snap, conceding, snap["settings"], E.DEFAULT_SORT)
    assert all("BLK" not in r["strengths"] for r in rows[:12])

    result = SS.scarcity_counts(snap)
    assert result["counts"]["BLK"]["total"][0] == 12


def test_bands_come_from_the_snapshot_not_a_constant():
    """A reband re-measures. Widening the primary band moves players into secondary."""
    snap = league_snapshot()
    flat_d(snap)
    for i in range(12):
        set_d(snap, i, {"REB": 1.2})

    assert SS.scarcity_counts(snap)["counts"]["REB"][SS.PRIMARY][0] == 12

    snap["settings"]["cat_band"] = 1.5
    reband = SS.scarcity_counts(snap)
    assert reband["counts"]["REB"][SS.PRIMARY][0] == 0
    assert reband["counts"]["REB"][SS.SECONDARY][0] == 12
    assert reband["counts"]["REB"]["total"][0] == 12


# --- sources ----------------------------------------------------------------------------

def test_source_selects_which_d_is_read():
    snap = league_snapshot()
    flat_d(snap)
    snap["players"][0]["values"]["HBP"]["d"]["STL"] = 1.5   # HBP only

    assert SS.scarcity_counts(snap, "BMP")["counts"]["STL"]["total"][0] == 0
    assert SS.scarcity_counts(snap, "HBP")["counts"]["STL"]["total"][0] == 1


def test_unknown_source_is_an_error():
    with pytest.raises(SS.StudyError, match="unknown source"):
        SS.scarcity_counts(league_snapshot(), "NOPE")


def test_too_few_players_is_an_error():
    """A short board is a hole in the study, not a shorter study."""
    with pytest.raises(SS.StudyError, match="needs 156 players"):
        SS.scarcity_counts(league_snapshot(n=100))


def test_rounds_must_be_positive():
    with pytest.raises(SS.StudyError, match="at least 1"):
        SS.scarcity_counts(league_snapshot(), rounds=0)


def test_explicit_rounds_shortens_the_pool():
    snap = league_snapshot()
    flat_d(snap)
    set_d(snap, 59, {"PTS": 1.5})   # rank 60, round 5
    result = SS.scarcity_counts(snap, rounds=5)
    assert result["meta"]["pool"] == 60
    assert result["counts"]["PTS"]["total"][4] == 1


# --- summary helpers --------------------------------------------------------------------

def test_totals_by_category_ranks_deepest_first():
    snap = league_snapshot()
    flat_d(snap)
    for i in range(10):
        set_d(snap, i, {"PTS": 1.5})
    for i in range(3):
        set_d(snap, i, {"BLK": 1.5})

    totals = SS.totals_by_category(SS.scarcity_counts(snap))
    assert totals[0] == ("PTS", 10)
    assert dict(totals)["BLK"] == 3
    assert [n for _, n in totals] == sorted((n for _, n in totals), reverse=True)


def test_last_round_with_reads_the_deepest_round_not_the_first_gap():
    """A category can go quiet for a round and come back; the tail is what matters."""
    snap = league_snapshot()
    flat_d(snap)
    set_d(snap, 0, {"AST": 1.5})     # round 1
    set_d(snap, 30, {"AST": 1.5})    # round 3 -- round 2 is empty

    assert SS.last_round_with(SS.scarcity_counts(snap), "AST") == 3


def test_last_round_with_returns_none_when_a_category_never_appears():
    snap = league_snapshot()
    flat_d(snap)
    assert SS.last_round_with(SS.scarcity_counts(snap), "AST") is None


def test_meta_records_what_was_measured():
    snap = league_snapshot()
    result = SS.scarcity_counts(snap, "BMP")
    meta = result["meta"]
    assert meta["source"] == "BMP"
    assert meta["teams"] == 12
    assert (meta["band"], meta["band_sec"]) == (1.0, 0.5)
    assert meta["digest"] == snap["meta"]["digest"][:12]
    assert meta["generated"] == snap["meta"]["generated"]
