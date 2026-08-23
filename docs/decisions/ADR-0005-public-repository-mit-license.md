# ADR-0005: Public repository under the MIT license

- Status: Accepted
- Date: 2026-08-23
- Owner: Bryan

## Context and Problem

The repository started private. Nothing in it is proprietary: the code is scaffolding, the docs describe a public API, and every secret and every byte of collected data is gitignored. `AGENTS.md` has said "treat this file as public" since the first commit, so the project was written for an audience it did not yet have.

Publishing is close to irreversible. Forks, clones, and search indexes survive a repository being made private again, and so does any credential that was ever committed. That makes visibility a security-posture decision rather than a settings toggle, and the decision log asks for a record when posture changes in a hard-to-reverse way.

A second question rides along with it: public code with no license is public code nobody may legally reuse. Silence here is itself a choice, and a confusing one.

## Decision Drivers

- Nothing in the repository needs to be secret; the boundaries that keep it that way already exist
- Irreversibility — the audit has to happen before the flip, not after
- The project is for one league and one owner; it should not imply obligations to anyone else
- License silence invites the wrong assumption in both directions

## Considered Options

1. Public, MIT licensed
2. Public, all rights reserved
3. Stay private

## Decision

**The repository is public and MIT licensed.** The README and the GitHub description both state that it is built for the owner's own league and is not supported for anyone else's.

"Personal use only" here describes intent and support, not permission. MIT grants reuse freely; what the framing withholds is the expectation of maintenance, stability, or help.

## Consequences

- Positive: the work is shareable and referenceable without a per-person access grant.
- Positive: the license question is answered explicitly rather than left to inference.
- Negative, and the one that matters: the boundaries in [AGENTS.md](../../AGENTS.md) — never commit a real API key, never commit anything under `data/` — stop being tidiness and become the security perimeter. A key pushed to a public repository is compromised the instant it lands, and must be rotated rather than reverted. Making the repository private again does not undo it.
- Negative: league-specific configuration is now visible. Acceptable: `config/league.yaml` holds settings, not credentials.
- Follow-ups: check `git status` against `.gitignore` before every commit, and treat any pushed secret as burned rather than removable.

## Pros and Cons of the Options

### Option 1 — Public, MIT licensed
- Good: shareable; unambiguous reuse terms; matches how the docs were already written.
- Bad: raises the cost of a mistake in the ingestion code's handling of `.env`.

### Option 2 — Public, all rights reserved
- Good: same visibility, no rights granted.
- Bad: readers cannot legally borrow even a snippet, which defeats the point of publishing a reference project. Carries the same secret-exposure risk with less of the benefit.

### Option 3 — Stay private
- Good: smallest blast radius for a leaked credential.
- Bad: sharing requires managing collaborator access one person at a time, for a project with nothing to hide.

## Links

- Boundaries and security handling: [AGENTS.md](../../AGENTS.md).
- License text: [LICENSE](../../LICENSE).
