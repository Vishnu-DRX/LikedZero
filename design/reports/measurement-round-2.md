# Measurement round 2: artist_in_playlist margin sweep + playlist classification audit (counts only)

Standalone proof-gathering for `design/BUILD_SPEC.md` Master decisions 10 (decisions 50 and 52), run via `python -m src.measure_round_2`. Neither task changed config.py/validate.js/planner/rules_engine or wrote/drafted any config -- this feeds a master sign-off decision. No song, artist or real playlist name appears below; playlists are labelled P01.. by name order (a separate labelling per task, since Task 1's candidate set excludes Vault_drx and Task 2's does not).

## Task 1 (decision 50): `artist_in_playlist` with a dominance margin

Same leave-one-out methodology and library snapshot as `design/reports/measurement-artist_in_playlist.md`, now gated on BOTH the min_tracks floor AND the top playlist being a clear multiple ahead of the runner-up (`margin`; a runner-up of 0 trivially passes). Aggregate only, per decision 50's own ask for a manageable table -- the per-playlist breakdown for the plain min_tracks sweep is already in the round-1 report.

**Library:** 2678 unique tracks, 31 candidate playlists (Vault_drx still excluded). **130** distinct primary artists qualify as "effectively single-playlist" (>= 90% of their >= 2 candidate-playlist tracks sit in one playlist) -- the Linkin-Park/21-Pilots-style case.

### General population

| min_tracks | margin | tracks | coverage | tie-rate | margin-block-rate | predicted | correct | precision | recall |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 2.0 | 2678 | 27.8% | 2.7% | 12.0% | 635 | 494 | 77.8% | 18.4% |
| 2 | 3.0 | 2678 | 27.8% | 2.7% | 28.6% | 511 | 424 | 83.0% | 15.8% |
| 3 | 2.0 | 2678 | 21.5% | 0.5% | 15.5% | 483 | 391 | 81.0% | 14.6% |
| 3 | 3.0 | 2678 | 21.5% | 0.5% | 28.3% | 409 | 346 | 84.6% | 12.9% |
| 5 | 2.0 | 2678 | 15.2% | 0.0% | 15.5% | 343 | 288 | 84.0% | 10.8% |
| 5 | 3.0 | 2678 | 15.2% | 0.0% | 29.3% | 287 | 255 | 88.8% | 9.5% |

### Effectively single-playlist artists only (the paradigm case)

Same combinations, restricted to tracks whose primary artist qualifies as above. This is the number that should determine whether `artist_in_playlist` gets built at all: does it clear ~90% precision here, even if coverage is necessarily small (most of the library is genuinely not this case).

| min_tracks | margin | tracks | coverage | tie-rate | margin-block-rate | predicted | correct | precision | recall |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 2.0 | 482 | 67.2% | 0.0% | 0.0% | 324 | 305 | 94.1% | 63.3% |
| 2 | 3.0 | 482 | 67.2% | 0.0% | 0.0% | 324 | 305 | 94.1% | 63.3% |
| 3 | 2.0 | 482 | 49.8% | 0.0% | 0.0% | 240 | 230 | 95.8% | 47.7% |
| 3 | 3.0 | 482 | 49.8% | 0.0% | 0.0% | 240 | 230 | 95.8% | 47.7% |
| 5 | 2.0 | 482 | 39.8% | 0.0% | 0.0% | 192 | 189 | 98.4% | 39.2% |
| 5 | 3.0 | 482 | 39.8% | 0.0% | 0.0% | 192 | 189 | 98.4% | 39.2% |

**Combinations clearing ~90% precision on the single-playlist-artist subset:**

- min_tracks=2, margin=2.0: precision 94.1% on 324 predicted tracks
- min_tracks=2, margin=3.0: precision 94.1% on 324 predicted tracks
- min_tracks=3, margin=2.0: precision 95.8% on 240 predicted tracks
- min_tracks=3, margin=3.0: precision 95.8% on 240 predicted tracks
- min_tracks=5, margin=2.0: precision 98.4% on 192 predicted tracks
- min_tracks=5, margin=3.0: precision 98.4% on 192 predicted tracks

## Task 2 (decision 52): playlist classification audit

