"""Decide whether a scheduled tick should refresh the workflow so GitHub does not pause the schedule.

GitHub disables scheduled workflows in a public repo with no activity for 60 days. The sync workflow's own
"Update run logs" commits may or may not count as activity (GitHub does not say), so this looks at the last commit
by anyone other than the bot and, once that is old, asks the workflow to disable and re-enable itself through the
Actions API (the technique the popular keepalive actions use). It cannot be proven short of waiting 60 days, so it
also prints a notice to look at the Actions tab.

    python -m src.keepalive            # prints days=N, refresh=true|false (also appended to $GITHUB_OUTPUT)

The workflow performs the API calls; this module only decides.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

BOT_EMAIL = "likedzero-bot@users.noreply.github.com"
# Start refreshing well before the 60-day cut-off, but only during one UTC hour a day so a 30-minute tick schedule
# toggles the workflow at most twice a day rather than 48 times.
REFRESH_AFTER_DAYS = 30
REFRESH_HOUR_UTC = 3


def last_human_commit(log_lines: list[str]) -> datetime | None:
    """First line of ``git log --format='%ct%x09%ae'`` whose author is not the bot."""
    for line in log_lines:
        stamp, _, email = line.strip().partition("\t")
        if not stamp.isdigit() or email.strip().lower() == BOT_EMAIL:
            continue
        return datetime.fromtimestamp(int(stamp), tz=timezone.utc)
    return None


def should_refresh(last_human: datetime | None, now: datetime) -> tuple[bool, int | None]:
    """(refresh?, days since the last human commit). Unknown history (a shallow clone) never triggers a refresh."""
    if last_human is None:
        return False, None
    days = (now - last_human).days
    return days >= REFRESH_AFTER_DAYS and now.hour == REFRESH_HOUR_UTC, days


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="python -m src.keepalive", description=__doc__.split("\n\n")[0]).parse_args(argv)
    out = subprocess.run(["git", "log", "--format=%ct%x09%ae"], capture_output=True, text=True, check=False).stdout
    refresh, days = should_refresh(last_human_commit(out.splitlines()), datetime.now(timezone.utc))
    lines = [f"days={'unknown' if days is None else days}", f"refresh={'true' if refresh else 'false'}"]
    print("\n".join(lines))
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
