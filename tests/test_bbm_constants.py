"""The fitted-constants file, and the gates that stop the wrong one being used.

Every check here exists because the failure it catches is invisible downstream. A
constants file paired with the wrong export, or missing a percentage rate, still produces
a board full of numbers that all look like numbers -- and every one of them is wrong by a
percent or two. See ADR-0021 and docs/bugs/2026-09-01-durh-zsc-pool-constants.md.

Fixtures are synthetic (ADR-0006): nothing in this file came off Basketball Monster.
"""

import json

import bbm_constants as BC
import bbm_reference as B
import pytest

from test_board_values import spread


def blob(**over):
    """A valid file, derived from a synthetic pool. Override a key to break one thing."""
    pool = spread(40)
    _, plain = B.build_pool(pool, 20)
    _, durant = B.build_durant_pool(pool, 20, B.LAMBDAS_BBM_2026_27_JOSH)
    out = BC.dump(
        {"plain": plain, "durant": durant}, dict(B.LAMBDAS_BBM_2026_27_JOSH),
        source="BMP", export_date="2026-01-01", bbm_source_id=17329,
        fitted_at="2026-01-01T00:00:00Z", fitted_from="synthetic",
        players_fitted=40, fit={},
    )
    out.update(over)
    return out


def parse(b=None, source="BMP", export_date="2026-01-01"):
    return BC.parse(b if b is not None else blob(), source=source, export_date=export_date)


class TestItBuildsUsableParams:
    def test_the_params_are_the_shape_the_valuation_consumes(self):
        got = parse()
        pool = spread(40)
        one = pool["p010"]
        assert set(B.category_values(one, got["plain"])) == set(B.CATEGORIES)
        assert set(B.durant_category_values(one, got["durant"])) == set(B.CATEGORIES)

    def test_a_category_value_is_the_z_the_constants_imply(self):
        got = parse()
        one = spread(40)["p010"]
        spec = got["plain"]["pV"]
        assert B.category_values(one, got["plain"])["pV"] == pytest.approx(
            (one["points"] - spec["mean"]) / spec["sd"])

    def test_the_structural_fields_are_rebuilt_and_never_read_from_disk(self):
        # A file that could redefine which stat a category reads, or flip a sign, would be
        # a way to invert turnovers by editing JSON. The loader takes those from the
        # category table and ignores anything the file says about them.
        b = blob()
        b["plain"]["toV"]["sign"] = +1
        b["plain"]["toV"]["key"] = "points"
        got = parse(b)
        assert got["plain"]["toV"]["sign"] == -1
        assert got["plain"]["toV"]["key"] == "turnovers"

    def test_lambdas_come_out_of_the_file_not_the_module(self):
        b = blob()
        b["lambdas"] = dict(b["lambdas"], pV=0.9)
        assert parse(b)["lambdas"]["pV"] == 0.9
        assert parse(b)["durant"]["pV"]["lam"] == 0.9


class TestPairingGates:
    def test_constants_for_another_source_are_refused(self):
        with pytest.raises(BC.ConstantsError, match="not 'BMP-ALT'"):
            parse(source="BMP-ALT")

    def test_constants_fitted_against_another_export_are_refused(self):
        # The one that matters most. Nothing downstream can see this: the numbers are all
        # plausible, and the board comes out uniformly, invisibly wrong.
        with pytest.raises(BC.ConstantsError, match="fitted against"):
            parse(export_date="2026-02-02")

    def test_an_unknown_schema_is_refused_rather_than_guessed_at(self):
        with pytest.raises(BC.ConstantsError, match="schema"):
            parse(blob(schema=99))


class TestShapeGates:
    def test_a_percentage_without_a_pool_rate_is_refused(self):
        b = blob()
        del b["plain"]["fg%V"]["rate"]
        with pytest.raises(BC.ConstantsError, match="need a pool 'rate'"):
            parse(b)

    def test_a_counting_category_carrying_a_rate_is_refused(self):
        b = blob()
        b["durant"]["pV"]["rate"] = 0.5
        with pytest.raises(BC.ConstantsError, match="carry no 'rate'"):
            parse(b)

    def test_a_missing_category_is_refused(self):
        # All nine, not the eight the board displays: ZSC averages nine.
        b = blob()
        del b["plain"]["toV"]
        with pytest.raises(BC.ConstantsError, match="toV"):
            parse(b)

    def test_a_missing_layer_is_refused(self):
        b = blob()
        del b["durant"]
        with pytest.raises(BC.ConstantsError, match="durant"):
            parse(b)

    def test_a_non_positive_spread_is_refused(self):
        b = blob()
        b["plain"]["sV"]["sd"] = 0.0
        with pytest.raises(BC.ConstantsError, match="sd="):
            parse(b)

    def test_a_lambda_outside_the_transform_domain_is_refused(self):
        b = blob()
        b["lambdas"] = dict(b["lambdas"], bV=-99.0)
        with pytest.raises(BC.ConstantsError, match="domain"):
            parse(b)

    def test_incomplete_lambdas_are_refused(self):
        b = blob()
        b["lambdas"] = {"pV": 0.4}
        with pytest.raises(BC.ConstantsError, match="all nine"):
            parse(b)


class TestLambdaDrift:
    def test_a_moved_counting_lambda_warns_and_does_not_raise(self):
        # Basketball Monster retuning their transform is the thing this design absorbs, so
        # it must be visible and must never block a refresh.
        b = blob()
        b["lambdas"] = dict(b["lambdas"], bV=B.LAMBDAS_BBM_2026_27_JOSH["bV"] + 0.4)
        got = parse(b)
        assert any("bV" in w for w in got["warnings"])

    def test_a_moved_percentage_lambda_is_silent(self):
        # They are fitted jointly with the pool rate and wander along a ridge without
        # meaning anything. Alarming every refresh would teach the reader to skip the alarm.
        b = blob()
        b["lambdas"] = dict(b["lambdas"], **{"ft%V": 1.40})
        assert parse(b)["warnings"] == []


class TestLoad:
    def test_a_missing_file_names_the_command_that_makes_one(self, tmp_path):
        with pytest.raises(BC.ConstantsError, match="calibrate_bbm.py"):
            BC.load(tmp_path / "nope.json", source="BMP", export_date="2026-01-01")

    def test_unreadable_json_says_so(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(BC.ConstantsError, match="not valid JSON"):
            BC.load(p, source="BMP", export_date="2026-01-01")

    def test_a_written_file_reads_back_to_the_same_constants(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps(blob()), encoding="utf-8")
        got = BC.load(p, source="BMP", export_date="2026-01-01")
        for cat in B.CATEGORIES:
            assert got["plain"][cat]["sd"] == pytest.approx(
                parse()["plain"][cat]["sd"])
