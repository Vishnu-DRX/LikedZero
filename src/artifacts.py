"""Machine-readable run artifacts for the dashboard (master decision 18).

Pure builders + tiny atomic writers. Files (all JSON, ``version: 1``):
  logs/latest-plan.json   inbox snapshot: every liked song, its decision, explain trace, signal tiers/confidence
  logs/runs.json          rolling index of the last 90 runs
  logs/YYYY-MM-DD.json    per-run log (written by sync.py, extended here via ``run_log_extras``)
See docs/dashboard/DATA.md for the field-by-field contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import AUTO_TARGET
from .models import Config, Enrichment, Playlist, Rule, Track
from .planner import decide, resolve_target
from .rules_engine import age_days, explain
from .signals import gate

VERSION = 1
TITLE_CONDITION_KEYS = {"artist_in", "track_name_contains", "album_name_contains"}
RUNS_KEPT = 90
WEAK_SOURCES = ("hint", "country_default")


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


def config_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def atomic_write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _rule_summary(rule: Rule, default_days: int) -> dict[str, Any]:
    weak = [f"language_in:{s}" for s in WEAK_SOURCES] if "language_in" in rule.match else []
    return {
        "name": rule.name,
        "enabled": rule.enabled,
        "target_playlist": rule.target_playlist,
        "target_position": rule.target_position,
        "threshold_days": rule.days_threshold if rule.days_threshold is not None else default_days,
        "conditions": rule.match,
        # design/proposals/more-conditions.md: exceptions shown separately from `conditions` (match) since they
        # have opposite polarity -- an empty mapping means "no exceptions", same convention as `match`'s dict.
        "unless": rule.unless,
        "uses_language": "language_in" in rule.match,
        "weak_signals_possible": weak,
    }


def _song(
    t: Track,
    raw: Enrichment | None,
    config: Config,
    now: datetime,
    playlists: Sequence[Playlist],
    precision: Mapping[str, Any] | None,
) -> dict[str, Any]:
    gated, blocked = gate(raw, precision)
    d = decide(t, gated, config, now)
    tr = explain(t, gated, config.rules, now, config.default_days_threshold)
    decision, reason = d.kind, ""
    target_status = None
    playlist: Playlist | None = None
    if d.kind == "move":
        playlist, problem, _ = resolve_target(d.target_name, playlists)
        if playlist is None:
            decision, target_status, reason = "target_problem", problem, f"target playlist {problem}"
        else:
            decision, target_status = "will_move", "resolved"
            reason = f"rule '{d.rule_name}' matched and the song is old enough"
    elif d.kind == "too_young":
        decision = "too_young"
        reason = f"rule '{d.rule_name}' matched; eligible after {d.threshold} days (evaluation stops here)"
    else:
        decision, reason = "no_match", "no enabled rule matched"
        if blocked:  # would a rule have matched with the withheld language?
            d2 = decide(t, raw, config, now)
            if d2.kind in ("move", "too_young"):
                decision = "blocked"
                reason = (
                    f"rule '{d2.rule_name}' would match on {blocked['language']} ({blocked['source']}), "
                    f"but that signal is {blocked['reason'].replace('_', ' ')}"
                )
    rule = next((r for r in config.rules if r.name == d.rule_name), None)
    threshold = d.threshold
    eligible = t.added_at + timedelta(days=threshold) if (t.added_at and threshold is not None and d.kind != "no_match") else None
    return {
        "title": t.name,
        "artists": [a.name for a in t.artists],
        "uri": t.uri,
        "added_at": iso(t.added_at),
        "age_days": round(age_days(t, now), 1) if t.added_at else None,
        "decision": decision,
        "reason": reason,
        "rule": d.rule_name if d.kind != "no_match" else None,
        "target_playlist": (playlist.name if playlist else d.target_name) if d.kind != "no_match" else None,
        "target_status": target_status,
        "eligible_on": iso(eligible),
        "target_position": (rule.target_position if rule else "bottom") if d.kind != "no_match" else None,
        "language": {
            "value": raw.language if raw else None,
            "source": raw.language_source if raw else None,
            "confidence": raw.language_confidence if raw else None,
            "used_for_rules": bool(raw and raw.language and gated and gated.language),
            "withheld": blocked,
        },
        "genres": {
            "values": list(raw.genres) if raw else [],
            "source": raw.genre_source if raw else None,
            "confidence": raw.genre_confidence if raw else None,
        },
        "artist_routing": (
            {"playlist": raw.artist_home_playlist, "track_count": raw.artist_home_track_count, "artist_total": raw.artist_home_total}
            if raw and raw.artist_home_playlist else None
        ),
        "explain": tr,
    }


def build_latest_plan(
    tracks: Sequence[Track],
    enrichments: Mapping[str, Enrichment],
    config: Config,
    now: datetime,
    playlists: Sequence[Playlist],
    *,
    precision: Mapping[str, Any] | None = None,
    run_id: str = "",
    mode: str = "dry_run",
    what_if: bool = False,
    cfg_hash: str = "",
    inbox_kind: str = "legacy_library",
) -> dict[str, Any]:
    """Inbox snapshot. ``what_if`` treats every rule as enabled (preview of disabled drafts)."""
    if what_if:
        config = replace(config, rules=tuple(replace(r, enabled=True) for r in config.rules))
    songs = [_song(t, enrichments.get(t.id), config, now, playlists, precision) for t in tracks]
    songs.sort(key=lambda s: (s["added_at"] is None, s["added_at"] or ""))  # oldest first

    counts = {k: 0 for k in ("will_move", "too_young", "no_match", "target_problem", "blocked")}
    for s in songs:
        counts[s["decision"]] += 1

    rules_out = []
    for rule in config.rules:
        would = wins = 0
        for s in songs:
            for e in s["explain"]["trace"]:
                if e["rule"] != rule.name:
                    continue
                if e["result"] in ("matched", "matched_too_young"):
                    would += 1
                    wins += 1
                elif e["result"] == "not_reached_but_would_match":
                    would += 1
        info = _rule_summary(rule, config.default_days_threshold)
        if rule.target_playlist == AUTO_TARGET:
            # design/proposals/artist_in_playlist.md: the target is resolved per-song, not fixed -- there is
            # nothing here for resolve_target() to look up, and "missing" would misreport a working rule.
            target_status = "dynamic"
        else:
            pl, problem, _ = resolve_target(rule.target_playlist, playlists)
            target_status = "resolved" if pl else problem
        info.update({
            "would_match": would,
            "wins": wins,
            "target_status": target_status,
            "status": "disabled" if not rule.enabled else "dead" if would == 0 else "shadowed" if wins == 0 else "ok",
        })
        rules_out.append(info)

    planned_in: dict[str, int] = {}
    for s in songs:
        if s["decision"] == "will_move":
            planned_in[s["target_playlist"]] = planned_in.get(s["target_playlist"], 0) + 1
    playlists_out = []
    seen: set[str] = set()
    for rule in config.rules:
        # An "auto" rule has no single fixed target to report on here -- each song it moves already appears
        # under its own REAL resolved playlist name below, via whichever rule (if any) also names that
        # playlist literally; artist_in_playlist-only targets simply don't get a dedicated Playlists row.
        if rule.target_playlist == AUTO_TARGET:
            continue
        key = rule.target_playlist.casefold()
        if key in seen:
            continue
        seen.add(key)
        pl, problem, _ = resolve_target(rule.target_playlist, playlists)
        playlists_out.append({
            "name": rule.target_playlist,
            "status": "resolved" if pl else problem,
            "size": pl.items_total if pl else None,
            "planned_in": planned_in.get(pl.name if pl else rule.target_playlist, 0),
            "rules": [r.name for r in config.rules if r.target_playlist.casefold() == key],
        })

    return {
        "version": VERSION,
        "generated_at": iso(now),
        "run_id": run_id,
        "mode": mode,
        "what_if": what_if,
        "inbox_kind": inbox_kind,
        "config_hash": cfg_hash,
        "liked_total": len(tracks),
        "default_days_threshold": config.default_days_threshold,
        "english_default": config.english_default,
        "inbox_since": config.inbox_since.isoformat() if config.inbox_since else None,
        "counts": counts,
        "rules": rules_out,
        "playlists": playlists_out,
        "songs": songs,
    }


def run_entry(
    *, run_id: str, now: datetime, mode: str, plan_counts: Mapping[str, int], moved: int, errors: int, warnings: int,
    liked_before: int, liked_after: int, duration_s: float, rule_counts: Mapping[str, int], log_file: str, what_if: bool = False,
    reconcile_ok: bool | None = None, moves_by_playlist: Mapping[str, int] | None = None,
    aborted: str | None = None,
) -> dict[str, Any]:
    if aborted:
        verdict = aborted  # P1-3: an abort before any write must never be reported as "ok"
    elif reconcile_ok is False:
        verdict = "mismatch"
    elif errors:
        verdict = "error"
    elif mode == "dry_run":
        verdict = "dry_run"
    elif reconcile_ok is False or (reconcile_ok is None and liked_before - moved != liked_after):
        verdict = "mismatch"
    else:
        verdict = "ok"
    return {
        "run_id": run_id,
        "time": iso(now),
        "mode": mode,
        "what_if": what_if,
        "planned_moves": plan_counts.get("will_move", 0),
        "moved": moved,
        "too_young": plan_counts.get("too_young", 0),
        "no_match": plan_counts.get("no_match", 0),
        "blocked": plan_counts.get("blocked", 0),
        "target_problems": plan_counts.get("target_problem", 0),
        "errors": errors,
        "warnings": warnings,
        "liked_before": liked_before,
        "liked_after": liked_after,
        "duration_seconds": round(duration_s, 1),
        "verdict": verdict,
        "rule_counts": dict(rule_counts),
        "moves_by_playlist": dict(moves_by_playlist or {}),
        "log": log_file,
    }


def update_runs_index(path: str | Path, entry: dict[str, Any], now: datetime, schedule: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepend ``entry`` (newest first), keep the last 90, write atomically."""
    path = Path(path)
    runs: list[dict[str, Any]] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("runs"), list):
            runs = [r for r in raw["runs"] if isinstance(r, dict) and r.get("run_id") != entry["run_id"]]
    except (OSError, ValueError):
        pass
    runs.insert(0, entry)
    data = {"version": VERSION, "generated_at": iso(now), "schedule": schedule, "runs": runs[:RUNS_KEPT]}
    atomic_write_json(path, data)
    return data


