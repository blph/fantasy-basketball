"""The three projection adapters and the join between them.

Every fixture here is hand-authored with invented players and invented numbers. The real
exports are provider data and this repository is public (ADR-0006), so nothing under
data/player_data/ is ever copied into a test.
"""

import textwrap

import pytest
import sources as S


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    return p


HBP_HEADER = "R#,PLAYER,ADP,POS,TEAM,GP,MPG,FG%,FT%,3PM,PTS,TREB,AST,STL,BLK,TO,TOTAL"


def hbp_row(rank, name, adp="5.0", gp="70"):
    """One Hashtag row. The percentage fields carry an embedded newline, as the real ones do."""
    return (
        f'{rank},{name},{adp},PG,ATL,{gp},33.0,"0.500\n(8.0/16.0)","0.800\n(4.0/5.0)",'
        f"2.0,22.0,6.0,5.0,1.2,0.6,2.5,10.00"
    )


def hbp_file(tmp_path, rows, name="HBP Projections - 2026-01-01.csv"):
    return write(tmp_path, name, "\n".join([HBP_HEADER, *rows]) + "\n")


ALPHA = "abcdefghijklmnopqrstuvwxyz"


def made_up_name(i):
    """A unique, purely alphabetic name.

    Alphabetic because `normalise` strips digits -- real players have none in their names,
    so numbered fixtures would all collapse onto one key and test nothing.
    """
    a, b, c = ALPHA[i // 26 % 26], ALPHA[i % 26], ALPHA[(i * 7 + 3) % 26]
    return f"{a.upper()}{b}{c}ley {c.upper()}{a}{b}son"


def hbp_200(tmp_path, names=None):
    names = names or [made_up_name(i) for i in range(S.BOARD_ROWS)]
    return hbp_file(tmp_path, [hbp_row(i + 1, n) for i, n in enumerate(names)])


VENDOR_HEADER = (
    "player_id,last_name,first_name,games,minutes,field_goals_attempted,field_goals,"
    "free_throws_attempted,free_throws,threes,threes_attempted,offensive_rebounds,"
    "defensive_rebounds,assists,blocks,steals,turnovers,fouls,technicals,"
    "double_doubles,triple_doubles,comments"
)


def vendor_row(pid, first, last, games=70, fgm=560, threes=140, ftm=280):
    return (
        f"{pid},{last},{first},{games},2310,1120,{fgm},350,{ftm},{threes},380,70,350,"
        f"350,42,84,175,150,0,0,0,"
    )


def vendor_file(tmp_path, rows, name="BMP Projections - 2026-01-01.csv"):
    return write(tmp_path, name, "\n".join([VENDOR_HEADER, *rows]) + "\n")


class TestNormalise:
    @pytest.mark.parametrize(
        ("raw", "want"),
        [
            ("Nikola Jokic", "nikolajokic"),
            ("Nikola Jokić", "nikolajokic"),          # diacritic folded
            ("Luka Dončić", "lukadoncic"),
            ("Kristaps Porziņģis", "kristapsporzingis"),
            ("Alperen Şengün", "alperensengun"),
            ("Jaren Jackson Jr.", "jarenjackson"),     # suffix stripped
            ("Gary Trent Jr", "garytrent"),
            ("Michael Porter III", "michaelporter"),
            ("Tim Hardaway Sr.", "timhardaway"),
            ("P.J. Washington", "pjwashington"),       # punctuation dropped
            ("De'Aaron Fox", "deaaronfox"),
            ("  Trae   Young  ", "traeyoung"),
        ],
    )
    def test_normalises(self, raw, want):
        assert S.normalise(raw) == want

    def test_applies_the_alias_table(self):
        # The two vendors disagree on the name itself, not on its punctuation, so the
        # normaliser cannot reconcile them and an explicit entry has to.
        assert S.normalise("Cameron Johnson") == S.normalise("Cam Johnson")
        assert S.normalise("Herbert Jones") == S.normalise("Herb Jones")


class TestLoadBoard:
    def test_reads_the_two_hundred_rows(self, tmp_path):
        board = S.load_board(hbp_200(tmp_path))
        assert len(board) == S.BOARD_ROWS
        assert board[0]["seed"] == 1 and board[-1]["seed"] == S.BOARD_ROWS

    def test_splits_the_percentage_field_into_makes_and_attempts(self, tmp_path):
        # A bare rate throws away the volume, and the percentage categories are
        # volume-weighted -- so makes and attempts both have to survive the parse.
        r = S.load_board(hbp_200(tmp_path))[0]["rates"]
        assert (r["fg_made"], r["fg_att"]) == (8.0, 16.0)
        assert (r["ft_made"], r["ft_att"]) == (4.0, 5.0)

    def test_skips_repeated_header_rows(self, tmp_path):
        # The real export repeats its header roughly every thirteen players.
        rows = []
        for i in range(S.BOARD_ROWS):
            if i and i % 13 == 0:
                rows.append(HBP_HEADER)
            rows.append(hbp_row(i + 1, made_up_name(i)))
        assert len(S.load_board(hbp_file(tmp_path, rows))) == S.BOARD_ROWS

    def test_takes_only_the_leading_integer_of_a_split_rank(self, tmp_path):
        # R# sometimes carries a second number -- rank movement -- as "18 38".
        rows = [hbp_row(i + 1, made_up_name(i)) for i in range(S.BOARD_ROWS)]
        rows[17] = rows[17].replace("18,", '"18 38",', 1)
        assert S.load_board(hbp_file(tmp_path, rows))[17]["seed"] == 18

    def test_blank_adp_stays_blank_rather_than_zero(self, tmp_path):
        # Blank means the market has not priced him. Zero would mean it prices him first.
        rows = [hbp_row(i + 1, made_up_name(i)) for i in range(S.BOARD_ROWS)]
        rows[4] = hbp_row(5, made_up_name(4), adp="")
        assert S.load_board(hbp_file(tmp_path, rows))[4]["adp"] is None

    def test_wrong_row_count_is_an_error(self, tmp_path):
        with pytest.raises(S.SourceError, match="the board is built for"):
            S.load_board(hbp_file(tmp_path, [hbp_row(1, "Solo Player")]))

    def test_non_contiguous_rank_is_an_error(self, tmp_path):
        rows = [hbp_row(i + 1, made_up_name(i)) for i in range(S.BOARD_ROWS)]
        rows[9] = hbp_row(999, made_up_name(9))
        with pytest.raises(S.SourceError, match="not contiguous"):
            S.load_board(hbp_file(tmp_path, rows))

    def test_unparsable_percentage_is_an_error(self, tmp_path):
        rows = [hbp_row(i + 1, made_up_name(i)) for i in range(S.BOARD_ROWS)]
        rows[2] = rows[2].replace('"0.500\n(8.0/16.0)"', "0.500")
        with pytest.raises(S.SourceError, match="unparsable"):
            S.load_board(hbp_file(tmp_path, rows))

    def test_colliding_names_are_an_error(self, tmp_path):
        names = [made_up_name(i) for i in range(S.BOARD_ROWS)]
        names[1] = "Jaren Jackson Jr."
        names[2] = "Jaren Jackson"          # normalises to the same key
        with pytest.raises(S.AmbiguousName):
            S.load_board(hbp_200(tmp_path, names))


class TestLoadVendor:
    def test_derives_points_without_double_counting_threes(self, tmp_path):
        # Made field goals ALREADY include threes. Counting a made three as three points
        # plus a two-point field goal is the classic way to get this silently wrong.
        v = S.load_vendor(vendor_file(tmp_path, [vendor_row(1, "Ada", "Lovelace")]))
        p = v[1]
        assert p["points"] == 2 * 560 + 140 + 280
        assert p["threes"] == 140

    def test_sums_offensive_and_defensive_rebounds(self, tmp_path):
        v = S.load_vendor(vendor_file(tmp_path, [vendor_row(1, "Ada", "Lovelace")]))
        assert v[1]["rebounds"] == 70 + 350

    def test_drops_players_projected_zero_games(self, tmp_path):
        # They cannot be rated, and leaving them in drags every pool mean toward zero.
        v = S.load_vendor(vendor_file(tmp_path, [
            vendor_row(1, "Ada", "Lovelace"),
            vendor_row(2, "Zero", "Games", games=0),
        ]))
        assert set(v) == {1}

    def test_a_file_with_no_playable_rows_is_an_error(self, tmp_path):
        with pytest.raises(S.SourceError, match="positive game count"):
            S.load_vendor(vendor_file(tmp_path, [vendor_row(1, "Zero", "Games", games=0)]))

    def test_colliding_names_are_an_error(self, tmp_path):
        with pytest.raises(S.AmbiguousName):
            S.load_vendor(vendor_file(tmp_path, [
                vendor_row(1, "Gary", "Trent Jr."),
                vendor_row(2, "Gary", "Trent"),
            ]))


class TestJoin:
    def _vendors(self, tmp_path, names, extra=()):
        rows = [vendor_row(100 + i, *n.split(" ", 1)) for i, n in enumerate(names)]
        rows += [vendor_row(900 + i, *n.split(" ", 1)) for i, n in enumerate(extra)]
        return {"BMP": S.load_vendor(vendor_file(tmp_path, rows))}

    def test_attaches_an_id_per_source_for_every_board_row(self, tmp_path):
        names = [made_up_name(i) for i in range(S.BOARD_ROWS)]
        board = S.load_board(hbp_200(tmp_path, names))
        report = S.join(board, self._vendors(tmp_path, names))
        assert report["BMP"] == [f"{S.BOARD_ROWS}/{S.BOARD_ROWS} matched"]
        assert all("BMP" in row["ids"] for row in board)

    def test_an_unresolved_player_is_an_error_and_is_named(self, tmp_path):
        # AGENTS.md: an unresolved player is an error, not a skipped row. A silently
        # dropped player is a hole in the board that looks like a player nobody rates.
        names = [made_up_name(i) for i in range(S.BOARD_ROWS)]
        board = S.load_board(hbp_200(tmp_path, names))
        vendors = self._vendors(tmp_path, names[1:], extra=["Spare Body"])
        with pytest.raises(S.UnresolvedPlayer, match=names[0]):
            S.join(board, vendors)

    def test_matches_across_a_diacritic_difference(self, tmp_path):
        names = [made_up_name(i) for i in range(S.BOARD_ROWS)]
        names[0] = "Nikola Jokić"
        board = S.load_board(hbp_200(tmp_path, names))
        vendor_names = list(names)
        vendor_names[0] = "Nikola Jokic"
        S.join(board, self._vendors(tmp_path, vendor_names))
        assert board[0]["ids"]["BMP"] == 100

    def test_an_unused_alias_is_reported_but_does_not_block(self, tmp_path, monkeypatch):
        # A player dropping out of Hashtag's top 200 is ordinary, so this cannot be fatal.
        # An alias that is genuinely broken surfaces as UnresolvedPlayer instead.
        monkeypatch.setitem(S.ALIASES, "someoldname", "somenewname")
        names = [made_up_name(i) for i in range(S.BOARD_ROWS)]
        board = S.load_board(hbp_200(tmp_path, names))
        report = S.join(board, self._vendors(tmp_path, names))
        assert "somenewname" in report["aliases"][0]
