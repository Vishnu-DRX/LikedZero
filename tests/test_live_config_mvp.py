"""The shipped config.yaml (MVP mode): a freshly liked song goes to the TOP of The Simulation Archives. Offline."""

from __future__ import annotations

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
    assert [r.name for r in config.rules if r.enabled] == ["Catch-all -> The Simulation Archives"]
    assert len(plan.moves) == 1
    m = plan.moves[0]
    assert m["playlist"] == "The Simulation Archives" and m["target_position"] == "top"
    assert [b.position for b in insert_batches(plan.moves)] == [0]


def test_song_liked_before_inbox_since_is_never_planned():
    config = load_config("config.yaml")
    old = datetime.combine(config.inbox_since, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=1)
    _, plan = _plan(30, liked_on=old)
    assert plan.moves == []
