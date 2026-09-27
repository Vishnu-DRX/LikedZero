# Phase review-fixes report — Master decisions 8 (2026-09-27 end-to-end review)

Implementation session, 2026-09-27. Decisions 44, 45, 46, in that order, per the master's brief. Decision 47's
deferred items were not built (see §5, a short recommendation as the spec requires). No `--apply` of any kind
was run by this session.

## 1. Verdict: **PASS** on all three decisions

44. P1-3, P1-4, P1-5/6, P1-7 — all four fixed together, tested.
45. `inbox_since` — added, enforced in the planner regardless of selector, surfaced in Configure and the
    Overview, required for `--allow-unselected`; `SPOTISORT_SCHEDULED_APPLY` wired but dormant (no `schedule:`
    trigger added — decision 38 unchanged).
46. Hygiene — README/Setup guide rewritten, default branch derived instead of hardcoded, CSV formula-injection
    fixed, CI browser matrix now fails loudly on a missing browser, `.claude/settings.json` deny pattern
    hardened for reordered args.

## 2. Proof

```
$ python -m pytest -q                    -> 1546 passed, 2 skipped   (e2e deselected by default)
$ python -m pytest -q -m e2e             -> 211 passed, 2 skipped    (3-browser matrix confirmed working locally too, see decision 46 §6)
```
Quality gate suite (decision 30) re-run in full per the brief, since P1-4's redaction change touches committed
log shape: dashboard fixtures regenerated (`python scripts/make_dashboard_fixtures.py`), fixture contract
tests updated and passing, all e2e suites (dashboard/builder/site/github-save/fork-genericness) green.

## 3. Decision 44 — fix now, all four together

### P1-3: `TooManyMoves` now writes an honest log
`src/sync.py`: the abort no longer returns before writing anything. It falls through to the normal
write-artifacts path with `verdict: "aborted_too_many"`, an empty journal (nothing was ever journaled — the
raise happens before `apply_moves` touches anything), `moved: 0`/`moves_by_playlist: {}` in `runs.json`, and
the guardian snapshot still gets refreshed. `artifacts.run_entry` gained an `aborted` parameter so the
`runs.json` entry's own verdict computation can't independently compute "ok" for a run that never wrote
anything (it previously would have, since `moved=0` and `liked_before == liked_after` looks clean by
coincidence).
```
$ python -m pytest -q tests/test_sync_apply.py -k inbox_since_or_max_moves   -> covered by
  test_allow_unselected_above_max_moves_still_writes_an_honest_log: asserts logs/runs.json/guardian snapshot
  are all written, verdict is "aborted_too_many" in both, journal is empty, moved=0.
```

### P1-4: committed logs drop the uri too, not just title/artist
`redact_plan`/`redact_log` (`src/artifacts.py`) now also null the `uri` field everywhere it appears (`moved`,
`journal`, `vanished`, `latest-plan.json` songs) and empty `moved_uris`/`still_liked`. This breaks `--restore`
from the **committed** log (its journal no longer has real uris) — deliberately: the real journal now lives
only in a new git-ignored `logs/restore-journal.json` (`artifacts.restore_journal_payload`, written whenever
`mode == "apply"`), which the workflow uploads as its own Actions artifact (`Prepare journal for artifact
upload` step, rewritten to read this dedicated file instead of parsing it back out of the now-redacted day's
log). The dashboard's Safety view tells the visitor to download that artifact first, when `titles_hidden` is
set, instead of showing a restore command that can no longer work against the committed file.

Also fixed the "private Actions artifact" over-claim: the step's comment and `docs/dashboard/DATA.md` now say
plainly that a public repo's artifacts are downloadable by any *signed-in GitHub user*, not private. Configure
and the Setup guide's "counts and URIs only" copy is reworded to "counts and decisions only, no
song-identifying links" — now actually true.
```
$ python -m pytest -q tests/test_artifacts.py -k redact       -> 6 passed, incl. new
  test_redact_log_empties_moved_uris_and_still_liked and test_restore_journal_payload_is_a_valid_restore_argument
$ python -m pytest -q tests/test_workflows.py                 -> 16 passed, incl. new
  test_journal_artifact_comes_from_the_private_restore_journal_not_the_committed_log and
  test_journal_artifact_wording_is_not_overclaimed_as_private
```

