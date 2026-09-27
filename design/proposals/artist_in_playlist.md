# Proposal: `artist_in_playlist` match key (auto-routing)

Status: **built (2026-09-27, Master decisions 11/decision 54).** `config.py`/`validate.js`/parity tests,
`rules_engine`/`planner` resolution, the Configure UI, dashboard explain wording and a live backtest-
integration test (reproducing the measured precision with the shipped code) are all in. Ships in `config.yaml`
as a single draft rule, `enabled: false` -- the master/user turns it on after reviewing a dry-run. See
`design/reports/phase-artist_in_playlist.md` for the proof. Ranked #1 in decision 47's deferred list.

**User confirmation (2026-09-27):** this is genuinely valuable — several playlists are dedicated to one or two
artists (e.g. Linkin Park, 21 Pilots), which is exactly the overwhelming-margin case this mechanism is suited
to. 100% coverage is explicitly not the goal; reliable precision on whatever it can confidently catch is. The
general `min_tracks`-only sweep below undersold it by lumping single-artist-playlist cases in with weak,
narrowly-split ones — a margin requirement (decision 50) should separate them.

## The problem

83% of the real library (641 of 774 songs) has no resolved language, and genre coverage is only ~49% of
artists. Language and genre rules can only ever reach the minority of the library where those signals exist.
Meanwhile the strongest signal available was sitting unused for anything except deriving language: **which of
the user's own playlists an artist's other songs are already in.** If most of an artist's existing songs sit in
"Fuel", a new song by that artist is very likely also a "Fuel" song — no MusicBrainz call, no script detection,
no ambiguity about romanised titles, and it needs nothing new: `src/enrich.py` already builds the artist →
playlist membership table for `language_playlists`. This proposal generalizes that table into a routing
mechanism, not just a language source.

## Decisions made with the user (2026-09-27)

1. **Argmax, not a threshold-gated boolean.** Rather than the user writing one rule per target playlist
   (`artist_in_playlist: ["Fuel"]` → `target_playlist: "Fuel"`), one rule resolves the target **at run time**
   to whichever eligible playlist has the most existing tracks by the song's artist. This removes the need for
   a `min_share` tie-breaker between rules entirely — there's only one rule, and it either finds a clear winner
   or it doesn't.
2. **`Vault_drx` is permanently excluded** from the candidate set. The user is setting it aside; a separate,
   purpose-built catch-all playlist will be designated later (feeding into Q6's proper `fallback_playlist`,
   not this mechanism).
3. **The user plans to reset Liked Songs to empty** to start real operation on a clean inbox — this is what
   the fresh-inbox design (decisions 12-17) was already built for, not a new complication.

## Schema (simplified 2026-09-27 after the margin re-measurement)

The margin knob from the original design turned out to be redundant: once a per-artist *dominance* requirement
is added (this artist's tracked-playlist tracks are overwhelmingly in one place), a runner-up can't realistically
be close enough for margin to matter (confirmed empirically — margin 2.0 and 3.0 gave byte-identical results on
the single-playlist-artist subset in `design/reports/measurement-round-2.md`). One knob instead of two:

```yaml
artist_in_playlist:
  min_tracks: 3        # artist needs at least this many existing tracks somewhere, or the signal is too weak
  min_dominance: 0.9    # ...and that top playlist must hold at least this share of the artist's tracked-playlist tracks
  exclude_playlists: ["Vault_drx"]    # never a candidate "home", however many tracks by the artist it holds

rules:
  - name: "Route to artist's home playlist"
    match:
      artist_in_playlist: true
    target_playlist: auto             # resolved per song: the eligible playlist with the most existing tracks by this artist
```

- `artist_in_playlist: true` in `match` is the gate: does this artist have a clear home at all (see resolution
  below)? Everything else about *which* playlist is in the global `artist_in_playlist` block, since the target
  is computed, not authored per rule.
- `target_playlist: auto` is a new sentinel value, valid only when the rule's match includes
  `artist_in_playlist`. Any other rule keeps using a literal playlist name exactly as today.
- **Resolution:** among the user's owned/collaborative playlists, minus `exclude_playlists`, count the song's
  artist's existing tracks per playlist. If the top playlist has `>= min_tracks` tracks by the artist AND those
  tracks are `>= min_dominance` of the artist's total tracked-playlist tracks, that playlist is the target.
  Otherwise the rule does not match — the song falls through to later rules or is left unmatched, never routed
  by a guess.

## Semantics and edge cases

- **The song being evaluated never votes for itself** — counts come only from the artist's other, already-placed tracks.
- **Interacts with `inbox_since`/the age gate exactly like every other key** — just another condition; the age
  gate still blocks first, per decision 2.
- **Interacts with `target_position`** normally — this determines the target playlist, not the insert position.
- **Backtest reuses this cleanly**: the existing backtest already treats "which playlist a track is really in"
  as ground truth, so this can be measured the same leave-one-out way the language-playlist precision already
  is, before any rule using it goes live.
- **Explain trace**: "Routed to *Fuel* — the artist has 12 tracks there, more than any other playlist (next
  closest: 2)" — sentence-first, same style as the language explain text, not a bare boolean.
