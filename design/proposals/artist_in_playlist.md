# Proposal: `artist_in_playlist` match key (auto-routing)

Status: **draft, awaiting final proof, design agreed with user 2026-09-27.** Ranked #1 in decision 47's
deferred list. Not implemented yet.

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

## Schema

```yaml
artist_in_playlist:
  min_tracks: 3                       # artist needs at least this many existing tracks somewhere, or the signal is too weak
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
  artist's existing tracks per playlist. If the top count is `>= min_tracks` and strictly greater than the
  second-highest count, that playlist is the target. Otherwise (below the floor, or an exact tie) the rule does
  not match — the song falls through to later rules or is left unmatched, never routed by a guess.

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

## What must be proven before this goes live (same bar as every other signal)

1. **Backtest precision/recall**, leave-one-out by artist, exactly like the language signal-precision table —
   measured, not assumed.
2. **`min_tracks` sensitivity sweep** (e.g. 2, 3, 5) on the real library, so the default isn't a guess.
3. **Explicit interaction check** against the live Hindi/Malayalam rules: for artists both signals would claim,
   does `artist_in_playlist` agree or conflict? The dashboard's existing shadowed-rule detection should surface
   any rule this one makes unreachable — confirm it actually does before enabling both.
4. **Confirm `Vault_drx` exclusion works** on the real library: assert no plan ever names it as an `auto` target.

## Why this over the other two ranked items (Q6, Q3)

Q6 (proper catch-all) and Q3 (unmatched queue) are smaller, more mechanical changes with clear scope. This one
is ranked first anyway because it's the only one that actually *increases* how much of the library the tool can
safely sort — everything else improves quality or visibility of what's already reachable. Build order stays:
this → Q6 (more useful once more of the library is actively routed rather than falling through to a catch-all)
→ Q3.

## Operational note: emptying Liked Songs

The user intends to reset Liked Songs to empty before real operation begins. The **guardian** (Phase 8b) will
report every one of the ~774 currently-liked songs as "no longer liked" the first run after that happens — this
is a large, correct, but noisy Safety-view entry for a deliberate reset, not a real alarm. Open question for
the master/user: add a one-time "acknowledge this reset" action so it doesn't read as a mass failure, or leave
it as a one-off warning to ignore. Not yet decided; flag before the reset happens.

## Ask for the master/user

Sign-off needed on: the schema above (`target_playlist: auto`, the exclude list, the strict-max tie rule), the
`min_tracks` default before the sweep picks a final value, the build order (this → Q6 → Q3), and the guardian
reset-acknowledgement question just above. Once approved, implementation follows the same pattern as every
other schema addition: `config.py` + `validate.js` + parity tests together, then planner/rules_engine, then
backtest measurement on the real library *before* enabling any rule that uses it — mirroring how
`english_default` was gated behind measured precision.
