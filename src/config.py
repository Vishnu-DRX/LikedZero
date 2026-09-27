"""Load and validate config.yaml (schema: IMPLEMENTATION_PLAN.md §6 plus `language_in`)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from .enrichment.languages import CANONICAL, normalize_language
from .models import Config, Rule

TOP_LEVEL_KEYS = {
    "default_days_threshold",
    "fallback_playlist",
    "rules",
    "language_playlists",
    "enrichment",
    "logging",
    "inbox_since",
    "artist_in_playlist",
}
ENRICHMENT_KEYS = {"musicbrainz", "english_default"}
LOGGING_KEYS = {"include_track_names"}
ARTIST_IN_PLAYLIST_KEYS = {"min_tracks", "min_dominance", "exclude_playlists"}
RULE_KEYS = {
    "name",
    "enabled",
    "match",
    "target_playlist",
    "days_threshold",
    "create_missing_playlists",
    "target_position",
}
AUTO_TARGET = "auto"  # design/proposals/artist_in_playlist.md: sentinel, valid only with match.artist_in_playlist
LIST_MATCH_KEYS = {"artist_in", "genre_contains", "language_in"}
INT_MATCH_KEYS = {"release_year_before", "release_year_after"}
STR_MATCH_KEYS = {"track_name_contains", "album_name_contains"}
BOOL_MATCH_KEYS = {"explicit"}
TRUE_ONLY_MATCH_KEYS = {"artist_in_playlist"}  # no defined meaning for `false`; only `true` is a valid gate
MATCH_KEYS = LIST_MATCH_KEYS | INT_MATCH_KEYS | STR_MATCH_KEYS | BOOL_MATCH_KEYS | TRUE_ONLY_MATCH_KEYS


class ConfigError(ValueError):
    """Raised with every validation problem found, each naming the rule."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("invalid config:\n  - " + "\n  - ".join(self.errors))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _validate_match(match: Any, where: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(match, dict) or not match:
        errors.append(f"{where}: 'match' must be a non-empty mapping")
        return {}
    clean: dict[str, Any] = {}
    for key, value in match.items():
        if key not in MATCH_KEYS:
            errors.append(f"{where}: unknown match key '{key}'")
        elif key in LIST_MATCH_KEYS:
            if (
                not isinstance(value, list)
                or not value
                or not all(_nonempty_str(v) for v in value)
            ):
                errors.append(f"{where}: '{key}' must be a non-empty list of non-empty strings")
            elif key == "language_in":
                langs = [normalize_language(v) for v in value]
                unknown = [v for v, n in zip(value, langs) if n is None]
                if unknown:
                    errors.append(f"{where}: unknown language {unknown[0]!r} in 'language_in' (e.g. {', '.join(CANONICAL[:6])}, or an ISO code)")
                else:
                    clean[key] = langs
            else:
                clean[key] = list(value)
        elif key in INT_MATCH_KEYS:
            if not _is_int(value) or not 1 <= value <= 9999:
                errors.append(f"{where}: '{key}' must be a year (integer 1-9999)")
            else:
                clean[key] = value
        elif key in STR_MATCH_KEYS:
            if not _nonempty_str(value):
                errors.append(f"{where}: '{key}' must be a non-empty string")
            else:
                clean[key] = value
        elif key in TRUE_ONLY_MATCH_KEYS:
            if value is not True:
                errors.append(f"{where}: '{key}' must be true (there is no defined meaning for false)")
            else:
                clean[key] = True
        elif not isinstance(value, bool):
            errors.append(f"{where}: '{key}' must be true or false")
        else:
            clean[key] = value
    return clean


