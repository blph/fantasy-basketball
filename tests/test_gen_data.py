"""Pin the markdown parser the whole draft board is fed from.

`gen_data.py` is the only code that reads the provider's export, so a defect here
is wrong in the sheet, wrong in `verify.py`, and wrong in every analysis
downstream, all agreeing with each other. It had no tests until this file.

Fixtures are hand-authored: invented players, invented numbers, real *shape*.
Never paste a row from `data/player_data/` in here — this repo is public
(ADR-0006).
"""

from __future__ import annotations

import pytest
from gen_data import CHECKS, cell_text, check, is_separator, parse

# The export's 17 columns, in the provider's order. The parser is index-based, so
# a column inserted upstream shifts every field after it -- this header is the
# record of what the indices assume.
HEADER = (
    "|  R#  | [PLAYER](javascript:__doPostBack('x','Sort$NAME')) |  ADP  | POS | TEAM "
    "| GP | MPG | [FG%](javascript:__doPostBack('x','Sort$fgp')) | FT% | 3PM | PTS "
    "| TREB | AST | STL | BLK | TO | TOTAL |"
)
SEPARATOR = "| :--: | :---: | :--: | :-: | :--: | :-: | :-: | :-: | :-: | :-: | :-: |"


def row(
    rank: str = "1",
    name: str = "Ambrose Quill",
    adp: str = "4.3",
    fg: str = "0.500(8.0/16.0)",
    ft: str = "0.800(4.0/5.0)",
    **over: str,
) -> str:
    """One export row. Defaults are deliberately round so arithmetic is checkable."""
    cells = {
        "pos": "C", "team": "DEN", "gp": "72", "mpg": "35.1", "tpm": "1.8",
        "pts": "28.4", "reb": "12.7", "ast": "10.4", "stl": "1.6", "blk": "0.7",
        "to": "3.5", "total": "15.93",
    }
    cells.update(over)
    return "| " + " | ".join([
        rank, f"[{name}](https://example.invalid/{rank}/player)", adp, cells["pos"],
        cells["team"], cells["gp"], cells["mpg"], fg, ft, cells["tpm"], cells["pts"],
        cells["reb"], cells["ast"], cells["stl"], cells["blk"], cells["to"],
        cells["total"],
    ]) + " |"


def write(tmp_path, *lines: str):
    p = tmp_path / "export.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class TestCellHelpers:
    def test_a_markdown_link_yields_its_label(self):
        assert cell_text("[Ambrose Quill](https://example.invalid/1/player)") == "Ambrose Quill"

    def test_a_plain_cell_passes_through(self):
        assert cell_text("  DEN  ") == "DEN"

    def test_the_alignment_row_is_a_separator(self):
        assert is_separator(SEPARATOR)

    def test_a_data_row_is_not_a_separator(self):
        assert not is_separator(row())


class TestParse:
    def test_columns_land_in_board_order(self, tmp_path):
        """The 20-field output order is what verify.py's COLS names. Pin it."""
        players, problems = parse(write(tmp_path, HEADER, SEPARATOR, row()))
        assert problems == []
        assert players == [[
            1, "Ambrose Quill", "DEN", "C", 4.3, 72.0, 35.1,
            8.0, 16.0, 0.500,          # fgm fga fgp
            4.0, 5.0, 0.800,           # ftm fta ftp
            1.8, 28.4, 12.7, 10.4, 1.6, 0.7, 3.5,
        ]]

    def test_makes_and_attempts_survive_the_percentage_cell(self, tmp_path):
        """The whole point of this parser: `0.573(10.5/18.3)` is three numbers.

        Keeping only the leading rate is what makes a bare-rate valuation possible,
        which AGENTS.md forbids. Makes and attempts must come through.
        """
        players, _ = parse(write(tmp_path, HEADER, SEPARATOR, row(fg="0.573(10.5/18.3)")))
        assert players[0][7:10] == [10.5, 18.3, 0.573]

    def test_repeated_header_blocks_are_skipped(self, tmp_path):
        """The export re-emits its header every ~13 players."""
        players, problems = parse(write(
            tmp_path, HEADER, SEPARATOR, row(rank="1", name="Ambrose Quill"),
            HEADER, row(rank="2", name="Bertram Vole"),
        ))
        assert problems == []
        assert [p[1] for p in players] == ["Ambrose Quill", "Bertram Vole"]

    def test_a_rank_cell_carrying_a_movement_indicator_keeps_only_the_rank(self, tmp_path):
        """`18 38` is rank 18 with a movement marker, not rank 1838."""
        players, _ = parse(write(tmp_path, HEADER, SEPARATOR, row(rank="18 38")))
        assert players[0][0] == 18

    def test_a_non_numeric_adp_becomes_empty_not_zero(self, tmp_path):
        """An undrafted player has no ADP. Zero would sort him first."""
        players, _ = parse(write(tmp_path, HEADER, SEPARATOR, row(adp="-")))
        assert players[0][4] == ""

    def test_a_short_row_is_reported_not_dropped(self, tmp_path):
        """A silently skipped row is a wrong board. It must surface as a problem."""
        players, problems = parse(write(tmp_path, HEADER, SEPARATOR, "| 1 | x | 2 |"))
        assert players == []
        assert len(problems) == 1
        assert "expected 17 columns" in problems[0][1]

    def test_an_unparseable_percentage_is_reported_not_dropped(self, tmp_path):
        players, problems = parse(write(tmp_path, HEADER, SEPARATOR, row(fg="n/a")))
        assert players == []
        assert len(problems) == 1
        assert "unparseable" in problems[0][1]


class TestCheck:
    """The integrity guards. A dropped or duplicated player is a wrong board."""

    def test_a_clean_pool_has_no_complaints(self):
        players = [[i, f"Player {i}"] + [0.0] * 18 for i in range(1, 5)]
        assert check(players) == []

    def test_a_gap_in_the_seed_ranks_is_caught(self):
        players = [[i, f"Player {i}"] + [0.0] * 18 for i in (1, 2, 4)]
        assert any("contiguous" in c for c in check(players))

    def test_a_duplicate_name_is_caught(self):
        players = [[i, "Ambrose Quill"] + [0.0] * 18 for i in (1, 2)]
        assert any("duplicate" in c for c in check(players))

    @pytest.mark.parametrize("problems", [[(3, "expected 17 columns, got 4", [])]])
    def test_unparsed_rows_are_carried_into_the_complaints(self, problems):
        players = [[1, "Ambrose Quill"] + [0.0] * 18]
        assert any("unparsed" in c for c in check(players, problems))

    def test_every_check_has_a_name_so_a_failure_says_which(self):
        """CHECKS is what lets the analysis loader report *which* guard tripped."""
        assert set(CHECKS) == {"contiguous", "duplicate", "unparsed"}
