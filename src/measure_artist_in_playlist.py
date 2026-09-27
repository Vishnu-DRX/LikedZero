"""Standalone measurement: `python -m src.measure_artist_in_playlist` (read-only).

Proof-gathering for the deferred `artist_in_playlist` proposal (design/proposals/artist_in_playlist.md,
decision 47 #1) -- NOT wired into config.py/validate.js/planner/rules_engine. This feeds a master sign-off
decision; it changes no schema and builds no rule.

Methodology mirrors src/backtest.py's leave-one-out approach: ground truth = which owned/collaborative
playlist a track is really in (a track can have several true homes). For each track, the candidate target is
the argmax, among *other* tracks credited to the track's primary (first-listed) artist, over every usable
playlist except the ones permanently excluded (Vault_drx, per the proposal). A prediction requires a count
that is both >= min_tracks and a STRICT max (a tie between the top playlists is "no prediction", never a
guess, per the proposal's own resolution rule) -- never the track's own membership (leave-one-out).

Outputs (counts only, safe to commit): design/reports/measurement-artist_in_playlist.md
Outputs (names, git-ignored):          logs/measure-artist_in_playlist-detail.md
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import ConfigError, load_config
from .enrichment.playlist_language import LanguageMap
from .models import Config, Playlist, Track
from .spotify_client import SpotifyClient, SpotifyError, load_env

TEST_PLAYLIST = "spotisort test"
EXCLUDED_PLAYLISTS = {"vault_drx"}  # casefolded; design/proposals/artist_in_playlist.md: permanently excluded
MIN_TRACKS_SWEEP = (2, 3, 5)
INTERACTION_LANGUAGES = ("hindi", "malayalam")  # the only two languages with an already-live rule


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def build_artist_counts(tracks: Sequence[Track], truth: Mapping[str, set[str]], candidate_ids: set[str]) -> dict[str, Counter[str]]:
    """primary-artist-id -> Counter[playlist_id] = track count, over candidate (non-excluded) playlists only."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for t in tracks:
        if not t.artists:
            continue
        artist_id = t.artists[0].id
        for pid in truth.get(t.id, ()):
            if pid in candidate_ids:
                counts[artist_id][pid] += 1
    return counts


def predict(track: Track, truth: Mapping[str, set[str]], artist_counts: Mapping[str, Counter[str]], min_tracks: int) -> dict[str, Any]:
    """One track's argmax resolution at a given min_tracks. Leave-one-out: the track's own vote(s) are subtracted."""
    if not track.artists:
        return {"status": "no_artist", "target": None}
    artist_id = track.artists[0].id
    own_homes = truth.get(track.id, set())
    raw = artist_counts.get(artist_id, Counter())
    counts = Counter({pid: n - (1 if pid in own_homes else 0) for pid, n in raw.items()})
    counts = Counter({pid: n for pid, n in counts.items() if n > 0})
    if not counts:
        return {"status": "no_signal", "target": None}
    max_count = max(counts.values())
    if max_count < min_tracks:
        return {"status": "below_floor", "target": None, "max_count": max_count}
    top = [pid for pid, n in counts.items() if n == max_count]
    if len(top) > 1:
        return {"status": "tie", "target": None, "max_count": max_count, "tied": top}
    return {"status": "predicted", "target": top[0], "max_count": max_count}


