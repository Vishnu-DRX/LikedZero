"""Standalone measurement: `python -m src.measure_round_2` (read-only).

Two measurement tasks for a master sign-off decision (design/BUILD_SPEC.md, Master decisions 10) -- neither
changes config.py/validate.js/planner/rules_engine, and neither writes or drafts any config:

  TASK 1 (decision 50): re-measure `artist_in_playlist` (design/proposals/artist_in_playlist.md) with a
  dominance MARGIN on top of the min_tracks floor, since decision 50's framing is precision over coverage --
  the general min_tracks-only sweep (design/reports/measurement-artist_in_playlist.md) let a weak "3-vs-2
  split" count the same as a genuinely dominant artist home. Also isolates the "effectively single-playlist
  artist" case (an artist whose candidate-playlist tracks are >=90% in one playlist) the user specifically
  confirmed matters, e.g. a dedicated Linkin Park or 21 Pilots playlist.

  TASK 2 (decision 52): a classification audit of EVERY owned/collaborative playlist (not just the 4 mapped
  for language), reusing src/analyze.py's existing per-playlist profiling (genres, artists, languages) to
  suggest which of language/genre/artist organizes each one, if any.

Both tasks share one library fetch (src.measure_artist_in_playlist.fetch_library) so the two sections of the
report describe the same snapshot.

Outputs (counts only, safe to commit): design/reports/measurement-round-2.md
Outputs (names, git-ignored):          logs/measure-round-2-detail.md
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .analyze import LANGUAGE_SHARE, Profile, analyze_playlist
from .config import ConfigError, load_config
from .enrichment.cache import DEFAULT_PATH, EnrichmentCache
from .enrichment.enricher import Enricher
from .enrichment.musicbrainz import MusicBrainz
from .measure_artist_in_playlist import (
    MIN_TRACKS_SWEEP,
    _pct,
    _ratio,
    build_artist_counts,
    classify_single_playlist_artists,
    fetch_library,
    sweep_margin,
)
from .models import Config, Track
from .spotify_client import SpotifyClient, SpotifyError, load_env

MARGIN_SWEEP = (2.0, 3.0)
SINGLE_PLAYLIST_MIN_TOTAL = 2
SINGLE_PLAYLIST_SHARE = 0.90

# Task 2 classification thresholds. Deliberately stricter than analyze.py's own GENRE_SHARE/LANGUAGE_SHARE
# (those decide "worth drafting a rule at all"; these decide "this playlist reads as X-pure", a stronger claim),
# and require enough of the playlist to actually carry the signal (coverage), not just a lopsided ratio over a
# handful of resolved tracks.
ARTIST_HOME_TOP1_SHARE = 0.50
ARTIST_HOME_TOP3_SHARE = 0.70
LANGUAGE_PURE_SHARE = LANGUAGE_SHARE  # reuse analyze.py's own bar (0.70) -- already the project's language-pure bar
GENRE_PURE_SHARE = 0.60
MIN_COVERAGE_FOR_PURITY = 0.50
TOO_SMALL_TRACKS = 10  # matches analyze.py's own MIN_TRACKS


# =================================================================================== Task 1: margin sweep


def render_task1(
    general: Mapping[tuple[int, float], dict[str, Any]], single: Mapping[tuple[int, float], dict[str, Any]],
    total_tracks: int, n_candidate_playlists: int, n_single_artists: int,
) -> list[str]:
    lines = [
        "## Task 1 (decision 50): `artist_in_playlist` with a dominance margin",
        "",
        "Same leave-one-out methodology and library snapshot as "
        "`design/reports/measurement-artist_in_playlist.md`, now gated on BOTH the min_tracks floor AND the "
        "top playlist being a clear multiple ahead of the runner-up (`margin`; a runner-up of 0 trivially "
        "passes). Aggregate only, per decision 50's own ask for a manageable table -- the per-playlist "
        "breakdown for the plain min_tracks sweep is already in the round-1 report.",
        "",
        f"**Library:** {total_tracks} unique tracks, {n_candidate_playlists} candidate playlists (Vault_drx "
        f"still excluded). **{n_single_artists}** distinct primary artists qualify as \"effectively "
        f"single-playlist\" (>= {SINGLE_PLAYLIST_SHARE:.0%} of their >= {SINGLE_PLAYLIST_MIN_TOTAL} "
        "candidate-playlist tracks sit in one playlist) -- the Linkin-Park/21-Pilots-style case.",
        "",
        "### General population",
        "",
        "| min_tracks | margin | tracks | coverage | tie-rate | margin-block-rate | predicted | correct | precision | recall |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for mt in MIN_TRACKS_SWEEP:
        for mg in MARGIN_SWEEP:
            r = general[(mt, mg)]
            lines.append(
                f"| {mt} | {mg} | {r['tracks']} | {_pct(r['coverage'])} | {_pct(r['tie_rate'])} | "
                f"{_pct(r['margin_block_rate'])} | {r['predicted']} | {r['correct']} | {_pct(r['precision'])} | {_pct(r['recall'])} |"
            )
    lines += [
        "",
        "### Effectively single-playlist artists only (the paradigm case)",
        "",
        "Same combinations, restricted to tracks whose primary artist qualifies as above. This is the number "
        "that should determine whether `artist_in_playlist` gets built at all: does it clear ~90% precision "
        "here, even if coverage is necessarily small (most of the library is genuinely not this case).",
        "",
        "| min_tracks | margin | tracks | coverage | tie-rate | margin-block-rate | predicted | correct | precision | recall |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    clears_90 = []
    for mt in MIN_TRACKS_SWEEP:
        for mg in MARGIN_SWEEP:
            r = single[(mt, mg)]
            lines.append(
                f"| {mt} | {mg} | {r['tracks']} | {_pct(r['coverage'])} | {_pct(r['tie_rate'])} | "
                f"{_pct(r['margin_block_rate'])} | {r['predicted']} | {r['correct']} | {_pct(r['precision'])} | {_pct(r['recall'])} |"
            )
            if (r["precision"] or 0) >= 0.90 and r["predicted"]:
                clears_90.append((mt, mg, r["precision"], r["predicted"]))
    lines += ["", "**Combinations clearing ~90% precision on the single-playlist-artist subset:**", ""]
    if clears_90:
        lines += [f"- min_tracks={mt}, margin={mg}: precision {_pct(p)} on {n} predicted tracks" for mt, mg, p, n in clears_90]
    else:
        lines.append("- None of the swept combinations reached 90% precision, even restricted to this subset.")
    lines.append("")
    return lines


# =================================================================================== Task 2: playlist audit


def classify(p: Profile) -> dict[str, Any]:
    """One playlist's shares + a suggested classification. Pure function, no I/O."""
    top1 = p.top_artists[0][1] / p.tracks if p.top_artists and p.tracks else 0.0
    top3 = sum(n for _, n in p.top_artists[:3]) / p.tracks if p.tracks else 0.0
    lang_share = (next(iter(p.languages.values())) / p.language_tracks) if p.language_tracks else 0.0
    lang_coverage = _ratio(p.language_tracks, p.tracks) or 0.0
    genre_share = (p.top_genres[0][1] / p.genre_tracks) if p.genre_tracks else 0.0
    genre_coverage = _ratio(p.genre_tracks, p.tracks) or 0.0

    if p.tracks < TOO_SMALL_TRACKS:
        label = "too-small-to-classify"
    else:
        candidates = []
        if top1 >= ARTIST_HOME_TOP1_SHARE or top3 >= ARTIST_HOME_TOP3_SHARE:
            candidates.append(("artist-home", max(top1, top3)))
        if lang_coverage >= MIN_COVERAGE_FOR_PURITY and lang_share >= LANGUAGE_PURE_SHARE:
            candidates.append(("language-pure", lang_share))
        if genre_coverage >= MIN_COVERAGE_FOR_PURITY and genre_share >= GENRE_PURE_SHARE:
            candidates.append(("genre-pure", genre_share))
        label = max(candidates, key=lambda c: c[1])[0] if candidates else "mixed-no-clear-pattern"

    return {
        "tracks": p.tracks, "artist_top1_share": round(top1, 4), "artist_top3_share": round(top3, 4),
        "language_share": round(lang_share, 4) if p.language_tracks else None, "language_coverage": round(lang_coverage, 4),
        "genre_share": round(genre_share, 4) if p.genre_tracks else None, "genre_coverage": round(genre_coverage, 4),
        "label": label,
    }