# ---------------------------------------------------------------- privacy (decision 32) and schedule


def redact_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Copy of a latest-plan snapshot with every song-identifying field removed (counts, decisions and rules
    stay). P1-4 (2026-09-27 review): a bare ``spotify:track:`` URI resolves to a real song in one request
    (open.spotify.com/track/<id>), so hiding titles/artists alone did not make this private -- the uri must go
    too, and so must any other free-text match condition that could name the song."""
    out = json.loads(json.dumps(plan))
    out["titles_hidden"] = True
    for s in out.get("songs", []):
        s["title"], s["artists"], s["uri"] = None, [], None
        for entry in (s.get("explain") or {}).get("trace", []):
            for c in entry.get("conditions", []):
                if c.get("key") in TITLE_CONDITION_KEYS:
                    c["actual"] = None
    return out


def redact_log(log: dict[str, Any]) -> dict[str, Any]:
    """Copy of a run log with every song-identifying field removed, including the uri (see `redact_plan`) --
    this copy is what gets committed publicly. The real journal (needed for --restore) is preserved
    separately by `sync.run`'s private, git-ignored restore-journal file, never by this committed copy."""
    out = json.loads(json.dumps(log))
    out["titles_hidden"] = True
    for m in out.get("moved", []):
        m["track"], m["artist"], m["uri"] = None, None, None
    for key in ("skipped_too_young", "skipped_playlist_missing"):
        for row in out.get(key, []):
            row["track"] = None
            if "artist" in row:
                row["artist"] = None
    for j in out.get("journal", []):
        j["name"], j["artists"], j["uri"] = None, None, None
    if "moved_uris" in out:
        out["moved_uris"] = []
    if "still_liked" in out:
        out["still_liked"] = []
    return out


