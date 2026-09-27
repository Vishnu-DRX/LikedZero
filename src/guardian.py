"""Liked-songs vanished-song guardian (decision 16).

Spotify has been observed silently dropping liked songs for this user. Every run snapshots the
full Liked Songs library (uri -> name/artists/added_at) to a local, git-ignored cache file (the
GitHub Actions workflow persists it across runs via ``actions/cache``, never commits it). On the
next run, any uri present in the previous snapshot but missing now -- and not removed by this run's
own moves -- is reported as "vanished" so it shows up in the run log and the dashboard's Safety view.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import artifacts
from .models import Track

DEFAULT_PATH = Path(".cache/liked-snapshot.json")


def load_snapshot(path: str | Path) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    tracks = raw.get("tracks") if isinstance(raw, dict) else None
    return tracks if isinstance(tracks, dict) else {}


def save_snapshot(path: str | Path, tracks: list[Track]) -> None:
    data = {
        "version": 1,
        "tracks": {
            t.uri: {
                "name": t.name,
                "artists": [a.name for a in t.artists],
                "added_at": artifacts.iso(t.added_at),
            }
            for t in tracks
        },
    }
    artifacts.atomic_write_json(path, data)


def find_vanished(
    previous: dict[str, dict[str, Any]], current_uris: set[str], removed_by_tool: set[str],
) -> list[dict[str, Any]]:
    """Uris the previous snapshot had, that are gone now, and that this run did not itself remove."""
    out = [
        {"uri": uri, **info}
        for uri, info in previous.items()
        if uri not in current_uris and uri not in removed_by_tool
    ]
    out.sort(key=lambda e: e.get("added_at") or "")
    return out
