"""The gate that compares the board to Basketball Monster rather than to itself.

Every other check in verify.py verifies internal consistency, and the board was internally
consistent while every value was wrong by 0.008 (see
docs/bugs/2026-09-01-durh-zsc-pool-constants.md). This is the one that would have caught it.

Fixtures are synthetic (ADR-0006): invented players, invented values.
"""


import verify as V

NAMES = ["Ada Quill", "Bo Marsh", "Cleo Vance", "Dax Orin"]


def data(durh, zsc, drops, dh=None):
    """A minimal Data.gs-shaped mapping: one source, four players."""
    rows = []
    for i in range(len(NAMES)):
        row = [0.0] * V.V_WIDTH
        row[V.V_DURH], row[V.V_DURH_RANK], row[V.V_DURH_DROP] = durh[i], i + 1, drops[i]
        row[V.V_ZSH], row[V.V_ZSH_RANK], row[V.V_ZSH_DROP] = 0.0, i + 1, "PTS"
        row[V.V_ZSC], row[V.V_ZSC_RANK] = zsc[i], i + 1
        for j in range(len(V.BV.CAT_LABELS)):
            row[V.V_DH0 + j] = (dh[i][j] if dh else -1.0 - 0.1 * j)
        rows.append(row)
    return {"PLAYERS": [[i + 1, n] + [""] * 18 for i, n in enumerate(NAMES)],
            "VALUES": {"BMP": rows}}


def tsv(tmp_path, values, drops, name="BBM Published - BMP - 2026-01-01.tsv"):
    """Their published grid: an id column, then Name, Value and DUR H2H."""
    lines = ["\t".join(["", "Name", "Value", "DUR H2H"])]
    for i, n in enumerate(NAMES):
        lines.append("\t".join([str(100 + i), n, f"{values[i][0]:.2f}",
                                f"{values[i][1]:.2f}#{i + 1}{drops[i]}"]))
    p = tmp_path / name
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


class TestAgreement:
    def test_a_board_that_matches_them_passes(self, tmp_path):
        d = data([1.09, 0.80, 0.51, 0.20], [1.02, 0.75, 0.48, 0.19],
                 ["3PM", "PTS", "REB", "BLK"])
        p = tsv(tmp_path, [(1.02, 1.09), (0.75, 0.80), (0.48, 0.51), (0.19, 0.20)],
                ["3", "pts", "reb", "blk"])
        assert V.diff_published(d, p, "BMP") == []

    def test_their_composite_cell_is_parsed_value_rank_then_category(self):
        # "1.09#13" is 1.09, rank 1, dropped 3PM -- not rank 13. Getting this wrong makes
        # every three-point drop look like a disagreement.
        m = V.PUB_TAG.match("1.09#13")
        assert m.group(1) == "1.09" and V.PUB_DROP[m.group(3)] == "3PM"
        assert V.PUB_TAG.match("-0.42#207ft%").group(3) == "ft%"


class TestItFailsOnRealDisagreement:
    def test_a_value_off_by_more_than_the_tolerance_fails(self, tmp_path):
        d = data([1.09, 0.80, 0.51, 0.20], [1.02, 0.75, 0.48, 0.19],
                 ["3PM", "PTS", "REB", "BLK"])
        p = tsv(tmp_path, [(1.02, 1.09), (0.75, 0.80), (0.48, 0.60), (0.19, 0.20)],
                ["3", "pts", "reb", "blk"])
        fails = V.diff_published(d, p, "BMP")
        assert any("DURH" in f and "worst row" in f for f in fails)

    def test_a_separable_dropped_category_disagreement_fails(self, tmp_path):
        # The two categories are far apart, so we could tell them apart and picked wrong.
        dh = [[-1.0, -9.0] + [0.0] * 6] + [[-1.0 - 0.1 * j for j in range(8)]] * 3
        d = data([1.09, 0.80, 0.51, 0.20], [1.02, 0.75, 0.48, 0.19],
                 ["FT%", "PTS", "REB", "BLK"], dh=dh)
        p = tsv(tmp_path, [(1.02, 1.09), (0.75, 0.80), (0.48, 0.51), (0.19, 0.20)],
                ["fg%", "pts", "reb", "blk"])
        assert any("dropped category" in f for f in V.diff_published(d, p, "BMP"))

    def test_a_tie_neither_side_can_call_is_reported_but_not_failed(self, tmp_path):
        # Their columns are published to two decimals and the percentage categories carry
        # a residual around 0.017, so a gap of 0.001 is a coin flip, not an error.
        dh = [[-1.000, -1.001] + [0.0] * 6] + [[-1.0 - 0.1 * j for j in range(8)]] * 3
        d = data([1.09, 0.80, 0.51, 0.20], [1.02, 0.75, 0.48, 0.19],
                 ["FT%", "PTS", "REB", "BLK"], dh=dh)
        p = tsv(tmp_path, [(1.02, 1.09), (0.75, 0.80), (0.48, 0.51), (0.19, 0.20)],
                ["fg%", "pts", "reb", "blk"])
        assert V.diff_published(d, p, "BMP") == []


class TestBadInput:
    def test_a_scrape_with_no_matching_player_says_so(self, tmp_path):
        d = data([1.0] * 4, [1.0] * 4, ["PTS"] * 4)
        p = tmp_path / "BBM Published - BMP - 2026-01-01.tsv"
        p.write_text("\tName\tValue\tDUR H2H\n1\tNobody Here\t1.00\t1.00#1pts\n",
                     encoding="utf-8")
        assert any("no board player matched" in f for f in V.diff_published(d, p, "BMP"))

    def test_a_scrape_without_the_value_columns_says_which(self, tmp_path):
        d = data([1.0] * 4, [1.0] * 4, ["PTS"] * 4)
        p = tmp_path / "BBM Published - BMP - 2026-01-01.tsv"
        p.write_text("\tName\tpV\n1\tAda Quill\t0.5\n", encoding="utf-8")
        assert any("missing" in f for f in V.diff_published(d, p, "BMP"))