### P1-5 + P1-6: the two token flows can no longer collide, and the token is shorter-lived
`docs/assets/github-pat.js`'s `get`/`set`/`clear` now key sessionStorage by `owner/repo` **and** the exact
scope set requested, so Configure's Contents-only token and run-now's Contents+Actions token live in different
slots even in the same tab — connecting one can never silently steal or 403-and-clear the other's slot.
`tokenUrl`'s default `expires_in` dropped from 90 to 7 days. `verify()` no longer trusts a bare
`GET /repos/{o}/{r}` (which succeeds for any valid token on a public repo regardless of its actual scope) —
it now checks `permissions.push` in the response body for Contents-write, and makes a real
`GET .../actions/workflows` call for Actions access, reporting the specific missing permission back to the
visitor.
```
$ python -m pytest -q -m e2e tests/e2e/test_dashboard.py -k run_now     -> 9 passed, incl. new
  test_run_now_token_url_defaults_to_a_7_day_expiry, test_run_now_verify_rejects_a_token_without_write_access,
  test_run_now_and_save_to_github_tokens_do_not_collide
$ python -m pytest -q -m e2e tests/e2e/test_github_save.py              -> 7 passed, incl. new
  test_save_to_github_verify_rejects_a_read_only_token, test_save_to_github_and_run_now_tokens_do_not_collide
```

### P1-7: the guardian distinguishes "no baseline" from "0 vanished", and stops sounding like an accusation
`guardian.load_snapshot` now returns `None` (not `{}`) when there's no baseline (first run, or the
`actions/cache` snapshot expired from 7 days' disuse) — `{}` now means "a real baseline that happened to have
0 songs", a genuinely different state. `sync.py` writes `log["guardian"] = {"baseline": "missing"|"ok"}`. The
Safety view shows a distinct neutral "No baseline yet" state instead of implying a clean bill of health it
didn't earn. The warning itself is reworded from "vanished... without SpotiSort removing them" to "no longer
liked (by you or Spotify)" — an intentional un-like is a normal action, not a loss, and must not read as one.
```
$ python -m pytest -q tests/test_guardian.py   -> 13 passed, incl. new
  test_load_snapshot_missing_file_means_no_baseline, test_third_run_with_nothing_vanished_reports_baseline_ok_not_missing
```

## 4. Decision 45 — `inbox_since`, then (dormant) `SPOTISORT_SCHEDULED_APPLY`

- **Config**: new key `inbox_since` (date or null), validated in `src/config.py` and `docs/builder/validate.js`
  (17 JS/Python parity cases pass, including malformed dates like `2026-02-30` that a naive regex would miss —
  both sides do real calendar validation).
- **Enforced in the planner, regardless of selector**: `build_plan` (`src/planner.py`) computes a hard floor
  from `config.inbox_since` and combines it with any `--since` selector (`max` of the two) — `--only-uris`,
  `--newest` and `--allow-unselected` all funnel through the same candidate list, so none can bypass it.
  `test_inbox_since_cannot_be_bypassed_by_a_wider_since_selector` proves a `--since` older than `inbox_since`
  does not widen the window.
- **Required for `--allow-unselected`**: `src/sync.py` refuses (exit 2) `--apply --allow-unselected` when
  `config.inbox_since` is `None`, before any Spotify client is even constructed.
- **Surfaced**: Configure gained an "Inbox start date" field (Basics step, native date input, schema-drawer
  entry); the Overview shows "Inbox since &lt;date&gt;" or a neutral "No inbox start date" callout;
  `latest-plan.json` carries the value at the top level.
