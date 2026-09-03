# Rebuild & re-sort duplicates the Draft Board's conditional formats

- Found: 2026-09-02, while adding the injury-risk column (ADR-0022)
- Status: **Open.** Recorded, not fixed. The full rebuild that shipped ADR-0022 flushed
  the accumulated backlog once, so the count is currently correct and climbing again.
- Severity: low now, and it degrades rather than breaks.

## What happens

Every `Draft Board ▸ Rebuild & re-sort` appends the Draft Board's entire conditional-format
rule list again, without removing the previous copy. Roughly 30 rules a run.

`clearConditionalFormatRules()` appears exactly once in `Build.gs`:

```js
// Build.gs:314, inside sheetByName
sh.clearConditionalFormatRules();
```

`rebuildAndResort` never reaches it — it passes the **live** sheet straight through:

```js
// Build.gs:2461
function rebuildAndResort() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Re-sort', function () {
    var sel = selectedSort(ss);
    buildDraftTab(ss, ss.getSheetByName('Draft Board'), ss.getSheetByName('Board'));
    ...
```

and `addRule` reads the existing list and pushes onto it:

```js
// Build.gs:343
function addRule(sh, rule) {
  var rules = sh.getConditionalFormatRules();
  rules.push(rule);
  sh.setConditionalFormatRules(rules);
}
```

So `formatDraftTab`'s rules accumulate. `Full rebuild` and `Step 4` both go through
`sheetByName` and clear first; only the re-sort path does not — and the re-sort is the one
you run repeatedly, including on draft night.

## Why it matters, and why it is not urgent

Duplicate rules are idempotent in appearance: the second copy of a rule paints the same
cells the same colour, so nothing looks wrong. The costs are that the sheet gets slower to
recalculate as the list grows, Sheets has a per-sheet rule cap that a long draft season of
re-sorts could approach, and the Conditional format side panel becomes unreadable if you
ever need to debug a rule by hand.

It also quietly hid a second problem. When `INJ` changed meaning from a current status
(`OUT` / `GTD`) to a durability tier (ADR-0022), the old rules could not be removed by a
re-sort — a re-sort would have *appended* the new `HIGH` / `MED` / `LOW` rules on top of the
stale pair and kept both forever. That is what forced a `Full rebuild` to deploy ADR-0022,
which is a much more expensive operation because it wipes the Board's hand-edited columns.

## The fix

One line, in `formatDraftTab`, before its first `addRule`:

```js
sh.clearConditionalFormatRules();
```

Deliberately not done in the ADR-0022 commit, to keep that change reviewable. It needs its
own commit and its own in-sheet verification, because it changes what `Rebuild & re-sort`
does to a live board — and the harness cannot prove it, since the harness never evaluates a
conditional format, only records that one was registered.

Check before and after in the sheet with `Format ▸ Conditional formatting` on the Draft
Board, counting the rules in the side panel.

## Related

- [ADR-0022](../decisions/ADR-0022-injury-risk-pipeline-column.md) — the change that
  surfaced this.
- `AGENTS.md`: "DO NOT trust the harness to prove a formula works." The same applies to a
  conditional format; the harness compares registrations, never renders.
