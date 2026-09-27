# Phase U2 report — UI cleanup pass (Master decisions 7, Part A)

Implementation session, 2026-09-27. Decisions 40-43, done before Phase 7 as instructed. No `--apply` of any
kind. No real Spotify data or song names appear in any committed screenshot (all fixture-based).

## 1. Verdict

1. Decision 40 (button vs link audit) — **PASS, zero offenders found.** Full table below.
2. Decision 41 (fork-genericness audit) — **PASS.** The site was already largely built runtime-derived
   (shell.js's `deriveFork`, data.js's `deriveRepoBase`); the new Phase 7 code was built the same way from
   the start. Required automated test added and passing: `tests/e2e/test_fork_genericness.py`.
3. Decision 42 (Simple/Detailed) — **PASS.** New default Simple mode, persisted toggle, first-visit callout,
   tooltips on the Simple KPI cards, fresh-viewer test, dashboard axe gate added for both modes (there wasn't
   one before this pass).
4. Decision 43 (quality gate re-run) — **PASS.** Lighthouse couldn't run locally (no Node/npm here), so it
   was verified on the real CI instead — see §6.

## 2. Proof

```
$ python -m pytest -q                    -> 1525 passed, 2 skipped   (e2e deselected by default)
$ python -m pytest -q -m e2e             -> 196 passed, 2 skipped    (dashboard 71, builder 72, site 47, github-save 5, fork-genericness 4, +misc)
$ python -m pytest -q -m e2e -k axe      -> 13 passed (9 site/builder, 4 new dashboard: 2 modes x 2 themes)
```
3-browser: only Chromium-family is installed on this machine (`available_browsers` soft-skips firefox/webkit,
same as every prior report); `test_pages_load_across_available_browsers` and the 375/768/1280 responsive
checks in `test_site.py` all pass on Chromium locally. **Pushed and confirmed on the real CI**: the `e2e`
workflow (which installs chromium+firefox+webkit) ran this exact commit and passed the identical 196/2 count
(`gh run view 36307372112`, 3m3s); the `Tests` and `lighthouse` workflows also passed on this push (`gh run
view` 36307372123 and 36307372097) — all three of decision 43's gates are green on real CI for this commit,
not just locally.

## 3. Decision 40 — button vs link audit

Grepped every `<a `/`<button` in `docs/**/*.{js,html}` (about 60 occurrences) and classified each by what it
does. Every action-performing control was **already** a `<button>`; every `<a>` found is genuine navigation
(a page, an anchor/hash-route, or an external site). No changes were needed — the table below is the audit's
output, not a list of fixes.

| Control | Purpose | Component |
|---|---|---|
| Run now (Overview) | performs an action (opens the run-now dialog) | `<button data-open>` |
| Save configuration / Save to GitHub / Download config.yaml | actions | `<button>` |
| Connect token "Save & verify" / "Commit" / "Overwrite…" / "Cancel" | actions | `<button>` |
| Restore / Compare with current (Versions) | actions | `<button>` |
| Copy to clipboard (`data-copy`) | action | `<button>` |
| Dismiss banner / mode callout / drawer close (`✕`) | actions | `<button data-close>`/`<button data-dismiss>` |
| Theme toggle, mobile menu, glossary open, Versions open, Schema reference open | actions | `<button>` (icon or `data-open`) |
| Inbox sort headers, "Show N more", Export CSV | actions | `<button>` |
| Song title / "Why?" (opens Explain drawer) | action | `<button class="link-btn">` — styled like a link, but a real `<button>` element and keyboard/AT-operable as one |
| Nav bar (Home/Configure/Dashboard/Setup guide/GitHub), brand logo, dashboard tabs, skip-to-content | navigation | `<a class="site-nav-link">` / plain `<a>` |
| "View on GitHub", "Upstream repository", "Your fork", social icons, LICENSE link | navigation (external) | `<a rel="noopener">` |
| Dashboard hash-route links ("Open Safety", decision-count chips, "Full run detail", "Back to all runs", run detail links) | navigation (SPA route change, same pattern as the tab bar) | `<a href="#/...">` |
| "Create a token on GitHub" / "Open the Actions tab" (run-now, Save to GitHub) | navigation (external, new tab) | `<a target="_blank" rel="noopener">` |

## 4. Decision 41 — fork-genericness audit

Grepped `docs/` for the literal strings `Vishnu-DRX` and `SpotiSort`. Every `Vishnu-DRX` hit was one of the
two allowed exceptions or a legitimate, non-fork-specific reference:
- `docs/site.config.json` (exception a).
- `assets/shell.js`'s `UPSTREAM_OWNER`/`UPSTREAM_URL` constants and every page's `<noscript>` fallback GitHub
  link (exception b: the canonical upstream credit link, decision 26).