def _validate_rule(raw: Any, index: int, errors: list[str]) -> Rule | None:
    if not isinstance(raw, dict):
        errors.append(f"rules[{index}]: must be a mapping")
        return None
    name = raw.get("name")
    where = f"rules[{index}] ({name!r})" if _nonempty_str(name) else f"rules[{index}]"
    before = len(errors)

    if not _nonempty_str(name):
        errors.append(f"{where}: 'name' is required and must be a non-empty string")
    for key in raw:
        if key not in RULE_KEYS:
            errors.append(f"{where}: unknown key '{key}'")
    target = raw.get("target_playlist")
    if not _nonempty_str(target):
        errors.append(f"{where}: 'target_playlist' is required and must be a non-empty string")
    is_auto_target = _nonempty_str(target) and target.strip().casefold() == AUTO_TARGET
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        errors.append(f"{where}: 'enabled' must be true or false")
    create = raw.get("create_missing_playlists", False)
    if not isinstance(create, bool):
        errors.append(f"{where}: 'create_missing_playlists' must be true or false")
    position = raw.get("target_position", "bottom")
    if position not in ("top", "bottom"):
        errors.append(f"{where}: 'target_position' must be 'top' or 'bottom'")
    days = raw.get("days_threshold")
    if days is not None and (not _is_int(days) or days < 0):
        errors.append(f"{where}: 'days_threshold' must be an integer >= 0")
    match = _validate_match(raw.get("match"), where, errors)
    uses_auto_artist = "artist_in_playlist" in match
    if is_auto_target and not uses_auto_artist:
        errors.append(f"{where}: target_playlist '{AUTO_TARGET}' is only valid with match: {{artist_in_playlist: true}}")
    if uses_auto_artist and not is_auto_target:
        errors.append(f"{where}: match 'artist_in_playlist' requires target_playlist: {AUTO_TARGET}")

    if len(errors) > before:
        return None
    return Rule(
        name=name,
        target_playlist=AUTO_TARGET if is_auto_target else target,
        match=match,
        enabled=enabled,
        days_threshold=days,
        create_missing_playlists=create,
        target_position=position,
    )