Every owned/collaborative, non-empty playlist (unlike Task 1, `Vault_drx` and the language-mapped playlists are included here -- this audits ALL of them, decision 52's whole point). Reuses `src/analyze.py`'s existing per-playlist profiling (content signals only: script/country-default/MusicBrainz, never `language_playlists`, so a playlist's own language reading is never circular). Classification thresholds: artist-home if the top artist has >= 50% of the playlist or the top 3 have >= 70% combined; language-pure or genre-pure if the dominant share (of tracks WITH a resolved language/genre) is >= 70% / 60% respectively AND at least 50% of the playlist actually has that signal resolved; too-small-to-classify under 10 tracks; otherwise mixed-no-clear-pattern. Where a playlist clears more than one bar, the strongest share wins the label -- this is a suggestion for the master/user to turn into real rules, not a final answer.

**Classification counts** (32 playlists, Vault_drx included here (unlike Task 1)): mixed-no-clear-pattern: 18, artist-home: 6, genre-pure: 4, too-small-to-classify: 3, language-pure: 1

| playlist | tracks | classification | artist top1 | artist top3 | language share (coverage) | genre share (coverage) |
|---|---|---|---|---|---|---|
| P01 | 66 | mixed-no-clear-pattern | 10.6% | 25.8% | 25.0% (6.1%) | 40.9% (33.3%) |
| P02 | 28 | artist-home | 100.0% | 100.0% | n/a (0.0%) | 100.0% (100.0%) |
| P03 | 28 | mixed-no-clear-pattern | 7.1% | 21.4% | 33.3% (21.4%) | 29.4% (60.7%) |
| P04 | 18 | mixed-no-clear-pattern | 11.1% | 22.2% | 50.0% (22.2%) | 37.5% (88.9%) |
| P05 | 28 | mixed-no-clear-pattern | 21.4% | 57.1% | 66.7% (32.1%) | 57.1% (50.0%) |
| P06 | 5 | too-small-to-classify | 80.0% | 120.0% | n/a (0.0%) | 100.0% (80.0%) |
| P07 | 20 | artist-home | 100.0% | 100.0% | n/a (0.0%) | 100.0% (100.0%) |
| P08 | 144 | mixed-no-clear-pattern | 10.4% | 24.3% | 66.7% (10.4%) | 73.5% (47.2%) |
| P09 | 216 | mixed-no-clear-pattern | 6.5% | 13.9% | 20.9% (19.9%) | 30.5% (81.9%) |
| P10 | 12 | genre-pure | 25.0% | 58.3% | 100.0% (25.0%) | 83.3% (100.0%) |
| P11 | 237 | mixed-no-clear-pattern | 4.6% | 8.9% | 17.9% (23.6%) | 27.3% (46.4%) |
| P12 | 14 | artist-home | 100.0% | 107.1% | n/a (0.0%) | 100.0% (100.0%) |
| P13 | 57 | genre-pure | 12.3% | 21.1% | 100.0% (1.8%) | 71.8% (68.4%) |
| P14 | 11 | artist-home | 90.9% | 109.1% | n/a (0.0%) | 100.0% (100.0%) |
| P15 | 63 | language-pure | 6.3% | 15.9% | 84.1% (69.8%) | 36.0% (39.7%) |
| P16 | 101 | mixed-no-clear-pattern | 9.9% | 29.7% | n/a (0.0%) | 100.0% (11.9%) |
| P17 | 73 | mixed-no-clear-pattern | 4.1% | 11.0% | 33.3% (12.3%) | 42.9% (67.1%) |
| P18 | 26 | mixed-no-clear-pattern | 7.7% | 15.4% | 33.3% (11.5%) | 50.0% (53.8%) |
| P19 | 1 | too-small-to-classify | 100.0% | 300.0% | n/a (0.0%) | n/a (0.0%) |
| P20 | 30 | genre-pure | 16.7% | 33.3% | 57.1% (23.3%) | 63.2% (63.3%) |
| P21 | 9 | too-small-to-classify | 11.1% | 33.3% | 100.0% (11.1%) | 40.0% (55.6%) |
| P22 | 12 | artist-home | 100.0% | 100.0% | n/a (0.0%) | 100.0% (100.0%) |
| P23 | 470 | mixed-no-clear-pattern | 3.6% | 8.5% | 37.7% (14.7%) | 50.1% (77.2%) |
| P24 | 35 | mixed-no-clear-pattern | 2.9% | 8.6% | 25.0% (11.4%) | 29.2% (68.6%) |
| P25 | 50 | mixed-no-clear-pattern | 10.0% | 24.0% | 33.3% (12.0%) | 34.3% (70.0%) |
| P26 | 199 | mixed-no-clear-pattern | 9.6% | 18.6% | 21.4% (21.1%) | 24.1% (70.9%) |
| P27 | 17 | artist-home | 94.1% | 111.8% | n/a (0.0%) | 100.0% (100.0%) |
| P28 | 144 | mixed-no-clear-pattern | 1.4% | 4.2% | 21.1% (13.2%) | 19.0% (54.9%) |
| P29 | 27 | mixed-no-clear-pattern | 7.4% | 14.8% | 66.7% (11.1%) | 54.2% (88.9%) |
| P30 | 46 | mixed-no-clear-pattern | 6.5% | 17.4% | 53.8% (28.3%) | 42.1% (41.3%) |
| P31 | 777 | mixed-no-clear-pattern | 0.8% | 2.3% | 20.2% (13.4%) | 23.0% (51.5%) |
| P32 | 16 | genre-pure | 6.2% | 18.8% | 100.0% (6.2%) | 66.7% (93.8%) |

## Caveats

- **Task 1 is primary-artist only**, same convention and same reasoning as `design/reports/measurement-artist_in_playlist.md`: a multi-artist track's candidate counts come from its first-listed artist only, not every credited artist.
- **Task 2's "artist top 3" share can exceed 100%.** `analyze.py`'s existing artist tally counts one vote per credited artist per track (unchanged here, reused as-is), so a track with several credited artists who are each independently frequent in the playlist is counted once per artist -- the top-3 *combined* share is a measure of "how much of the playlist involves these 3 names", not a partition of the playlist, and small playlists with heavily co-credited tracks can show a combined share well past 100%. "Artist top 1" cannot exceed 100% (one artist can only appear once per track) and is the more reliable of the two signals.
- **Playlist membership is a proxy** for both tasks, same caveat as `backtest.py`: a track can reasonably fit more than one playlist.
- **Task 2's language/genre reading is content-signal-only** (script, country default, MusicBrainz), matching `analyze.py`'s own deliberate choice to never use `language_playlists` here -- a playlist that itself teaches a language would otherwise trivially read back as 100% that language.
- **A named local detail file** (never commit it) can be produced with `--detail-out <path>`.
