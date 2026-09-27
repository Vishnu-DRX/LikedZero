# Measurement: `artist_in_playlist` min_tracks sweep (counts only)

Standalone proof-gathering for `design/proposals/artist_in_playlist.md`, run via `python -m src.measure_artist_in_playlist`. Not wired into config.py/validate.js/planner -- this feeds a master sign-off decision, nothing here changed the schema or built a rule.

**Library:** 2678 unique tracks across 31 candidate playlists (owned/collaborative, non-empty, the `SpotiSort Test` playlist and the playlist(s) this proposal permanently excludes excluded). Playlists are labelled P01.. by name order; no song, artist or playlist name appears in this file (see the caveats section for what that means for this measurement, and how to get a named detail file locally).

## Sweep

### Aggregate

| min_tracks | tracks | coverage | tie-rate (of covered) | predicted | correct | precision | recall |
|---|---|---|---|---|---|---|---|
| 2 | 2678 | 27.8% | 2.7% | 724 | 556 | 76.8% | 20.8% |
| 3 | 2678 | 21.5% | 0.5% | 572 | 453 | 79.2% | 16.9% |
| 5 | 2678 | 15.2% | 0.0% | 406 | 329 | 81.0% | 12.3% |

`skipped_no_artist` (tracks with no credited artist, excluded from every row above): min_tracks=2: 0, min_tracks=3: 0, min_tracks=5: 0

### Per playlist

#### min_tracks = 2

| playlist | true tracks | coverage | tie-rate | predicted | tp | precision | recall |
|---|---|---|---|---|---|---|---|
| P01 | 66 | 28.8% | 0.0% | 22 | 17 | 77.3% | 25.8% |
| P02 | 28 | 100.0% | 0.0% | 29 | 28 | 96.5% | 100.0% |
| P03 | 28 | 0.0% | n/a | 1 | 0 | 0.0% | 0.0% |
| P04 | 18 | 44.4% | 0.0% | 0 | 0 | n/a | 0.0% |
| P05 | 28 | 67.9% | 0.0% | 19 | 18 | 94.7% | 64.3% |
| P06 | 5 | 80.0% | 0.0% | 5 | 4 | 80.0% | 80.0% |
| P07 | 20 | 100.0% | 0.0% | 21 | 20 | 95.2% | 100.0% |
| P08 | 144 | 36.1% | 5.8% | 53 | 46 | 86.8% | 31.9% |
| P09 | 216 | 33.8% | 1.4% | 62 | 29 | 46.8% | 13.4% |
| P10 | 12 | 58.3% | 0.0% | 0 | 0 | n/a | 0.0% |
| P11 | 237 | 22.4% | 5.7% | 60 | 46 | 76.7% | 19.4% |
| P12 | 14 | 100.0% | 0.0% | 14 | 14 | 100.0% | 100.0% |
| P13 | 57 | 17.5% | 0.0% | 10 | 10 | 100.0% | 17.5% |
| P14 | 11 | 90.9% | 0.0% | 13 | 10 | 76.9% | 90.9% |
| P15 | 63 | 23.8% | 20.0% | 9 | 7 | 77.8% | 11.1% |
| P16 | 101 | 36.6% | 8.1% | 35 | 29 | 82.9% | 28.7% |
| P17 | 73 | 16.4% | 0.0% | 7 | 6 | 85.7% | 8.2% |
| P18 | 26 | 23.1% | 0.0% | 0 | 0 | n/a | 0.0% |
| P19 | 1 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P20 | 30 | 30.0% | 0.0% | 12 | 8 | 66.7% | 26.7% |
| P21 | 9 | 11.1% | 0.0% | 0 | 0 | n/a | 0.0% |
| P22 | 12 | 100.0% | 0.0% | 15 | 12 | 80.0% | 100.0% |
| P23 | 470 | 44.9% | 0.9% | 219 | 158 | 72.2% | 33.6% |
| P24 | 35 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P25 | 50 | 22.0% | 0.0% | 7 | 6 | 85.7% | 12.0% |
| P26 | 199 | 51.8% | 1.0% | 89 | 66 | 74.2% | 33.2% |
| P27 | 17 | 94.1% | 0.0% | 16 | 16 | 100.0% | 94.1% |
| P28 | 144 | 4.9% | 0.0% | 0 | 0 | n/a | 0.0% |
| P29 | 27 | 3.7% | 0.0% | 0 | 0 | n/a | 0.0% |
| P30 | 46 | 13.0% | 0.0% | 6 | 6 | 100.0% | 13.0% |
| P31 | 16 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |

