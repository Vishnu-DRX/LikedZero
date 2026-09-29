# Phase: the dashboard doesn't share the design system at all (Master decisions 14, item 65)

Root cause per decision 65: `docs/dashboard/index.html` never loaded `components.css`/`site.css`, so it had
been built as a parallel, separately-styled page since early on instead of inheriting the U1 component
library (decision 23). This phase fixes that at the root — loads the shared stylesheets, replaces the
dashboard's hand-rolled header/footer with `shell.js`'s shared renderer, converts the run-now PAT dialog from
a drawer to the shared modal pattern, and audits the rest of the dashboard's UI for the same
"styled-by-`dashboard.css`-instead-of-`components.css`" pattern. A live coordinator report during this phase
also flagged a related symptom (the theme-toggle icon disappearing in light mode); investigating it surfaced a
genuine **site-wide** bug in `shell.js` itself, fixed here too (see §5).

## 0. Method

Read every relevant file in full before editing: `docs/dashboard/index.html`, `dashboard.css`, `app.js`,
`data.js`, `views.js`, `run-now.js`, and the shared `docs/assets/{shell,ui,components,site}.css/js` +
`docs/builder/index.html` + `docs/builder/app.js` (as the "what does the correctly-wired page already do"
reference). Cross-checked every planned rename against `tests/e2e/test_dashboard.py` and `test_site.py`
first — grepped for literal class-name/id assertions before touching markup, so risky renames (badge/banner
modifiers, `.help-btn`, the theme button) were known-safe or their test updated *because* the markup
correctly changed, not to paper over a regression.

## 1. Header — fixed

**Confirmed the reported symptom directly**: `docs/dashboard/index.html` hand-rolled `<div class="site-head">`
with its own `<nav class="site-links">` (four links: Home/Configure/Dashboard/GitHub — no Setup guide),
a plain filled-square `<span class="brand-mark">` instead of the shared SVG logo mark, and a single-character
theme button (`&#9680;`) instead of the shared sun/moon icon toggle.

**Fix**: replaced the whole header block with `<div id="site-shell"><noscript>...</noscript></div>` +
`<script src="../assets/shell.js" data-active="dashboard"></script>`, exactly the contract every other page
(`docs/index.html`, `docs/builder/index.html`, `docs/setup/index.html`) already uses. Now renders: the real
logo mark, all five nav links (Home · Configure · Dashboard · Setup guide · GitHub) with `aria-current="page"`
correctly on Dashboard, the shared sun/moon theme toggle, the mobile hamburger menu, and the GitHub
star-count widget — none of which the dashboard had before.

**Dashboard-specific additions kept, layered on top, not rebuilt as a duplicate whole header** (per the
instruction): the Detailed-mode switch and its first-visit callout stayed in their own `.mode-bar` row below
the shared header; the Glossary button (dashboard-only, no shared equivalent) moved into that same row
(`data-open="glossary-drawer"`, wired for free by `ui.js`'s existing delegated `[data-open]` handler — no new
JS needed, same pattern Configure's own "Versions" button already uses).

**Proof:** live comparison (§7) — nav link set, active-page styling, logo mark, and theme toggle icon are now
byte-for-byte the same DOM shell script output as Home/Configure, confirmed via `document.querySelector`
against a live local instance, not just visual inspection.

## 2. The run-now PAT dialog — fixed (drawer → dialog)

**Confirmed the reported symptom**: `#run-now-dialog` used `class="drawer"` with its own `.scrim` sibling div
and `drawer-head`/`drawer-body` classes — the dashboard's own slide-in-panel convention — while Configure's
`#github-save-dialog` (same underlying `github-pat.js` logic, different markup) used `class="dialog"`
(`components.css`'s actual centered-modal component).

**Decision taken (as instructed, "your call, recommend the modal"):** converted the dashboard's version to the
`dialog` pattern, matching Configure. Concretely: `<div class="overlay" id="run-now-dialog"><div class="dialog"
role="dialog" aria-labelledby="run-now-title"><div class="dialog-head">...<div class="dialog-body"
id="run-now-body">`. The separate `.scrim` div was dropped entirely — `components.css`'s `.overlay` element
*is* the scrim (it already carries the dimmed background + centering flexbox), so a child scrim div was
always a redundant, dashboard-only artifact of the pre-fix implementation, not a second component to
preserve. `ui.js`'s `open()/close()` already work identically for either pattern (it looks for
`.dialog, .drawer` inside the target and only cares about that, not the scrim), so no JS changes were needed
for run-now.js itself beyond class renames (`btn primary` → `btn btn-primary`, `btn secondary small` →
`btn btn-secondary btn-sm`, the dry-run checkbox → `class="check"` inside a `.check-row` label, matching every
other checkbox on the site).

**Proof:** live-opened the dialog via `window.SpotiUI.open('run-now-dialog')` on a local instance and
confirmed `role="dialog"`, `aria-modal="true"`, and — visually (§7) — a centered modal, not a right-edge
drawer. `tests/e2e/test_dashboard.py`'s existing run-now test block (lines ~579–715, 15 tests covering
connect/verify/dispatch/error paths) needed **zero** changes: it only ever asserted `#run-now-dialog`
visibility, `[data-close]`, and `get_by_role("button", name=...)` — never the drawer-vs-dialog CSS pattern —
so the conversion was invisible to it, and all 15 still pass.

