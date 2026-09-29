# Phase: one shared PAT for Configure + run-now (Master decisions 15)

Master decisions 15 supersedes P1-5's deliberate scope-keyed token separation (decision 44). P1-5's reasoning
(narrower token = smaller blast radius) was sound in general, but for this tool's actual threat model — a
single user, one repo, a self-chosen (default 7-day) expiry, sessionStorage-only, never persisted — the
repeated "connect again for the other feature" friction outweighed the marginal blast-radius benefit. The user
hit this live, twice: connecting via Configure's Save-to-GitHub didn't carry over to the dashboard's Run now,
and vice versa. This phase requests the union of scopes (`Contents: write` + `Actions: write`) from both entry
points and shares one cached token between them.

## 0. Method

Read `docs/assets/github-pat.js` in full first to understand its existing `get`/`set`/`clear`/`tokenUrl`/
`verify`/`dispatchWorkflow` API before changing anything, per the instruction to keep that shape if reasonable.
Then read both call sites (`docs/builder/app.js`'s `GH_SCOPES` block and `docs/dashboard/run-now.js`'s `SCOPES`
block) in full, and grepped the whole `docs/` tree for any other `GithubPAT.*` caller — confirmed there are only
these two (a future `analyze.yml` trigger per decision 58/59 is designed but not yet built, so no third caller
exists in this codebase today).

## 1. `docs/assets/github-pat.js` — storage keyed by owner/repo alone, not by scope set

**Change:** `keyFor(owner, repo, scopes)` → `keyFor(owner, repo)`. The old `scopeKey()` helper (which turned the
scopes array into a sorted `name:level,...` string appended to the storage key) is removed. `get`/`set`/`clear`
keep `scopes` as a parameter for call-site compatibility (and in case a genuinely narrower, deliberately
non-shared token is ever needed again) — it's just no longer part of the key.

**Why key by owner/repo rather than "both callers happen to request the identical array" (the other option the
instruction offered):** dropping scope from the key entirely is more robust than relying on both callers'
arrays staying textually identical forever. Decision 58 (not yet built) already plans a third caller — the
"Analyze my library" trigger — that explicitly reuses run-now's PAT component but with a *different*, narrower
scope request (`Actions: write` only, no `Contents`). If storage were still keyed by exact scope set, that
future caller would silently open a third, non-shared slot the moment it's built, reintroducing exactly the bug
this phase fixes. Keying by owner/repo alone means any future caller that requests a subset of what's already
stored transparently reuses the existing (broader) token, no re-keying decision needed later.

`verify()` and `tokenUrl()` are unchanged — they still consult whatever `scopes` array the caller passes, which
is correct: they should request/check exactly what the caller says it needs, only the *storage* is now shared.

## 2. `docs/builder/app.js`'s `GH_SCOPES` — now the union

```js
var GH_SCOPES = [{ name: 'contents', level: 'write' }, { name: 'actions', level: 'write' }];
```
(was `[{ name: 'contents', level: 'write' }]`). This is the exact same array `docs/dashboard/run-now.js`'s
`SCOPES` already used — run-now needed no scope change, it was already Contents+Actions (decision 44 gave it
the broader set on purpose since dispatching a workflow needs `Actions: write`; Configure previously requested
only what *it itself* needed, `Contents: write`, which was the actual source of the asymmetry).

## 3. Connect-flow copy — updated at both entry points

Both `renderGithubConnect()` (Configure, `app.js`) and `renderConnect()` (run-now, `run-now.js`) now:
- describe the token as covering **both** features in the deep-link's `description` field (visible on GitHub's
  token-creation page itself) and in the on-page step list, not just "lets Configure commit config.yaml" /
  "lets the dashboard dispatch the Sync workflow" in isolation;
- state explicitly, in the last numbered step, that the same token also covers the other entry point with no
  need to reconnect.

`docs/setup/index.html`'s two relevant steps ("Create your config" and "First dry run") were also reworded —
the first now notes the token also covers Run now, the second now says a token connected via Save to GitHub is
"ready immediately" for Run now rather than describing them as two separate, similar-but-distinct connect steps.

## 4. Test changes — flipped from "do not collide" to "do share", not just deleted

