"""Liked-songs vanished-song guardian (decision 16): pure snapshot/compare logic, plus end-to-end
proof that `python -m src.sync` reports a song Spotify silently dropped, and never flags a song the
run itself moved out of Liked Songs."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from fakes import client_factory, make_track, uri
from src import guardian, sync

BASE_NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
CONFIG = """\
default_days_threshold: 14
rules:
  - name: chill
    match:
      artist_in: ["Bonobo"]
    target_playlist: Chill
"""


# ------------------------------------------------------------------ pure functions

def test_load_snapshot_missing_file_is_empty(tmp_path):
    assert guardian.load_snapshot(tmp_path / "nope.json") == {}


def test_load_snapshot_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "snap.json"
    p.write_text("not json", encoding="utf-8")
    assert guardian.load_snapshot(p) == {}


def test_save_then_load_round_trips(tmp_path):
    p = tmp_path / "snap.json"
    t = make_track(1)
    guardian.save_snapshot(p, [t])
    loaded = guardian.load_snapshot(p)
    assert loaded == {uri(1): {"name": "Song 1", "artists": ["Bonobo"], "added_at": guardian.artifacts.iso(t.added_at)}}


def test_find_vanished_reports_uri_missing_now_and_not_removed_by_tool():
    previous = {uri(1): {"name": "A"}, uri(2): {"name": "B"}, uri(3): {"name": "C"}}
    current = {uri(1), uri(3)}  # uri(2) is gone
    vanished = guardian.find_vanished(previous, current, removed_by_tool=set())
    assert [v["uri"] for v in vanished] == [uri(2)]
    assert vanished[0]["name"] == "B"


def test_find_vanished_excludes_the_tools_own_removals():
    previous = {uri(1): {"name": "A"}, uri(2): {"name": "B"}}
    current = {uri(1)}  # uri(2) is gone, but...
    vanished = guardian.find_vanished(previous, current, removed_by_tool={uri(2)})  # ...the tool removed it
    assert vanished == []


def test_find_vanished_first_run_with_empty_previous_reports_nothing():
    assert guardian.find_vanished({}, {uri(1)}, set()) == []


# ------------------------------------------------------------------ end-to-end via `python -m src.sync`

@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    monkeypatch.setattr(sync, "load_env", lambda *a, **k: False)
    return tmp_path, cfg


def argv(tmp, cfg, *extra):
    return [
        "--config", str(cfg), "--logs-dir", str(tmp / "logs"), "--cache", str(tmp / "cache.json"),
        "--guardian-cache", str(tmp / "guardian.json"),
        "--no-network", "--env", str(tmp / "nonexistent.env"), *extra,
    ]


def latest_log(tmp):
    files = sorted((tmp / "logs").glob("2*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8"))


def test_first_run_has_no_vanished_and_writes_a_snapshot(env, monkeypatch):
    tmp, cfg = env
    fs = client_factory(_fs_with([make_track(1, age_days=1), make_track(2, age_days=1)]))
    monkeypatch.setattr(sync, "SpotifyClient", fs)
    assert sync.main(argv(tmp, cfg)) == 0
    log = latest_log(tmp)
    assert log["vanished"] == []
    snap = guardian.load_snapshot(tmp / "guardian.json")
    assert set(snap) == {uri(1), uri(2)}


def test_second_run_reports_a_song_that_vanished_outside_the_tool(env, monkeypatch):
    tmp, cfg = env
    fake = _fs_with([make_track(1, age_days=1), make_track(2, age_days=1), make_track(3, age_days=1)])
    monkeypatch.setattr(sync, "SpotifyClient", client_factory(fake))
    assert sync.main(argv(tmp, cfg)) == 0  # baseline snapshot: uri(1..3)

    fake.liked.remove(uri(2))  # simulate Spotify silently dropping it (not via any SpotiSort call)

    assert sync.main(argv(tmp, cfg)) == 0
    log = latest_log(tmp)
    assert [v["uri"] for v in log["vanished"]] == [uri(2)]
    assert log["vanished"][0]["name"] == "Song 2"
    assert any("guardian" in w and "vanished" in w for w in log["warnings"])


def test_songs_the_run_itself_moves_are_never_flagged_as_vanished(env, monkeypatch):
    tmp, cfg = env
    fake = _fs_with([make_track(1, age_days=30)])  # old enough, matches the "chill" rule
    fake.add_playlist("chill1", "Chill")
    monkeypatch.setattr(sync, "SpotifyClient", client_factory(fake))
    assert sync.main(argv(tmp, cfg)) == 0  # baseline snapshot includes uri(1)

    assert sync.main(argv(tmp, cfg, "--apply", "--newest", "1")) == 0  # moves + removes uri(1) itself
    log = latest_log(tmp)
    assert log["vanished"] == []


def _fs_with(tracks):
    from fakes import FakeSpotify
    fs = FakeSpotify()
    fs.set_liked(tracks)
    return fs
