# Apps

Static HTML/CSS/JS. No build step, no dev server ([ADR-0001](../docs/decisions/ADR-0001-python-and-static-html-stack.md)).

| App | Phase | Purpose |
| --- | --- | --- |
| `draft-assistant/` | 3 | Draft-day board: rankings, ADP, projections, per-category z-scores, tiers, scarcity, injury flags |
| `roster-manager/` | 5 | Ongoing roster view: add/drop and lineup recommendations against our category standing |

## Rules

- **Read data only.** Apps never call a provider API and never recompute valuations at load time. Python precomputes marts; apps display them.
- **Must work offline, opened directly from the filesystem.** Draft day has no tolerance for a failed build or a dead network.
- Data reaches an app as a generated static JSON file exported by the Python layer, not a live query.