## 3. Footer — was ALSO a separate duplicate, not just the two named symptoms; fixed

Not one of the two symptoms named in the master's decision, but found immediately once the header work
started (same root cause): `<footer class="site-foot"><div class="wrap"><p>...disclaimer only...</p></div>
</footer>` — a single disclaimer line, missing every other element `shell.js`'s shared footer renders: the
upstream-repo link, the live GitHub star count, the "Your fork" link (derived at runtime per decision 26/41),
the "Built by \<name\>" credit line, and the social-icon row (from `docs/site.config.json`).

**Fix**: removed the static footer block entirely; `shell.js`'s `mount()` appends the real one to `<body>`
automatically (same mechanism as every other page — nothing dashboard-specific needed here at all).

**Proof:** `document.querySelector('.site-footer').innerText` on a live local instance now reads
`"LikedZero is an independent open-source project... / Upstream repository / Built by Vishnu-DRX / © 2026 ·
MIT licence · LICENSE"` — the full shared footer, not the old one-line disclaimer.

## 4. Other shared chrome — checked each one named in the instruction

- **Mobile nav menu**: was entirely absent before (the old header had no responsive collapse at all — its
  `.site-links` just wrapped). Now present automatically via `shell.js`/`site.css`'s `#site-menu-btn` +
  `.site-nav.is-open` mechanism, confirmed live at the 591px pane width (§7 screenshot) and exercised
  indirectly by `test_mobile_menu_keyboard_and_escape` (`test_site.py`), which runs against the shared shell
  the dashboard now also loads.
- **Theme toggle**: fixed (see §1) — but see §5 for a real bug this surfaced.
- **"Star/Fork on GitHub" widget**: was completely absent (the old header had a plain `<a>GitHub</a>` text
  link, no star count, no fork detection). Now present via the shared footer (§3) and header's GitHub nav
  link with `rel="noopener"`. Live star fetch confirmed firing (`https://api.github.com/repos/Vishnu-DRX/
  LikedZero`) and failing silently when blocked, per decision 26 — this is *why* two dashboard tests needed a
  one-line update, see §8.
- **Buttons, badges, banners, tooltips/help, tables, form controls, checkboxes, overlays**: audited and fixed,
  see §6.

## 5. A real, site-wide bug found while verifying the theme toggle (not just a dashboard issue)

The coordinator asked me to explicitly verify the theme-toggle icon in both themes rather than assume the
header swap fixed it automatically. It did **not**, fully: verifying live surfaced a genuine bug in
`shell.js` itself, present on **every page**, not something my dashboard changes introduced or could fix by
themselves.