def render_task2(rows: Mapping[str, dict[str, Any]], label: Mapping[str, str], excluded_note: str) -> list[str]:
    counts = Counter(r["label"] for r in rows.values())
    lines = [
        "## Task 2 (decision 52): playlist classification audit",
        "",
        "Every owned/collaborative, non-empty playlist (unlike Task 1, `Vault_drx` and the language-mapped "
        "playlists are included here -- this audits ALL of them, decision 52's whole point). Reuses "
        "`src/analyze.py`'s existing per-playlist profiling (content signals only: script/country-default/"
        "MusicBrainz, never `language_playlists`, so a playlist's own language reading is never circular). "
        f"Classification thresholds: artist-home if the top artist has >= {ARTIST_HOME_TOP1_SHARE:.0%} of the "
        f"playlist or the top 3 have >= {ARTIST_HOME_TOP3_SHARE:.0%} combined; language-pure or genre-pure if "
        f"the dominant share (of tracks WITH a resolved language/genre) is >= {LANGUAGE_PURE_SHARE:.0%} / "
        f"{GENRE_PURE_SHARE:.0%} respectively AND at least {MIN_COVERAGE_FOR_PURITY:.0%} of the playlist "
        "actually has that signal resolved; too-small-to-classify under "
        f"{TOO_SMALL_TRACKS} tracks; otherwise mixed-no-clear-pattern. Where a playlist clears more than one "
        "bar, the strongest share wins the label -- this is a suggestion for the master/user to turn into "
        "real rules, not a final answer.",
        "",
        f"**Classification counts** ({sum(counts.values())} playlists, {excluded_note}): " +
        ", ".join(f"{k}: {v}" for k, v in counts.most_common()),
        "",
        "| playlist | tracks | classification | artist top1 | artist top3 | language share (coverage) | genre share (coverage) |",
        "|---|---|---|---|---|---|---|",
    ]
    for pid in sorted(rows, key=lambda p: label[p]):
        r = rows[pid]
        lang_cell = f"{_pct(r['language_share'])} ({_pct(r['language_coverage'])})" if r["language_share"] is not None else f"n/a ({_pct(r['language_coverage'])})"
        genre_cell = f"{_pct(r['genre_share'])} ({_pct(r['genre_coverage'])})" if r["genre_share"] is not None else f"n/a ({_pct(r['genre_coverage'])})"
        lines.append(
            f"| {label[pid]} | {r['tracks']} | {r['label']} | {_pct(r['artist_top1_share'])} | "
            f"{_pct(r['artist_top3_share'])} | {lang_cell} | {genre_cell} |"
        )
    lines.append("")
    return lines


