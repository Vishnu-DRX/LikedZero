# Why SpotiSort can't get genre, popularity or audio features from Spotify

Settled 2026-09-27, so this doesn't get relitigated. Verified two ways: live-tested against our own registered
app (every one of `/artists` batch, `/audio-features`, `/albums` batch returned 403 just now; `popularity` is
absent from the track object entirely — see `spotify-api-explore/FINDINGS.md`), and traced to its root cause
via public sources below.

## The mechanism: Extended Quota Mode

Spotify apps run in one of two modes:
- **Development Mode** (the default, what SpotiSort's app is, and what any fork's app will be): capped at 5
  authorized users, and — since the Nov 2024 and Feb 2026 changes — cut off from `popularity`, artist
  `genres`, batch artist/album lookups, and the `audio-features`/`audio-analysis` endpoints entirely.
- **Extended Quota Mode**: unlimited users, higher rate limits, and — critically — **exempt from those
  restrictions**. Tools that already had this access before the cutoffs kept it; ours never had it and can't
  retroactively get it.

Confirmed straight from the maintainer of `exportify` (a popular Spotify-export tool that still shows genre,
popularity and full audio features today), in his own words:
> "I have had extended quota access since 2019. I was mildly freaked out when I saw they were changing things,
> but as far as I could tell, they weren't changing access for apps already granted the extension."
> — [pavelkomarov/exportify, Discussion #88](https://github.com/pavelkomarov/exportify/discussions/88)

**Why we can't get the same access:** as of May 2025, Spotify only grants Extended Quota Mode to an
established business with an active, launched service and **at least 250,000 monthly active users**
([Spotify's own Quota Modes docs](https://developer.spotify.com/documentation/web-api/concepts/quota-modes)).
A personal, fork-and-run tool has no path to that bar. This is a closed door, not a matter of finding the
right endpoint or asking the right way.

## Why Spotify did this

Reporting on the changes ([Medium: "Spotify's API Lock-Down"](https://medium.com/@apollinereymond/spotifys-api-lock-down-the-end-of-open-data-for-the-music-business-0a9bf07dba27),
[Substack: "Closing the Curtain"](https://thesoundbyte.substack.com/p/closing-the-curtain-spotifys-new), Aug
2026) gives Spotify's stated reasons as: preventing AI developers from scraping large datasets for training,
protecting user privacy, and safeguarding the listening-behavior data that powers Spotify's own recommendation
and playlist-curation engine from being used to build competing products for free. The commentary is skeptical
this is really about privacy or AI — major competitors (Apple Music, YouTube Music) have their own data and
aren't meaningfully affected — and reads it more as Spotify simply no longer giving away, for free, data that's
valuable to itself; small independent developers are the ones who actually lose access.

## What this means for SpotiSort

The design doesn't change: genre and language come from MusicBrainz plus the user's own playlist data (see
`IMPLEMENTATION_PLAN.md`'s Revision 2 errata and `design/proposals/artist_in_playlist.md`), because there is no
legitimate path to richer Spotify metadata for a project like this one, now or foreseeably.
