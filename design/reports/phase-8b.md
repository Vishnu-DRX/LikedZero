# Phase 8b report — close the live-proof gap, enable the real rule set, run-now button, liked-songs guardian

Implementation session, 2026-09-27. Steps 1-4 of Master decisions 6, in order. No `--apply` was run by this
session (denied by `.claude/settings.json`; the user ran every live write themselves, as in the G2 report).
No song or playlist names beyond fixture/test fixtures appear in this report.

## 1. Verdict: **PASS** on all four steps

1. Decision 36 (close the live-proof gap) — PASS: `--restore` and `target_position: top` proven live, for the
   first time, against the disposable `SpotiSort Test` playlist only.
2. Decision 37 (real config) — PASS: `config.yaml` now runs Hindi -> Dil and Malayalam -> NewAgeMadrasMail at
   the default 14-day threshold; Japanese/English/catch-all stay disabled; a cloud dry-run re-ran afterward.
3. Decision 38 (cron stays manual) — PASS: no `schedule:` trigger added; verified below.
4. Decision 39 (Phase 8b) — PASS: run-now button (client-side `workflow_dispatch` via a fine-grained PAT) and
   the liked-songs vanished-song guardian (decision 16), sharing one PAT auth component for reuse by Phase 7.

## 2. Proof

### Step 1 — live proof of `--restore` and `top` (decision 36)
The user liked one throwaway song and ran the write commands themselves (I prepared the throwaway config and
commands, and never touched `--apply`):
```
config.local.yaml (gitignored, deleted after): one rule, target "SpotiSort Test", target_position: top,
days_threshold: 0, match: release_year_after: 1900 (matches anything)

$ python -m src.sync --apply --newest 1 --config config.local.yaml
-> logs/2026-09-27.json, mode: apply, verdict: ok, 1 journal entry
User confirmed in Spotify: song at the TOP of "SpotiSort Test", gone from Liked Songs.

$ python -m src.sync --restore logs/2026-09-27.json --apply --remove-from-target
User confirmed in Spotify: song back in Liked Songs, gone from "SpotiSort Test".
```
This is the first live proof of `--restore` and of `target_position: top`'s `position: 0` body field (both were
previously only proven against the in-memory simulator, see `phase-4-nonlive.md` and `phase-8a.md` §6). No real
target playlist was touched.

### Step 2 — real config, cloud dry-run (decision 37)
```
$ git diff (config.yaml): "Malayalam -> NewAgeMadrasMail" days_threshold: 0 override removed; "Hindi -> Dil"
  enabled=false -> true. Japanese/English/catch-all unchanged (disabled).
$ python -c "from src.config import load_config; load_config('config.yaml')"  -> config.yaml is valid
$ git push origin main                                                        -> 8c6da5f
$ gh workflow run sync.yml -f dry_run=true                                    -> run 36297998328
$ gh run watch 36297998328 --exit-status                                      -> success
```
The workflow's own "Commit run logs" step pushed a fresh `logs/latest-plan.json`/`logs/runs.json` (`ad2f56c`)
reflecting the two now-live rules; this session's local checkout was fast-forwarded to that commit before any
further work, so nothing here is built on stale data.

### Step 3 — cron (decision 38)
```
$ git diff HEAD~1 -- .github/workflows/sync.yml   -> no content change (line-ending noise only)
$ grep -c "^  schedule:" .github/workflows/sync.yml -> 0
```
`sync.yml` still declares only `workflow_dispatch`. The Overview will keep showing "Not scheduled" until a
`schedule:` trigger is deliberately added later.

### Step 4 — Phase 8b (decision 39)
```
$ python -m pytest -q                    -> 1525 passed, 2 skipped   (e2e deselected by default)
$ python -m pytest -q -m e2e             -> 175 passed, 2 skipped    (56 dashboard + run-now, site, builder)
```
New/changed tests: `tests/test_guardian.py` (9 cases: pure snapshot/compare logic, first-run baseline, a song
Spotify silently drops between two runs, and proof that a song the run itself moves is never misreported as
vanished). `tests/e2e/test_dashboard.py` gained 4 run-now cases (button gated on the Repo source; the connect
step's deep-link URL; full connect -> verify -> dispatch round trip incl. the "live run needs newest" client
guard; a rejected token's error message) and an updated Safety assertion (the placeholder text is gone; the
demo fixtures now carry one vanished-song example on the latest run to prove the real render path).

