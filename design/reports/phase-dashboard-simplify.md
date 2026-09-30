# Phase: drop Simple/Detailed mode; remove Backtest and Safety as dashboard tabs (Master decisions 16)

User instruction (verbatim, per decision 16): *"remove detailed mode in dashboard, just show all tabs
regardless and remove backtest and safety tabs."* This is a **dashboard UI change only**. It does not touch
`src/apply.py`'s journal/reconcile/restore safety mechanism, does not touch `src/backtest.py` as a tool, and
does not change how `logs/*.json` are written — confirmed by `git diff --stat` (§4) showing zero touches to
either file. Dashboard goes from 8 views to 6: **Overview, Inbox, Rules, Playlists, Runs, Signals**.

## 0. Method

Read every file that could plausibly reference the removed feature before editing, not just the two named
tabs: `docs/dashboard/{index.html,app.js,data.js,views.js,dashboard.css,DATA.md}`, `docs/sw.js` (precache
list), `docs/index.html`/`docs/setup/index.html` (marketing copy), `README.md`, `lighthouserc.json`, both
dashboard-fixture-generating scripts (`scripts/make_dashboard_fixtures.py`) and their test
(`tests/test_dashboard_fixtures.py`), and the full `tests/e2e/test_dashboard.py`. Grepped for `backtest` and
`safety` (case-insensitive) across `docs/` and `tests/` after every edit pass, and separately for
`simple`/`detailed`/`mode-toggle`/`mode-callout`, to catch references the task description didn't explicitly
name (e.g. `docs/sw.js`'s precached fixture list, `lighthouserc.json`'s `mode=detailed` Lighthouse URL,
`scripts/make_dashboard_fixtures.py`'s backtest-fixture generator). Every remaining hit after the final pass
was individually confirmed to be either a different, legitimate use of the same English word ("safety
verdict" KPI card, "safety check" in the glossary, `test_workflows.py`'s unrelated docstring) or historical
record in `design/reports/`/`design/reviews/` (left untouched, per this project's standing convention).

## 1. Remove the Simple/Detailed mode toggle (decision 67)

**`docs/dashboard/index.html`**: removed the `.mode-bar`'s `<label class="switch">` (the toggle input, its UI
span, and label text) and the entire `#mode-callout` banner block (icon, "Switch to Detailed" button, dismiss
button). The Glossary button — a real dashboard feature, unrelated to the mode toggle — stays, now the only
thing in that row. Also resized the static first-paint skeleton from 4 KPI cards to 7: with Simple mode gone,
Overview's real card count is always 7 (it used to vary 4 vs 7 depending on mode), so the zero-JS skeleton that
exists purely to avoid a CLS jump on first paint needed to match the one shape that now always renders.

**`docs/dashboard/app.js`**: removed `modeToggle`/`modeCallout`/`modeCalloutSwitch`/`modeCalloutDismiss`
element refs, the entire "Simple/Detailed mode" block (`SIMPLE_HIDDEN_VIEWS`, `qsMode`/`storedMode`/
`modeChosen`/`mode` state, `dismissModeCallout()`, `applyMode()`, their three event listeners), `buildTabs()`'s
mode-based filtering (now always renders `VW.ORDER` in full), `render()`'s mode-based redirect-to-overview
guard and `mode: mode` context field, and `loadingSkeleton()`'s mode-conditional card count (now a flat `7`).

**`docs/dashboard/views.js`**: removed every `if (ctx.mode === 'simple') { ... }` branch —
`V.overview.render`'s reduced 4-card/banner-only path (kept only the always-full 7-card + "what happens next"
+ decision-chips path) and `V.inbox.render`/`V.inbox.bind`'s reduced 3-column table (kept only the full
search/decision-filter/rule-filter/sort/CSV-export table). Deleted `SIMPLE_STATUS`/`simpleStatusBadge()`
(the plain-English status badges used only by the now-gone reduced Inbox table) since nothing else referenced
them.

**`docs/dashboard/data.js`**: removed `KEY.mode`/`KEY.modeCalloutSeen` (the two localStorage keys the toggle
used) — `store()` itself is untouched (still used by `KEY.source`/`KEY.repo`).

**`docs/dashboard/dashboard.css`**: removed `.mode-bar`'s "Simple/Detailed switch" framing comment and
`#mode-callout`'s rules (the row it laid out no longer holds a switch, just the Glossary button — kept the
`.mode-bar` class name and flex layout since a future dashboard-only toolbar button could reuse it, but
retitled the comment).