- The Setup guide's "fork `github.com/Vishnu-DRX/SpotiSort`" instruction and its "open an issue on the
  upstream repository" link — both correctly point at the real upstream (that's where a fork *comes from*
  and where issues *should* go), never at the reader's own address. Every later step already says "your fork"
  and uses `<your-username>` placeholders, not a hardcoded owner.

Everything that actually needs to be per-visitor was already, or (Phase 7) was built to be, derived from
`location` at runtime:
- Repo mode: `data.js`'s `deriveRepoBase()` (`<owner>.github.io` + first path segment → raw.githubusercontent.com URL).
- run-now: `data.js`'s `repoOwnerName()`, built on the same derivation.
- "Your fork" footer link: `shell.js`'s `deriveFork()`.
- Configure's local storage namespacing: `app.js`'s pre-existing `deriveOwnerRepo()`.
- Phase 7's "Save to GitHub": new `ownerRepoParts()` in `app.js`, same `<owner>.github.io` + path-segment rule,
  refusing to guess (a clear message, not a fallback repo name) when not served from GitHub Pages.

**Required test** (`tests/e2e/test_fork_genericness.py`): serves the real built site under
`https://someoneelse.github.io/their-fork/` via Playwright route interception (the navigated URL is genuinely
that origin — `location.hostname`/`pathname` are real, not mocked) and asserts:
1. Repo mode fetches `raw.githubusercontent.com/someoneelse/their-fork/main/logs/*` (not the maintainer's).
2. run-now's token deep-link has `target_name=someoneelse`.
3. Save to GitHub's token deep-link also has `target_name=someoneelse`, and the connected commit form names
   `someoneelse/their-fork`.
4. The upstream credit link (`github.com/Vishnu-DRX/SpotiSort`) is unchanged, and the "Your fork" link points
   at `github.com/someoneelse/their-fork` — both on the same page.
All 4 pass.

## 5. Decision 42 — dashboard Simple/Detailed

- **Toggle**: `#mode-toggle` (same `.switch` component as Configure's Advanced toggle, copied into
  `dashboard.css` rather than pulling in the whole site stylesheet), persisted as
  `spotisort.dashboard.mode` (localStorage), overridable per-load with `?mode=simple|detailed` (same rule as
  the existing `source` param). **Simple is the default** when nothing is stored and no query param is given.
- **Overview (Simple)**: the existing "Overall: Healthy/Needs attention" line, exactly **4** KPI cards (Last
  run, Pending, Moves this week, Safety verdict — the four that answer "is it working / is there anything
  to do / is it safe"), and one banner ("Everything looks fine" / "This needs attention") in place of the
  Signals/Backtest/Runs views. Next scheduled run / Liked songs / Errors and warnings cards, the "what will
  happen next" paragraph and the decision-count chips are Detailed-only (they're either raw counts or
  duplicate what the banner already says in plain words).
- **Inbox (Simple)**: exactly 3 columns — Song, Status (plain sentences: "Will move soon", "Not old enough
  yet", "Nothing matches it", "Can't reach its playlist", "Not sure yet"), Why (opens the same Explain drawer
  Detailed uses). No decision/rule filter dropdowns, no sortable columns, no CSV export, no age/eligible-date/
  language columns.
- **Nav**: Signals, Backtest and Runs are removed from the tab bar in Simple mode; landing on one directly
  (typed hash, old bookmark) redirects to Overview rather than erroring.
- **Tooltips**: the three Simple-mode KPI cards that aren't already plain English (Pending, Moves this week,
  Safety verdict) get a `help-btn`/`data-tip` (decision 24's existing pattern), in both modes since `card()`
  now takes an optional tip and Detailed reuses the exact same card HTML. Last run's badge/timestamp and
  Liked/Errors counts were judged already self-explanatory and left alone, matching "every label that isn't
  plain English" rather than adding tooltips everywhere indiscriminately.
- **First-visit callout**: a dismissible `banner-info` above the tabs ("Prefer more detail? Switch to
  Detailed"), shown only when the visitor has never chosen a mode AND never dismissed it; dismissing, or using
  the toggle directly, remembers that permanently (`spotisort.dashboard.modeCalloutSeen`).
- **CLS**: the zero-JS static skeleton in `index.html` and the JS-built loading skeleton
  (`app.js:loadingSkeleton()`) were both a fixed 7-card shape; since Simple's real Overview only has 4, this
  would have been a new CLS regression the moment Simple became the default. Both are now sized to match the
  mode about to render (static skeleton defaults to 4, the common case; the JS skeleton is mode-aware).
- **Proof**: `test_simple_mode_is_the_default_for_a_fresh_viewer` (a genuinely fresh browser context, no
  `mode=` param) asserts the toggle is unchecked, exactly the 4 cards + banner are present, the nav has 5 tabs,
  and the page text reads as a plain sentence — without ever opening `#glossary-drawer`. Plus 6 more tests
  (Inbox columns, redirect-away, toggle persistence, callout shown-once/dismiss/switch, tooltip presence) and
  4 new axe runs (2 modes × 2 themes, 0 serious/critical).

## 6. Decision 43 — quality gate re-run

- `python -m pytest -q -m e2e -k axe`: 13 passed, 0 serious/critical violations, including the 4 new
  dashboard cases this pass added (there was no dashboard axe test before Phase U2).
- `python -m pytest -q -m e2e tests/e2e/test_site.py`: 47 passed (axe, committed screenshots, budget, 3-browser
  soft-skip) — no regressions from the shell/footer fix below.
- **Found and fixed while auditing, unrelated to the Simple/Detailed layout itself**: `assets/shell.js`'s
  social-icon footer built its `aria-label` from `config.name_label_prefix`, a field that has never existed in
  `site.config.json` — every social icon (in this repo, just "GitHub") had the accessible name
  "undefinedGithub". Fixed to `"<name>’s " + capitalize(key)` (falls back to just the capitalized key when
  `config.name` is absent). Caught via a fork-genericness test's accessibility tree dump, not by an existing
  assertion — no test previously read that aria-label's text.
- **Found and fixed**: `docs/sw.js`'s precache list never gained `dashboard/run-now.js` or
  `assets/github-pat.js` when Phase 8b added them, so a visitor who had the dashboard cached offline before
  this pass would silently get 404s for the run-now button after this release, until they hard-reloaded.
  Bumped `CACHE_VERSION` to v11, added both files, and `test_dashboard_works_offline_via_service_worker` now
  asserts both are present (it previously didn't check for either, which is how this shipped unnoticed in
  Phase 8b).
- **Found and fixed**: `lighthouserc.json` tested `dashboard/?source=demo` — `demo` has never been a valid
  `source` value (only `repo|fixtures|files`); it silently fell through to the default instead of exercising
  what the config author intended. Fixed to `?source=fixtures`, and added a second dashboard URL with
  `&mode=detailed` so Lighthouse now covers both Simple (default) and Detailed.
- **Lighthouse could not be run locally** (no Node/npm/`lhci` in this session), so the fix above was pushed
  and verified on the real CI instead: the `lighthouse` workflow (`on: push`) ran against this exact commit
  and **passed** (`gh run view 36307372097` — all four categories, all four URLs including the new Simple and
  Detailed dashboard pair, ≥ 0.9). Gate confirmed, not just patched.
- 375/768/1280 responsive + no-horizontal-overflow: unchanged existing coverage in `test_site.py`
  (`test_page_loads_cleanly`) and `test_dashboard.py` (`test_no_horizontal_overflow_and_screenshots`, all 8
  views × 2 widths) all still pass after the mode-bar/callout additions.

## 7. What was built / changed
- `docs/dashboard/app.js`, `data.js`, `views.js`, `index.html`, `dashboard.css`: Simple/Detailed mode plumbing,
  mode-aware skeleton, Overview/Inbox Simple renders, tab filtering + redirect, first-visit callout.
- `docs/assets/shell.js`: social-icon aria-label bug fix.
- `docs/sw.js`: added the two Phase 8b files to the precache list, version bump.
- `lighthouserc.json`: fixed the dead `source=demo` param, added a Detailed-mode URL.
- `tests/e2e/test_dashboard.py`: 7 Simple/Detailed tests, 4 axe tests, before/after screenshots, offline-cache
  assertion extended.
- `tests/e2e/conftest.py`: `serve_fake_origin()` helper (shared by the fork-genericness and Phase 7 tests).
- `tests/e2e/test_fork_genericness.py`: new, 4 tests (required proof for decision 41).

## 8. Risks & known gaps
- Firefox/webkit are not installed on this machine, so the 3-browser gate only ran Chromium locally; confirmed
  green on the real CI (which installs all three) for this exact commit, see §2/§6.
- Simple mode's 4-card choice (Last run, Pending, Moves this week, Safety verdict) and which KPI labels got
  tooltips are judgment calls within the brief, not something the brief enumerated exactly — flagging for
  review in case the master wants a different four or more/fewer tooltips.

## 9. Next
Phase 7 (see `phase-7.md`, done immediately after this in the same session, reusing everything decision 41
already required from it).