- **`SPOTISORT_SCHEDULED_APPLY`**: `sync.yml`'s `Sync` step now branches on `github.event_name == 'schedule'`;
  when true and the repository variable `SPOTISORT_SCHEDULED_APPLY` is `true`, it passes
  `--apply --allow-unselected` (no `--newest`, since a schedule can't supply one) — which `src/sync.py` itself
  still refuses without `inbox_since`, a deliberate second line of defence. **`on:` has no `schedule:` trigger**
  (decision 38 unchanged), so `IS_SCHEDULE` is always false today and this logic is inert.
```
$ python -m pytest -q tests/test_config.py -k inbox_since        -> 8 passed
$ python -m pytest -q tests/test_planner.py -k inbox_since       -> 4 passed
$ python -m pytest -q tests/test_sync_apply.py -k inbox_since    -> 1 passed
$ python -m pytest -q -m e2e tests/e2e/test_builder.py -k "inbox_since or js_validator_matches"  -> 18 passed
$ python -m pytest -q tests/test_workflows.py -k schedule        -> 2 passed
  (test_sync_schedule_branch_requires_the_apply_variable_and_uses_allow_unselected,
   test_sync_has_no_schedule_trigger_yet)
```

## 5. Decision 46 — hygiene

- **README/Setup guide drift**: README rewritten top to bottom (was describing "Phase 1 done, nothing sorts
  yet" and "`--apply` is not available yet" — both long false). Setup guide gained the missing
  "enable Actions on your fork" step (GitHub disables Actions on every new fork; the old steps assumed it was
  already on), reworded "scheduled run" claims to match reality, and mentions **Save to GitHub** / **Run now**
  as alternatives to the manual download/Actions-tab flow.
- **Default branch**: `docs/dashboard/data.js`'s `deriveRepoBase()` now resolves the real default branch
  eventually-correctly (immediate "main" fallback, corrected and cached in sessionStorage for the *next* load
  — same pattern `shell.js`'s star count already uses, never blocks the current render).
  `docs/assets/github-pat.js`'s `verify()` now returns the real `default_branch` from its own authenticated
  repo GET (no extra request), which `run-now.js` uses as the workflow-dispatch `ref` instead of a hardcoded
  `'main'`. `builder/app.js`'s Contents API `PUT` now omits `branch` entirely — GitHub commits to the repo's
  actual default branch when it's left out, the same as the existing `GET` already relied on, so there was no
  need to track it there at all.
- **CSV formula injection**: `csvCell` (`docs/dashboard/views.js`) now prefixes a cell starting with `= + - @`
  with a literal `'`, so a hostile song title can't execute as a formula when the exported CSV opens in
  Excel/Sheets.
- **CI browser matrix**: `.github/workflows/e2e.yml` sets `SPOTISORT_BROWSERS=chromium,firefox,webkit`
  (was `auto`, which silently drops any browser that fails to launch and still reports green — locally that
  meant 2 passed, 175 skipped). Also fixed the underlying gap this depended on: `available_browsers`
  (`tests/e2e/conftest.py`) previously soft-skipped a missing browser in *either* mode; it now raises a clear
  `RuntimeError` naming the missing browser(s) when the list was explicit (not `auto`), so CI actually fails
  loudly instead of quietly shrinking coverage. Verified manually with
  `SPOTISORT_BROWSERS=chromium,not-a-real-browser` (see transcript; a real CI run will confirm on push).
- **`--apply` deny pattern**: `.claude/settings.json`'s deny entries changed from
  `Bash(python -m src.sync --apply:*)` (only matches `--apply` immediately after the command) to
  `Bash(python -m src.sync*--apply*)` (matches `--apply` anywhere in the argument list, e.g.
  `--config x.yaml --apply` or `--newest 3 --apply --max-moves 10`). This is a Claude Code permission-config
  change, not something `pytest` exercises; not automatically tested, flagged here for the master to spot-check
  if desired.
- **Not done** (explicitly marked "consider" in decision 46, not required): slimming the committed
  `latest-plan.json` (currently ~1.4 MB and growing). Left for a future pass once P1-4's approach (drop uri,
  keep everything else) is seen to hold up in practice.

## 6. Decision 47 — recommendation, not built

Per the spec, none of Q1–Q9 were implemented. Ranking the three the review itself ranked highest, for the
master's sign-off before any of this is scheduled:

1. **Q1 `artist_in_playlist`** — reuses the playlist-language-learning machinery already in `src/enrich.py`
   for a new match key, generalized beyond language. Highest value: covers most of the 83% of the library with
   no resolved language, needs no MusicBrainz, and should score very high precision in the backtest (the
   signal — "this artist's other songs already live here" — is stronger than anything else available).
2. **Q6 proper catch-all** — `fallback_playlist: {playlist, target_position}` or a `match: {any: true}` rule,
   dropping the `release_year_after: 1900` hack. Needed for the eventual Vault use case (decision 17) and is a
   small, contained schema change.
3. **Q3 unmatched-queue** — "Needs a rule: N songs older than 2x threshold" on the dashboard, reusing
   `analyze.py`'s existing per-playlist statistics to suggest one. Lower engineering cost than Q1/Q6 since it's
   presentation over data that mostly already exists, but only useful once there's something to point at.

Q2 (`unless:`), Q4 (`action: keep`), Q5 (`action: copy`), Q7 (`artist_id_in`), Q8 (digest), Q9 (re-like
handling) are all real but lower-value-per-effort than the above three, per the review's own ranking, and each
needs its own config.py + validate.js + parity tests (the schema is otherwise frozen) — recommend batching them
only after Q1/Q6/Q3 land and are seen to hold up.

## 7. What was built / changed (files)
- `src/artifacts.py`, `src/sync.py`, `src/guardian.py` — P1-3/P1-4/P1-7.
- `src/config.py`, `src/models.py`, `src/planner.py` — `inbox_since`.
- `docs/assets/github-pat.js`, `docs/dashboard/run-now.js`, `docs/builder/app.js` — P1-5/P1-6, default branch.
- `docs/dashboard/data.js`, `docs/dashboard/views.js`, `docs/dashboard/DATA.md` — uri redaction wording,
  guardian baseline UI, inbox_since surfacing, CSV fix, default-branch resolution.
- `docs/builder/index.html`, `docs/builder/schema.js`, `docs/builder/validate.js` — inbox_since field + parity.
- `.github/workflows/sync.yml` — abort logging already covered in sync.py; journal-artifact source, scheduled
  apply wiring (dormant), wording fixes.
- `.github/workflows/e2e.yml`, `tests/e2e/conftest.py` — explicit browser matrix, fail-loudly fix.
- `.claude/settings.json` — deny pattern hardening.
- `README.md`, `docs/setup/index.html` — drift fixes.
- `.gitignore` — `logs/restore-journal.json` never committed.
- Tests: `tests/test_artifacts.py`, `tests/test_guardian.py`, `tests/test_config.py`, `tests/test_planner.py`,
  `tests/test_sync_apply.py`, `tests/test_sync_dry_run.py`, `tests/test_workflows.py`,
  `tests/test_dashboard_fixtures.py`, `tests/e2e/test_dashboard.py`, `tests/e2e/test_builder.py`,
  `tests/e2e/test_github_save.py` — new/updated cases for every fix above.
- `scripts/make_dashboard_fixtures.py`, `docs/dashboard/fixtures/*.json` — regenerated for the new `guardian`
  field and `inbox_since` demo value.

## 8. Risks & known gaps
- `.claude/settings.json`'s hardened deny pattern is reasoned about, not automatically tested (no pytest
  coverage of Claude Code's own permission engine exists in this repo).
- The CI browser-matrix fail-loudly fix is verified locally by deliberately requesting a nonexistent browser
  name; the real `e2e` GitHub Actions run on this push **confirms it** — `gh run watch 36316760072`, all three
  browsers installed and passed (2m43s), plus `Tests` and `lighthouse` both green on the same push.
- `docs/dashboard/data.js`'s default-branch resolution is only eventually correct (first load on a non-`main`
  fork still briefly assumes `main` before the background fetch corrects it for the next load) — acceptable
  since Repo mode only ever *reads*, but worth knowing.
- Decision 47's items remain unbuilt by design; see §6 for the recommendation the spec asked for instead.