Three existing tests asserted the *old*, now-intentionally-reversed behavior (P1-5's separation). Each was
rewritten to assert the new behavior, keeping the coverage rather than dropping it:

- `tests/e2e/test_dashboard.py::test_run_now_and_save_to_github_tokens_do_not_collide` →
  `test_run_now_reuses_save_to_github_token`: seeds `sessionStorage` with a token under the union scope set
  (what a completed Configure connect now actually writes), opens Run now, and asserts it shows the dispatch
  form (`#run-now-dispatch` visible) with **no** connect step (`#run-now-token` absent) — the exact inverse of
  the old assertion.
- `tests/e2e/test_github_save.py::test_save_to_github_and_run_now_tokens_do_not_collide` →
  `test_save_to_github_reuses_run_now_token`: same inversion in the other direction (seed run-now's token,
  open Save to GitHub, assert the commit form appears with no reconnect step).
- `tests/e2e/test_github_save.py::test_save_to_github_button_offers_deep_link_scoped_to_this_fork`: the
  `assert "actions=write" not in href` line (which documented the old Contents-only deep link) flipped to
  `assert "actions=write" in href`.
- `tests/e2e/test_fork_genericness.py::test_save_to_github_targets_the_viewers_own_fork`: same deep-link
  assertion flip (`actions=write` is now expected), found only once the full e2e suite was run across all
  three browsers — this test lives in the fork-genericness file, not the two files the task named, and was
  missed by grepping just `test_dashboard.py`/`test_github_save.py`; caught because the full gate suite (§6)
  is what's actually required, not just the two named files.
- Three more tests in `test_github_save.py` (`test_connect_verify_commit_first_time_creates_the_file`,
  `test_conflict_shows_diff_and_never_silently_overwrites`,
  `test_versions_drawer_shows_github_commits_labelled_separately`) mocked only
  `GET /repos/{owner}/{repo}` for their `verify()` call. Since Configure's `verify()` now also checks Actions
  access (because `GH_SCOPES` includes an `actions` scope, exactly like run-now already did), these three began
  timing out waiting for `#gh-commit-msg` — the unmocked `GET /repos/{owner}/{repo}/actions/workflows` call hit
  the real network and hung. Fixed by adding the same route mock run-now's equivalent tests already used
  (`fulfill(200, {"workflows": []})`) to all three. This was a genuine consequence of the scope change, not a
  loosened assertion — the same three tests also now exercise slightly more of `verify()`'s real code path
  than before (both the Contents and the Actions check), which is strictly more coverage, not less.

## 5. Full quality gate suite (decision 30)

```
python -m pytest -q                                                            -> 1688 passed, 6 skipped, 277 deselected (26.6s)
SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e -> 275 passed, 2 skipped (128.8s)
python -m pytest tests/e2e -q -m e2e -k axe                                     -> 17 passed (0 new serious/critical violations)
```
All three browsers (Chromium, Firefox, WebKit) launched and ran without any `playwright install` workaround
needed. The interleaved `ConnectionAbortedError`/`BrokenPipeError` tracebacks in the raw e2e output are the
same pre-existing local-dashboard-server-closing-connections-early artifact noted in
`design/reports/phase-more-conditions.md` §8 and `phase-dashboard-design-system.md` §9 — not test failures;
every run above exits 0.

**Lighthouse runs in CI only** (`treosh/lighthouse-ci-action`) — not runnable in this local environment;
unverified here, the standing caveat every prior phase report in this repo notes.

**Live tests (`SPOTISORT_LIVE=1`) were not run** — no `.env`/credentials exist in this worktree, and nothing in
this phase touches Spotify's API, enrichment, or any Python code at all; the entire diff is two `docs/` JS
files, one `docs/` HTML file, `docs/sw.js`'s cache version, and three e2e test files.

`docs/sw.js`'s `CACHE_VERSION` bumped `'v13'` → `'v14'`: `assets/github-pat.js`, `builder/app.js`,
`dashboard/run-now.js`, and `setup/index.html` are all in the precached `SHELL` list and all changed content,
per the file's own standing instruction to bump the version whenever any cached file changes.

`docs/screenshots/*.png` (20 files) were regenerated by the e2e screenshot test as a side effect of running the
suite — visible in `git status`. Not manually inspected pixel-by-pixel; the underlying pages were independently,
programmatically verified live in §6 below.

## 6. Live cross-flow verification (not just the test suite)

Two techniques were used, matching the two the task named as acceptable, for two different reasons documented
below.

### 6a. Direct JS evaluation against a running instance — the storage mechanism itself

Started a local static server (`python -m http.server 8931 --directory docs`) and opened
`http://127.0.0.1:8931/dashboard/index.html` in the Browser tool. Ran this directly in the live page console
(`javascript_tool`):

```js
window.sessionStorage.clear();
const before = window.GithubPAT.get('octo', 'spot', [{name:'contents',level:'write'},{name:'actions',level:'write'}]);
window.GithubPAT.set('octo', 'spot', [{name:'contents',level:'write'},{name:'actions',level:'write'}], 'github_pat_from_configure_flow');
const seenByRunNow = window.GithubPAT.get('octo', 'spot', [{name:'contents',level:'write'},{name:'actions',level:'write'}]);
const seenByNarrowerFutureCaller = window.GithubPAT.get('octo', 'spot', [{name:'contents',level:'write'}]);
const keys = Object.keys(window.sessionStorage).filter(k => k.indexOf('likedzero.pat') === 0);
```
**Actual result:**
```json
{
  "before": null,
  "seenByRunNow": "github_pat_from_configure_flow",
  "seenByNarrowerFutureCaller": "github_pat_from_configure_flow",
  "storageKeys": ["likedzero.pat.octo/spot"]
}
```
One storage key, shared regardless of which scope array is passed to `get()` — including a narrower, made-up
subset standing in for a future caller, confirming §1's "robust to future third callers" reasoning is not just
theoretical.

### 6b. Real button click on a running instance — Configure connecting, Run now benefiting

Same local server/tab. Set the dashboard's repo data source to `octo/spot` (via the real "Raw GitHub folder
URL" field + "Save URL"/"Reload data" buttons — `raw.githubusercontent.com` fetches were redirected to the
bundled fixtures via a `window.fetch` override injected in the page console, since the real
`github.com/octo/spot` doesn't exist; this only substitutes the *data* fetch, not any PAT logic). With the
session's `sessionStorage` already holding the token from §6a (i.e., the exact state a completed Configure
"Save & verify" would have left, since `renderGithubConnect`'s success handler calls
`window.GithubPAT.set(rr.owner, rr.repo, GH_SCOPES, tok)` — the same call reproduced in §6a), clicked the real
"Run now" button.