**`README.md`**: replaced the "Simple / Detailed toggle" paragraph in "How to read the dashboard" with one
line stating every view always renders its full content.

## 2. Remove the Backtest and Safety tabs entirely (decision 68)

Grepped `docs/dashboard/` and `tests/e2e/test_dashboard.py` for `backtest`/`safety` (case-insensitive) after
every edit pass — not just the two nav entries — per the task's explicit instruction to grep and remove every
reference, matching the discipline decisions 9 (guardian removal) and 14 (dashboard design-system fix) already
established in this repo.

**`docs/dashboard/index.html`**: removed the `<li><a href="#/safety">Safety</a></li>` and
`<li><a href="#/backtest">Backtest</a></li>` nav entries.

**`docs/dashboard/views.js`**:
- Deleted `V.safety` (its render function, and the `timeline()` helper — an SVG liked-count-over-time chart —
  that only it called) and `V.backtest` (its render function) wholesale.
- Deleted `pctCell()` — the percent-with-bar table-cell helper used only by `V.backtest`'s playlist/rule
  tables; confirmed via grep it had no other caller before removing.
- Removed the `safety`/`backtest` entries from `VIEW_EXPLAIN` (the per-view "what does this mean?" popover
  text) and from `window.DashViews.ORDER` (now `['overview', 'inbox', 'rules', 'playlists', 'runs',
  'signals']` — six, in the order decision 16 specifies).
