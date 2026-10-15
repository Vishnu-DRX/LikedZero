"""The shipped config.yaml: language and artist rules run first, and a freshly liked song nothing else claims goes to
the TOP of The Simulation Archives (the catch-all). Offline."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.config import load_config
from src.models import Playlist
from src.planner import build_plan, insert_batches
from tests.fakes import make_track


def _plan(added_days_ago: float, liked_on: datetime | None = None):
    config = load_config("config.yaml")
    now = datetime.now(timezone.utc)
    t = make_track(1, age_days=added_days_ago)
    t = t.__class__(**{**t.__dict__, "added_at": liked_on or now - timedelta(days=added_days_ago)})
    pl = [Playlist("SIM0000000000000000001", "The Simulation Archives", "me", True, False)]
    return config, build_plan([t], {}, config, now, pl)


def test_new_song_goes_to_top_of_simulation_archives():
    config, plan = _plan(0.01)
    enabled = [r.name for r in config.rules if r.enabled]
    assert enabled[-1] == "Catch-all -> The Simulation Archives"  # last, so it only catches what nothing else claimed
    assert "Hindi -> Dil" in enabled and "Queen -> Her Highness" in enabled
    assert "Route to artist's home playlist (draft)" not in enabled  # the auto-router stays off by decision
    assert config.musicbrainz and config.language_playlists["Dil"] == "hindi"
    assert len(plan.moves) == 1
    m = plan.moves[0]
    assert m["playlist"] == "The Simulation Archives" and m["target_position"] == "top"
    assert [b.position for b in insert_batches(plan.moves)] == [0]


def test_song_liked_before_inbox_since_is_never_planned():
    config = load_config("config.yaml")
    old = datetime.combine(config.inbox_since, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=1)
    _, plan = _plan(30, liked_on=old)
    assert plan.moves == []


def test_two_songs_keep_liked_songs_order_at_top_of_simulation_archives():
    """Liked Songs shows newest first: song-1 above song-2. After the real planner + apply, the top of the
    playlist is song-1, song-2, then whatever was already there (not reversed)."""
    from src.apply import apply_moves
    from tests.fakes import JournalRecorder, build_world

    now = datetime.now(timezone.utc)
    fs, (song1, song2) = build_world(2, ("SIM0000000000000000001",))
    song1 = replace(song1, added_at=now - timedelta(minutes=5))  # newest = top of Liked Songs
    song2 = replace(song2, added_at=now - timedelta(minutes=10))
    fs.set_liked([song1, song2])
    existing = [make_track(100 + i) for i in range(1, 4)]
    fs.add_playlist("SIM0000000000000000001", items=existing)
    config = load_config("config.yaml")
    pl = [Playlist("SIM0000000000000000001", "The Simulation Archives", "me", True, False)]
    plan = build_plan([song2, song1], {}, config, now, pl)  # input order must not matter
    res = apply_moves(fs, plan.moves, liked_uris_before=set(fs.liked), write_journal=JournalRecorder(fs), max_moves=50,
                      sleep=lambda s: None)
    assert res.ok
    assert fs.playlist_uris("SIM0000000000000000001") == [song1.uri, song2.uri] + [t.uri for t in existing]