**Root cause**: `shell.js`'s `renderHeader()` markup included a static `hidden` attribute on the sun-icon SVG:
`<svg class="icon icon-sun" ... hidden>`. `components.css`'s base reset has `[hidden] { display: none
!important; }`. `ui.js`'s `theme.sync()` toggles visibility purely via a `data-theme-now` attribute + CSS
rules in `site.css` (`[data-theme-toggle][data-theme-now="light"] .icon-sun { display: block; }`) — it never
removes the `hidden` attribute. Since `!important` always wins over that non-`!important` CSS rule regardless
of specificity, the sun icon could **never** display once light theme was active, on any page: the moon icon
correctly hides (it has no `hidden` attribute to begin with, so the plain CSS rule works), but the sun icon
never appears to replace it — the toggle button renders with **no icon at all** in light mode. This matches
exactly what was reported ("the icon and background both end up white/light" — really: no icon, an apparently
blank button against the light background).

**Verified this reproduces on the unmodified Home page** (`docs/index.html`, untouched by this phase) before
concluding it wasn't a dashboard-only issue — confirmed live: `sunDisplay: "none"` even with
`data-theme-now="light"` set, on `/LikedZero/` with no dashboard code loaded at all.

**Fix**: removed the static `hidden` attribute from `shell.js`'s sun-icon markup (one line). `site.css`'s
plain `[data-theme-toggle] .icon-sun { display: none; }` rule already hides it by default with no
`!important` involved, so the attribute was redundant even before it became actively harmful.

**Live proof (both themes, as asked):**
```js
// dark (default): moon shown, sun hidden — correct, unaffected by the bug
{ dataThemeNow: "dark", moonDisplay: "block", sunDisplay: "none", ariaLabel: "Switch to light theme" }
// light, BEFORE the fix:
{ dataThemeNow: "light", moonDisplay: "none", sunDisplay: "none"  }   // <- no icon at all
// light, AFTER the fix:
{ dataThemeNow: "light", moonDisplay: "none", sunDisplay: "block", sunStroke: "rgb(18, 18, 18)" }
```
`sunStroke: rgb(18, 18, 18)` against the light-theme body background `rgb(246, 246, 246)` confirms the icon
is not just present but visibly contrasting (dark stroke on light background) — the original symptom is
fully resolved, not just "technically displayed."

Also click-tested the real button end-to-end (not just attribute manipulation) on the dashboard: dark → click
→ light (sun visible) → click → dark (moon visible), both directions correct.

**Regression tests added** so this can't silently come back:
- `tests/e2e/test_site.py::test_keyboard_skip_link_and_theme_toggle_persist` (site-wide, runs against Home) —
  now asserts the *visible* icon's `display` is not `none` and the *hidden* icon's `display` is `none`, both
  immediately after toggling and again after a reload, instead of only checking the `data-theme` attribute.
- `tests/e2e/test_dashboard.py::test_theme_tokens_follow_color_scheme` — now asserts both icons explicitly
  after each click, with a comment naming this as the coordinator-reported bug this phase fixed.

## 6. Audit of the rest of the dashboard's UI (buttons, tooltips, badges, glossary drawer, …)

Went through every class the dashboard's CSS/JS defined and checked whether `components.css` already defines
the same thing under its own name. Found this was pervasive, not limited to the header/dialog:

| Dashboard's own (before) | Shared equivalent (`components.css`) | Fixed by |
|---|---|---|
| `.btn.primary` / `.btn.secondary` / `.btn.ghost` / `.btn.small` | `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-sm` | renamed across `views.js`, `run-now.js` |
| `.icon-btn` | `.btn.btn-icon` | renamed across `index.html`, `views.js`, `app.js` |
| `.badge-ok` / `-warn` / `-bad` / `-info` | `.badge-success` / `-warning` / `-danger` / `-info` | `badge()`/`badgeClass()` helper in `views.js` now maps kind → the real modifier once, centrally |
| `.banner-warn` / `-bad` (plain `.banner`/`.banner-info` already matched) | `.banner-warning` / `-danger` | `banner()` helper mapped the same way; **also found two call sites that built badge/banner classes by hand, bypassing the helpers** — the Overview "Inbox by decision" links and the Explain drawer's "Withheld from rules" banner — fixed both to go through the shared mapping too |
| `.help-btn` | `.help` | renamed (2 sites: the `helpBtn()` helper, and one hand-built instance in the Playlists view) |
| bare `table` element selector | `.table` class | added `class="table"` to every `<table>` the dashboard renders (11 sites across Inbox/Rules/Playlists/Runs/Safety/Signals/Backtest) |
| bare `input[type=text/search]`, `select` element selectors | `.input` / `.select` classes | added the classes to every text/search input and `<select>` (`#repo-url`, `#source-select`, `#inbox-q` ×2, `#inbox-decision`, `#inbox-rule`, `#files-input`) |
| bare `input[type=checkbox]` element selector | `input.check` | added `class="check"` to the run-selection checkbox (Runs view) and the run-now dry-run checkbox |
| `.tooltip` / `.popover` (dashboard's own copy, slightly different border colour) | `.tooltip` / `.popover` | removed the duplicate — `ui.js` already manipulates these by the shared class names, so the dashboard's copy was pure drift, never actually needed |
| `.scrim` + `.drawer` (custom position:fixed) for the Explain drawer, glossary drawer, run-now dialog | `.overlay` / `.overlay-side` / `.dialog` / `.drawer` (flex-positioned by the parent, no separate scrim element) | rebuilt all three overlays on the shared structural pattern (§1–§3, and the Explain drawer below) |
| `.drawer-head` / `.drawer-body` | `.dialog-head` / `.dialog-body` (components.css defines these generically — Configure's own Versions/Schema *drawers* already reuse them, not just its *dialogs*) | renamed in the glossary drawer and Explain drawer markup |

**Glossary drawer**: converted from `<div class="overlay">` + `.scrim` + `.drawer`/`drawer-head`/`drawer-body`
to `<div class="overlay overlay-side">` + `.drawer`/`dialog-head`/`dialog-body` — now structurally identical
to Configure's Versions and Schema-reference drawers, not just visually similar.

**Explain drawer** (Inbox → click a song → "Why?"): decision 65 explicitly exempts this one from needing to
*look* like Configure ("dashboard-specific... don't need to match Configure/Home") — kept it a slide-in side
drawer, not converted to a centered dialog. But its *plumbing* was a full parallel reimplementation of
`ui.js`'s overlay system: its own `focusables()`, its own `setInert()` (hardcoded to `.site-head, .wrap,
.site-foot, .skip` — three of those four selectors no longer even exist after §1/§3's fix, so this would have
silently broken background-inerting the moment the header/footer changed if left as-is), its own `keydown`
listener for Escape and Tab-trapping, its own click listener for `[data-close]`. Rewrote it to open/close
through `window.SpotiUI.open()/close()` — the exact same machinery every dialog and drawer elsewhere on the
site already uses — which deleted ~35 lines of duplicated focus-trap/inert/Escape code and, as a side effect,
made the inert-marking generic (it now correctly inerts whatever the real DOM siblings are, rather than a
hardcoded, now-stale selector list). Kept the wider `36rem` drawer width (vs. Configure's drawers' `30rem`
default) as a one-line, documented addition in `dashboard.css` — the Explain content genuinely needs more
room, and decision 65's own text calls dashboard-specific additions-on-top acceptable.

**Sort buttons (`.sort-btn`) and the song-title-as-button pattern (`.link-btn`)**: audited, kept as
dashboard-specific, not renamed — with reasoning, not by default:
- `.link-btn` has no equivalent in `components.css` (no "text-styled action" component exists there), and it
  is already a real `<button>`, not an `<a>` — satisfies decision 40's action-vs-navigation rule as-is.
  `tests/e2e/test_dashboard.py` asserts on this exact class name in several places (`.link-btn`, e.g. line
  169), confirming it's an intentional, load-bearing pattern, not an oversight.
- `.sort-btn` looks similar to `components.css`'s `.th-sort` (used by `ui.js`'s generic `sortBy()`), but the
  dashboard's sort is genuinely different underneath: type-aware (numeric age, ISO date, decision-priority
  order, language string) with per-view state for CSV export and "N more" paging, versus `ui.js`'s generic
  text/number toggle. Reusing `.th-sort`'s exact JS would have been a functional regression (losing type-aware
  sort), so this stayed its own thing — kept visually consistent (bold text + inline arrow) with `.th-sort` on
  purpose, documented in `dashboard.css` as a deliberate, reasoned exception rather than silently left alone.

**Internal dashboard consistency across Inbox/Rules/Playlists/Runs/Safety/Signals/Backtest** (the specific ask
in the phase brief): all eight views already funnel every status pill, warning strip, KPI card, and data table
through the same small set of shared helper functions defined once in `views.js` (`badge()`, `banner()`,
`card()`, `tableWrap()`, `pctCell()`) — there was **no** per-view reimplementation of table/card/button chrome
to find beyond the two raw class-string call sites listed in the table above (both fixed). The duplication in
this file was entirely about those helpers emitting the *wrong* (dashboard-only) class names, not about the
views disagreeing with each other.

**Dead code found and removed in passing**: `.filter-chips` and `.density-toggle` in the old `dashboard.css`
had zero references anywhere in `views.js`/`app.js`/`index.html` — leftover CSS for decision 34's originally
planned filter-chip/density-toggle UI that the Inbox view ended up implementing with plain `<select>`
dropdowns instead. Removed; not a design-system duplication, just orphaned CSS noticed while trimming the
file.

**`dashboard.css` after the pass**: 283 lines → 155 lines. What's left is genuinely dashboard-only: the
source-bar/files-drop (decision 31's "Open local files" feature has no shared equivalent), the hash-router
tab strip (confirmed via repo-wide grep that no other page actually uses `components.css`'s ARIA `.tablist`/
`.tab` component either — this is a different kind of navigation, not a duplicate of an unused component),
the data-freshness stamp, the KPI `.grid`/`.card`/`.metric-*`/`.callout` spacing additions (`components.css`'s
`.card` has no bottom-margin by design — it expects a `.stack`/`.grid` wrapper; the dashboard renders many
standalone cards outside of `.grid` too, so it adds just `margin` + `min-width:0`, not a parallel `.card`),
the signals/backtest bar-chart and safety timeline SVG styles, and the Explain-trace list. Every section is
commented with *why* it isn't shared (either "no shared equivalent" or a specific reasoned exception like
`.sort-btn` above).

## 7. Live comparison (proof, not just a summary claim)

Ran a local static server (`http.server`, base path `/LikedZero/`, same technique the e2e conftest and the
prior rename-phase report both use) and drove it with the Browser tool — this is independent of the
Playwright suite, an out-of-band confirmation the fix actually renders correctly:

- **Header**: Home, Configure, and Dashboard now render an identical header — same logo mark, same five nav
  links, same `aria-current="page"` styling, same theme-toggle button — confirmed by inspecting the live DOM
  (`document.querySelector('.site-header')`) on all three pages, not just by eye.
- **Footer**: `.site-footer` on the dashboard now contains the upstream link, star-count slot, hidden
  "Your fork" link (correctly hidden — this local server isn't `*.github.io`), and the "Built by Vishnu-DRX"
  credit — matching Home/Configure's footer structure exactly (§3's proof).
- **Mobile nav**: at the pane's narrow (591px) width, the hamburger menu appears exactly as it does on
  Home/Configure (screenshot taken, confirms same collapsed-header layout).
- **Run-now dialog**: opened live via `SpotiUI.open('run-now-dialog')`; confirmed `.dialog` (not `.drawer`)
  and, visually, a centered modal — screenshot taken and matches Configure's "Save to GitHub" dialog's
  layout/position.
- **Glossary drawer**: opened live; confirmed it renders as a right-edge slide-in panel styled by the shared
  `.drawer`/`dialog-head`/`dialog-body` classes — screenshot taken.
- **Explain drawer**: opened live from the Inbox view (a real user click, not a direct API call); confirmed
  `role="dialog"`, focus lands on the close button automatically (via `SpotiUI.open()`'s generic focus logic,
  not custom code), and the content renders with shared badges/cards — screenshot taken.
- **Theme toggle, both directions**: full before/after data in §5.

Screenshots from this pass were not committed (this was an ad hoc local server outside the repo's e2e
fixtures, in the scratchpad, not `logs/screens/`) — the *committed* screenshots come from the real Playwright
suite's `test_no_horizontal_overflow_and_screenshots` (§8), which re-ran and regenerated all of them under the
fixed markup.

## 8. Test suite changes and why each one was needed

Three genuine markup/behavior changes required matching test updates — each is a test change *because* the
implementation intentionally changed, not a loosened assertion:

1. **`api.github.com` is now a legitimate external request from the dashboard** (the shared footer's star
   fetch, decision 26) — `test_no_requests_leave_the_site_with_fixtures` and
   `test_source_switch_repo_fixtures_files`'s external-origin allowlist both updated to exclude/allow it,
   using the exact same filter comment/pattern `test_builder.py`'s equivalent test already established for
   Configure. Without loading `shell.js`, the dashboard never made this call; now every page does, uniformly.
2. **`.help-btn` → `.help`** (§6) — `test_simple_kpi_cards_have_tooltips` updated to the new selector.
3. **Theme toggle is now 2-state (dark/light), not 3-state (auto/light/dark)** — this is an intentional
   simplification, not a regression: decision 65 says to reuse `shell.js`'s shared toggle "instead of
   dashboard's own copy," and the shared toggle (used by Home/Configure/Setup/404 already) only ever offers a
   direct dark↔light toggle, no explicit "back to auto" state. `test_theme_tokens_follow_color_scheme`
   rewritten for the new click sequence and given the icon-visibility assertions from §5.

No other test in the suite needed a single change — everything else (badge/banner colours, table/input/select
classes, the run-now dialog's pattern, the Explain drawer's refactor) was either invisible to the existing
`data-testid`/id/role-based assertions or covered by the class-name checks already walked through in §6's
table.

## 9. Full quality gate suite (decision 30)

```
python -m pytest -q -m "not live"                                              -> 1963 passed, 2 skipped, 6 deselected (152.0s)
SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e -> 275 passed, 2 skipped (118.6s)
python -m pytest tests/e2e -q -m e2e -k axe                                    -> 17 passed (0 new serious/critical violations)
python -m pytest tests/e2e/test_dashboard.py -q -m e2e                         -> 82 passed
python -m pytest tests/e2e/test_site.py tests/e2e/test_builder.py tests/e2e/test_fork_genericness.py tests/e2e/test_github_save.py -q -m e2e -> 193 passed, 2 skipped
python -m pytest tests/e2e/test_site.py::test_shell_and_home_byte_budget       -> 1 passed (shell+Home budget unaffected — dashboard files aren't in that budget list)
```
All three browsers (Chromium, Firefox, WebKit) launch and pass in this environment — no
`playwright install` workaround was needed this time (unlike a prior phase's report), so no environment note
to add here. The `BrokenPipeError`/`ConnectionAbortedError` tracebacks interleaved in the raw e2e output are
the same pre-existing local-dashboard-server-closing-connections-early artifact noted in
`design/reports/phase-more-conditions.md` §8 — not test failures; every run above exits 0.

`docs/screenshots/*.png` (54 files, dashboard + site pages) were regenerated by the e2e screenshot test as a
side effect of running the suite after markup changes — visible in `git status` as modified. Not manually
inspected pixel-by-pixel per file; the underlying pages were independently, programmatically verified live in
§7.

**Lighthouse runs in CI only** (`treosh/lighthouse-ci-action`) — not runnable in this local environment;
unverified here, the same standing caveat every prior phase report in this repo notes.

**Live tests (`SPOTISORT_LIVE=1`) were not run.** No `.env`/credentials exist in this worktree. Separately,
nothing in this phase touches Spotify's API, enrichment providers, or any Python code at all — the entire
diff is `docs/` (dashboard + the one shared `shell.js`/`sw.js` fix) and the two e2e test files.

`docs/sw.js`'s `CACHE_VERSION` bumped `'v12'` → `'v13'` since every cached dashboard shell file
(`index.html`, `dashboard.css`, `app.js`, `views.js`, `run-now.js`) changed content, per the standing
instruction ("bump `CACHE_VERSION` whenever any cached file changes").

## Files touched

`docs/assets/shell.js` (the theme-icon bug fix, §5), `docs/sw.js` (cache version bump),
`docs/dashboard/{index.html,dashboard.css,app.js,data.js,views.js,run-now.js}`,
`tests/e2e/{test_dashboard.py,test_site.py}`, plus 54 regenerated screenshots.

## Deviations / judgment calls made, flagged for the master to double-check

None that changed the master's instructions, but three "your call, document it" decisions were made along
the way, all reasoned above rather than assumed:
1. Run-now dialog converted to the `dialog` pattern (modal), matching the master's own stated recommendation
   — not actually a deviation, just confirming the choice was followed.
2. Theme toggle lost its 3-state "auto" cycle in favour of the shared 2-state toggle (§8, item 3) — an
   intentional, reasoned simplification for consistency, not an oversight; flagging it explicitly since it is
   a small behavior change a user might notice.
3. The Explain drawer's width customization (`36rem` vs. the shared default `30rem`) was kept — a deliberate,
   minimal, documented addition rather than full conformance, matching decision 65's own allowance for
   dashboard-specific additions layered on shared components.

The theme-icon bug (§5) was not something this phase was originally scoped to fix — it surfaced only because
the coordinator asked for explicit live verification rather than an assumption that the header swap would
cover it. It did not, on its own; the actual fix was one line in `shell.js`, applied because it is a genuine,
previously-undiscovered, site-wide bug affecting every page, not scope creep.