- **Independent of `language_playlists`**: a playlist can be both a language source and an
  `artist_in_playlist` candidate; they share the same underlying artist→playlist table but serve different
  match keys.

## Status: proven, approved to build (2026-09-27)

Measured (`design/reports/measurement-round-2.md`, Task 1): restricted to artists whose tracked-playlist tracks
are `>=90%` in one playlist, precision is **94.1%–98.4%** depending on `min_tracks` (2/3/5), comfortably above
the project's 90% bar, at meaningful recall (63.3% down to 39.2% of that subset). **Recommended default:
`min_tracks: 3`, `min_dominance: 0.9`** (95.8% precision, 47.7% recall of the qualifying subset) — a reasonable
middle point; `min_tracks: 2` (94.1%/63.3%) is the looser alternative if more recall is wanted.

Confirmed live against the real library (2026-09-27): all 6 playlists the audit flagged as artist-dominant
resolve to real, named artists (Anavae, Linkin Park, Queen, Twenty One Pilots, Klasey Jones, The Midnight) — see
`config.yaml`, which now has explicit `artist_in` rules for exactly these 6, added directly rather than waiting
on the dynamic mechanism, since they cost nothing and don't need to wait.

**Done (decision 55):**
1. Interaction/shadowing check: the dashboard's existing shadowed-rule detection generalizes to
   `artist_in_playlist` with no code change (it works off the generic explain trace); confirmed with a unit
   test (`tests/test_artifacts.py::test_auto_rule_shadowing_is_detected`) and a dashboard e2e test.
2. `Vault_drx` exclusion confirmed live: `tests/test_artist_in_playlist_live.py::test_vault_drx_is_never_an_auto_target_on_the_real_library`.
3. Backtest-integration proof: `tests/test_artist_in_playlist_live.py::test_shipped_artist_playlist_map_reproduces_measured_precision`
   runs the actual shipped `ArtistPlaylistMap` (not the standalone measurement script) against the real
   library and reproduces the measured 94.1%/95.8%/98.4% precision (min_tracks 2/3/5) within tolerance.

## Why this over the other two ranked items (Q6, Q3)

Q6 (proper catch-all) and Q3 (unmatched queue) are smaller, more mechanical changes with clear scope. This one
is ranked first anyway because it's the only one that actually *increases* how much of the library the tool can
safely sort — everything else improves quality or visibility of what's already reachable. Build order stays:
this → Q6 (more useful once more of the library is actively routed rather than falling through to a catch-all)
→ Q3.

## Operational note: emptying Liked Songs

The user intends to reset Liked Songs to empty before real operation begins — this is what the fresh-inbox
design (decisions 12-17) was already built for. (The guardian feature that would previously have raised a mass
false alarm over this reset has been removed entirely, see Master decisions 9 — no longer a concern.)

## Ask for the master/user

Sign-off needed on: the schema above (`target_playlist: auto`, the exclude list, the strict-max tie rule), the
`min_tracks` default before the sweep picks a final value, and the build order (this → Q6 → Q3). Once approved,
implementation follows the same pattern as every other schema addition: `config.py` + `validate.js` + parity tests together, then planner/rules_engine, then
backtest measurement on the real library *before* enabling any rule that uses it — mirroring how
`english_default` was gated behind measured precision.
