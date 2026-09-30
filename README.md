# LikedZero

A rules-based, fork-and-run tool that treats Spotify **Liked Songs as an inbox**. After a configurable number of
days, liked tracks are matched against your rules and **moved into playlists you already have**. It never
creates playlists unless a rule explicitly allows it. There is no backend and no schedule by default — you
start every run yourself (locally, via the dashboard's **Run now** button, or via the Actions tab).

## Status

The core sorter, safety machinery (dry-run, journal, verify, reconcile, restore),
MusicBrainz/script/playlist-based language enrichment, and the Pages site (Home, Setup guide, Configure,
Dashboard) are all built and covered by tests. `--apply` is available and guarded (see Safety guarantees
below). Scheduling is deliberately not enabled yet — see "Going unattended" below.

## Prerequisites

- Spotify Premium (required to create a Developer app). It cannot be verified via the API, so this is documentation only.
- Python 3.12+
- A GitHub account (and the `gh` CLI for the secrets step)

## Setup

The [Setup guide](https://vishnu-drx.github.io/LikedZero/setup/) on the Pages site walks through this with
copy buttons and "you should see" checks. In short:

1. Fork this repo.
2. In your fork's **Actions** tab, click "I understand my workflows, go ahead and enable them" — GitHub
   disables Actions on every new fork, so nothing below will run until you do this.
3. Create a Spotify Developer app at <https://developer.spotify.com/dashboard> with the redirect URI exactly
   `http://127.0.0.1:8888/callback`. Note the Client ID. No Client Secret is needed (PKCE).
4. Copy `.env.example` to `.env` and fill in `SPOTIFY_CLIENT_ID`.
5. `python -m pip install -r requirements.txt`
6. `python -m src.spotify_client --setup` opens the browser, captures the code on localhost:8888 and writes `SPOTIFY_REFRESH_TOKEN` to `.env`. Nothing secret is printed.
7. Optional live read-only check: `SPOTISORT_LIVE=1 python -m src.spotify_client --smoke` (PowerShell: `$env:SPOTISORT_LIVE=1` first).
8. `powershell scripts/set_secrets.ps1` once, to store the two Actions secrets (`SPOTIFY_CLIENT_ID`, `SPOTIFY_REFRESH_TOKEN`). The script reads `.env` locally and pipes the values to `gh` without echoing them.
9. In your fork's **Settings → Actions → General → Workflow permissions**, select **Read and write permissions** (lets a run commit its own logs), then **Settings → Pages**, source **Deploy from a branch**, branch `main`, folder `/docs`.

## Config

Build `config.yaml` with the form-based **Configure** page at `docs/builder/` (on GitHub Pages:
`https://<your-user>.github.io/LikedZero/builder/`), or copy `config.example.yaml` by hand. Configure
validates with the same rules as the sorter, previews the YAML live, imports an existing file, works offline
and can be installed as an app; nothing leaves your browser. It can also commit `config.yaml` straight to your
fork via **Save to GitHub** (a fine-grained token you create and control, kept in the browser tab only), or you
can download/copy it and commit it yourself. Supported match keys:

`artist_in`, `genre_contains`, `language_in`, `release_year_before`, `release_year_after`, `explicit`, `track_name_contains`, `album_name_contains`, `artist_in_playlist`, `any`, `artist_country_in`, `any_of`

- Conditions within a rule are ANDed.
- The first matching rule wins; a too-young match blocks rather than falling through to a broader later rule.
- Rules can be disabled.
- Each rule may set its own `days_threshold` and `target_position` (`top` or `bottom` of the target playlist).
- `artist_in_playlist: true` routes a song to whichever of your own playlists already holds most of that
  artist's tracks — no genre or language needed. Pair it with `target_playlist: auto` (the only valid target
  for this key); tune `artist_in_playlist.min_tracks`/`min_dominance` (defaults 3 / 0.9) and
  `exclude_playlists` (`Vault_drx` is always excluded, whether or not it's listed) at the top level of
  `config.yaml`. See `design/proposals/artist_in_playlist.md`.
- `any: true` matches unconditionally — the real catch-all. Put a rule using it last; everything above it is
  tried first, and it only catches what nothing else did.
- `artist_country_in: [IN, US, ...]` checks the primary artist's MusicBrainz/ISRC country (2-letter ISO codes;
  the same field already fetched for `enrichment.english_default`, no extra API calls). Like `country_default`,
  it's an exact field lookup but still a weak signal — informational, not something to rely on alone.
- `unless:` is an optional per-rule block, same match-key vocabulary as `match`, AND-combined among itself. If
  a rule's `match` passes AND its `unless` also fully passes, the rule is blocked — treated exactly like a
  non-match, so evaluation continues to the next rule (this is not the age-gate's hard stop). Cannot contain
  `artist_in_playlist` (its `auto` target only resolves from a rule's top-level `match`).
- `any_of: [...]` inside `match` is "OR within one rule": a list of match-condition groups (same vocabulary,
  each internally ANDed); the whole key passes if any one group passes, then ANDs with the rest of `match` as
  usual. A group cannot contain `artist_in_playlist` or nest another `any_of`. Also usable inside `unless`.
  See `design/proposals/more-conditions.md` for the full design writeup of these last three keys.
- `inbox_since` (a date) is optional for manual runs, but songs liked before it are never evaluated regardless
  of how a run is started — see "Going unattended" below.

Spotify no longer provides genres or a language field. Genre and language come from MusicBrainz, the title's
script, and language learned from your own playlists (`language_playlists` in config); expect them to be
best-effort, and check the dashboard's **Signals** view for measured precision per source.

## Try it (read-only)

- `python -m src.sync` previews what would move (dry-run; writes nothing, logs to `logs/`).
- `python -m src.analyze` drafts `config.draft.yaml` from your existing playlists (all rules disabled; review, then copy into `config.yaml`).
- `python -m src.enrich --report` measures genre/language coverage of your Liked Songs.
- `python -m src.backtest` simulates your rules against playlists you already sorted by hand, for a precision/recall estimate before ever running live.
- **See your own data:** commit `config.yaml`, then either click **Run now** on your Dashboard's Overview, or in your fork on GitHub open **Actions → Sync → Run workflow** (leave "Dry run" ticked). Once it finishes it commits `logs/*.json` back to your fork; your Pages site's Dashboard reads them straight from your fork in **Repo** mode. If you would rather not commit logs to a public repo, or want to see them immediately, use the Dashboard's **Open local files** source and drag your `logs/` folder in — nothing is uploaded, it never leaves your browser.

## Going unattended (schedules)

There is no `schedule:` trigger in `.github/workflows/sync.yml` yet, by design (nothing runs unless you start
it). Before ever enabling one:

1. Set `inbox_since` in `config.yaml` (Configure surfaces this, and the Overview shows whether it is set). This
   is the one guard that survives regardless of how a run is started — an unattended run cannot reach songs
   liked before it, no matter what selector it uses.
2. `--apply --allow-unselected` (what an unattended run needs, since a schedule can't supply `--newest`) is
   refused by `src/sync.py` itself unless `inbox_since` is set — this is enforced twice, once in the workflow
   and once in the tool, deliberately.
3. Add a `schedule:` trigger to `sync.yml` and set the repository variable `SPOTISORT_SCHEDULED_APPLY=true`.
   Until you do both, `IS_SCHEDULE`/`SPOTISORT_SCHEDULED_APPLY` logic already in the workflow stays dormant.

## How to read the dashboard

The dashboard is read-only: it cannot change Spotify, and it is part of the Pages site (there is no separate
local server to run for normal use). It has three data sources, and it always shows which one is active in a
label above the source picker:

- **Repo** (the default once the site is published on `*.github.io`) reads your fork's `logs/` folder straight from `raw.githubusercontent.com`. This needs `logs/*.json` to actually be committed, which the Sync workflow does for you (see "Try it" above).
- **Demo data** is the fixture data bundled with the site, for visitors who have not forked yet. It is the default everywhere else (e.g. running the site locally).
- **Open local files** is a drag-and-drop/file-picker area that reads `logs/*.json` files entirely in your browser via the File API — nothing is uploaded anywhere. Committed logs never carry a song's title, artist or Spotify URI unless `logging.include_track_names: true` is set (default is off, so public forks show counts and decisions only); Open local files is the only source that can show you real titles, since the files never leave your computer.

The source picker remembers your last choice. Every view shows when its data was made; a yellow banner appears
if it is more than 2 days old. Every view always renders its full content — there is no reduced Simple mode.

- **Overview** asks "is it healthy?": last run and its verdict, whether an inbox start date (`inbox_since`) is set, next scheduled run (or "Not scheduled"), liked songs, how many are pending, moves this week, errors and warnings, the safety verdict, and one sentence on what the next run would do. A **Run now** button dispatches the Sync workflow directly from here (via a token you create and control).
- **Inbox** asks "what is waiting, and why?": every liked song with its decision. Search, filter and sort it, then click a title to open the **Explain** drawer: each rule in order with passed and failed conditions, and the language and genre signals behind the decision.
- **Rules** asks "what does each rule do?": how many songs each rule matches and wins, when it last matched, and flags for problem rules.
- **Playlists** asks "can every target be written to?": found, missing, not writable or ambiguous, its size and how many songs the next run adds.
- **Runs** is the history, with a detail page per run — including the reconcile result, restore command and journal of removals for apply runs — and a side-by-side comparison of two runs.
- **Signals** asks "how far can each language signal be trusted?": coverage, and precision per signal and language.

The dashboard no longer has separate Safety or Backtest tabs: the reconcile/restore/journal detail they showed
lives in each apply run's detail page under **Runs**, and `python -m src.backtest` (precision/recall per
playlist, confusions, worst misroutes) is still a standalone command-line tool — its safety guarantees and
measurements are unchanged, only the dedicated dashboard tabs for them were removed.

Colours are never the only clue; every badge has a word. Green (ok) means fine, blue (info) means neutral
information such as a dry run or a song that is too young, amber (warning) means look at this, red means a
problem.

Language tiers: **Playlist** (learned from your own language playlists) and **Script** (the writing system of
the title) are trusted. **Hint** and **Country default** are guesses; they may drive a rule only when measured
at 90% precision or better ("qualified").

Terms: **Dead** rule: no song matches it. **Shadowed** rule: songs match, but an earlier rule always takes them
first. **Blocked** song: a rule would have matched, but only through a language signal that is not qualified.
**Withheld** signal: the language was found but hidden from the rules for that reason. **What-if**: a preview
in which disabled rules count as enabled; it is not what a normal run does. **Legacy library**: the data comes
from your old Liked Songs archive, not a live inbox.

## Safety guarantees

- Dry-run by default; `--apply` needs an explicit selector (`--newest`, `--only-uris`, or `--allow-unselected`
  for unattended runs only, which itself requires `inbox_since`).
- A `--max-moves` cap aborts a plan that's too big — and still writes an honest log (`aborted_too_many`) so the
  dashboard says so plainly, rather than silently disappearing.
- Journal before any removal; verify after every move; reconcile against the journal on each run; restore from
  the journal (`--restore`) if needed.
- Only `spotify:track:` URIs are touched. Only playlists you own or that are collaborative are written to.
- Committed public logs never carry a song's title, artist or URI by default (a bare URI resolves to a real
  song in one request, so it's stripped too) — only counts and decisions.

## Development

```
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m pytest tests/e2e -q -m e2e   # needs `playwright install`
```

Live tests are skipped unless `SPOTISORT_LIVE=1`.

## License

Open source — fork and run against your own Spotify Developer app and GitHub Actions secrets. No shared backend.
