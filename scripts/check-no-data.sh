#!/usr/bin/env bash
#
# Blocks provider data and credentials from entering this public repository.
#
#   --staged    what a commit is about to add   (used by .githooks/pre-commit)
#   --tracked   what is already committed       (used by CI)
#
# Why: FantasyPros' Premium tier is licensed for personal, non-commercial use and
# Yahoo's API has its own terms. Neither permits republishing their data, and a
# public repo is republishing. See "Data and API access" in README.md and
# docs/decisions/ADR-0006-no-provider-data-redistribution.md.

set -euo pipefail

MODE="${1:---staged}"

case "$MODE" in
  --staged)  FILES=$(git diff --cached --name-only --diff-filter=ACMR) ;;
  --tracked) FILES=$(git ls-files) ;;
  *) echo "usage: $0 [--staged|--tracked]" >&2; exit 2 ;;
esac

[ -n "$FILES" ] || exit 0

FAILED=0

# --- 1. Forbidden paths -----------------------------------------------------
# Anything under data/ except its README, any real .env, and any database or
# tabular export. These are generated locally and rebuildable from the API.
#
# The draft board's local copy is provider data under its own names, blocked
# wherever the file lands rather than only under data/, because a copy dragged
# into docs/ or tests/ is still the same file: Data.gs is the sheet's generated
# input (and its write_atomic temp, e.g. `.Data.gs.<random>.tmp`, in case a hard
# kill lands between the temp write and the rename), `board - <date>.json` the
# local snapshot, draft-state*.json the live draft and its lock, *.bak.json the
# backups board.py writes before it replaces a state, and a pull filename
# (`<timestamp> live.json` / `<timestamp> copy.json`, pull_sheet.py's format)
# the sheet as read back by Playwright.
BOARD_RE='(^|/)\.?Data\.gs(\.[^/]*\.tmp)?$|(^|/)board - [^/]*\.json$|(^|/)draft-state[^/]*\.json(\.lock)?$|\.bak\.json$|(^|/)[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z (live|copy)\.json$'

BAD_PATHS=$(printf '%s\n' "$FILES" | grep -Ev '^data/README\.md$|^\.env\.example$' |
  grep -E -e '^data/|(^|/)\.env($|\.)|\.(duckdb|duckdb\.wal|parquet|csv|tsv)$' -e "$BOARD_RE" || true)

if [ -n "$BAD_PATHS" ]; then
  echo "BLOCKED: provider data or local database files must not be committed."
  printf '%s\n' "$BAD_PATHS" | sed 's/^/  /'
  FAILED=1
fi

# --- 2. Credential-shaped content -------------------------------------------
# A named secret assigned a non-empty value, or an x-api-key header carrying
# something other than a placeholder. Empty assignments in .env.example, a
# `<placeholder>` value, a name quoted in backticks as `NAME=`, and the literal
# `x-api-key: <key>` in the docs are intentionally not matches.
SECRET_RE='(FANTASYPROS_API_KEY|YAHOO_CLIENT_ID|YAHOO_CLIENT_SECRET|YAHOO_REFRESH_TOKEN|DRAFT_SHEET_ID)[[:space:]]*[=:][[:space:]]*[^[:space:]"'"'"'`<]|x-api-key[[:space:]]*:[[:space:]]*[A-Za-z0-9]'

# The draft sheet's id inside a Google Sheets URL. Not a credential -- the sheet
# is private and the id opens nothing on its own -- but it names the owner's
# Drive file, and nothing committed needs it: scripts read DRAFT_SHEET_ID from
# .env and docs write <SHEET_ID>, which this does not match. Only line numbers
# are printed, so the id is not repeated into a CI log.
SHEET_RE='spreadsheets/d/[A-Za-z0-9_-]{30,}'

while IFS= read -r file; do
  [ -f "$file" ] || continue
  [ "$file" = "scripts/check-no-data.sh" ] && continue   # this file names the patterns
  if MATCH=$(grep -nEI "$SECRET_RE" "$file" 2>/dev/null); then
    echo "BLOCKED: $file looks like it carries a credential."
    printf '%s\n' "$MATCH" | sed 's/^/  /'
    FAILED=1
  fi
  if LINES=$(grep -nEI "$SHEET_RE" "$file" 2>/dev/null | cut -d: -f1 | tr '\n' ' '); [ -n "$LINES" ]; then
    echo "BLOCKED: $file carries a Google Sheets id (line $LINES). Write <SHEET_ID>; the real one lives in .env."
    FAILED=1
  fi
done <<< "$FILES"

if [ "$FAILED" -ne 0 ]; then
  cat <<'EOF'

Nothing under data/, no local draft-board file, no real key and no sheet id
belongs in this repository. If a key ever reaches a public commit it is
compromised on arrival: rotate it, do not revert.
Policy: README.md, "Data and API access".
EOF
  exit 1
fi

exit 0
