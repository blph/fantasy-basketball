#!/usr/bin/env python3
"""Read a fitted-constants file and turn it into standardisation params.

Basketball Monster's per-category values are z-scores against constants we cannot derive:
their means agree with a top-156 pool to about half a percent, their standard deviations
only to one to three percent, and no pool size fits both moments at once (ADR-0021, and
the reverse-engineering doc's III.2). So for the two sources where they publish values, we
recover their constants by regression instead of deriving our own -- `calibrate_bbm.py`
does the recovering, this module does the reading.

Nothing here is a constant. The numbers live in a dated file beside the export they were
fitted against, and they are refitted on every refresh, because they are a property of a
projection set that moves. A constants file paired with the wrong export is the failure
this module exists to prevent: every number in it still looks like a number, and the whole
board comes out wrong by a percent or two with nothing to see.

The file carries only fitted values. `kind`, `key`, `made`, `att` and `sign` are rebuilt
from `bbm_reference.COUNTING` / `PERCENTAGE`, so a file on disk can never redefine which
stat a category reads or invert a sign.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bbm"))

from bbm_reference import (  # noqa: E402
    CATEGORIES,
    COUNTING,
    LAMBDAS_BBM_2026_27_JOSH,
    PERCENTAGE,
)

#: Bump when the file's shape changes. An old file is refused, not guessed at.
SCHEMA = 1

#: Yeo-Johnson's search domain. A lambda outside it is a broken fit, not a finding.
LAM_LIMIT = 4.0

#: How far a refitted counting-category lambda may drift from the seed before it is worth
#: mentioning. A warning, never an error: Basketball Monster moving their lambdas is the
#: thing this whole design exists to absorb, so it must not be able to block a refresh.
#:
#: Only the counting categories are checked. The two percentage lambdas are fitted jointly
#: with the pool rate and trade off against it along a ridge, so they wander between
#: refreshes without meaning anything (doc III.1). Alarming on them every time would teach
#: the reader to skip the alarm, which is worse than not having one.
LAM_DRIFT_WARN = 0.05

_LAYER_KEYS = ("plain", "durant")


class ConstantsError(Exception):
    """A fitted-constants file is not usable for the build being run."""


def _spec(name: str, entry: dict, layer: str, lam: float) -> dict:
    """One category's params, with the structural fields rebuilt rather than read."""
    for key, cat, sign in COUNTING:
        if cat == name:
            if "rate" in entry:
                raise ConstantsError(
                    f"{layer}.{name}: counting categories carry no 'rate'. A rate here means "
                    f"the file was written against a different category table."
                )
            out = {"kind": "counting", "key": key, "sign": sign,
                   "mean": float(entry["mean"]), "sd": float(entry["sd"])}
            break
    else:
        for made, att, cat in PERCENTAGE:
            if cat == name:
                if "rate" not in entry:
                    raise ConstantsError(
                        f"{layer}.{name}: percentage categories need a pool 'rate'. Without it "
                        f"the impact column is measured against nothing."
                    )
                out = {"kind": "percentage", "made": made, "att": att, "sign": +1,
                       "rate": float(entry["rate"]),
                       "mean": float(entry["mean"]), "sd": float(entry["sd"])}
                break
        else:  # pragma: no cover - CATEGORIES is COUNTING + PERCENTAGE by construction
            raise ConstantsError(f"{layer}.{name}: not a known category")

    if out["sd"] <= 0:
        raise ConstantsError(
            f"{layer}.{name}: sd={out['sd']}. A non-positive spread cannot standardise "
            f"anything; the fit failed and the file should not have been written."
        )
    if layer == "durant":
        out["lam"] = lam
    return out