- Overview's Safety-verdict KPI card (`data-card="safety"`) **stays** — it's decision 19's own item 1 ("safety
  verdict (reconcile OK / mismatch)"), not the removed Safety *view*, and decision 16 doesn't touch it. Its
  "Open Safety" link (which pointed at the now-gone `#/safety`) was repointed to `#/runs` ("See run details"),
  since the reconcile/restore/journal detail it used to link to now lives only in each apply run's detail page
  under Runs (§3 explains why that's still fully covered).

**`docs/dashboard/dashboard.css`**: removed the dead CSS the two deleted views owned exclusively —
`.pct-cell` (backtest playlist/rule tables), `.chart`/`.chart .grid-line`/`.chart .axis-text`/`.chart .line`/
`.chart .pt-ok`/`.chart .pt-dry`/`.chart .pt-bad`/`.legend`/`.legend svg` (the Safety timeline SVG and its
legend) — confirmed via grep that `views.js` no longer emits any of these class names after §1/§2's edits.
`.bar`/`.bar-row` **stay**: the Signals view's `barRows()` helper (language/genre source breakdown bars) and
the Explain drawer's confidence bar both still use them.

**`docs/dashboard/data.js`**: removed the `backtest`/`detail` entries from `FILES`, `COMMANDS`, and `LABELS`
(the fetch-target/empty-state-command/freshness-label maps) — nothing in the dashboard fetches
`backtest.json`/`backtest-detail.json` any more, so `loadAll()`'s generic "fetch every key in `FILES`" loop
naturally stops requesting them.

**`docs/dashboard/fixtures/`**: deleted `backtest.json` and `backtest-detail.json` — they existed solely as
demo data for the now-removed Backtest view. **`scripts/make_dashboard_fixtures.py`**: deleted the `backtest()`
generator function and its `_BT_*` fixture-data constants, and the two `atomic_write_json(... backtest...)`
calls in `generate()`; updated the module docstring to note explicitly that `python -m src.backtest`'s own
real output format is unaffected — this script just stopped emitting a *demo copy* of it for a view that no
longer reads it. **Confirmed `src/backtest.py` itself is untouched** (§4) — it still writes
`backtest.json`/`backtest-detail.json`/`backtest-detail.md`/`signal-precision.json` exactly as before; only
`signal-precision.json` is still consumed by the dashboard (Signals view).

**`docs/dashboard/DATA.md`**: removed the `backtest.json`/`backtest-detail.json` sections from the dashboard's
own data *contract* (nothing reads them any more), replaced with one sentence noting they're still real
`python -m src.backtest` outputs, just no longer part of this contract.

**`docs/sw.js`**: removed `dashboard/fixtures/backtest-detail.json`/`backtest.json` from the precached-shell
file list (nothing left to precache once they're not fetched); bumped `CACHE_VERSION` `'v13'` → `'v14'` per
the file's own standing instruction ("bump whenever any cached file changes") — every cached dashboard shell
file (`index.html`, `dashboard.css`, `app.js`, `data.js`, `views.js`) changed content in this phase.

**`docs/screenshots/`**: deleted the eight screenshot files that only existed for the removed surface —
`dashboard-{backtest,safety}-{375,1280}.png` and `dashboard-{overview,inbox}-{simple,detailed}-1280.png` (the
decision-42 Simple-vs-Detailed proof pair, now meaningless with the toggle gone).

**`lighthouserc.json`**: removed the `http://localhost/dashboard/?source=fixtures&mode=detailed` collection
URL — found while grepping for `mode=` across the repo; with `mode` no longer a URL parameter the dashboard
recognises, that entry was now identical in practice to the `?source=fixtures` URL already in the list, so
keeping it would just have doubled a Lighthouse run for no new coverage.

**`README.md`**: replaced the Safety/Backtest bullet points in "How to read the dashboard" with one paragraph
stating both tabs are gone, and where their information moved (Safety's reconcile/restore/journal → each apply
run's own detail page under Runs; Backtest → still a standalone `python -m src.backtest` command, unaffected).

## 3. Test suite: what each removed test protected, and where that protection lives now

Per the task's explicit instruction ("don't just delete coverage wholesale — check what each removed test was
actually protecting"), went through every deleted test individually rather than bulk-deleting the two
`# ---- safety`/`# ---- backtest` sections:

| Removed test | What it protected | Still protected by |
|---|---|---|
| `test_safety_timeline_restore_reconcile` | The liked-count-over-time SVG chart | Nothing — the chart itself is gone with the view, nothing left to protect (decision 68: "not merged elsewhere ... gone") |
| ↳ same test, restore command + reconcile OK for the **2026-09-15** (clean) apply run | Restore command text, "Reconcile: OK" rendering | **New test** `test_run_detail_shows_reconcile_ok_and_restore_for_a_clean_apply_run` — opens that same run's detail page under Runs and asserts the same restore command and an "OK" (not "Mismatch") reconcile badge |
| ↳ same test, restore command + reconcile Mismatch for the **2026-09-17** (mismatching) apply run | Restore command text, "Mismatch" + "expected 42, found 43" rendering | Already covered — `test_runs_history_detail_and_diff` already opens this exact run's detail page and asserts all of this; unchanged, no new test needed |
| ↳ same test, journal table content | At least one journal row renders | Covered by both of the above (each opens a `<details>` journal table and asserts row count ≥ 1 / a specific count) |
| `test_backtest_names_in_local_detail_mode`, `test_backtest_without_detail_uses_ids` | Backtest view's precision/recall rendering, P01-vs-name fallback, confusions/misroutes tables | Nothing — the entire Backtest view is gone with no dashboard-side rendering left to protect. `src/backtest.py`'s own precision/recall/confusion computation (the actual logic these tests exercised transitively through fixture data) is unaffected and remains fully covered by `tests/test_backtest.py` (untouched, not part of this phase) |
| `test_simple_mode_is_the_default_for_a_fresh_viewer` | Fresh-viewer default state, KPI card presence, nav label set | **New test** `test_no_mode_toggle_and_full_overview_for_a_fresh_viewer` — same fresh-viewer setup (no page fixture defaults), now asserts the toggle/callout don't exist at all, all 7 KPI cards render (not a reduced 4), and the nav is the 6-view list |
| `test_simple_mode_inbox_has_three_columns_and_explain_works` | Inbox rendering + Explain-drawer-from-a-click | **New test** `test_inbox_always_shows_the_full_toolbar` (rendering) + every pre-existing Explain-drawer test (`test_explain_*`, unchanged — they already exercised the full-table click path, since `dash()`'s old default was already `mode="detailed"`) |
| `test_simple_mode_redirects_away_from_advanced_views` | Router behaviour for `signals`/`backtest`/`runs` hashes | `signals` and `runs` are ordinary views now (never "hidden"), covered by their own view tests; `backtest`'s and `safety`'s router-fallback behaviour is covered by the **new** `test_backtest_and_safety_tabs_are_gone` |
| `test_mode_toggle_switches_and_persists`, `test_first_visit_callout_shown_once_and_dismissible`, `test_first_visit_callout_switch_button_opts_into_detailed`, `test_simple_kpi_cards_have_tooltips` | Toggle behaviour, callout dismiss/persist, tooltip presence on KPI cards | Toggle/callout: nothing to protect, the feature is gone (asserted absent in the new fresh-viewer test). Tooltip presence: folded into the same new fresh-viewer test, which asserts `.help` buttons on pending/moves/safety cards exactly as the old test did |
| `test_axe_zero_serious_or_critical_on_overview_and_inbox`'s `mode` parametrization | 0 serious/critical axe violations in **both** modes | Only one rendering path exists now; kept the `theme` parametrization (dark/light), dropped `mode` — still runs axe against both themes on both views |
| `test_simple_vs_detailed_screenshots` | Committed before/after screenshots proving decision 42 | Not applicable any more — decision 42 is superseded by decision 67; deleted with no replacement (there is only one "after" state to screenshot now, already covered by `test_no_horizontal_overflow_and_screenshots`'s per-view screenshots) |

**New tests added** (beyond the replacements in the table): `test_backtest_and_safety_tabs_are_gone` — asserts
the nav doesn't list either name, and that navigating to a stale `#/backtest` or `#/safety` hash (e.g. an old
bookmark) renders Overview, not a blank page or a crash, proving the router's default-to-`overview` fallback
(§68's "not just hidden by CSS" requirement).

**Other mechanical updates** (behaviour unchanged, just the removed `mode=` URL parameter/kwarg swept out):
the `dash` pytest fixture no longer accepts or appends `mode=`; every call site that passed
`mode="detailed"`/`mode="simple"` explicitly (`test_csv_export_prevents_formula_injection`,
`test_dashboard_works_offline_via_service_worker`, `test_storage_blocked_does_not_break_the_page`) had that
kwarg/query-param dropped since there's only one behaviour to select now;
`test_tabs_keyboard_routing_and_aria`'s nav-label assertion updated from the 8-view list to the 6-view list;
`test_empty_states_name_the_command`'s per-view command dict lost its `safety`/`backtest` entries.

**`tests/test_dashboard_fixtures.py`**: replaced the `backtest.json`/`backtest-detail.json` shape-contract
assertions (§90-113 of the old file) with two assertions that those files are **absent** from the fixtures
directory — the round-trip test (`test_fixtures_regenerate_identically`, comparing `generate()`'s output names
against the real directory glob) already fails loudly if the generator and the committed fixtures ever drift
apart again, so no separate shape check is needed once the file just doesn't exist.

## 4. Confirming the critical safety distinction was respected

The task was explicit that this is dashboard UI only, and named three things that must stay untouched. Verified
directly, not just by not having edited them:

```
$ git diff --stat -- src/apply.py src/backtest.py
(no output — zero changes to either file)

$ git status --short logs/
(no output — logs/ untouched, consistent with it being git-ignored for real runs anyway)
```

`src/apply.py`'s journal-before-remove/verify/reconcile/restore mechanism is exactly as it was before this
phase. `src/backtest.py` still runs as `python -m src.backtest` and still writes
`backtest.json`/`backtest-detail.json`/`backtest-detail.md`/`signal-precision.json` in its own unchanged
format — `tests/test_backtest.py` (109 test functions, none touched) still exercises it end-to-end and still
passes (confirmed in §6's full offline run). The only thing that changed is that the dashboard stopped
*reading and rendering* two of those four files.

## 5. Live verification (not just unit/e2e tests)

Per the task's explicit instruction to live-verify, not rely on tests alone: served `docs/` with
`python -m http.server` and drove it with the Browser tool (same technique prior phase reports in this repo
use, e.g. `phase-dashboard-design-system.md` §7).

- **Six tabs render and are navigable**: opened `/dashboard/?source=fixtures#/overview` — nav shows exactly
  `Overview · Inbox · Rules · Playlists · Runs · Signals`, no Simple/Detailed switch, no first-visit callout,
  just the Glossary button in that row (screenshot taken). `get_page_text` confirmed all 7 KPI cards render
  (Last run, Next scheduled run, Liked songs, Pending, Moves this week, Errors and warnings, Safety verdict)
  with real fixture data, and the Safety-verdict card's link now reads "See run details" pointing at `#/runs`
  instead of the old "Open Safety".
- **Backtest and Safety do not appear anywhere in the nav, and a stale hash doesn't render them**: navigated
  directly to `#/backtest` and separately to `#/safety` (simulating an old bookmark or a stale link from
  somewhere else on the site) — in both cases the page title stayed `"Overview · LikedZero dashboard"` and the
  route fell back to Overview, confirmed via the tab's title bar after navigation (not just by not seeing an
  error — the router genuinely never matches those names to a view, per `parseRoute()`'s
  `V[path[0]] ? path[0] : 'overview'` fallback).
- **No leftover mode-toggle UI**: `#mode-toggle`, `#mode-callout`, `#mode-callout-dismiss` all return zero
  elements in the live DOM (also asserted programmatically in the new `test_no_mode_toggle_and_full_overview_for_a_fresh_viewer`
  e2e test, §3).

## 6. Full quality gate suite (decision 30, re-run per decision 69)

```
python -m pytest -q -m "not e2e"
  -> 1688 passed, 6 skipped, 264 deselected (40.5s)

SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e
  -> 262 passed, 2 skipped (178.5s)

SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e -k axe
  -> 15 passed (0 serious/critical violations, dark + light, Overview + Inbox)

SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e/test_dashboard.py -q -m e2e
  -> 69 passed
```
All three browsers (Chromium, Firefox, WebKit) launch and pass in this environment; confirmed with a
standalone Playwright launch check for all three before running the suite. The interleaved
`BrokenPipeError`/socket-exception tracebacks in the raw e2e output are the same pre-existing
local-dashboard-server-closing-connections-early artifact noted in prior phase reports (e.g.
`phase-more-conditions.md` §8, `phase-dashboard-design-system.md` §9) — not test failures; every run above
exits 0.

`docs/screenshots/*.png` were regenerated by `test_no_horizontal_overflow_and_screenshots` as a normal side
effect of running the full e2e suite after markup changes (same behaviour documented in every prior phase
report that touched dashboard/site markup) — visible in `git status` as modified for the six surviving
dashboard views plus the unrelated site-* marketing pages (also regenerated by the same full-suite run), and
as **deleted** for the eight screenshot files that had no view left to represent (§2).

**Lighthouse runs in CI only** (`treosh/lighthouse-ci-action`) — `npx`/`node` are not installed in this local
environment, so it was not runnable here; unverified locally, the same standing caveat every prior phase report
in this repo notes. `lighthouserc.json` was updated (§2) to drop its now-nonexistent `mode=detailed` dashboard
URL so the next CI run doesn't collect a redundant, semantically-stale entry.

**Live tests (`SPOTISORT_LIVE=1`) were not run.** No `.env`/credentials exist in this worktree, and nothing in
this phase touches Spotify's API, enrichment providers, or any Python module at all — the entire diff is
`docs/`, two test files, one fixture-generator script, and `lighthouserc.json`.

## Files touched

`docs/dashboard/{index.html,dashboard.css,app.js,data.js,views.js,DATA.md}`, `docs/sw.js` (precache list +
cache-version bump), `docs/dashboard/fixtures/{backtest.json,backtest-detail.json}` (deleted),
`scripts/make_dashboard_fixtures.py`, `lighthouserc.json`, `README.md`,
`tests/{e2e/test_dashboard.py,test_dashboard_fixtures.py}`, plus regenerated/deleted `docs/screenshots/*.png`.
**Not touched**: `src/apply.py`, `src/backtest.py`, `src/*` generally (zero Python source changes), `logs/`,
`config.yaml`.

## Deviations / judgment calls made, flagged for the master to double-check

None that changed the master's instructions, but a few "your call, document it" decisions were made along the
way:

1. **The Safety-verdict KPI card's "Open Safety" link now points at `#/runs`** ("See run details") instead of
   the removed `#/safety`. The card itself is decision 19's own Overview item, unaffected by decision 68 — only
   its deep link needed a new destination since the page it pointed to is gone. Chose Runs because that's where
   the reconcile/restore/journal detail actually still lives (each apply run's own detail page), not a generic
   "nowhere" link.
2. **`.mode-bar` class name and its flex-row CSS were kept** (just its Simple/Detailed-specific content
   removed) rather than deleted outright, since the Glossary button still needs a row to live in and a future
   dashboard-only toolbar addition could reuse the same layout rule. Retitled its CSS comment to stop claiming
   it's mode-specific.
3. **Deleted `backtest.json`/`backtest-detail.json` from the fixtures directory and stopped
   `scripts/make_dashboard_fixtures.py` from generating them**, rather than leaving them as orphaned demo data
   nothing reads. This follows the task's own instruction ("fixture files/fields only consumed by those two
   views") but is worth the master's attention since it also required updating
   `tests/test_dashboard_fixtures.py`'s contract test (removed shape assertions, added "file is absent"
   assertions) — a slightly larger test-file footprint than "just remove two dict entries."
4. **`lighthouserc.json`'s redundant `mode=detailed` dashboard URL was removed** — spotted while grepping for
   `mode=` repo-wide, not explicitly named in the task's file list, but clearly the same class of stale
   reference the task asked to sweep out (a URL parameter the dashboard no longer recognises).

Nothing here required stopping to ask — all four are small, reasoned, and consistent with decision 16's own
"remove at the root, don't leave a dead reference" framing (the same discipline decisions 9 and 14 already
established in this repo).
