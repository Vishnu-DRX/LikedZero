"""Pure rule-matching logic (no I/O). No popularity key: Spotify removed the field.

Semantics
- Rules are evaluated in file order; the first enabled rule that matches wins.
- All keys inside one rule's ``match`` are AND-combined.
- The age gate (``days_threshold``, else the default) is checked on the matched rule only: a too-young
  match leaves the song in Liked Songs and stops evaluation (it never falls through to later rules).
- A track with no ``added_at`` never satisfies an age gate (conservative: never moved).
- Genre/language conditions are simply false when enrichment is missing or empty.
- ``release_year_before`` is strict (year < N); ``release_year_after`` is strict (year > N).
- ``unless`` (design/proposals/more-conditions.md): an optional per-rule exception block, same match-key
  vocabulary as ``match``, AND-combined among itself. When a rule's ``match`` passes AND its ``unless`` also
  fully passes, the rule is blocked -- treated exactly like a non-match, so evaluation simply continues to the
  next rule (this is *not* the age-gate's hard stop; an exception decides whether the rule wins at all).
- ``any_of`` (design/proposals/more-conditions.md): a match key whose value is a list of match-condition
  groups (dicts, same vocabulary); the whole key passes if ANY group's conditions all pass, and is then
  AND-combined with the rest of the rule's ``match`` like any other key.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Sequence

from .models import Enrichment, Match, Rule, Track

DEFAULT_DAYS_THRESHOLD = 14
_YEAR_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")


def release_year(release_date: str | None, precision: str | None = None) -> int | None:
    """Year from a Spotify ``release_date`` at ``year``, ``month`` or ``day`` precision.

    Returns None when the string is missing or malformed. The string shape decides;
    ``precision`` is accepted for interface symmetry with the API and only used to
    reject a value that is shorter than its declared precision.
    """
    if not release_date:
        return None
    m = _YEAR_RE.match(release_date.strip())
    if not m:
        return None
    parts = sum(1 for g in m.groups() if g)
    needed = {"year": 1, "month": 2, "day": 3}.get(precision or "", 1)
    if parts < needed:
        return None
    return int(m.group(1))


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_days(track: Track, now: datetime) -> float | None:
    """Days since the track was liked; naive datetimes are treated as UTC."""
    if track.added_at is None:
        return None
    return (_aware(now) - _aware(track.added_at)).total_seconds() / 86400


def resolve_days_threshold(rule: Rule, default_days_threshold: int) -> int:
    return rule.days_threshold if rule.days_threshold is not None else default_days_threshold


def _fold(value: str) -> str:
    return value.strip().casefold()


def check_key(track: Track, enrichment: Enrichment | None, key: str, wanted: Any) -> tuple[bool, Any, Any]:
    """Evaluate one match key. Returns (passed, actual_value_seen, what_matched)."""
    if key == "artist_in":
        names = {_fold(a.name) for a in track.artists}
        hits = [w for w in wanted if _fold(w) in names]
        return bool(hits), [a.name for a in track.artists], hits[0] if hits else None
    if key == "genre_contains":
        genres = list(enrichment.genres) if enrichment else []
        folded = [_fold(g) for g in genres]
        hit = next((w for w in wanted if _fold(w) and any(_fold(w) in g for g in folded)), None)
        return hit is not None, genres, hit
    if key == "language_in":
        lang = enrichment.language if enrichment else None
        ok = bool(lang) and _fold(lang) in {_fold(w) for w in wanted}
        return ok, lang, lang if ok else None
    if key in ("release_year_before", "release_year_after"):
        year = release_year(track.release_date, track.release_date_precision)
        if year is None:
            return False, None, None
        ok = year < wanted if key == "release_year_before" else year > wanted
        return ok, year, year if ok else None
    if key == "explicit":
        ok = bool(track.explicit) is wanted
        return ok, bool(track.explicit), wanted if ok else None
    if key == "track_name_contains":
        ok = bool(wanted.strip()) and _fold(wanted) in _fold(track.name)
        return ok, track.name, wanted if ok else None
    if key == "album_name_contains":
        ok = bool(wanted.strip()) and _fold(wanted) in _fold(track.album_name)
        return ok, track.album_name, wanted if ok else None
    if key == "any":
        return True, True, True  # decision 51: the real catch-all -- matches unconditionally
    if key == "artist_in_playlist":
        home = enrichment.artist_home_playlist if enrichment else None
        if home is None:
            return False, None, None
        actual = {"playlist": home, "artist_tracks": enrichment.artist_home_track_count, "artist_total": enrichment.artist_home_total}
        return True, actual, home
    if key == "artist_country_in":
        # design/proposals/more-conditions.md: exact field lookup (MusicBrainz/ISRC country), not an inferred
        # signal -- informational, not gated behind a precision bar the way language_in's weak sources are.
        country = enrichment.artist_country if enrichment else None
        ok = bool(country) and country.upper() in {w.upper() for w in wanted}
        return ok, country, country if ok else None
    if key == "any_of":
        # design/proposals/more-conditions.md: OR-groups. `wanted` is a list of match-condition groups (dicts),
        # each AND-combined internally; the whole thing passes if ANY group passes. `actual` reports every
        # group's own pass/fail + what matched inside it, so the explain trace can show which branch won --
        # not just the winner is returned, all branches are, for full visibility.
        branches: list[dict[str, Any]] = []
        matched_index: int | None = None
        for i, group in enumerate(wanted):
            g_ok, g_hits = _eval_group(track, enrichment, group)
            branches.append({"branch": i, "passed": g_ok, "matched": g_hits})
            if g_ok and matched_index is None:
                matched_index = i
        return matched_index is not None, branches, matched_index
    return False, None, None  # unknown key: never silently ignore a condition


def _eval_group(track: Track, enrichment: Enrichment | None, group: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """AND-combined conditions within one ``any_of`` branch. Returns (passed, {key: hit})."""
    hits: dict[str, Any] = {}
    for key, wanted in group.items():
        ok, _, hit = check_key(track, enrichment, key, wanted)
        if not ok:
            return False, {}
        hits[key] = hit
    return True, hits


def _match_keys(
    track: Track, enrichment: Enrichment | None, match: dict[str, Any]
) -> dict[str, Any] | None:
    """Return {key: what matched} if every key is satisfied, else None."""
    matched: dict[str, Any] = {}
    for key, wanted in match.items():
        ok, _, hit = check_key(track, enrichment, key, wanted)
        if not ok:
            return None
        matched[key] = hit
    return matched


def _blocked_by(track: Track, enrichment: Enrichment | None, unless: dict[str, Any]) -> dict[str, Any] | None:
    """{key: hit} if every ``unless`` condition is satisfied (the rule is blocked), else None.

    design/proposals/more-conditions.md: a blocked rule is treated exactly like a non-match -- evaluation
    falls through to the next rule, it does not hard-stop the way a too-young age gate does (decision 2's
    "blocks, does not fall through" is specifically about the *age gate* on the rule that already won; an
    `unless` exception decides whether this rule wins at all, which is a condition-matching question, not an
    age-gate question -- the natural reading of "broad rule, unless X" is "then try the next rule").
    """
    if not unless:
        return None
    ok, hits = _eval_group(track, enrichment, unless)
    return hits if ok else None


_HIT_DESCRIBERS = {
    "artist_in": lambda h: f"artist_in matched {h}",
    "genre_contains": lambda h: f"genre_contains matched {h!r}",
    "language_in": lambda h: f"language_in matched {h}",
    "release_year_before": lambda h: f"release_year_before matched {h}",
    "release_year_after": lambda h: f"release_year_after matched {h}",
    "explicit": lambda h: f"explicit matched {h}",
    "track_name_contains": lambda h: f"track_name_contains matched {h!r}",
    "album_name_contains": lambda h: f"album_name_contains matched {h!r}",
    "any": lambda h: "any (always true)",
    "artist_in_playlist": lambda h: f"artist_in_playlist matched (home: {h['playlist'] if isinstance(h, dict) else h})",
    "artist_country_in": lambda h: f"artist_country_in matched {h}",
    "any_of": lambda h: f"any_of matched branch {h}",
}


def _describe_hit(key: str, hit: Any) -> str:
    fn = _HIT_DESCRIBERS.get(key)
    return fn(hit) if fn else f"{key} matched"


def _describe_block(unless_conditions: list[dict[str, Any]]) -> str:
    parts = [_describe_hit(c["key"], c.get("hit")) for c in unless_conditions]
    return "blocked by exception: " + " and ".join(parts)


def explain(
    track: Track,
    enrichment: Enrichment | None,
    rules: Sequence[Rule],
    now: datetime,
    default_days_threshold: int = DEFAULT_DAYS_THRESHOLD,
) -> dict[str, Any]:
    """Rule-by-rule trace, in order, for one track (the dashboard's Explain drawer).

    Every rule's conditions are evaluated (so the dashboard can show shadowed rules), but ``stopped_here`` marks the
    rule that actually decided the song: the first enabled rule whose conditions pass. Later rules are 'not_reached'.
    """
    age = age_days(track, now)
    trace: list[dict[str, Any]] = []
    decided: str | None = None
    for rule in rules:
        threshold = resolve_days_threshold(rule, default_days_threshold)
        entry: dict[str, Any] = {"rule": rule.name, "enabled": rule.enabled, "threshold_days": threshold, "conditions": []}
        if not rule.enabled or not rule.match:
            entry["result"] = "skipped_disabled" if not rule.enabled else "skipped_empty"
            trace.append(entry)
            continue
        all_ok = True
        for key, wanted in rule.match.items():
            ok, actual, _ = check_key(track, enrichment, key, wanted)
            entry["conditions"].append({"key": key, "wanted": wanted, "actual": actual, "passed": ok})
            all_ok = all_ok and ok

        # design/proposals/more-conditions.md (unless): only relevant when the rule's own match already passed.
        # A blocked rule is reported distinctly (not just "failed"/"not_reached") so the dashboard can say *why*.
        blocked_desc = None
        if all_ok and rule.unless:
            entry["unless_conditions"] = []
            unless_ok = True
            for key, wanted in rule.unless.items():
                ok, actual, hit = check_key(track, enrichment, key, wanted)
                entry["unless_conditions"].append({"key": key, "wanted": wanted, "actual": actual, "passed": ok, "hit": hit})
                unless_ok = unless_ok and ok
            if unless_ok:
                blocked_desc = _describe_block(entry["unless_conditions"])

        if blocked_desc:
            entry["result"] = "blocked_by_exception"
            entry["blocked_reason"] = blocked_desc
        elif decided is not None:
            entry["result"] = "not_reached_but_would_match" if all_ok else "not_reached"
        elif all_ok:
            decided = rule.name
            aged = age is not None and age >= threshold
            entry["result"] = "matched" if aged else "matched_too_young"
        else:
            entry["result"] = "failed"
        trace.append(entry)
    return {"trace": trace, "decided_by": decided, "age_days": age}


def first_match(
    track: Track,
    enrichment: Enrichment | None,
    rules: Sequence[Rule],
    now: datetime,
    default_days_threshold: int = DEFAULT_DAYS_THRESHOLD,
) -> Match | None:
    """First enabled rule whose *conditions* match, with ``aged`` saying whether its age gate is met.

    Conditions are matched first-match-wins; the age gate is checked only on that rule, so a too-young
    match stops evaluation instead of leaking into a later, broader rule (master decision 2).
    """
    age = age_days(track, now)
    for rule in rules:
        if not rule.enabled or not rule.match:
            continue
        matched = _match_keys(track, enrichment, rule.match)
        if matched is None:
            continue
        if rule.unless and _blocked_by(track, enrichment, rule.unless) is not None:
            continue  # design/proposals/more-conditions.md: blocked == not matched, fall through
        threshold = resolve_days_threshold(rule, default_days_threshold)
        aged = age is not None and age >= threshold
        return Match(rule=rule, matched=matched, age_days=age, threshold=threshold, aged=aged)
    return None


def evaluate(
    track: Track,
    enrichment: Enrichment | None,
    rules: Sequence[Rule],
    now: datetime,
    default_days_threshold: int = DEFAULT_DAYS_THRESHOLD,
) -> Match | None:
    """The rule to act on now, or None (no match, or matched but not old enough yet)."""
    match = first_match(track, enrichment, rules, now, default_days_threshold)
    return match if match is not None and match.aged else None