def parse(blob: dict, *, source: str, export_date: str) -> dict:
    """Validate a decoded constants file and build the params the pipeline consumes.

    Returns {"plain": {...}, "durant": {...}, "lambdas": {...}, "meta": {...}, "warnings": [...]}.
    Every mismatch below is a hard error, because none of them is visible downstream.
    """
    if blob.get("schema") != SCHEMA:
        raise ConstantsError(
            f"schema {blob.get('schema')!r}, expected {SCHEMA}. Refit with calibrate_bbm.py."
        )
    if blob.get("source") != source:
        raise ConstantsError(
            f"constants are for source {blob.get('source')!r}, not {source!r}. "
            f"BMP and BMP-ALT are different projection sets with different pools."
        )
    if blob.get("export_date") != export_date:
        raise ConstantsError(
            f"constants were fitted against the {blob.get('export_date')!r} export, "
            f"the build is scoring {export_date!r}. Refit against this export."
        )

    lambdas = blob.get("lambdas")
    if not isinstance(lambdas, dict) or set(lambdas) != set(CATEGORIES):
        raise ConstantsError(
            f"lambdas must name all nine categories; got {sorted(lambdas or [])}"
        )
    lambdas = {c: float(lambdas[c]) for c in CATEGORIES}
    for c, lam in lambdas.items():
        if not -LAM_LIMIT <= lam <= LAM_LIMIT:
            raise ConstantsError(
                f"lambda {c}={lam} is outside the fitter's [-{LAM_LIMIT}, {LAM_LIMIT}] "
                f"domain, so it is a broken fit rather than a measurement."
            )

    counting = {c for _, c, _ in COUNTING}
    warnings = []
    for c in sorted(counting):
        lam, seed = lambdas[c], LAMBDAS_BBM_2026_27_JOSH[c]
        if abs(lam - seed) > LAM_DRIFT_WARN:
            warnings.append(
                f"lambda {c} refitted to {lam:+.4f}, {lam - seed:+.4f} from the "
                f"{seed:+.4f} seed -- Basketball Monster may have retuned their transform"
            )

    params = {}
    for layer in _LAYER_KEYS:
        block = blob.get(layer)
        if not isinstance(block, dict):
            raise ConstantsError(f"missing '{layer}' block")
        missing = set(CATEGORIES) - set(block)
        if missing:
            raise ConstantsError(
                f"{layer}: missing {', '.join(sorted(missing))}. All nine are required -- "
                f"ZSC averages nine even though the board displays eight."
            )
        params[layer] = {
            c: _spec(c, block[c], layer, lambdas[c]) for c in CATEGORIES
        }

    return {
        "plain": params["plain"],
        "durant": params["durant"],
        "lambdas": lambdas,
        "meta": {k: blob.get(k) for k in
                 ("source", "export_date", "fitted_at", "fitted_from",
                  "players_fitted", "bbm_source_id")},
        "fit": blob.get("fit", {}),
        "warnings": warnings,
    }


def load(path: Path, *, source: str, export_date: str) -> dict:
    """Read and validate the constants file at `path`. See `parse`."""
    try:
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConstantsError(
            f"{Path(path).name} not found. Run:\n"
            f"  python3 scripts/draft-board/calibrate_bbm.py "
            f"--source {source} --date {export_date}"
        ) from None
    except ValueError as exc:
        raise ConstantsError(f"{Path(path).name} is not valid JSON: {exc}") from None
    try:
        return parse(blob, source=source, export_date=export_date)
    except ConstantsError as exc:
        raise ConstantsError(f"{Path(path).name}: {exc}") from None


def dump(params: dict, lambdas: dict, *, source: str, export_date: str,
         bbm_source_id, fitted_at: str, fitted_from: str, players_fitted: int,
         fit: dict, lambda_seed: dict | None = None) -> dict:
    """The inverse of `parse`: the on-disk blob for a set of fitted params.

    Writes only the fitted numbers. The structural fields (`kind`, `key`, `sign`) are the
    reader's to rebuild, so the file cannot carry a contradiction of the category table.
    """
    def strip(block):
        out = {}
        for c in CATEGORIES:
            spec = block[c]
            entry = {"mean": round(spec["mean"], 8), "sd": round(spec["sd"], 8)}
            if spec["kind"] == "percentage":
                entry["rate"] = round(spec["rate"], 8)
            out[c] = entry
        return out

    return {
        "schema": SCHEMA,
        "source": source,
        "bbm_source_id": bbm_source_id,
        "export_date": export_date,
        "fitted_at": fitted_at,
        "fitted_from": fitted_from,
        "players_fitted": players_fitted,
        "lambdas": {c: round(lambdas[c], 6) for c in CATEGORIES},
        "lambda_seed": dict(lambda_seed or LAMBDAS_BBM_2026_27_JOSH),
        "plain": strip(params["plain"]),
        "durant": strip(params["durant"]),
        "fit": fit,
    }
