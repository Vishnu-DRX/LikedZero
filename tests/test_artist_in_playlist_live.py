"""Live, READ-ONLY (skipped unless SPOTISORT_LIVE=1): confirms the SHIPPED artist_in_playlist resolution
(src/enrichment/artist_playlist.py's ArtistPlaylistMap) reproduces the precision numbers measured in
design/reports/measurement-round-2.md Task 1 -- the proof that the min_tracks+min_dominance simplification
(Master decisions 11/decision 54) didn't change the measured result, using the real shipped code end to end,
not the standalone measurement script. Only `classify_single_playlist_artists` (which subset to test on, an
analysis choice, not a resolution mechanism) is reused from the measurement script.
"""

from __future__ import annotations

import pytest

from src.config import load_config
from src.enrichment.artist_playlist import ArtistPlaylistMap
from src.measure_artist_in_playlist import build_artist_counts, classify_single_playlist_artists, fetch_library
from src.spotify_client import SpotifyClient, load_env

pytestmark = pytest.mark.live

MIN_DOMINANCE = 0.9
# design/reports/measurement-round-2.md Task 1, single-playlist-artist subset:
EXPECTED_PRECISION = {2: 0.941, 3: 0.958, 5: 0.984}
TOLERANCE = 0.05  # real-world library drift since the 2026-09-27 measurement, not methodology slop


def test_shipped_artist_playlist_map_reproduces_measured_precision():
    load_env()
    config = load_config("config.yaml")
    client = SpotifyClient.from_env(dry_run=True)  # read-only by construction
    lib = fetch_library(client, config)
    tracks, truth, candidate_ids, names = lib["tracks"], lib["truth"], lib["candidate_ids"], lib["names"]

    raw_counts = build_artist_counts(tracks, truth, candidate_ids)
    single_artists = classify_single_playlist_artists(raw_counts, min_total=2, share=0.90)
    assert single_artists, "expected at least one effectively-single-playlist artist on the real library"

    for min_tracks, expected in EXPECTED_PRECISION.items():
        amap = ArtistPlaylistMap(min_tracks, MIN_DOMINANCE)  # the actual shipped class
        for pid in candidate_ids:
            amap.add_playlist(pid, names[pid], [t for t in tracks if pid in truth[t.id]])

        predicted = correct = 0
        for t in tracks:
            if not t.artists or t.artists[0].id not in single_artists:
                continue
            home = amap.resolve(t)  # the actual shipped leave-one-out resolution
            if home is None:
                continue
            predicted += 1
            if home.playlist_id in truth.get(t.id, ()):
                correct += 1

        assert predicted > 0, f"min_tracks={min_tracks}: no predictions made on the single-playlist-artist subset"
        precision = correct / predicted
        assert precision >= 0.90, f"min_tracks={min_tracks}: shipped precision {precision:.3f} did not clear the 90% bar"
        assert abs(precision - expected) <= TOLERANCE, (
            f"min_tracks={min_tracks}: shipped precision {precision:.3f} drifted from the measured "
            f"{expected:.3f} by more than {TOLERANCE:.0%} -- re-check the resolution logic, not just the library"
        )


def test_vault_drx_is_never_an_auto_target_on_the_real_library():
    """Master decisions 11/decision 55: confirm the hardcoded exclusion actually holds live."""
    load_env()
    config = load_config("config.yaml")
    client = SpotifyClient.from_env(dry_run=True)
    lib = fetch_library(client, config)
    tracks, truth, candidate_ids, names = lib["tracks"], lib["truth"], lib["candidate_ids"], lib["names"]
    assert not any(names[pid].casefold().strip() == "vault_drx" for pid in candidate_ids)

    amap = ArtistPlaylistMap(config.artist_in_playlist_min_tracks, config.artist_in_playlist_min_dominance)
    for pid in candidate_ids:
        amap.add_playlist(pid, names[pid], [t for t in tracks if pid in truth[t.id]])
    resolved_names = {amap.resolve(t).playlist_name for t in tracks if amap.resolve(t) is not None}
    assert "Vault_drx" not in resolved_names
