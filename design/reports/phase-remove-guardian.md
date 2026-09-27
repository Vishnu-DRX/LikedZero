# Phase: remove the liked-songs guardian entirely (Master decisions 9)

Decisions 48-49 (`design/BUILD_SPEC.md`): drop the liked-songs guardian feature (decision 16, built in Phase
8a/8b) completely, not just fix its wording, and not replace it with anything. Reasoning recorded by the
master: it structurally cannot distinguish an intentional un-like from Spotify silently dropping a song, its
`actions/cache` baseline evaporates after 7 days of inactivity, and the user's planned Liked-Songs reset to a
fresh, empty inbox would otherwise fire a ~774-song false alarm on its very first run.

This request arrived as a cross-session message from the "SpotiSort Master" design session (not a fresh
directive typed by the user directly into this session). Before acting, I pulled `main`, re-read
`design/BUILD_SPEC.md`, and confirmed decisions 48-49 there verbatim match what the cross-session message
described — so the removal below is executed against the binding spec, not against the peer message alone.

## 48. Remove every guardian/vanished reference

| Area | What was removed |
|---|---|
| `src/guardian.py` | Deleted entirely (snapshot load/save, `find_vanished`). |
| `src/sync.py` | `guardian` import, `--guardian-cache` CLI arg, `previous_snapshot` load, `vanished`/`guardian_baseline` computation, the `guardian: N song(s) no longer liked` warning, `guardian.save_snapshot` call, `log["vanished"]`/`log["guardian"]`, and the `vanished=` kwarg passed to `artifacts.run_entry`. |
| `src/artifacts.py` | `run_entry`'s `vanished` parameter and the `"vanished"` field in its returned dict (the `runs.json` count); `redact_log`'s vanished-redaction branch. |
| `docs/dashboard/views.js` (Safety view) | The whole "Vanished-song warnings" card, its `baseline`/`vanished` branches, and the now-unused `latestLogP` fetch that only existed to feed it. |
| `docs/dashboard/DATA.md` | `vanished` removed from the `runs.json` and per-run-log contracts; `guardian:{baseline:...}` field removed from the per-run-log contract. |
| `.github/workflows/sync.yml` | The "Restore guardian snapshot" `actions/cache` step (`.cache/liked-snapshot.json`, key `guardian-v1-*`). |
| `tests/test_guardian.py` | Deleted (the module it tested is gone). |
| `tests/test_sync_dry_run.py`, `tests/test_sync_apply.py` | `--guardian-cache` argv entries removed; the one assertion reading back `guardian.json`'s snapshot removed. |
| `tests/test_dashboard_fixtures.py` | `vanished`/`guardian` dropped from `RUN_KEYS`/`LOG_KEYS` contract sets. |
| `tests/e2e/test_dashboard.py` | The Safety-view assertion reading the vanished-song card removed. |
| `scripts/make_dashboard_fixtures.py` | `vanished=` fields on every `RUN_SPECS` entry and the latest-run spec, the `VANISHED_SONGS` sample-data dict, and the `"vanished"`/`"guardian"` keys written into each fabricated per-run log — all removed; fixtures regenerated (`python scripts/make_dashboard_fixtures.py`, byte-for-byte reproducible per the script's own docstring, confirmed by `test_fixtures_regenerate_identically`). |
| `README.md` | Status line, the Safety view description, and the Safety-guarantees bullet all dropped their guardian mentions. |
| `logs/*.json`, `logs/runs.json`, `logs/latest-plan.json` | Refreshed via a real local `python -m src.sync` dry-run (no writes; allowed under this project's own `--apply` deny rule) so the committed real artifacts match the new schema, not just the fixtures. |

Not touched, and correctly so: `src/apply.py`'s `res.aborted = "reconcile mismatch: song(s) vanished from Liked Songs..."` wording and its test assertions. That's the pre-existing, unrelated reconcile-mismatch path from cross-cutting rule 1 (a song the tool itself did not remove going missing *during* an apply run) — it predates the guardian feature and is not being removed.

### Grep proof (zero live hits)

```
grep -rIln "guardian\|vanished" --exclude-dir=.git --exclude-dir=.pytest_cache \
     --exclude-dir="design/reports" --exclude-dir="design/reviews" .
```
Result, after all edits and fixture/log regeneration:
```
./design/BUILD_SPEC.md                  <- decisions 48-49's own binding text, must stay
./design/proposals/artist_in_playlist.md <- one historical mention of the (now-removed) feature in prose
./logs/runs.json                        <- one old run entry (pre-dating this change) still carries a
                                            "vanished" key; nothing reads it any more (grep of docs/dashboard
                                            confirms), so it's inert history, not a dead code path
./src/apply.py                          <- unrelated wording, see above
./tests/test_apply.py                   <- tests for that unrelated wording
```
`design/reports/*.md` and `design/reviews/*.md` are excluded per the spec's own instruction (historical
record). No dashboard section, workflow step, or code path references the removed feature.

## 49. Quality gates re-run

```
python -m pytest -q
```
**1536 passed, 2 skipped, 213 deselected** (the 2 skips are the pre-existing live-only tests).

```
SPOTISORT_BROWSERS=chromium python -m pytest tests/e2e -q -m e2e
```
**211 passed, 2 skipped** (104s). Confirms the dashboard contract tests (`test_dashboard_fixtures.py`), the
Safety-view Playwright test, and the fork-genericness/PARITY suites all still pass with the new (smaller)
run-log and `runs.json` schemas.

## Deviations from the phase instruction

None. Decision 47's deferred items (`artist_in_playlist` etc.) were not touched, as instructed — the min_tracks
sweep it's waiting on is still outstanding and it is not approved to build.