def parse_config(data: Any) -> Config:
    """Validate an already-parsed YAML document. Raises ConfigError listing all problems."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(["top level must be a mapping"])
    errors: list[str] = []
    for key in data:
        if key not in TOP_LEVEL_KEYS:
            errors.append(f"unknown top-level key '{key}'")

    default_days = data.get("default_days_threshold", 14)
    if not _is_int(default_days) or default_days < 0:
        errors.append("'default_days_threshold' must be an integer >= 0")
    fallback = data.get("fallback_playlist")
    if fallback is not None and not _nonempty_str(fallback):
        errors.append("'fallback_playlist' must be a playlist name or null")

    inbox_since: date | None = None
    raw_since = data.get("inbox_since")
    if raw_since is not None:
        if isinstance(raw_since, datetime):
            inbox_since = raw_since.date()
        elif isinstance(raw_since, date):
            inbox_since = raw_since
        elif isinstance(raw_since, str):
            try:
                inbox_since = date.fromisoformat(raw_since.strip())
            except ValueError:
                errors.append("'inbox_since' must be a date (YYYY-MM-DD) or null")
        else:
            errors.append("'inbox_since' must be a date (YYYY-MM-DD) or null")

    lang_playlists: dict[str, str] = {}
    raw_lp = data.get("language_playlists", {})
    if raw_lp is None:
        raw_lp = {}
    if not isinstance(raw_lp, dict):
        errors.append("'language_playlists' must be a mapping of playlist name -> language")
    else:
        for name, lang in raw_lp.items():
            canon = normalize_language(lang)
            if not _nonempty_str(name):
                errors.append("'language_playlists': playlist names must be non-empty strings")
            elif canon is None:
                errors.append(f"'language_playlists' ({name!r}): unknown language {lang!r}")
            else:
                lang_playlists[name] = canon

    musicbrainz = True
    english_default = False
    raw_enrich = data.get("enrichment", {})
    if raw_enrich is None:
        raw_enrich = {}
    if not isinstance(raw_enrich, dict):
        errors.append("'enrichment' must be a mapping")
    else:
        for key in raw_enrich:
            if key not in ENRICHMENT_KEYS:
                errors.append(f"unknown key 'enrichment.{key}'")
        if "musicbrainz" in raw_enrich:
            if not isinstance(raw_enrich["musicbrainz"], bool):
                errors.append("'enrichment.musicbrainz' must be true or false")
            else:
                musicbrainz = raw_enrich["musicbrainz"]
        if "english_default" in raw_enrich:
            if not isinstance(raw_enrich["english_default"], bool):
                errors.append("'enrichment.english_default' must be true or false")
            else:
                english_default = raw_enrich["english_default"]

    include_names = False
    raw_logging = data.get("logging", {})
    if raw_logging is None:
        raw_logging = {}
    if not isinstance(raw_logging, dict):
        errors.append("'logging' must be a mapping")
    else:
        for key in raw_logging:
            if key not in LOGGING_KEYS:
                errors.append(f"unknown key 'logging.{key}'")
        if "include_track_names" in raw_logging:
            if not isinstance(raw_logging["include_track_names"], bool):
                errors.append("'logging.include_track_names' must be true or false")
            else:
                include_names = raw_logging["include_track_names"]

    ai_min_tracks = 3
    ai_min_dominance = 0.9
    ai_exclude: list[str] = []
    raw_ai = data.get("artist_in_playlist", {})
    if raw_ai is None:
        raw_ai = {}
    if not isinstance(raw_ai, dict):
        errors.append("'artist_in_playlist' must be a mapping")
    else:
        for key in raw_ai:
            if key not in ARTIST_IN_PLAYLIST_KEYS:
                errors.append(f"unknown key 'artist_in_playlist.{key}'")
        if "min_tracks" in raw_ai:
            v = raw_ai["min_tracks"]
            if not _is_int(v) or v < 1:
                errors.append("'artist_in_playlist.min_tracks' must be an integer >= 1")
            else:
                ai_min_tracks = v
        if "min_dominance" in raw_ai:
            v = raw_ai["min_dominance"]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 < v <= 1):
                errors.append("'artist_in_playlist.min_dominance' must be a number > 0 and <= 1")
            else:
                ai_min_dominance = float(v)
        if "exclude_playlists" in raw_ai:
            v = raw_ai["exclude_playlists"]
            if not isinstance(v, list) or not all(_nonempty_str(x) for x in v):
                errors.append("'artist_in_playlist.exclude_playlists' must be a list of non-empty strings")
            else:
                ai_exclude = list(v)
    # decision 54: Vault_drx must always be excluded, even if the user's own list omits it. Deliberately NOT
    # merged in here -- this field carries exactly what the user configured; the hardcoded exclusion is
    # enforced independently, at the point of use, in enrichment/artist_playlist.py's excluded_playlist_names()
    # (so it holds even if a caller builds a Config directly, bypassing this parser).

    raw_rules = data.get("rules", [])
    rules: list[Rule] = []
    if not isinstance(raw_rules, list):
        errors.append("'rules' must be a list")
    else:
        seen: set[str] = set()
        for i, raw in enumerate(raw_rules):
            rule = _validate_rule(raw, i, errors)
            if rule is None:
                continue
            folded = rule.name.casefold()
            if folded in seen:
                errors.append(f"rules[{i}] ({rule.name!r}): duplicate rule name")
            seen.add(folded)
            rules.append(rule)

    if errors:
        raise ConfigError(errors)
    return Config(
        default_days_threshold=default_days,
        fallback_playlist=fallback,
        rules=tuple(rules),
        language_playlists=lang_playlists,
        musicbrainz=musicbrainz,
        english_default=english_default,
        include_track_names=include_names,
        inbox_since=inbox_since,
        artist_in_playlist_min_tracks=ai_min_tracks,
        artist_in_playlist_min_dominance=ai_min_dominance,
        artist_in_playlist_exclude_playlists=tuple(ai_exclude),
    )


def load_config(path: str | Path = "config.yaml") -> Config:
    """Read, parse and validate a config file."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError([f"cannot read {path}: {exc.strerror or exc}"]) from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError([f"{path} is not valid YAML: {exc}"]) from exc
    return parse_config(data)
