# Dashboard data contract (all files are JSON, `"version": 1`)

The dashboard is static and part of the Pages site (decision 31: no localhost server in the product). It reads these
files from one of three *sources*: **Repo** (`https://raw.githubusercontent.com/<owner>/<repo>/main/logs/<file>`,
default once served from `*.github.io`), **Demo** (the bundled fixtures, for visitors), or **Open local files**
(a drag-and-drop/file-picker area that reads the same file names straight off disk via the File API, entirely
client-side — nothing is uploaded, and this is the only source that ever shows real song titles from a public fork,
since committed logs may have them redacted, see `titles_hidden` below). `python -m src.dashboard` still exists as a
niche developer convenience (serves the site plus `logs/` read-only on 127.0.0.1) but is not offered as a source in
the dashboard UI.
Every file carries `generated_at` (ISO-8601 UTC): show it as the **data-freshness stamp**; older than 2 days => warning banner.
Missing file => empty state that says which command produces it. Song/playlist names appear in the plan/detail files,
unless `titles_hidden` is set (see below).

## `runs.json` — rolling index (newest first, max 90)
`{version, generated_at, schedule:{cron, description, next_run}|null, runs:[{run_id, time, mode ("dry_run"|"apply"), what_if, planned_moves, moved, too_young, no_match,
blocked, target_problems, errors, warnings, liked_before, liked_after, duration_seconds,
started_at, finished_at, scheduled_for|null, workflow_started_at|null, trigger ("schedule"|"workflow_dispatch"|null), verdict ("dry_run"|"ok"|"mismatch"|"error"),
rule_counts:{rule_name: wins}, moves_by_playlist:{playlist_name: n}, log:"YYYY-MM-DD.json"}]}`
Timing (all UTC ISO; the dashboard shows each in IST and UTC): `time` = `started_at` = when `src.sync` started,
`finished_at` = when it wrote the log, `scheduled_for` = the schedule slot the run claimed (null for manual/local runs),
`workflow_started_at` = when GitHub fired the workflow run (`github.run_started_at`), so `scheduled_for` to
`workflow_started_at` is GitHub's own delay. Runs recorded before this existed lack these keys; the dashboard falls back to `time` + `duration_seconds`.
The per-run log carries the same five timing keys at top level.
`schedule` is written by `src.sync` from `config.yaml`'s `schedule:` block (or the legacy cron variable). The Overview
shows a "Next run" card only when it holds a time or description; absent = unknown (no card, no claim), `null` = sync
found no enabled schedule (no card; the "what happens next" sentence says no automatic runs are set up).
`moves_by_playlist` is what the run moved (a dry run: would move), used for the one-line run summary.

## `YYYY-MM-DD.json` — per-run log (fetched on demand from `runs[].log`)
`{date, run_id, mode, dry_run, what_if, evaluated, moved:[{track, artist, uri, playlist, playlist_id, rule, matched, age_days,
threshold_days, already_in_target, original_added_at, target_position}], skipped_no_match, skipped_too_young:[...],
skipped_playlist_missing:[{track,target_playlist,rule,reason,would_create}], errors:[str], warnings:[str],
journal:[{uri,name,artists,original_added_at,target_playlist_id}], liked_before,
liked_after, verdict, rule_counts, config_hash, plan_counts, http_audit:{"GET api.spotify.com":n,...}, runtime_seconds,
titles_hidden (present+true when logging.include_track_names is false on a GitHub Actions run: track/artist AND uri
fields on `moved`/`journal` are null, `moved_uris`/`still_liked` are emptied -- P1-4, 2026-09-27 review: a
bare uri resolves to a real song in one request, so hiding titles alone was not private; local runs always keep
everything, and the real journal for `--restore` survives separately in the git-ignored `restore-journal.json`)}`
Apply runs (Phase 4) add `reconcile:{expected_after, actual_after, ok}`, `restore_command` (string), `batches:[{playlist_id, size, committed}]`.

