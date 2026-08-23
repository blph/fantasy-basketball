# ADR-0006: Publish no provider data, and enforce it mechanically

- Status: Accepted
- Date: 2026-08-23
- Owner: Bryan

## Context and Problem

[ADR-0005](ADR-0005-public-repository-mit-license.md) made the repository public under MIT. That turns a question that did not previously matter into one that does: what, exactly, is being published?

The code and the docs are ours to license. The data is not. FantasyPros' Premium tier is licensed for **personal, non-commercial use** ([endpoint reference](../api/fantasypros-endpoints.md)), and the Yahoo Fantasy Sports API carries its own terms. Neither grants a right to redistribute their data, and publishing it in a public repository is redistribution regardless of intent or volume.

Two problems followed from the flip:

1. **Nothing said so.** A visitor saw a project built on the FantasyPros API, an MIT license, and no statement scoping what that license covers. MIT reads as covering everything in the repository — including, by implication, data that is not ours to license.

2. **A standing rule contradicted the policy.** The Testing section of `AGENTS.md` said fixtures are *"archived JSON from `data/raw/`, copied into `tests/fixtures/` and committed."* Written while the repo was private, that is a direct instruction to commit verbatim provider responses to what is now a public repository. Nothing had been committed under it — `tests/` held only `.gitkeep` — so the cost of changing it was zero. The cost of finding it later, after a season of fixtures, would not have been.

The deeper issue is that the previous protection was `.gitignore` plus discipline. `.gitignore` does not stop `git add -f`, and discipline does not survive draft night at 2am.

## Decision Drivers

- Provider terms permit personal use, not republication
- The MIT grant must be scoped explicitly, or it over-claims
- A rule that contradicts the policy will eventually be followed
- Guardrails that depend on remembering them are not guardrails
- Irreversibility: a published payload, like a published key, cannot be recalled

## Considered Options

1. Documented policy plus mechanical enforcement
2. Documented policy alone
3. Commit sanitized or truncated real responses as fixtures

## Decision

**No provider data is published in this repository, in any form**, and the rule is enforced by a check rather than by memory.

- The README's "Data and API access" section is the canonical statement, and it scopes the MIT grant to code and documentation only.
- Test fixtures are **synthetic**: hand-authored JSON matching the *shape* of a real response, with invented players and numbers. When a live response reveals a shape a fixture gets wrong, the fixture is edited to match the shape; the payload is never pasted.
- `scripts/check-no-data.sh` refuses anything under `data/`, any real `.env`, any database or tabular export, and any credential-shaped string. It runs from `.githooks/pre-commit` against staged files and from CI against the whole tracked tree.

Both layers exist deliberately. The hook gives fast local feedback and can be bypassed with `--no-verify` or simply never activated; CI cannot be, and it is the one that catches a mistake made in another clone or in the GitHub web editor.

## Consequences

- Positive: the licensing position is stated rather than inferred, in the place a visitor actually looks.
- Positive: committing data now takes deliberate effort against two independent checks, instead of a moment's inattention.
- Positive: the CI check runs against the full tracked tree, so it also detects data committed before the guard existed.
- Negative: synthetic fixtures can drift from real response shapes, and a test passing against a fixture the provider no longer matches is exactly the "wrong number that looks right" this project ranks as its worst failure. Mitigated by the [verification checklist](../api/fantasypros-endpoints.md#verification-checklist) — reconcile fixture shapes against live responses whenever an endpoint's schema is confirmed or changes.
- Negative: writing a fixture by hand costs more than capturing one. Accepted; it is a one-time cost per endpoint.
- Negative: the pre-commit hook needs `git config core.hooksPath .githooks` in each clone. A repository cannot activate its own hooks, so this is documented in the README's Getting started block and backstopped by CI.
- Follow-ups: when the Yahoo integration lands, extend the credential patterns in `scripts/check-no-data.sh` to cover its token cache.

## Pros and Cons of the Options

### Option 1 — Policy plus enforcement
- Good: the stated rule and the enforced rule are the same rule. Survives inattention and other clones.
- Bad: two more files to maintain; hook activation is a manual step.

### Option 2 — Policy alone
- Good: nothing to build.
- Bad: the protection is `.gitignore` plus memory, which is what was already in place. `git add -f` defeats it, and the failure is silent and public.

### Option 3 — Sanitized real responses as fixtures
- Good: exact shape fidelity, so tests match reality.
- Bad: sanitizing is a judgment call made under time pressure, and a truncated provider response is still a provider response. It also puts every future fixture on the wrong side of a line that is much easier to hold at zero.

## Links

- Public repository decision: [ADR-0005](ADR-0005-public-repository-mit-license.md).
- Access tiers and terms: [docs/api/fantasypros-endpoints.md](../api/fantasypros-endpoints.md).
- Policy statement: [README.md](../../README.md) — "Data and API access".
