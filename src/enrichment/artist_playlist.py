"""Learn which playlist is an artist's "home", for the `artist_in_playlist` match key
(design/proposals/artist_in_playlist.md). Mirrors `playlist_language.py`'s approach: each track's PRIMARY
(first-credited) artist "votes" for the playlist it sits in, over the user's own owned/collaborative playlists
-- the same primary-artist-only, leave-one-out convention `design/reports/measurement-artist_in_playlist.md`
and `measurement-round-2.md` measured (so the shipped precision matches what was proven, not a variant of it).

An artist has a resolved home only when the top playlist clears BOTH `min_tracks` and `min_dominance` -- and a
genuine tie for the top spot is never guessed at, regardless of how low `min_dominance` is configured (a tie
can only clear >50% dominance if the runner-up has just one track fewer than the true total, so this tie guard
is mostly a defensive backstop for a low min_dominance, not something the shipped default of 0.9 needs to lean on).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable

from ..models import Playlist, Track

# Master decisions 11 / decision 54: Vault_drx must never be a candidate target even if a user's own
# `exclude_playlists` list omits it -- this must not rely on config alone, so it is enforced here too,
# independent of whatever `Config.artist_in_playlist_exclude_playlists` already merged it into.
HARDCODED_EXCLUDED_PLAYLISTS = frozenset({"vault_drx"})
TEST_PLAYLIST = "spotisort test"


def excluded_playlist_names(configured: Iterable[str]) -> frozenset[str]:
    """Casefolded names that may never be an artist_in_playlist target."""
    return frozenset(n.casefold().strip() for n in configured) | HARDCODED_EXCLUDED_PLAYLISTS


@dataclass(frozen=True)
class ArtistHome:
    playlist_id: str
    playlist_name: str
    track_count: int  # N: the artist's tracks in playlist_name
    artist_total: int  # M: the artist's tracks across every candidate playlist


class ArtistPlaylistMap:
    def __init__(self, min_tracks: int, min_dominance: float) -> None:
        self.min_tracks = min_tracks
        self.min_dominance = min_dominance
        self._counts: dict[str, Counter[str]] = defaultdict(Counter)
        self._names: dict[str, str] = {}
        self._track_playlists: dict[str, set[str]] = defaultdict(set)

    def add_playlist(self, playlist_id: str, name: str, tracks: Iterable[Track]) -> None:
        self._names[playlist_id] = name
        for t in tracks:
            self._track_playlists[t.id].add(playlist_id)
            if t.artists and t.artists[0].id:
                self._counts[t.artists[0].id][playlist_id] += 1

    def resolve(self, track: Track) -> ArtistHome | None:
        """Leave-one-out: a track already sitting in a candidate playlist never votes for its own home (its
        own membership, tracked via `add_playlist`, is subtracted automatically). None = no confident home."""
        if not track.artists or not track.artists[0].id:
            return None
        raw = self._counts.get(track.artists[0].id)
        if not raw:
            return None
        own = self._track_playlists.get(track.id, set())
        counts = Counter({pid: n - (1 if pid in own else 0) for pid, n in raw.items()})
        counts = Counter({pid: n for pid, n in counts.items() if n > 0})
        if not counts:
            return None
        total = sum(counts.values())
        ranked = counts.most_common()
        top_pid, top_n = ranked[0]
        if len(ranked) > 1 and ranked[1][1] == top_n:
            return None  # genuine tie: never guess
        if top_n < self.min_tracks or top_n / total < self.min_dominance:
            return None
        return ArtistHome(top_pid, self._names[top_pid], top_n, total)

    def __len__(self) -> int:
        return len(self._counts)


def build_artist_playlist_map(
    playlists: Iterable[Playlist],
    iter_items: Callable[[str], Iterable[Track]],
    *,
    min_tracks: int,
    min_dominance: float,
    exclude: Iterable[str] = (),
) -> ArtistPlaylistMap:
    """`iter_items(playlist_id) -> Iterable[Track]` -- caller supplies the read (real client or a fixture),
    same inversion-of-control pattern used throughout this codebase for testability."""
    excluded = excluded_playlist_names(exclude)
    m = ArtistPlaylistMap(min_tracks, min_dominance)
    for pl in playlists:
        if not pl.usable:
            continue
        name_cf = pl.name.casefold().strip()
        if name_cf == TEST_PLAYLIST or name_cf in excluded:
            continue
        m.add_playlist(pl.id, pl.name, iter_items(pl.id))
    return m
