# Proposal: `artist_in_playlist` match key

Status: **draft, awaiting master/user sign-off** — not implemented. Ranked #1 in decision 47's deferred list.

## The problem

83% of the real library (641 of 774 songs) has no resolved language, and genre coverage is only ~49% of
artists. Language and genre rules can only ever reach the minority of the library where those signals exist.
Meanwhile the strongest signal available was sitting unused for anything except deriving language: **which of
the user's own playlists an artist's other songs are already in.** If 12 of an artist's 14 songs already sit in
"Fuel", a new song by that artist is very likely also a "Fuel" song — no MusicBrainz call, no script detection,
no ambiguity about romanised titles.

This is also the single highest-value item precisely because it needs nothing new: `src/enrich.py` already
builds an artist → playlist membership table to learn `language_playlists`. This proposal generalizes that
table into a match key of its own.

## Schema change

New optional `match` key, usable like any other (AND-combined with the rest of the rule):

```yaml
- name: "Fuel regulars"
  match:
    artist_in_playlist: ["Fuel"]
  target_playlist: "Fuel"
```

`artist_in_playlist: [<playlist name>, ...]` — true if the track's artist (any credited artist, same
convention as `artist_in`) has at least `artist_in_playlist.min_tracks` existing tracks in **any** of the named
playlists. Playlist names are resolved the same way target playlists already are (owned/collaborative only).

Two new **global** config knobs (not per-rule, to keep the rule schema small):
```yaml
artist_in_playlist:
  min_tracks: 3      # an artist needs at least this many tracks already in the playlist to count (default 3)
  min_share: 0.5      # ...and they must make up at least this share of the artist's tracked-playlist tracks
```
`min_share` matters for an artist who is legitimately split across several playlists (e.g. half their catalogue
in "Fuel", half in "dusty tapes") — without it, the artist would match both and first-match-wins would pick
whichever rule happens to come first, silently.

## Semantics and edge cases

- **The target song itself is excluded** from its own artist's playlist counts (it's either already there, in
  which case it's a no-op via the existing `already_in_target` handling, or it's the new song being evaluated
  and must not vote for itself).
- **A song already liked and already in one of these playlists is not a special case** — it's just a track
  whose artist has 1+ tracks in that playlist; the rule fires or doesn't by the normal threshold.
- **Interacts with `inbox_since`/age gate exactly like every other key** — it's just another condition; the
  age gate still blocks first, per decision 2.
- **Interacts with `target_position`** normally — this is just a match key, not a target.
- **Backtest reuses this cleanly**: the existing backtest already treats "which playlist a track is really in"
  as ground truth, so `artist_in_playlist`'s own accuracy can be measured the same way every other signal was
  (leave-one-out by artist, as the language playlist precision numbers already do), before it ever reaches a
  real config.
- **Explain trace**: show "learned from N of the artist's M tracks already in <playlist>" — same
  sentence-first style as the language explain text, not a bare boolean.
- **Does not read `language_playlists`** — this is deliberately playlist-membership-general, not tied to the
  language feature. A playlist can be both a language source and an `artist_in_playlist` target; they're
  independent signals that happen to share the same underlying artist→playlist table.

## What I'd want proven before this goes live (mirrors how language signals were gated)

1. **Backtest precision/recall per playlist**, leave-one-out, same methodology as the existing signal-precision
   table — not assumed, measured, same as every other signal in this project.
2. **A `min_tracks`/`min_share` sensitivity sweep** (e.g. 2/0.4, 3/0.5, 5/0.6) on the real library, so the
   defaults aren't a guess.
3. **Explicit interaction check** against the already-live Hindi/Malayalam rules: does `artist_in_playlist`
   agree with, contradict, or overlap the language-learned rules for the same artists? A conflict should be
   visible in Configure (e.g. two enabled rules would both plausibly fire for the same artist) — this is
   exactly what the dashboard's existing shadowed-rule detection should already catch, but confirm it does.

## Why this over the other two ranked items

Q6 (proper catch-all) and Q3 (unmatched queue) are smaller, more mechanical changes with clear scope. This one
is ranked first anyway because it's the only one that actually *increases* how much of the library the tool can
safely sort — everything else improves quality or visibility of what's already reachable. Recommend building
this first, then Q6 (the catch-all is more useful once more of the library is being actively routed rather than
falling through to it), then Q3.

## Ask for the master/user

Sign-off needed on: the schema shape above, the two global defaults (3 tracks / 50% share), and the order
(this → Q6 → Q3). Once approved, implementation follows the same pattern as every other schema addition:
`config.py` + `validate.js` + parity tests together, then planner/rules_engine, then backtest measurement on
the real library *before* enabling any rule that uses it, mirroring how `english_default` was gated behind
measured precision.