**Actual result** (read from the live DOM, `document.getElementById('run-now-body').innerHTML`, and confirmed
visually):
```html
<p class="small muted">Connected to <code>octo/spot</code>. <button ...>Forget token</button></p>
<div class="field"><label class="check-row"><input type="checkbox" class="check" id="run-now-dry" checked> Dry run (no writes)</label></div>
<div class="field"><label for="run-now-newest">Only touch the N newest liked songs...</label>...
```
No "Fine-grained personal access token" field, no connect step — straight to the dispatch form. Screenshot
taken confirming the same visually (dialog titled "Run now", "Connected to octo/spot", dry-run checkbox,
newest/max-moves fields, "Dispatch the Sync workflow" button — no token input anywhere).

### 6c. The reverse direction — Run now connecting, Configure benefiting

Configure's own `ownerRepoParts()` derives owner/repo from `location.hostname` ending in `.github.io`
specifically (unlike the dashboard's repo field, which is a plain user-typed value) — so driving its real
"Save to GitHub" button end-to-end requires the page to actually believe it's served from `*.github.io`.
`location.hostname` isn't reassignable from page-console JS, and this environment has no way to point a real
`*.github.io` hostname at a local server without a hosts-file/system-settings change, which is out of bounds
here. This direction was therefore verified with the technique this repo's own required decision-41
fork-genericness proof already established for exactly this class of problem — Playwright's request-level
origin faking (`serve_fake_origin`, `tests/e2e/conftest.py`), which serves the real site under a genuine fake
origin (`https://someoneelse.github.io/their-fork/`) so `location.hostname` is authentically that value, not
mocked at the JS level:

`tests/e2e/test_github_save.py::test_save_to_github_reuses_run_now_token` — seeds `sessionStorage` with
run-now's token under the union scope set, clicks the real "Save to GitHub" button on the faked origin, and
asserts the commit form (`#gh-commit-msg`) appears with no token field (`#gh-token` absent). **Passing** (part
of the 275/275 e2e run in §5). This is a real button click against real production code in a real browser
engine (run three ways: Chromium, Firefox, WebKit) — the only difference from §6b's technique is *how* the
origin is established (Playwright network-level interception vs. a literal local hostname), not whether the
click and render are real.

## Files touched

`docs/assets/github-pat.js`, `docs/builder/app.js`, `docs/dashboard/run-now.js`, `docs/setup/index.html`,
`docs/sw.js` (cache version bump), `tests/e2e/{test_dashboard.py,test_github_save.py,test_fork_genericness.py}`,
plus 20 regenerated screenshots.

## Deviations / judgment calls, flagged for the master to double-check

1. **Storage keyed by owner/repo alone, not "both callers request the identical array"** — the task offered
   both as acceptable; I picked the more robust one (§1) because decision 58's planned future caller
   (`analyze.yml`, Actions-only scope) would otherwise reopen this exact bug the moment it's built. Flagging
   since it's a slightly bigger change inside `github-pat.js` than the minimal "just change the two callers'
   arrays" option would have been, even though the net diff is actually smaller (removes `scopeKey()` entirely
   rather than adding a third scope-key branch later).
2. **`scopes` parameter kept (but now unused for keying) in `get`/`set`/`clear`** rather than removed from the
   signature — done to avoid touching every call site's argument list for a parameter that's still meaningful
   to `verify()`/`tokenUrl()`, per the instruction to keep the API shape if reasonable. If the master would
   rather it be dropped for clarity, that's a small follow-up.
3. Found and fixed a third stale "do not collide" test (`test_fork_genericness.py`) beyond the two files named
   in the task — caught only by running the *full* e2e suite rather than the two named files, confirming why
   decision 30's full-suite requirement matters here specifically.
4. Direction 2 of the live cross-flow proof (§6c) used Playwright's origin-faking rather than a literal manual
   click-through in the Browser pane, for the concrete technical reason given there (Configure's owner/repo
   derivation needs a real `*.github.io` `location.hostname`, which nothing in this environment can produce
   locally without a system-settings change). This is the same technique the repo's own decision-41 test
   already relies on for this exact class of verification, not a new or weaker substitute.