def sweep(
    tracks: Sequence[Track], truth: Mapping[str, set[str]], candidate_ids: set[str],
    artist_counts: Mapping[str, Counter[str]], min_tracks: int,
) -> dict[str, Any]:
    """Aggregate + per-playlist coverage/precision/recall/tie-rate at one min_tracks value."""
    n = skip_no_artist = coverage_n = tie_n = predicted_n = correct_n = 0
    truth_by_pl: Counter[str] = Counter()
    cov_by_pl: Counter[str] = Counter()
    tie_by_pl: Counter[str] = Counter()
    pred_by_pl: Counter[str] = Counter()
    tp_by_pl: Counter[str] = Counter()
    predictions: dict[str, dict[str, Any]] = {}

    for t in tracks:
        homes = truth.get(t.id, set())
        for pid in homes:
            if pid in candidate_ids:
                truth_by_pl[pid] += 1
        if not t.artists:
            skip_no_artist += 1
            continue
        n += 1
        res = predict(t, truth, artist_counts, min_tracks)
        predictions[t.id] = res
        if res["status"] in ("below_floor", "no_signal"):
            continue
        coverage_n += 1
        for pid in homes:
            if pid in candidate_ids:
                cov_by_pl[pid] += 1
        if res["status"] == "tie":
            tie_n += 1
            for pid in res["tied"]:
                if pid in homes:
                    tie_by_pl[pid] += 1
            continue
        predicted_n += 1
        target = res["target"]
        pred_by_pl[target] += 1
        if target in homes:
            correct_n += 1
            tp_by_pl[target] += 1

    per_pl = {}
    for pid in candidate_ids:
        tr, cov, tie, pred, tp = truth_by_pl[pid], cov_by_pl[pid], tie_by_pl[pid], pred_by_pl[pid], tp_by_pl[pid]
        per_pl[pid] = {
            "tracks": tr, "coverage": _ratio(cov, tr), "tie_rate": _ratio(tie, cov), "predicted": pred, "tp": tp,
            "precision": _ratio(tp, pred), "recall": _ratio(tp, tr),
        }
    aggregate = {
        "tracks": n, "skipped_no_artist": skip_no_artist,
        "coverage": _ratio(coverage_n, n), "tie_rate": _ratio(tie_n, coverage_n), "predicted": predicted_n,
        "correct": correct_n, "precision": _ratio(correct_n, predicted_n), "recall": _ratio(correct_n, n),
    }
    return {"aggregate": aggregate, "per_playlist": per_pl, "predictions": predictions}


