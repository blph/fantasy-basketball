"""Resolve a typed player name to one row of the local board.

A name typed on draft day is spelt the way Yahoo spells it, not the way Hashtag does, and
it is typed in a hurry. Resolution therefore runs in a fixed order and stops at the first
step that yields exactly one player:

    1. `sources.normalise` -- the very key the board was joined on, `sources.ALIASES` included
    2. `YAHOO_ALIASES`     -- Yahoo's spelling, where it differs from the provider's
    3. `--team`            -- breaks a tie between two candidates, in either team spelling
    4. partial match       -- READS ONLY: a unique substring of a board key

Writes stop after step 3. A write that lands on the wrong player ticks GONE on someone
still available, and the board then hides him for the rest of the draft; a read that lands
on the wrong player prints a row the reader can see is wrong. That asymmetry is the whole
reason reads and writes resolve differently.
"""

from __future__ import annotations

import difflib

import export_yahoo_rankings as EY
import sources as S

#: Yahoo's normalised spelling -> the normalised board key, for players Yahoo names
#: differently from Hashtag. Empty until a draft proves an entry is needed: every entry is
#: an assertion that two spellings are one person, and a stale one can start matching the
#: wrong player. Keys and values are both `sources.normalise` output.
YAHOO_ALIASES: dict[str, str] = {}

#: Yahoo's team code -> the provider's, the reverse of the exporter's fixups, so `--team`
#: accepts either spelling. Snapshot teams are always the provider's.
YAHOO_TO_PROVIDER = {yahoo: provider for provider, yahoo in EY.TEAM_FIXUPS.items()}


class ResolveError(Exception):
    """A name matched no player, or more than one. The CLI exits 3."""

    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.suggestions = list(suggestions or [])


def key_of(name: str) -> str:
    """The board key a typed name stands for: normalised, then Yahoo-aliased."""
    key = S.normalise(name)
    return YAHOO_ALIASES.get(key, key)


def provider_team(team: str) -> str:
    """A team code in the provider's spelling, whichever spelling was typed."""
    code = team.strip().upper()
    return YAHOO_TO_PROVIDER.get(code, code)


def _label(player: dict) -> str:
    return f"{player['name']} ({player['team']})"


def _exact(snapshot: dict, name: str) -> list[dict]:
    """Players whose key is the typed name's own key or its Yahoo alias.

    Both, not the alias alone: when Yahoo's spelling of one player is the provider's
    spelling of another, both are genuine candidates and only `--team` can choose.
    """
    key = S.normalise(name)
    wanted = {key, YAHOO_ALIASES.get(key, key)}
    return [p for p in snapshot["players"] if p["key"] in wanted]


def on_board(snapshot: dict, name: str) -> bool:
    """Whether a name matches a board key exactly, before any tie-break."""
    return bool(_exact(snapshot, name))


def suggestions(snapshot: dict, name: str, limit: int = 5) -> list[str]:
    """Up to `limit` board players whose key is close to the typed name's, closest first."""
    by_key = {p["key"]: p for p in snapshot["players"]}
    close = difflib.get_close_matches(S.normalise(name), list(by_key), n=limit, cutoff=0.6)
    return [_label(by_key[k]) for k in close]


def near_match(snapshot: dict, name: str, threshold: float = 0.8) -> bool:
    """Whether a name is close enough to a board player that it is probably a misspelling.

    A substring counts as near too. A surname typed alone scores well under 0.8 against the
    full key, and filing it off-board would lose a board player exactly as a typo would.
    """
    key = S.normalise(name)
    if not key:
        return False
    for p in snapshot["players"]:
        if key in p["key"]:
            return True
        if difflib.SequenceMatcher(None, key, p["key"]).ratio() >= threshold:
            return True
    return False


def resolve(snapshot: dict, name: str, *, write: bool, team: str | None = None) -> dict:
    """The one snapshot player a typed name means, or `ResolveError`.

    Reads fall back to a unique partial match; writes accept only an exact key or alias.
    """
    key = S.normalise(name)
    if not key:
        raise ResolveError(f"'{name}': no letters to match on")
    candidates = _exact(snapshot, name)
    partial = False
    if not candidates and not write:
        candidates = [p for p in snapshot["players"] if key in p["key"]]
        partial = True
    if team and candidates:
        code = provider_team(team)
        narrowed = [p for p in candidates if p["team"].upper() == code]
        if not narrowed:
            raise ResolveError(f"'{name}': no candidate plays for {team}",
                               [_label(p) for p in candidates])
        candidates = narrowed
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        how = "partially matches" if partial else "matches"
        raise ResolveError(f"'{name}' {how} {len(candidates)} players; add --team",
                           [_label(p) for p in candidates])
    if write:
        raise ResolveError(f"'{name}' is not an exact board name (writes never guess)",
                           suggestions(snapshot, name))
    raise ResolveError(f"'{name}' is not on the board", suggestions(snapshot, name))
