# Proposal: expand the match-key vocabulary

Status: **menu for the user to pick from — nothing here approved yet.** Current vocabulary (as of `config.py`):
`artist_in`, `genre_contains`, `language_in`, `release_year_before`/`after`, `explicit`,
`track_name_contains`/`album_name_contains`, plus the new `artist_in_playlist` (Master decisions 11).

Grouped by cost, since some of these are free (data already in hand) and some need new API calls or real
engineering. Recommend picking from Tier 1 first — same "measure before build" discipline as everything else in
this project, but these are cheap/mechanical enough that most don't need a backtest gate the way language/genre
signals did (they're exact fields from Spotify/MusicBrainz, not inferred signals with an error rate).

## Tier 1 — free: already fetched, just not exposed as a condition

| New key | What it checks | Source | Notes |
|---|---|---|---|
| `duration_seconds_before` / `duration_seconds_after` | Track length | Spotify `duration_ms`, already fetched | E.g. filter out short interludes/skits, or route long ambient tracks. |
| `artist_count_at_least` / `artist_count_at_most` | How many credited artists | Spotify `artists[]`, already fetched | A cleaner, more general version of "is this a collab" than text-matching "feat." in the title. |
| `album_type_in: [single, album, compilation]` | Spotify's own album classification | Spotify `album.album_type`, already fetched | E.g. route singles differently from album cuts. |
| `artist_country_in` | The artist's MusicBrainz/ISRC country | Already fetched for the `english_default` signal, just not exposed on its own | Useful when language itself doesn't resolve but region still might matter to you (e.g. "artist_country_in: [IN]"). Same precision caveat as country_default — weak, not a strong signal. |
| `artist_type_in: [person, group]` | Solo artist vs. band/group | Same MusicBrainz artist lookup already being made, one more field parsed out | Zero new API cost, it's in the same response. |

## Tier 2 — structural (not a new field, but more expressive rules)

| Feature | What it does |
|---|---|
| `unless:` exceptions | A rule can have a broad `match` plus a narrower `unless` that blocks it — e.g. "Hindi -> Dil, unless artist_in: [Arijit Singh]" (he has his own playlist). This is Q2 from the earlier review. |
| OR-groups within one rule | Right now, matching "A or B" means writing two separate rules. An `any_of: [...]` block inside `match` would let one rule express it directly. |

## Tier 3 — needs new MusicBrainz calls (real cost, same tradeoff as the skipped work/release-language lookup)

| New key | What it checks | Cost |
|---|---|---|
| `release_type_in: [live, remix, soundtrack, compilation]` | MusicBrainz's release-group secondary types | A second MusicBrainz call per album (not per artist), at the same 1/s rate limit — meaningfully slower enrichment, same tradeoff already declined once for work/release language. |

Most of what a title like "(Live)" or "(Acoustic)" would catch is already reachable today via
`track_name_contains`, without any new engineering — worth trying that first before paying for Tier 3.

## Ask for the user

Which of Tier 1 do you actually want? They're cheap enough to build several at once. Do you want `unless:`
exceptions now (Tier 2), given it's directly useful for cases like the Arijit Singh example? Tier 3 is a real
cost for a fairly narrow win — recommend skipping unless a specific need comes up.
