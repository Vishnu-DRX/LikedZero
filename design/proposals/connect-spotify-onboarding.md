# Proposal (deferred): "Connect Spotify" browser-side onboarding (Option A)

Status: **written up, not approved to build.** Deferred in favor of Option B (Master decisions 12,
`design/BUILD_SPEC.md`), which ships first and reuses existing infrastructure.

## The idea

A "Connect Spotify" button on the site itself, separate from the GitHub PAT flow already built for
Save-to-GitHub/run-now. The browser does a PKCE login directly against Spotify (same pattern
`spotify_client.py --setup` already uses locally, ported to JS), reads the visitor's playlists live, and runs
the classification analysis entirely client-side — producing a draft config before the visitor has forked
anything, let alone set up GitHub Actions secrets. This would be the best possible first impression: see your
own personalized config on the homepage before committing to anything.

## Why it's deferred, not rejected

- **A new, separate OAuth surface.** Needs its own registered-app guidance (the visitor's Spotify Client ID,
  typed into the site — not secret, but a new field to explain), and a redirect URI added to their Developer
  app pointing at the hosted site, on top of the `127.0.0.1:8888/callback` one already needed for the local
  `--setup` step. Two redirect URIs to explain instead of one.
- **MusicBrainz genre lookups don't fit a browser tab.** ~15-25 minutes of rate-limited (1/s) sequential calls
  for a real library is a bad thing to ask a visitor to sit through in a tab. This mode would have to skip
  genre entirely and rely on artist/language classification only (fast — a handful of Spotify calls, no
  MusicBrainz needed at all), same limitation Option B's first pass has for a different reason (empty cache).
- **Real, if modest, new security surface to review** before shipping: a page that reads a chunk of a visitor's
  real Spotify library client-side, even read-only, is a bigger claim on trust than the existing
  download/paste-only Configure flow.

## What it would reuse

- The PKCE flow itself: port the already-proven logic from `spotify_client.py`'s `--setup`, not reinvent it.
- The same classification logic decision 56 puts into `analyze.py` — ideally one shared implementation (or a
  carefully parity-tested JS port, same discipline as `validate.js` mirroring `config.py`) rather than a third
  independent copy of the same heuristics.
- The existing Configure import path: the client-side draft would feed into the same "load as unsaved draft,
  review, then Save" flow Option B's "Import my draft" button already uses.

## Ask, when this is picked back up

Sign-off needed on: accepting the second redirect-URI setup step, the artist/language-only (no genre) scope for
a browser-side first pass, and whether this replaces or sits alongside Option B once both exist (recommendation:
alongside — Option B stays the "already forked, want a full re-analysis with genre" path; this becomes the
"haven't forked yet, curious what my config would look like" path).