## 3. What was built

**Liked-songs guardian (decision 16)** — `src/guardian.py`: every run (dry or apply) snapshots the full Liked
Songs library (uri -> name/artists/added_at) to `.cache/liked-snapshot.json` (git-ignored; the workflow persists
it across runs via `actions/cache`, same always-miss/restore-keys-fallback trick as the enrichment cache — never
committed). On the next run, any uri the previous snapshot had that is gone now, and that *this run's own moves*
did not remove, is reported as vanished. Wired into `src/sync.py` (`run()`): `log["vanished"]` on every run log,
a `guardian:` warning when non-empty, `vanished` count added to `runs.json` entries (`src/artifacts.run_entry`),
and `redact_log` nulls vanished names/artists under the same titles-opt-out rule as `moved`/`journal`. Dashboard:
the Safety view's "Vanished-song warnings" placeholder (`phase-8a.md` §6) is now real — it reads the *latest*
run's log and shows either "None" or a table of vanished songs. `docs/dashboard/DATA.md` documents the new field.

**Run-now button + shared PAT auth component (decision 39)** — `docs/assets/github-pat.js`: deep-links to
`https://github.com/settings/personal-access-tokens/new` with `name`/`description`/`target_name`/`expires_in`
and `contents=write`/`actions=write` pre-filled via GitHub's documented URL parameters; GitHub has no URL
parameter for "only select repositories" + which repo (confirmed against GitHub's own docs and a community
report of the limitation), so the visitor still picks the repo by hand — the UI says so explicitly. The token
is held in `sessionStorage` only, keyed per `owner/repo`, verified with a `GET /repos/{owner}/{repo}` call before
being trusted. This is a shared component: Phase 7's config-commit feature will reuse it rather than building
its own token flow. `docs/dashboard/run-now.js` is the dialog logic (connect -> verify -> run form -> dispatch
via `POST /repos/{owner}/{repo}/actions/workflows/sync.yml/dispatches`), opened from a new "Run now" button on
Overview (only shown for the Repo data source) through the existing generic overlay system in `assets/ui.js`
(same mechanism as the glossary drawer). The run form mirrors `sync.yml`'s own inputs (dry run toggle, newest N,
max moves) and enforces the same "a live run needs newest" guard client-side before ever calling GitHub.
`docs/dashboard/data.js` gained `repoOwnerName()` to read `{owner, repo}` from the already-configured Repo
source, so run-now always targets the same repo the dashboard is already reading logs from.

**Fixtures** — `scripts/make_dashboard_fixtures.py` gained a `vanished` field per run spec and one demo
vanished-song entry on the latest run, so the Demo data source shows the guardian feature working, not just an
empty state. `docs/dashboard/fixtures/*.json` and the contract tests (`tests/test_dashboard_fixtures.py`)
regenerated/updated accordingly.

## 4. Deviations / questions for master
None. All four steps matched the brief; the one recorded deviation (G2's staged-protocol skip) was already
accepted as a one-off in Master decisions 6 and is not repeated here — step 1 *is* that staged protocol, run
post-hoc as instructed.

## 5. Risks & known gaps
- The guardian's baseline is empty on a fork's very first run (nothing to compare against), so a song that
  vanished *before* the first snapshot cannot be detected — expected, not a bug.
- Run-now's PAT flow is client-side only and untested against the real github.com token-creation page in this
  session (no browser available against the live site); the deep-link parameter names are taken from GitHub's
  own current documentation and changelog, not from a live click-through. Worth the master or user trying it
  once against a real fork before relying on it.
- `--max-moves` on a run-now dispatch is only as safe as `sync.yml`'s own guard (default 50, hard cap enforced
  server-side by `src/sync.py`); the dashboard does not duplicate that cap check client-side beyond passing the
  value through.

## 6. Next
Master's call on Phase 7 (GitHub write-back, reusing `github-pat.js`) vs. further hardening of 8b (e.g. a
`--restore-vanished` convenience command, mentioned as optional in decision 16 but not built here since the
brief only asked for the warning).
