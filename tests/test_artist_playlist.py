"""Unit tests for src/enrichment/artist_playlist.py using fabricated data (no I/O, no network)."""

from __future__ import annotations

from src.enrichment.artist_playlist import (
    HARDCODED_EXCLUDED_PLAYLISTS,
    ArtistHome,
    ArtistPlaylistMap,
    build_artist_playlist_map,
    excluded_playlist_names,
)
from src.models import Artist, Playlist, Track


def t(i, artist, home_id=None):
    return Track(id=f"t{i}", uri=f"spotify:track:t{i}", name=f"Song {i}", artists=(artist,))


A = Artist("a1", "Dominant Artist")
B = Artist("a2", "Close Artist")


# ------------------------------------------------------------------ excluded_playlist_names

def test_excluded_playlist_names_always_includes_vault_drx():
    assert excluded_playlist_names([]) == {"vault_drx"}
    assert "vault_drx" in excluded_playlist_names(["Some Other Playlist"])


def test_excluded_playlist_names_casefolds_and_strips():
    assert excluded_playlist_names(["  Fuel  ", "SERENITY"]) == {"fuel", "serenity", "vault_drx"}


def test_hardcoded_excluded_playlists_constant_is_vault_drx_only():
    assert HARDCODED_EXCLUDED_PLAYLISTS == frozenset({"vault_drx"})


# ------------------------------------------------------------------ ArtistPlaylistMap.resolve

def build_map(min_tracks=2, min_dominance=0.9):
    return ArtistPlaylistMap(min_tracks, min_dominance)


def test_resolve_none_when_artist_unknown():
    m = build_map()
    m.add_playlist("P1", "Fuel", [t(1, A)])
    assert m.resolve(t(99, B)) is None


def test_resolve_none_when_track_has_no_artists():
    m = build_map()
    track = Track(id="t1", uri="spotify:track:t1", name="Instrumental")
    assert m.resolve(track) is None


def test_resolve_below_min_tracks_floor():
    m = build_map(min_tracks=5, min_dominance=0.5)
    m.add_playlist("P1", "Fuel", [t(i, A) for i in range(1, 4)])  # only 3, below floor of 5
    assert m.resolve(t(99, A)) is None


def test_resolve_below_min_dominance():
    m = build_map(min_tracks=2, min_dominance=0.9)
    m.add_playlist("P1", "Fuel", [t(1, A), t(2, A), t(3, A)])
    m.add_playlist("P2", "Other", [t(4, A), t(5, A)])
    # P1=3, P2=2, total=5, dominance = 3/5 = 0.6 < 0.9
    assert m.resolve(t(99, A)) is None


def test_resolve_confident_home():
    m = build_map(min_tracks=2, min_dominance=0.8)
    m.add_playlist("P1", "Fuel", [t(i, A) for i in range(1, 10)])
    m.add_playlist("P2", "Other", [t(20, A)])
    home = m.resolve(t(99, A))
    assert home == ArtistHome("P1", "Fuel", 9, 10)


def test_resolve_leave_one_out_excludes_the_track_s_own_membership():
    m = build_map(min_tracks=2, min_dominance=0.5)
    # A's only 2 tracks are both in P1; evaluating one of THOSE tracks itself must not let it vote for itself
    tracks = [t(1, A), t(2, A)]
    m.add_playlist("P1", "Fuel", tracks)
    assert m.resolve(tracks[0]) is None  # loo: only 1 other track remains, below min_tracks=2


def test_resolve_genuine_tie_never_guesses_even_with_low_dominance():
    m = build_map(min_tracks=1, min_dominance=0.1)  # deliberately permissive floor/dominance
    m.add_playlist("P1", "Fuel", [t(1, A)])
    m.add_playlist("P2", "Other", [t(2, A)])
    # tied 1-1: even though dominance 0.5 would clear a 0.1 bar, a genuine tie is never resolved
    assert m.resolve(t(99, A)) is None


def test_resolve_exact_min_tracks_boundary_is_inclusive():
    m = build_map(min_tracks=3, min_dominance=0.5)
    m.add_playlist("P1", "Fuel", [t(i, A) for i in range(1, 4)])  # exactly 3
    assert m.resolve(t(99, A)) is not None


def test_resolve_exact_min_dominance_boundary_is_inclusive():
    m = build_map(min_tracks=1, min_dominance=0.75)
    m.add_playlist("P1", "Fuel", [t(1, A), t(2, A), t(3, A)])
    m.add_playlist("P2", "Other", [t(4, A)])
    # P1=3, total=4, dominance exactly 0.75
    home = m.resolve(t(99, A))
    assert home is not None and home.playlist_name == "Fuel"


def test_len_counts_distinct_artists():
    m = build_map()
    m.add_playlist("P1", "Fuel", [t(1, A), t(2, B)])
    assert len(m) == 2


# ------------------------------------------------------------------ build_artist_playlist_map

def test_build_artist_playlist_map_excludes_vault_drx_regardless_of_config():
    playlists = [Playlist("p1", "Fuel", "me", True, False), Playlist("vdx", "Vault_drx", "me", True, False)]
    items = {"p1": [t(i, A) for i in range(1, 5)], "vdx": [t(i, A) for i in range(100, 200)]}
    m = build_artist_playlist_map(playlists, lambda pid: items[pid], min_tracks=2, min_dominance=0.5, exclude=[])
    home = m.resolve(t(999, A))
    assert home is not None and home.playlist_name == "Fuel"  # never Vault_drx, despite its huge count


def test_build_artist_playlist_map_skips_test_playlist():
    playlists = [Playlist("p1", "SpotiSort Test", "me", True, False)]
    items = {"p1": [t(i, A) for i in range(1, 10)]}
    m = build_artist_playlist_map(playlists, lambda pid: items[pid], min_tracks=1, min_dominance=0.5, exclude=[])
    assert len(m) == 0


def test_build_artist_playlist_map_skips_unusable_playlists():
    playlists = [Playlist("p1", "Followed", "someone-else", False, False)]
    items = {"p1": [t(i, A) for i in range(1, 10)]}
    m = build_artist_playlist_map(playlists, lambda pid: items[pid], min_tracks=1, min_dominance=0.5, exclude=[])
    assert len(m) == 0


def test_build_artist_playlist_map_honours_configured_exclude_list():
    playlists = [Playlist("p1", "Fuel", "me", True, False), Playlist("p2", "Archive", "me", True, False)]
    items = {"p1": [t(i, A) for i in range(1, 5)], "p2": [t(i, A) for i in range(100, 300)]}
    m = build_artist_playlist_map(playlists, lambda pid: items[pid], min_tracks=2, min_dominance=0.5, exclude=["Archive"])
    home = m.resolve(t(999, A))
    assert home is not None and home.playlist_name == "Fuel"
