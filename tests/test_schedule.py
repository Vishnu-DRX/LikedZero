"""config.yaml `schedule:` (validation) and src/schedule.py (is the 30-minute workflow tick due?). Offline."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src import schedule as sch
from src.config import ConfigError, parse_config
from src.models import Schedule

UTC = timezone.utc


def S(**kw) -> Schedule:
    base = dict(enabled=True, timezone="Asia/Kolkata", time="09:00")
    base.update(kw)
    return Schedule(**base)


def utc(y, mo, d, h, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


# --------------------------------------------------------------------------- validation

def test_schedule_defaults_to_disabled():
    cfg = parse_config({})
    assert cfg.schedule == Schedule() and cfg.schedule.enabled is False and cfg.schedule.apply is False


def test_schedule_full_example_parses():
    cfg = parse_config({"schedule": {"enabled": True, "timezone": "Asia/Kolkata", "time": "21:30", "days": ["mon", "fri"]}})
    assert cfg.schedule == Schedule(True, "Asia/Kolkata", "21:30", ("mon", "fri"), False)


@pytest.mark.parametrize("bad,match", [
    ({"enabled": "yes"}, "enabled"),
    ({"apply": 1}, "apply"),
    ({"timezone": "Mars/Olympus"}, "timezone"),
    ({"timezone": "asia/kolkata"}, "timezone"),
    ({"timezone": ""}, "timezone"),
    ({"timezone": 5}, "timezone"),
    ({"time": "9:00"}, "time"),
    ({"time": "09:15"}, "time"),
    ({"time": "24:00"}, "time"),
    ({"time": 540}, "time"),  # unquoted 09:00 is read as a number by YAML 1.1
    ({"days": []}, "days"),
    ({"days": ["monday"]}, "days"),
    ({"days": ["mon", "mon"]}, "days"),
    ({"days": "mon"}, "days"),
    ({"other": 1}, "unknown key 'schedule.other'"),
])
def test_schedule_rejects_bad_values(bad, match):
    with pytest.raises(ConfigError, match=match):
        parse_config({"schedule": bad})


@pytest.mark.parametrize("raw", [[], "daily", 3])
def test_schedule_must_be_a_mapping(raw):
    with pytest.raises(ConfigError, match="'schedule' must be a mapping"):
        parse_config({"schedule": raw})


def test_schedule_none_is_default():
    assert parse_config({"schedule": None}).schedule == Schedule()


def test_live_scheduled_apply_requires_inbox_since():
    with pytest.raises(ConfigError, match="requires 'inbox_since'"):
        parse_config({"schedule": {"enabled": True, "apply": True}})
    assert parse_config({"inbox_since": "2026-10-10", "schedule": {"enabled": True, "apply": True}}).schedule.apply is True


# --------------------------------------------------------------------------- is_due

def test_due_exactly_at_the_slot_and_within_the_window():
    # 09:00 IST = 03:30 UTC
    sc = S()
    assert sch.is_due(sc, utc(2026, 10, 12, 3, 30), None)[0]
    assert sch.is_due(sc, utc(2026, 10, 12, 4, 40), None)[0]  # a late (delayed) tick still counts


def test_not_due_before_or_very_long_after_the_slot():
    sc = S()
    assert not sch.is_due(sc, utc(2026, 10, 12, 3, 29), utc(2026, 10, 11, 3, 31))[0]
    assert sch.is_due(sc, utc(2026, 10, 12, 5, 1), None)[0]  # GitHub dropped the early ticks: still catches up
    assert sch.is_due(sc, utc(2026, 10, 12, 15, 29), None)[0]
    assert not sch.is_due(sc, utc(2026, 10, 12, 15, 31), None)[0]  # 12 h 1 min late: the slot is given up


def test_already_ran_since_the_slot_is_not_due_again():
    sc = S()
    now = utc(2026, 10, 12, 4, 0)
    assert not sch.is_due(sc, now, utc(2026, 10, 12, 3, 40))[0]
    assert sch.is_due(sc, now, utc(2026, 10, 11, 3, 40))[0]  # yesterday's run does not count


def test_disabled_is_never_due():
    assert not sch.is_due(S(enabled=False), utc(2026, 10, 12, 3, 30), None)[0]


def test_days_filter_uses_the_local_weekday():
    # 2026-10-12 is a Monday. 23:30 IST Monday = 18:00 UTC Monday; on Tuesday 00:30 IST the Monday slot is 1h old.
    sc = S(time="23:30", days=("mon",))
    assert sch.is_due(sc, utc(2026, 10, 12, 18, 0), None)[0]
    assert sch.is_due(sc, utc(2026, 10, 12, 18, 50), None)[0]
    assert not sch.is_due(sc, utc(2026, 10, 13, 18, 0), None)[0]  # Tuesday slot is not an allowed day


def test_slot_belongs_to_the_local_date_not_the_utc_date():
    # New York 22:00 on Sunday 2026-10-11 (EDT, UTC-4) is already Monday 02:00 UTC.
    sc = S(timezone="America/New_York", time="22:00", days=("sun",))
    assert sch.is_due(sc, utc(2026, 10, 12, 2, 10), None)[0]


def test_dst_change_moves_the_utc_time_but_not_the_local_time():
    sc = S(timezone="America/New_York", time="09:00")
    assert sch.latest_slot(sc, utc(2026, 10, 30, 14)) == utc(2026, 10, 30, 13)  # EDT
    assert sch.latest_slot(sc, utc(2026, 11, 3, 15)) == utc(2026, 11, 3, 14)  # EST after 1 Nov


def test_next_slot_skips_disabled_days():
    sc = S(time="09:00", days=("wed",))
    assert sch.next_slot(sc, utc(2026, 10, 12, 0)) == utc(2026, 10, 14, 3, 30)  # Monday -> Wednesday 09:00 IST


def test_last_run_time_reads_the_newest_entry(tmp_path):
    p = tmp_path / "runs.json"
    assert sch.last_run_time(p) is None
    p.write_text(json.dumps({"runs": [{"time": "2026-10-10T19:01:37+00:00"}, {"time": "2026-10-11T03:40:00+00:00"}]}))
    assert sch.last_run_time(p) == utc(2026, 10, 11, 3, 40)
    p.write_text("not json")
    assert sch.last_run_time(p) is None


def test_main_writes_github_output(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("schedule:\n  enabled: false\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert sch.main(["--config", str(cfg), "--runs", str(tmp_path / "runs.json")]) == 0
    assert out.read_text().split() == ["run=false", "apply=false"]


def test_main_skips_instead_of_failing_on_a_broken_or_missing_config(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert sch.main(["--config", str(tmp_path / "missing.yaml")]) == 0
    bad = tmp_path / "bad.yaml"
    bad.write_text("schedule: 3\n", encoding="utf-8")
    assert sch.main(["--config", str(bad)]) == 0
    assert "::warning::" in capsys.readouterr().out
    assert out.read_text().split() == ["run=false", "apply=false"] * 2


def test_due_main_sets_apply_only_when_configured(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    tz = "UTC"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"inbox_since: 2026-10-10\nschedule:\n  enabled: true\n  timezone: {tz}\n  time: \"{now:%H}:{'00' if now.minute < 30 else '30'}\"\n  apply: true\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert sch.main(["--config", str(cfg), "--runs", str(tmp_path / "runs.json")]) == 0
    assert out.read_text().split() == ["run=true", "apply=true"]


def test_overview_description_from_config():
    from src.artifacts import schedule_info_from_config

    now = utc(2026, 10, 12, 0)
    info = schedule_info_from_config(S(days=("mon", "fri")), now)
    assert info["description"] == "Mon, Fri at 09:00 (Asia/Kolkata), dry run only"
    assert info["next_run"] == "2026-10-12T03:30:00Z" or info["next_run"].startswith("2026-10-12T03:30")
    assert schedule_info_from_config(S(apply=True), now)["description"].endswith("moves songs")
    assert schedule_info_from_config(S(enabled=False), now) is None