def interaction_check(
    tracks: Sequence[Track], lmap: LanguageMap, lang_target_id: Mapping[str, str], predictions: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """For tracks the live Hindi/Malayalam rules would already match (playlist-learned, leave-one-out): does
    artist_in_playlist's prediction (at this min_tracks) agree with the same target, conflict with a
    different one, or make no prediction at all?"""
    out = {lang: {"would_match": 0, "agree": 0, "conflict": 0, "no_prediction": 0} for lang in INTERACTION_LANGUAGES}
    for t in tracks:
        lang = lmap.language_for(t, loo=True)
        if lang not in lang_target_id:
            continue
        row = out[lang]
        row["would_match"] += 1
        res = predictions.get(t.id, {"status": "no_artist"})
        if res["status"] != "predicted":
            row["no_prediction"] += 1
        elif res["target"] == lang_target_id[lang]:
            row["agree"] += 1
        else:
            row["conflict"] += 1
    return out


def render_report(
    *, sweeps: Mapping[int, dict[str, Any]], interactions: Mapping[int, Mapping[str, dict[str, int]]],
    label: Mapping[str, str], n_playlists: int, excluded_note: str, total_tracks: int,
) -> str:
    lines = [
        "# Measurement: `artist_in_playlist` min_tracks sweep (counts only)",
        "",
        "Standalone proof-gathering for `design/proposals/artist_in_playlist.md`, run via "
        "`python -m src.measure_artist_in_playlist`. Not wired into config.py/validate.js/planner -- this "
        "feeds a master sign-off decision, nothing here changed the schema or built a rule.",
        "",
        f"**Library:** {total_tracks} unique tracks across {n_playlists} candidate playlists (owned/collaborative, "
        f"non-empty, the `SpotiSort Test` playlist and {excluded_note} excluded). Playlists are labelled P01.. "
        "by name order; no song, artist or playlist name appears in this file (see the caveats section for what "
        "that means for this measurement, and how to get a named detail file locally).",
        "",
        "## Sweep",
        "",
        "### Aggregate",
        "",
        "| min_tracks | tracks | coverage | tie-rate (of covered) | predicted | correct | precision | recall |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for mt in MIN_TRACKS_SWEEP:
        a = sweeps[mt]["aggregate"]
        lines.append(
            f"| {mt} | {a['tracks']} | {_pct(a['coverage'])} | {_pct(a['tie_rate'])} | {a['predicted']} | "
            f"{a['correct']} | {_pct(a['precision'])} | {_pct(a['recall'])} |"
        )
    lines += ["", "`skipped_no_artist` (tracks with no credited artist, excluded from every row above): " +
              ", ".join(f"min_tracks={mt}: {sweeps[mt]['aggregate']['skipped_no_artist']}" for mt in MIN_TRACKS_SWEEP), ""]

    lines += ["### Per playlist", ""]
    for mt in MIN_TRACKS_SWEEP:
        lines += [f"#### min_tracks = {mt}", "",
                  "| playlist | true tracks | coverage | tie-rate | predicted | tp | precision | recall |",
                  "|---|---|---|---|---|---|---|---|"]
        rows = sweeps[mt]["per_playlist"]
        for pid in sorted(rows, key=lambda p: label[p]):
            r = rows[pid]
            if r["tracks"] == 0:
                continue
            lines.append(
                f"| {label[pid]} | {r['tracks']} | {_pct(r['coverage'])} | {_pct(r['tie_rate'])} | {r['predicted']} | "
                f"{r['tp']} | {_pct(r['precision'])} | {_pct(r['recall'])} |"
            )
        lines.append("")

    lines += ["## Interaction check: agreement with the live Hindi/Malayalam rules", "",
               "For tracks the live `Hindi -> Dil` / `Malayalam -> NewAgeMadrasMail` rules would already match "
               "(playlist-learned language, leave-one-out): does `artist_in_playlist`'s prediction at this "
               "min_tracks point at the *same* playlist (agree), a *different* eligible playlist (conflict), "
               "or make no prediction at all?", "",
               "| min_tracks | language | would-match | agree | conflict | no prediction |",
               "|---|---|---|---|---|---|"]
    for mt in MIN_TRACKS_SWEEP:
        for lang in INTERACTION_LANGUAGES:
            row = interactions[mt][lang]
            lines.append(f"| {mt} | {lang} | {row['would_match']} | {row['agree']} | {row['conflict']} | {row['no_prediction']} |")
    lines.append("")

    lines += [
        "## Read (not a decision -- for the master to weigh)",
        "",
        _recommendation(sweeps),
        "",
        "## Caveats",
        "",
        "- **Primary-artist only.** A multi-artist track's candidate counts come from its first-listed "
        "artist only, not every credited artist (unlike `language_playlists`, which votes for all credited "
        "artists). This avoids a collab track's counts inflating two different artists' \"home\" playlists "
        "under one shared count table; it also means a track by an artist known mainly as a featured "
        "credit may be undercounted. Worth re-measuring with an all-credited-artists variant before sign-off "
        "if collabs turn out to be a large share of conflicts/misses.",
        "- **Playlist membership is a proxy for \"true home\"**, same caveat as `backtest.py`: a track can "
        "reasonably fit more than one playlist, so a \"conflict\" or \"miss\" here is not necessarily wrong "
        "in a way a human would agree with.",
        "- **Coverage/tie-rate here are conditional**: coverage = fraction of tracks where *some* candidate "
        "playlist's count reaches min_tracks at all; tie-rate = fraction *of those* where the top was tied "
        "(not a fraction of the whole library) -- this isolates \"the floor wasn't met\" from \"the floor was "
        "met but the tie rule vetoed it\".",
        "- **This file intentionally omits playlist names** per the task instructions. A named detail file for "
        "local reference only (never commit it) can be produced with `--detail-out <path>`.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _recommendation(sweeps: Mapping[int, dict[str, Any]]) -> str:
    rows = {mt: sweeps[mt]["aggregate"] for mt in MIN_TRACKS_SWEEP}
    best = max(MIN_TRACKS_SWEEP, key=lambda mt: (rows[mt]["precision"] or 0, rows[mt]["coverage"] or 0))
    parts = [f"min_tracks={mt}: coverage {_pct(rows[mt]['coverage'])}, precision {_pct(rows[mt]['precision'])}, "
             f"recall {_pct(rows[mt]['recall'])}, tie-rate {_pct(rows[mt]['tie_rate'])}" for mt in MIN_TRACKS_SWEEP]
    return ("As min_tracks rises, coverage falls and precision should rise (fewer, more confident candidates) "
            "unless the tie-rate dominates instead -- read the table above for the real shape on this library "
            "rather than trusting this one-line summary. Numbers: " + "; ".join(parts) + f". Of the three swept "
            f"values, {best} has this run's best precision (ties broken by coverage) -- that is a starting "
            "point for the master's judgment call, not a recommendation to ship it, since precision alone "
            "ignores how much of the library each threshold actually reaches.")


def render_detail(sweeps: Mapping[int, dict[str, Any]], names: Mapping[str, str]) -> str:
    lines = ["# artist_in_playlist measurement detail (local only; contains playlist names)", ""]
    for mt in MIN_TRACKS_SWEEP:
        lines += [f"## min_tracks = {mt}", "", "| playlist | true tracks | coverage | tie-rate | predicted | tp | precision | recall |",
                  "|---|---|---|---|---|---|---|---|"]
        rows = sweeps[mt]["per_playlist"]
        for pid, r in sorted(rows.items(), key=lambda kv: names.get(kv[0], kv[0]).casefold()):
            if r["tracks"] == 0:
                continue
            lines.append(
                f"| {names.get(pid, pid)} | {r['tracks']} | {_pct(r['coverage'])} | {_pct(r['tie_rate'])} | "
                f"{r['predicted']} | {r['tp']} | {_pct(r['precision'])} | {_pct(r['recall'])} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def fetch_library(client: SpotifyClient, config: Config) -> dict[str, Any]:
    """One read of every owned/collaborative, non-empty playlist (excluding `SpotiSort Test`). Shared by every
    measurement script so a single library snapshot backs every report generated from one run, and so nobody
    pays for a second full fetch. Returns tracks/truth/names/candidate_ids/lang map, all keyed as elsewhere in
    this module."""
    playlists = list(client.iter_my_playlists())
    usable: list[Playlist] = [p for p in playlists if p.usable and p.name.casefold() != TEST_PLAYLIST]

    truth: dict[str, set[str]] = defaultdict(set)
    by_id: dict[str, Track] = {}
    names: dict[str, str] = {}
    lang_by_name = {k.casefold().strip(): v for k, v in config.language_playlists.items()}
    lang_of_playlist: dict[str, str] = {}
    for pl in usable:
        items = list(client.iter_playlist_items(pl.id))
        if not items:
            continue
        names[pl.id] = pl.name
        if pl.name.casefold().strip() in lang_by_name:
            lang_of_playlist[pl.id] = lang_by_name[pl.name.casefold().strip()]
        for t in items:
            by_id.setdefault(t.id, t)
            truth[t.id].add(pl.id)
        print(f"  read {len(items):4d} tracks from {pl.name!r}", file=sys.stderr)
    tracks = list(by_id.values())
    print(f"{len(tracks)} unique tracks from {len(names)} playlists", file=sys.stderr)

    candidate_ids = {pid for pid in names if names[pid].casefold().strip() not in EXCLUDED_PLAYLISTS}
    excluded_ids = set(names) - candidate_ids
    if not excluded_ids:
        print("warning: no playlist named among EXCLUDED_PLAYLISTS was found -- nothing excluded from candidacy", file=sys.stderr)

    lmap = LanguageMap()
    for pl in usable:
        if pl.id in lang_of_playlist:
            lmap.add_playlist([t for t in tracks if pl.id in truth[t.id]], lang_of_playlist[pl.id])
    lang_target_id = {lang: pid for pid, lang in lang_of_playlist.items() if lang in INTERACTION_LANGUAGES and pid in candidate_ids}
    missing_langs = [lang for lang in INTERACTION_LANGUAGES if lang not in lang_target_id]
    if missing_langs:
        print(f"warning: no language playlist configured for {missing_langs} -- interaction check will be empty for them", file=sys.stderr)

    return {
        "usable": usable, "tracks": tracks, "truth": truth, "names": names, "candidate_ids": candidate_ids,
        "excluded_ids": excluded_ids, "lmap": lmap, "lang_target_id": lang_target_id,
    }


# ---------------------------------------------------------------------------------------------- margin sweep
# Master decisions 10 / decision 50: precision over coverage. A raw min_tracks floor alone let a weak
# "3-vs-2 split" count the same as a genuinely dominant artist home; a dominance MARGIN (top count must be a
# clear multiple of the runner-up, not just ahead of it) isolates the paradigm case the user confirmed matters
# (a playlist effectively dedicated to one or two artists) from the general, noisier population.

def predict_margin(
    track: Track, truth: Mapping[str, set[str]], artist_counts: Mapping[str, Counter[str]], min_tracks: int, margin: float,
) -> dict[str, Any]:
    """Like `predict`, but on top of the min_tracks floor and the strict-max tie rule, the top playlist must
    also be `margin` times the runner-up's count (a runner-up of 0 trivially passes -- an "infinite margin")."""
    if not track.artists:
        return {"status": "no_artist", "target": None}
    artist_id = track.artists[0].id
    own_homes = truth.get(track.id, set())
    raw = artist_counts.get(artist_id, Counter())
    counts = Counter({pid: n - (1 if pid in own_homes else 0) for pid, n in raw.items()})
    counts = Counter({pid: n for pid, n in counts.items() if n > 0})
    if not counts:
        return {"status": "no_signal", "target": None}
    ranked = counts.most_common()
    max_count = ranked[0][1]
    if max_count < min_tracks:
        return {"status": "below_floor", "target": None, "max_count": max_count}
    top = [pid for pid, n in ranked if n == max_count]
    if len(top) > 1:
        return {"status": "tie", "target": None, "max_count": max_count, "tied": top}
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if runner_up > 0 and max_count < margin * runner_up:
        return {"status": "below_margin", "target": None, "max_count": max_count, "runner_up": runner_up}
    return {"status": "predicted", "target": top[0], "max_count": max_count, "runner_up": runner_up}


def classify_single_playlist_artists(
    artist_counts: Mapping[str, Counter[str]], min_total: int = 2, share: float = 0.90,
) -> set[str]:
    """Artist ids whose candidate-playlist tracks (RAW, not leave-one-out -- this classifies the artist's whole
    catalog shape, not one held-out track) are >= `share` concentrated in a single playlist, with at least
    `min_total` tracks total (an artist with exactly 1 track is trivially "100% in one playlist" but carries no
    signal once that track is the one being held out)."""
    out = set()
    for artist_id, counts in artist_counts.items():
        total = sum(counts.values())
        if total < min_total:
            continue
        if max(counts.values()) / total >= share:
            out.add(artist_id)
    return out


def sweep_margin(
    tracks: Sequence[Track], truth: Mapping[str, set[str]], artist_counts: Mapping[str, Counter[str]],
    min_tracks: int, margin: float, restrict_artist_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Aggregate-only (no per-playlist breakdown -- decision 50 asked for a manageable table). When
    `restrict_artist_ids` is given, only tracks whose primary artist is in that set count toward every number,
    so the same function produces both the general-population row and the single-playlist-artist row."""
    n = skip_no_artist = coverage_n = tie_n = margin_blocked_n = predicted_n = correct_n = 0
    predictions: dict[str, dict[str, Any]] = {}
    for t in tracks:
        if not t.artists:
            skip_no_artist += 1
            continue
        if restrict_artist_ids is not None and t.artists[0].id not in restrict_artist_ids:
            continue
        n += 1
        res = predict_margin(t, truth, artist_counts, min_tracks, margin)
        predictions[t.id] = res
        if res["status"] in ("below_floor", "no_signal"):
            continue
        coverage_n += 1
        if res["status"] == "tie":
            tie_n += 1
            continue
        if res["status"] == "below_margin":
            margin_blocked_n += 1
            continue
        predicted_n += 1
        if res["target"] in truth.get(t.id, ()):
            correct_n += 1
    return {
        "tracks": n, "skipped_no_artist": skip_no_artist, "coverage": _ratio(coverage_n, n),
        "tie_rate": _ratio(tie_n, coverage_n), "margin_block_rate": _ratio(margin_blocked_n, coverage_n),
        "predicted": predicted_n, "correct": correct_n, "precision": _ratio(correct_n, predicted_n),
        "recall": _ratio(correct_n, n), "predictions": predictions,
    }


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
    lmap, lang_target_id = lib["lmap"], lib["lang_target_id"]

    artist_counts = build_artist_counts(tracks, truth, candidate_ids)

    sweeps = {mt: sweep(tracks, truth, candidate_ids, artist_counts, mt) for mt in MIN_TRACKS_SWEEP}
    interactions = {mt: interaction_check(tracks, lmap, lang_target_id, sweeps[mt]["predictions"]) for mt in MIN_TRACKS_SWEEP}

    pl_ids = sorted(candidate_ids, key=lambda i: names[i].casefold())
    label = {pid: f"P{n + 1:02d}" for n, pid in enumerate(pl_ids)}
    excluded_note = "the playlist(s) this proposal permanently excludes" if excluded_ids else "(nothing matched the exclusion list)"

    report = render_report(
        sweeps=sweeps, interactions=interactions, label=label, n_playlists=len(candidate_ids),
        excluded_note=excluded_note, total_tracks=len(tracks),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out} (counts only)")

    if args.detail_out:
        detail_path = Path(args.detail_out)
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_path.write_text(render_detail(sweeps, names), encoding="utf-8")
        print(f"wrote {detail_path} (names -- local reference only, never commit)")

    for mt in MIN_TRACKS_SWEEP:
        a = sweeps[mt]["aggregate"]
        print(f"min_tracks={mt}: coverage={_pct(a['coverage'])} precision={_pct(a['precision'])} "
              f"recall={_pct(a['recall'])} tie_rate={_pct(a['tie_rate'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.measure_artist_in_playlist", description=__doc__.split("\n")[0])
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--env", default=".env")
    p.add_argument("--out", default="design/reports/measurement-artist_in_playlist.md")
    p.add_argument("--detail-out", default=None, help="also write a named (git-ignored) detail file to this path")
    args = p.parse_args(argv)
    try:
        return run(args)
    except (SpotifyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
