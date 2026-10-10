from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.keepalive import BOT_EMAIL, REFRESH_AFTER_DAYS, REFRESH_HOUR_UTC, last_human_commit, should_refresh

NOW = datetime(2026, 12, 1, REFRESH_HOUR_UTC, 10, tzinfo=timezone.utc)


def ts(dt: datetime) -> int:
    return int(dt.timestamp())


def test_last_human_commit_skips_bot_commits():
    lines = [f"{ts(NOW)}\t{BOT_EMAIL}", f"{ts(NOW - timedelta(days=40))}\tvishnu@example.com"]
    assert last_human_commit(lines) == NOW - timedelta(days=40)


def test_last_human_commit_none_when_only_bot_or_empty():
    assert last_human_commit([f"{ts(NOW)}\t{BOT_EMAIL.upper()}"]) is None
    assert last_human_commit([]) is None
    assert last_human_commit(["garbage"]) is None


def test_recent_human_activity_needs_no_refresh():
    assert should_refresh(NOW - timedelta(days=REFRESH_AFTER_DAYS - 1), NOW) == (False, REFRESH_AFTER_DAYS - 1)


def test_old_activity_refreshes_only_in_the_daily_hour():
    last = NOW - timedelta(days=REFRESH_AFTER_DAYS + 5)
    assert should_refresh(last, NOW) == (True, REFRESH_AFTER_DAYS + 5)
    assert should_refresh(last, NOW.replace(hour=REFRESH_HOUR_UTC + 1))[0] is False


def test_unknown_history_never_refreshes():
    assert should_refresh(None, NOW) == (False, None)