def render_caveats() -> list[str]:
    return [
        "## Caveats",
        "",
        "- **Task 1 is primary-artist only**, same convention and same reasoning as "
        "`design/reports/measurement-artist_in_playlist.md`: a multi-artist track's candidate counts come "
        "from its first-listed artist only, not every credited artist.",
        "- **Task 2's \"artist top 3\" share can exceed 100%.** `analyze.py`'s existing artist tally counts "
        "one vote per credited artist per track (unchanged here, reused as-is), so a track with several "
        "credited artists who are each independently frequent in the playlist is counted once per artist -- "
        "the top-3 *combined* share is a measure of \"how much of the playlist involves these 3 names\", not "
        "a partition of the playlist, and small playlists with heavily co-credited tracks can show a combined "
        "share well past 100%. \"Artist top 1\" cannot exceed 100% (one artist can only appear once per track) "
        "and is the more reliable of the two signals.",
        "- **Playlist membership is a proxy** for both tasks, same caveat as `backtest.py`: a track can "
        "reasonably fit more than one playlist.",
        "- **Task 2's language/genre reading is content-signal-only** (script, country default, MusicBrainz), "
        "matching `analyze.py`'s own deliberate choice to never use `language_playlists` here -- a playlist "
        "that itself teaches a language would otherwise trivially read back as 100% that language.",
        "- **A named local detail file** (never commit it) can be produced with `--detail-out <path>`.",
        "",
    ]


def render_task2_detail(rows: Mapping[str, dict[str, Any]], names: Mapping[str, str]) -> list[str]:
    lines = ["## Task 2 detail (names)", "", "| playlist | tracks | classification | artist top1 | artist top3 | language share (coverage) | genre share (coverage) |",
             "|---|---|---|---|---|---|---|"]
    for pid, r in sorted(rows.items(), key=lambda kv: names.get(kv[0], kv[0]).casefold()):
        lang_cell = f"{_pct(r['language_share'])} ({_pct(r['language_coverage'])})" if r["language_share"] is not None else f"n/a ({_pct(r['language_coverage'])})"
        genre_cell = f"{_pct(r['genre_share'])} ({_pct(r['genre_coverage'])})" if r["genre_share"] is not None else f"n/a ({_pct(r['genre_coverage'])})"
        lines.append(
            f"| {names.get(pid, pid)} | {r['tracks']} | {r['label']} | {_pct(r['artist_top1_share'])} | "
            f"{_pct(r['artist_top3_share'])} | {lang_cell} | {genre_cell} |"
        )
    lines.append("")
    return lines


