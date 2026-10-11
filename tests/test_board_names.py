"""Name resolution for the local board CLI.

Every name here is invented (`made_up_name`, or spelt out below). Nothing is copied from a
provider export: the repo is public and the data is not ours to republish (ADR-0006).
"""

from __future__ import annotations

import board_names as N
import pytest

from board_fixtures import make_snapshot
from test_sources import made_up_name

SHARED = ["Quennel Varrow", "Tobin Varrow"]


@pytest.fixture
def snap():
    names = [made_up_name(i) for i in range(15)]
    names[13], names[14] = SHARED
    teams = ["BOS"] * 13 + ["GS", "NY"]
    return make_snapshot(names=names, player_teams=teams)


def test_exact_name_resolves_on_read_and_write(snap):
    name = made_up_name(3)
    assert N.resolve(snap, name, write=True)["name"] == name
    assert N.resolve(snap, name.upper() + " Jr.", write=False)["name"] == name


def test_read_takes_a_unique_partial_match(snap):
    name = made_up_name(4)
    surname = name.split()[1]
    assert N.resolve(snap, surname, write=False)["name"] == name


def test_write_never_takes_a_partial_match(snap):
    surname = made_up_name(4).split()[1]
    with pytest.raises(N.ResolveError, match="not an exact board name"):
        N.resolve(snap, surname, write=True)


def test_fuzzy_name_suggests_the_player(snap):
    name = made_up_name(6)
    typo = name[:-1]
    with pytest.raises(N.ResolveError) as err:
        N.resolve(snap, typo, write=True)
    assert name + " (BOS)" in err.value.suggestions


def test_ambiguous_partial_needs_team(snap):
    with pytest.raises(N.ResolveError, match="partially matches 2 players; add --team"):
        N.resolve(snap, "Varrow", write=False)


@pytest.mark.parametrize("team", ["GS", "GSW", "gsw"])
def test_team_breaks_a_tie_in_either_spelling(snap, team):
    assert N.resolve(snap, "Varrow", write=False, team=team)["name"] == SHARED[0]


def test_team_that_matches_no_candidate_is_an_error(snap):
    with pytest.raises(N.ResolveError, match="no candidate plays for MIA"):
        N.resolve(snap, made_up_name(2), write=True, team="MIA")


def test_yahoo_alias_resolves_on_write(snap, monkeypatch):
    import sources as S

    monkeypatch.setitem(N.YAHOO_ALIASES, S.normalise("Kwen Varrow"), S.normalise(SHARED[0]))
    assert N.key_of("Kwen Varrow") == S.normalise(SHARED[0])
    assert N.resolve(snap, "Kwen Varrow", write=True)["name"] == SHARED[0]


def test_alias_onto_another_board_name_is_a_tie_team_breaks(snap, monkeypatch):
    import sources as S

    # Yahoo's spelling of one player is the provider's spelling of another: both are
    # real candidates, and guessing either would tick the wrong man.
    monkeypatch.setitem(N.YAHOO_ALIASES, S.normalise(SHARED[1]), S.normalise(SHARED[0]))
    with pytest.raises(N.ResolveError, match="matches 2 players"):
        N.resolve(snap, SHARED[1], write=True)
    assert N.resolve(snap, SHARED[1], write=True, team="NYK")["name"] == SHARED[1]


def test_no_letters_is_an_error(snap):
    with pytest.raises(N.ResolveError, match="no letters"):
        N.resolve(snap, "1234", write=False)


def test_near_match(snap):
    name = made_up_name(8)
    assert N.near_match(snap, name[:-1])
    assert N.near_match(snap, name.split()[1])       # a bare surname is near, not off-board
    assert not N.near_match(snap, "Zymurgist Oxbowquill")


def test_suggestions_are_capped(snap):
    assert len(N.suggestions(snap, made_up_name(1), limit=2)) <= 2