#### min_tracks = 3

| playlist | true tracks | coverage | tie-rate | predicted | tp | precision | recall |
|---|---|---|---|---|---|---|---|
| P01 | 66 | 24.2% | 0.0% | 19 | 14 | 73.7% | 21.2% |
| P02 | 28 | 100.0% | 0.0% | 29 | 28 | 96.5% | 100.0% |
| P03 | 28 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P04 | 18 | 33.3% | 0.0% | 0 | 0 | n/a | 0.0% |
| P05 | 28 | 53.6% | 0.0% | 15 | 15 | 100.0% | 53.6% |
| P06 | 5 | 80.0% | 0.0% | 5 | 4 | 80.0% | 80.0% |
| P07 | 20 | 100.0% | 0.0% | 21 | 20 | 95.2% | 100.0% |
| P08 | 144 | 23.6% | 0.0% | 40 | 34 | 85.0% | 23.6% |
| P09 | 216 | 29.2% | 0.0% | 50 | 29 | 58.0% | 13.4% |
| P10 | 12 | 58.3% | 0.0% | 0 | 0 | n/a | 0.0% |
| P11 | 237 | 13.5% | 0.0% | 39 | 28 | 71.8% | 11.8% |
| P12 | 14 | 100.0% | 0.0% | 14 | 14 | 100.0% | 100.0% |
| P13 | 57 | 12.3% | 0.0% | 7 | 7 | 100.0% | 12.3% |
| P14 | 11 | 90.9% | 0.0% | 13 | 10 | 76.9% | 90.9% |
| P15 | 63 | 12.7% | 0.0% | 6 | 4 | 66.7% | 6.3% |
| P16 | 101 | 31.7% | 9.4% | 28 | 26 | 92.9% | 25.7% |
| P17 | 73 | 4.1% | 0.0% | 0 | 0 | n/a | 0.0% |
| P18 | 26 | 15.4% | 0.0% | 0 | 0 | n/a | 0.0% |
| P19 | 1 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P20 | 30 | 16.7% | 0.0% | 7 | 5 | 71.4% | 16.7% |
| P21 | 9 | 11.1% | 0.0% | 0 | 0 | n/a | 0.0% |
| P22 | 12 | 100.0% | 0.0% | 15 | 12 | 80.0% | 100.0% |
| P23 | 470 | 35.1% | 0.0% | 169 | 127 | 75.1% | 27.0% |
| P24 | 35 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P25 | 50 | 4.0% | 0.0% | 0 | 0 | n/a | 0.0% |
| P26 | 199 | 44.2% | 0.0% | 79 | 60 | 75.9% | 30.1% |
| P27 | 17 | 94.1% | 0.0% | 16 | 16 | 100.0% | 94.1% |
| P28 | 144 | 3.5% | 0.0% | 0 | 0 | n/a | 0.0% |
| P29 | 27 | 3.7% | 0.0% | 0 | 0 | n/a | 0.0% |
| P30 | 46 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P31 | 16 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |

#### min_tracks = 5