## `latest-plan.json` — inbox snapshot
`{version, generated_at, run_id, mode, what_if, inbox_kind ("legacy_library"|"fresh_inbox": src.sync writes "fresh_inbox" when
`inbox_since` is set, else "legacy_library"; the dashboard shows its "whole library is in scope" banner only for
"legacy_library" WITHOUT an `inbox_since`, so older plan files still labelled legacy stay quiet),
config_hash, liked_total,
default_days_threshold, english_default, inbox_since:"YYYY-MM-DD"|null (decision 45/P1-2: songs liked before this
are never evaluated by any selector; shown on Overview, required before --allow-unselected), counts:{will_move,too_young,no_match,target_problem,blocked},
rules:[{name, enabled, target_playlist, target_position ("top"|"bottom"), threshold_days, conditions:{key:value},
unless:{key:value} (empty mapping = no exceptions; design/proposals/more-conditions.md), uses_language,
weak_signals_possible:[..], would_match, wins, target_status ("resolved"|"missing"|"not_writable"|"ambiguous"|"dynamic"),
status ("ok"|"dead"|"shadowed"|"disabled")}],
playlists:[{name, status, size, planned_in, rules:[rule names]}] (a rule whose `target_playlist` is the
`artist_in_playlist` sentinel `"auto"` -- design/proposals/artist_in_playlist.md -- never appears here: there
is no single fixed target to report on; its per-song resolved target still appears under the real playlist
name via `songs[].target_playlist` and `artist_routing` below),
songs:[{title, artists:[..], uri, added_at, age_days, decision ("will_move"|"too_young"|"no_match"|"target_problem"|"blocked"),
reason, rule|null, target_playlist|null (already the RESOLVED real name for an artist_in_playlist match, never
the literal "auto"), target_status|null, eligible_on|null, target_position|null,
language:{value|null, source ("playlist"|"script"|"hint"|"country_default")|null, confidence 0..1|null, used_for_rules:bool, withheld:{language,source,precision,samples,reason}|null},
genres:{values:[..], source|null, confidence|null},
artist_routing:{playlist, track_count, artist_total}|null (design/proposals/artist_in_playlist.md: set whenever
this song's artist has a resolved "home" playlist under the config's `artist_in_playlist.min_tracks`/
`min_dominance`, regardless of whether an artist_in_playlist rule was the one that actually decided the song;
`track_count`/`artist_total` are N of M -- the artist's tracks already in `playlist` vs. across every candidate
playlist -- leave-one-out, so this song's own membership, if any, is never counted),
titles_hidden (present+true on a titles-redacted snapshot: title/artists/uri are null; open local files to see them),
explain:{trace:[{rule, enabled, threshold_days, conditions:[{key,wanted,actual,passed}],
  unless_conditions:[{key,wanted,actual,passed,hit}] (present only when this rule's own match passed and it has
  an `unless` block; design/proposals/more-conditions.md), blocked_reason (present only on "blocked_by_exception",
  a short human string e.g. "blocked by exception: artist_in matched Arijit Singh"),
  result ("matched"|"matched_too_young"|"failed"|"not_reached"|"not_reached_but_would_match"|"blocked_by_exception"|
  "skipped_disabled"|"skipped_empty")}],
  decided_by|null, age_days}}]}`
Rule `status`: `dead` = no song would match it; `shadowed` = songs would match but an earlier rule always wins; `disabled`.
`mode` matters: after a real run (`"apply"`) this file is the inbox as it was when that run STARTED (before the moves),
so the dashboard takes "songs waiting now" from that run's `liked_after` in `runs.json`, not from `liked_total`/`counts`.
`what_if:true` means disabled rules were treated as enabled (preview) — show a clear banner. Rule `target_status`
`"dynamic"` is specific to an `artist_in_playlist` rule's `target_playlist: "auto"` -- there is nothing to
resolve at the rule level, only per song.

## Not read by the dashboard
`enrichment-coverage.json` (`python -m src.enrich --report`), `signal-precision.json` and `backtest.json` /
`backtest-detail.json` / `backtest-detail.md` (`python -m src.backtest`) are still real command-line outputs, but the
dashboard has no Signals or Backtest view any more, so they are not part of this contract and the dashboard never
reads them. (`src.sync` itself still reads `logs/signal-precision.json` to decide which weak language signals may
drive a rule.)