# =================================================================================== driver


def run(args: argparse.Namespace) -> int:
    load_env(args.env)
    try:
        config: Config = load_config(args.config)
    except (ConfigError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    client = SpotifyClient.from_env(dry_run=True)  # read-only by construction
    lib = fetch_library(client, config)
    tracks, truth, names = lib["tracks"], lib["truth"], lib["names"]
    candidate_ids, excluded_ids = lib["candidate_ids"], lib["excluded_ids"]

    # ---- Task 1
    artist_counts = build_artist_counts(tracks, truth, candidate_ids)
    single_artists = classify_single_playlist_artists(artist_counts, SINGLE_PLAYLIST_MIN_TOTAL, SINGLE_PLAYLIST_SHARE)
    general = {(mt, mg): sweep_margin(tracks, truth, artist_counts, mt, mg) for mt in MIN_TRACKS_SWEEP for mg in MARGIN_SWEEP}
    single = {(mt, mg): sweep_margin(tracks, truth, artist_counts, mt, mg, restrict_artist_ids=single_artists)
              for mt in MIN_TRACKS_SWEEP for mg in MARGIN_SWEEP}
    task1_lines = render_task1(general, single, len(tracks), len(candidate_ids), len(single_artists))

    # ---- Task 2 (reuses the same fetched tracks; per-playlist enrichment, content signals only like analyze.py)
    cache = EnrichmentCache(args.cache)
    mb = MusicBrainz() if (config.musicbrainz and not args.no_network) else None
    enricher = Enricher(cache, mb, None, config.english_default)  # no language_map: non-circular, matches analyze.py
    enrichments: dict[str, Any] = {}
    for i, t in enumerate(tracks, 1):
        enrichments[t.id] = enricher.resolve(t)
        if i % 200 == 0:
            print(f"  enriched {i}/{len(tracks)} (musicbrainz requests {mb.requests_made if mb else 0})", file=sys.stderr)
    if cache.dirty:
        cache.save()

    profiles: dict[str, Profile] = {}
    for pid in names:
        pl_tracks = [t for t in tracks if pid in truth[t.id]]
        profiles[pid] = analyze_playlist(names[pid], pl_tracks, enrichments)
    rows = {pid: classify(p) for pid, p in profiles.items()}

    pl_ids = sorted(names, key=lambda i: names[i].casefold())
    label = {pid: f"P{n + 1:02d}" for n, pid in enumerate(pl_ids)}
    excluded_note = "Vault_drx included here (unlike Task 1)" if excluded_ids else "no playlist was excluded"
    task2_lines = render_task2(rows, label, excluded_note)

    report = "\n".join([
        "# Measurement round 2: artist_in_playlist margin sweep + playlist classification audit (counts only)",
        "",
        "Standalone proof-gathering for `design/BUILD_SPEC.md` Master decisions 10 (decisions 50 and 52), run "
        "via `python -m src.measure_round_2`. Neither task changed config.py/validate.js/planner/rules_engine "
        "or wrote/drafted any config -- this feeds a master sign-off decision. No song, artist or real "
        "playlist name appears below; playlists are labelled P01.. by name order (a separate labelling per "
        "task, since Task 1's candidate set excludes Vault_drx and Task 2's does not).",
        "",
    ] + task1_lines + task2_lines + render_caveats())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out} (counts only)")

    if args.detail_out:
        detail_lines = ["# Measurement round 2 detail (local only; contains playlist names)", ""] + render_task2_detail(rows, names)
        detail_path = Path(args.detail_out)
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_path.write_text("\n".join(detail_lines), encoding="utf-8")
        print(f"wrote {detail_path} (names -- local reference only, never commit)")

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.measure_round_2", description=__doc__.split("\n")[0])
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--env", default=".env")
    p.add_argument("--cache", default=str(DEFAULT_PATH))
    p.add_argument("--out", default="design/reports/measurement-round-2.md")
    p.add_argument("--detail-out", default=None, help="also write a named (git-ignored) detail file to this path")
    p.add_argument("--no-network", action="store_true", help="do not call MusicBrainz (cache + local signals only)")
    args = p.parse_args(argv)
    try:
        return run(args)
    except (SpotifyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