| playlist | true tracks | coverage | tie-rate | predicted | tp | precision | recall |
|---|---|---|---|---|---|---|---|
| P01 | 66 | 24.2% | 0.0% | 19 | 14 | 73.7% | 21.2% |
| P02 | 28 | 100.0% | 0.0% | 29 | 28 | 96.5% | 100.0% |
| P03 | 28 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P04 | 18 | 27.8% | 0.0% | 0 | 0 | n/a | 0.0% |
| P05 | 28 | 21.4% | 0.0% | 6 | 6 | 100.0% | 21.4% |
| P06 | 5 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P07 | 20 | 100.0% | 0.0% | 21 | 20 | 95.2% | 100.0% |
| P08 | 144 | 14.6% | 0.0% | 23 | 21 | 91.3% | 14.6% |
| P09 | 216 | 20.8% | 0.0% | 43 | 24 | 55.8% | 11.1% |
| P10 | 12 | 41.7% | 0.0% | 0 | 0 | n/a | 0.0% |
| P11 | 237 | 5.1% | 0.0% | 14 | 10 | 71.4% | 4.2% |
| P12 | 14 | 100.0% | 0.0% | 14 | 14 | 100.0% | 100.0% |
| P13 | 57 | 12.3% | 0.0% | 7 | 7 | 100.0% | 12.3% |
| P14 | 11 | 90.9% | 0.0% | 13 | 10 | 76.9% | 90.9% |
| P15 | 63 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P16 | 101 | 20.8% | 0.0% | 21 | 21 | 100.0% | 20.8% |
| P17 | 73 | 4.1% | 0.0% | 0 | 0 | n/a | 0.0% |
| P18 | 26 | 7.7% | 0.0% | 0 | 0 | n/a | 0.0% |
| P19 | 1 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P20 | 30 | 0.0% | n/a | 1 | 0 | 0.0% | 0.0% |
| P21 | 9 | 11.1% | 0.0% | 0 | 0 | n/a | 0.0% |
| P22 | 12 | 100.0% | 0.0% | 15 | 12 | 80.0% | 100.0% |
| P23 | 470 | 25.3% | 0.0% | 122 | 93 | 76.2% | 19.8% |
| P24 | 35 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P25 | 50 | 2.0% | 0.0% | 0 | 0 | n/a | 0.0% |
| P26 | 199 | 26.6% | 0.0% | 42 | 33 | 78.6% | 16.6% |
| P27 | 17 | 94.1% | 0.0% | 16 | 16 | 100.0% | 94.1% |
| P28 | 144 | 2.8% | 0.0% | 0 | 0 | n/a | 0.0% |
| P29 | 27 | 3.7% | 0.0% | 0 | 0 | n/a | 0.0% |
| P30 | 46 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |
| P31 | 16 | 0.0% | n/a | 0 | 0 | n/a | 0.0% |

## Interaction check: agreement with the live Hindi/Malayalam rules

For tracks the live `Hindi -> Dil` / `Malayalam -> NewAgeMadrasMail` rules would already match (playlist-learned language, leave-one-out): does `artist_in_playlist`'s prediction at this min_tracks point at the *same* playlist (agree), a *different* eligible playlist (conflict), or make no prediction at all?

| min_tracks | language | would-match | agree | conflict | no prediction |
|---|---|---|---|---|---|
| 2 | hindi | 122 | 53 | 2 | 67 |
| 2 | malayalam | 102 | 35 | 11 | 56 |
| 3 | hindi | 122 | 40 | 0 | 82 |
| 3 | malayalam | 102 | 28 | 9 | 65 |
| 5 | hindi | 122 | 23 | 0 | 99 |
| 5 | malayalam | 102 | 21 | 0 | 81 |

## Read (not a decision -- for the master to weigh)

As min_tracks rises, coverage falls and precision should rise (fewer, more confident candidates) unless the tie-rate dominates instead -- read the table above for the real shape on this library rather than trusting this one-line summary. Numbers: min_tracks=2: coverage 27.8%, precision 76.8%, recall 20.8%, tie-rate 2.7%; min_tracks=3: coverage 21.5%, precision 79.2%, recall 16.9%, tie-rate 0.5%; min_tracks=5: coverage 15.2%, precision 81.0%, recall 12.3%, tie-rate 0.0%. Of the three swept values, 5 has this run's best precision (ties broken by coverage) -- that is a starting point for the master's judgment call, not a recommendation to ship it, since precision alone ignores how much of the library each threshold actually reaches.

## Caveats

- **Primary-artist only.** A multi-artist track's candidate counts come from its first-listed artist only, not every credited artist (unlike `language_playlists`, which votes for all credited artists). This avoids a collab track's counts inflating two different artists' "home" playlists under one shared count table; it also means a track by an artist known mainly as a featured credit may be undercounted. Worth re-measuring with an all-credited-artists variant before sign-off if collabs turn out to be a large share of conflicts/misses.
- **Playlist membership is a proxy for "true home"**, same caveat as `backtest.py`: a track can reasonably fit more than one playlist, so a "conflict" or "miss" here is not necessarily wrong in a way a human would agree with.
- **Coverage/tie-rate here are conditional**: coverage = fraction of tracks where *some* candidate playlist's count reaches min_tracks at all; tie-rate = fraction *of those* where the top was tied (not a fraction of the whole library) -- this isolates "the floor wasn't met" from "the floor was met but the tie rule vetoed it".
- **This file intentionally omits playlist names** per the task instructions. A named detail file for local reference only (never commit it) can be produced with `--detail-out <path>`.

