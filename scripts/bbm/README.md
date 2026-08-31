# Basketball Monster's valuation, reimplemented

`bbm_reference.py` is a from-scratch implementation of the method reverse-engineered in
[the reference document](../../docs/references/basketball-monster-projections-reverse-engineering.md).

It needs **no Basketball Monster access and no particular file format**. Give it projected
season totals from any source and it returns the nine category values, `Value`, `Rank`,
`DURANT` and `DURANT H2H`.

Standard library only, so it adds no runtime dependency (see [AGENTS.md](../../CLAUDE.md)).

```python
import bbm_reference as B

players = {pid: B.per_game(projection) for pid, projection in my_projections.items()}
players = {k: v for k, v in players.items() if v}      # drop zero-games players
pool, params = B.build_pool(players, q=156)            # q = teams x roster spots

vals  = B.category_values(players["someone"], params)  # the nine
score = B.value(players["someone"], params)            # their mean
ranks = B.rank_and_round({k: B.value(v, params) for k, v in players.items()}, teams=12)
```

For DURANT, build its own pool — it standardises transformed values, so the constants differ:

```python
dpool, dparams = B.build_durant_pool(players, 156, B.LAMBDAS_BBM_2026_27_JOSH)
dur,  dropped  = B.durant(players["someone"], dparams)
h2h,  dropped2 = B.durant_h2h(players["someone"], dparams)
```

`LAMBDAS_BBM_2026_27_JOSH` reproduces *their* published numbers for that one season and
source. For your own projections, fit your own with `B.fit_lambda` — and read the note beside
the constant, because the two do not coincide.

## Accuracy

Measured against Basketball Monster's published columns (their exports are gitignored, so
this is not a committed test):

| | `Value` MAE | Spearman | Max rank move |
|---|---|---|---|
| Josh source | 0.0075 | 0.99942 | 8 |
| Bonus source | 0.0050 | 0.99968 | 6 |
| `DURANT` | 0.0083 | 0.99902 | — |
| `DURANT H2H` | 0.0079 | 0.99919 | — |

The committed tests in `tests/test_bbm_reference.py` are synthetic and check the arithmetic,
not the provider data — this repo is public ([ADR-0006](../../docs/decisions/ADR-0006-no-provider-data-redistribution.md)).
