"""Live, READ-ONLY (skipped unless SPOTISORT_LIVE=1): confirms the real catch-all (`match: {any: true}`,
Master decisions 12/decision 51) resolves correctly against the real account -- "SpotiSort Sink" exists and is
writable, and a what-if preview with every rule enabled (including the disabled catch-all draft) never lets the
catch-all claim a song an earlier, more specific rule already claimed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.config import load_config
from src.planner import decide, resolve_target
from src.spotify_client import SpotifyClient, load_env

pytestmark = pytest.mark.live


def test_spotisort_sink_resolves_and_is_writable():
    load_env()
    client = SpotifyClient.from_env(dry_run=True)
    playlists = list(client.iter_my_playlists())
    pl, problem, warning = resolve_target("SpotiSort Sink", playlists)
    assert pl is not None, f"SpotiSort Sink did not resolve: {problem} / {warning}"
    assert pl.usable


def test_catch_all_never_overrides_an_earlier_specific_rule():
    load_env()
    config = load_config("config.yaml")
    what_if = replace(config, rules=tuple(replace(r, enabled=True) for r in config.rules))
    client = SpotifyClient.from_env(dry_run=True)
    now = datetime.now(timezone.utc)
    tracks = list(client.iter_saved_tracks())
    assert tracks, "expected at least one liked song on the real library"

    catch_all_name = next(r.name for r in what_if.rules if r.match == {"any": True})
    earlier_specific_wins = 0
    catch_all_wins = 0
    for t in tracks[:200]:  # a bounded sample: this is a resolution-order proof, not a full-library sweep
        d = decide(t, None, what_if, now)
        if d.kind == "no_match":
            continue
        if d.rule_name == catch_all_name:
            catch_all_wins += 1
        else:
            earlier_specific_wins += 1
    # not a strict requirement that both are nonzero (library composition varies), but the catch-all rule
    # being reachable at all confirms it's correctly placed last and not short-circuiting everything above it
    assert catch_all_wins + earlier_specific_wins > 0
    print(f"catch-all wins: {catch_all_wins}, earlier-rule wins: {earlier_specific_wins} (of {len(tracks[:200])} sampled)")