def restore_journal_payload(log: Mapping[str, Any]) -> dict[str, Any]:
    """The real (never redacted) journal of an apply run, shaped so the file itself is a valid `--restore`
    argument (`apply.load_journal` requires `mode: "apply"` and `dry_run: false`). P1-4 (2026-09-27 review):
    once `redact_log` also strips the uri from the committed public log, this is the only place --restore's
    real data survives -- written to a git-ignored local file and picked up by the workflow's own journal
    artifact upload, never committed."""
    return {
        "date": log.get("date"), "run_id": log.get("run_id"), "mode": log.get("mode"), "dry_run": False,
        "restore_command": log.get("restore_command"), "journal": log.get("journal", []),
    }


def schedule_info(cron: str | None, now: datetime) -> dict[str, Any] | None:
    """Describe a simple cron ('M H * * *' daily, or 'M H * * D' weekly) for the Overview; None = not scheduled."""
    if not cron or not cron.strip():
        return None
    parts = cron.split()
    if len(parts) != 5 or parts[2] != "*" or parts[3] != "*" or not (parts[0].isdigit() and parts[1].isdigit()):
        return {"cron": cron, "description": f"Scheduled ({cron})", "next_run": None}
    minute, hour = int(parts[0]), int(parts[1])
    dow = None if parts[4] == "*" else int(parts[4]) % 7 if parts[4].isdigit() else -1
    if dow == -1 or not (0 <= minute < 60 and 0 <= hour < 24):
        return {"cron": cron, "description": f"Scheduled ({cron})", "next_run": None}
    nxt = now.astimezone(timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    for _ in range(8):
        # cron day-of-week: 0 = Sunday; python weekday(): 0 = Monday
        if nxt > now and (dow is None or (nxt.weekday() + 1) % 7 == dow):
            break
        nxt += timedelta(days=1)
    when = f"{hour:02d}:{minute:02d} UTC"
    names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    return {"cron": cron, "description": f"Every day at {when}" if dow is None else f"Every {names[dow]} at {when}",
            "next_run": iso(nxt)}
