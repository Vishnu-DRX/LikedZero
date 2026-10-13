"""Decide whether a scheduled workflow tick should run the sync (config.yaml `schedule:`).

GitHub Actions cron is fixed in the workflow file, so the workflow ticks every 30 minutes and this module checks
the user's own schedule (local time + timezone, edited from the Configure page) against that tick. A tick is due
when the most recent scheduled slot is at most WINDOW old and no run has been recorded since that slot.

    python -m src.schedule --config config.yaml --runs logs/runs.json

prints ``run=true|false`` and ``apply=true|false`` lines (also appended to $GITHUB_OUTPUT when set).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ConfigError, load_config
from .models import SCHEDULE_DAYS, Schedule

# GitHub delays scheduled runs under load (often 5-20 minutes) and sometimes drops ticks for hours (the 11 and 12 Oct
# 2026 slots were missed that way). A slot therefore stays claimable for 12 hours so a late tick still catches up;
# the "already ran since the slot" check keeps it to exactly one run per slot.
WINDOW = timedelta(hours=12)


def latest_slot(schedule: Schedule, now: datetime) -> datetime | None:
    """The most recent scheduled moment at or before ``now`` (UTC, aware), honouring the allowed weekdays."""
    tz = ZoneInfo(schedule.timezone)
    local = now.astimezone(tz)
    hour, minute = (int(x) for x in schedule.time.split(":"))
    for back in range(8):
        day = local.date() - timedelta(days=back)
        if SCHEDULE_DAYS[day.weekday()] not in schedule.days:
            continue
        slot = datetime.combine(day, time(hour, minute), tzinfo=tz)
        if slot <= local:
            return slot.astimezone(timezone.utc)
    return None


def next_slot(schedule: Schedule, now: datetime) -> datetime | None:
    """The next scheduled moment after ``now`` (UTC, aware)."""
    tz = ZoneInfo(schedule.timezone)
    local = now.astimezone(tz)
    hour, minute = (int(x) for x in schedule.time.split(":"))
    for ahead in range(8):
        day = local.date() + timedelta(days=ahead)
        if SCHEDULE_DAYS[day.weekday()] not in schedule.days:
            continue
        slot = datetime.combine(day, time(hour, minute), tzinfo=tz)
        if slot > local:
            return slot.astimezone(timezone.utc)
    return None


def is_due(schedule: Schedule, now: datetime, last_run: datetime | None) -> tuple[bool, str]:
    if not schedule.enabled:
        return False, "schedule is not enabled in config.yaml"
    slot = latest_slot(schedule, now)
    if slot is None:
        return False, "no scheduled day in the last week"
    if now - slot > WINDOW:
        return False, f"last slot {slot.isoformat()} is outside the {int(WINDOW.total_seconds() // 60)}-minute window"
    if last_run is not None and last_run >= slot:
        return False, f"already ran at {last_run.isoformat()} for the {slot.isoformat()} slot"
    return True, f"due: slot {slot.isoformat()}"


def last_run_time(runs_path: Path) -> datetime | None:
    try:
        data = json.loads(runs_path.read_text(encoding="utf-8"))
        times = [datetime.fromisoformat(r["time"]) for r in data.get("runs", []) if r.get("time")]
    except (OSError, ValueError, KeyError, AttributeError):
        return None
    return max(times) if times else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.schedule", description=__doc__.split("\n\n")[0])
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--runs", default="logs/runs.json")
    args = p.parse_args(argv)
    try:
        schedule = load_config(args.config).schedule
    except (ConfigError, OSError) as exc:
        # A tick that fails would email the owner every 30 minutes; skip with a visible annotation instead. Real
        # runs (manual, or a tick that is due) still validate the config loudly in the workflow's own check step.
        schedule = Schedule()
        due, reason = False, f"config.yaml unusable, skipping this tick: {str(exc).splitlines()[0]}"
        print(f"::warning::{reason}")
    else:
        due, reason = is_due(schedule, datetime.now(timezone.utc), last_run_time(Path(args.runs)))
    lines = [f"run={'true' if due else 'false'}", f"apply={'true' if due and schedule.apply else 'false'}"]
    print(reason)
    print("\n".join(lines))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
