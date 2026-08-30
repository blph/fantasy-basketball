# ADR-0015: numpy, matplotlib and scipy as analysis-only dev dependencies

- Status: Accepted
- Date: 2026-08-30
- Owner: Bryan

## Context

[AGENTS.md](../../CLAUDE.md) states that runtime dependencies land in Phase 2 and
that each one needs an ADR. The project has honoured that: `dependencies = []`,
and `scripts/draft-board/valuation.py` does all of its mean and standard-deviation
work with the stdlib `statistics` module. `export_yahoo_rankings.py` goes as far
as hardcoding the season rather than parse YAML, with the comment "pyyaml is not a
declared dependency and a runtime dep needs an ADR."

Two things then happened without a record.

**`scripts/analysis/` was added importing numpy and matplotlib**, neither of which
is declared anywhere. They resolved from a user-site `pip install --user` on the
owner's machine. CI installs `pip install -e ".[dev]"` and nothing else, so the
analysis scripts could not run there, and no test could import them. Nothing
failed, because nothing tested them — the gap was invisible rather than absent.

**A normality analysis of the nine scoring categories needed statistical tests.**
Shapiro-Wilk and Anderson-Darling are the two that carry the analysis: the first
is the highest-power omnibus at n ≈ 156, and the second is the only tail-weighted
test in the battery, which matters because the tails are where z-scoring prices
the top of the draft.

## Decision

**Declare `numpy`, `matplotlib` and `scipy` in the `dev` extra**, with version
floors:

```toml
dev = [
  "pytest>=8.0",
  "ruff>=0.6",
  "numpy>=1.26",
  "matplotlib>=3.8",
  "scipy>=1.11",
]
```

The project still ships **zero runtime dependencies**. These three are permitted
because:

- **They never enter `src/`.** They serve `scripts/analysis/`, which produces PNGs
  and markdown for a human to read. Nothing in the pipeline, the database, or any
  app imports them, and the boundary in AGENTS.md — "analytics and apps read the
  database" — is untouched.
- **They are bounded by the same clock as the draft board.** `scripts/analysis/`
  reads `valuation.py`, which [ADR-0008](ADR-0008-google-sheet-draft-board.md)
  scopes to the 2026-27 draft and deletes when Phase 2 lands.
- **The alternative is worse.** Hand-rolling Shapiro-Wilk means implementing
  Royston's algorithm; hand-rolling Anderson-Darling means the Stephens tables. In
  a repository whose first stated priority is that *a wrong number that looks right
  is worse than no number*, an unvalidated statistical test is precisely the thing
  not to write. Version floors are pinned so chart output and test statistics do
  not drift between machines.

They go in `dev` rather than a separate `analysis` extra so that CI installs them
and `scripts/analysis/` is actually covered by `pytest`. That is the whole point:
the previous arrangement left it untestable.

## Consequences

**CI installs about 100 MB more to run `ruff` and `pytest`.** Accepted knowingly.
The alternative — a separate `analysis` extra that CI does not install — would
leave `scripts/analysis/` in exactly the untested state this ADR exists to end.

**The numpy and matplotlib already in use become legitimate.** They were a policy
violation from the moment `scripts/analysis/` was written; this is the record that
should have accompanied it.

**A precedent exists now, and it is narrow.** "Analysis tooling that never enters
`src/`" is the category. A dependency that the pipeline, database or an app
imports is a runtime dependency and still needs its own ADR under the Phase 2
rule. Adding to this list is not automatic.

**SciPy's API is not frozen.** `scipy.stats.anderson` changed its signature in
1.17 and will drop its critical-value attributes in 1.19.
`scripts/analysis/normality.py` handles both forms rather than pinning an upper
bound, so the floor stays low and the code stays current.

## Alternatives considered

**A separate `analysis` extra.** Cleaner separation, and CI stays light. Rejected
because CI would not install it, so any test importing those modules would have to
be skipped — which returns `scripts/analysis/` to being untested.

**Stdlib only.** Skewness, kurtosis, the D'Agostino-Pearson K², and the ECDF
comparison are all closed forms and would have been fine. Shapiro-Wilk and
Anderson-Darling are not, and dropping them would have meant either a weaker
analysis or an unvalidated implementation of a published test.

**Leaving numpy and matplotlib undeclared.** The status quo. Rejected: it is a
standing policy violation, and it silently prevents CI from ever running the code.
