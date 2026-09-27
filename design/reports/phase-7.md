# Phase 7 report — GitHub write-back for Configure

Implementation session, 2026-09-27, immediately after Phase U2 (Part A). No `--apply` of any kind; this phase
never touches Spotify at all, only GitHub's Contents/commits API from the visitor's own browser and their own
token.

## 1. Verdict: **PASS**, verified against mocked GitHub responses only (see §5 caveat)

1. Reuses `docs/assets/github-pat.js` as-is, unmodified — no new token flow.
2. "Save configuration" gained a "Save to GitHub" button that connects, commits `config.yaml` via the Contents
   API, and handles a 409 conflict with a diff + explicit overwrite/cancel choice (never a silent clobber).
3. The Versions drawer's "On GitHub" section lists the last 5 commits to `config.yaml`, labelled separately
   from "Saved locally", each with Compare/Restore.
4. Passes the fork-genericness test from Part A (`tests/e2e/test_fork_genericness.py::test_save_to_github_targets_the_viewers_own_fork`).
5. No secrets/tokens logged; token lives in `sessionStorage` only, same as run-now.

## 2. Proof
```
$ python -m pytest -q -m e2e tests/e2e/test_github_save.py       -> 5 passed
$ python -m pytest -q -m e2e tests/e2e/test_fork_genericness.py  -> 4 passed (incl. the Phase 7 target check)
$ python -m pytest -q -m e2e                                     -> 196 passed, 2 skipped
$ python -m pytest -q                                             -> 1525 passed, 2 skipped
```
Test coverage, all against a real DOM in a real (Chromium) browser, with GitHub's REST API mocked via
Playwright route interception (`page.route`), served under a genuinely different fake origin
(`https://someoneelse.github.io/their-fork/`, not the maintainer's) so nothing here is accidentally
self-referential:
- **Deep link scoped to this fork**: `target_name=someoneelse`, `contents=write` present, `actions=write`
  absent (Phase 7 only ever needs Contents, unlike run-now's Contents+Actions).
- **Not on Pages**: opening "Save to GitHub" from `127.0.0.1` (no owner/repo derivable) shows a plain message
  naming the problem, not a guess.
- **First-time create**: `GET contents/config.yaml` → 404 → `PUT` with no `sha` → 201; the PUT body's
  base64-decoded content matches the Review step's own YAML preview byte-for-byte, `branch: "main"`.
- **Conflict, never silently clobbered**: a PUT that 409s (simulating another commit landing between this
  client's own pre-commit GET and its PUT — the actual race the real API guards against) shows the
  diff against GitHub's *current* content, offers "Overwrite GitHub's version with mine" or "Cancel"; the
  mock asserts the overwrite retry uses the sha the conflict view just re-fetched, not the stale one that
  caused the 409 (a real overwrite with the wrong sha would just 409 again).
- **Versions panel**: after a successful connect, opening Versions shows "On GitHub" with the mocked commit
  list (message, timestamp, Compare/Restore), separately headed from "Saved locally".

## 3. What was built
- `docs/builder/index.html`: "Save to GitHub" button next to "Save configuration"; a new `#github-save-dialog`
  (reuses the existing `.dialog`/`.overlay` component, same as Compare/Schema); the Versions drawer split into
  "Saved locally" / "On GitHub" sections; `assets/github-pat.js` script tag added; updated the stale "Until
  GitHub write-back ships…" hint text under the action buttons.
- `docs/builder/app.js` — new functions, all reusing existing app.js internals (`current.yaml`, `blocked()`,
  `lineDiff()`, `openCompare()`, `restoreVersion()`, the `h()` DOM helper) rather than duplicating them:
  - `ownerRepoParts()`: `<owner>.github.io` + first path segment → `{owner, repo, real}`; `real: false`
    (not a guess) when not served from GitHub Pages.
  - `openGithubSave()` / `renderGithubConnect()` / `renderGithubCommitForm()`: the connect-then-commit flow,
    built via `h()` (DOM nodes, not `innerHTML` string concatenation) specifically so that a malicious or
    corrupted `config.yaml` on GitHub can never inject markup into the page — the diff view in particular
    renders untrusted remote file content.
  - `githubGetFile()` / `githubPutFile()`: the Contents API GET (sha + base64 content) and PUT (base64 content,
    `sha` only when updating, `branch: "main"`).
  - `doGithubCommit()`: on 401 clears the stored token and reopens the connect flow; on 409 hands off to…
  - `renderGithubConflict()`: re-fetches the current remote file, renders a line diff (`lineDiff`, the same
    algorithm Compare-with-current already used) via DOM nodes, and requires an explicit "Overwrite" click
    before retrying with the freshly-fetched sha — "Cancel" just returns to the commit form, changing nothing.
  - `loadGithubVersions()` / `githubFileAtRef()` / `compareGithubCommit()` / `restoreGithubCommit()`: the "On
    GitHub" Versions section, lazy-loaded only when the drawer is actually opened (`ui:open` event, the same
    generic overlay system `assets/ui.js` already provides) so it never costs an API call on every keystroke.
- Base64 helpers (`b64EncodeUtf8`/`b64DecodeUtf8`) for UTF-8-safe encode/decode of the Contents API's `content`
  field (song/playlist names in `config.yaml` can be non-ASCII).
- `tests/e2e/conftest.py`: `serve_fake_origin()`, a reusable helper that routes a fake `*.github.io` origin to
  the real files on disk — shared by this phase's tests and the Part A fork-genericness test.
- `tests/e2e/test_github_save.py`: 5 new tests (deep link, not-on-Pages message, first-time create, conflict,
  versions panel).

## 4. Cross-cutting rules checked
- Never reads/logs `.env` or any Spotify credential — this phase never touches `src/` or Spotify at all.
- The GitHub PAT is handled exactly like run-now's: `sessionStorage` only, verified with a `GET` before being
  trusted, never placed in a URL, never logged. Reused `github-pat.js` unmodified, so there is exactly one
  place in the codebase that touches a GitHub token's lifecycle for both features.
- No fork-genericness violation: grepped the new code for `Vishnu-DRX`/hardcoded repo names — none;
  `ownerRepoParts()` is the only source of truth for which repo gets committed to.

## 5. Deviations / caveats
- **Verified only against mocked GitHub responses, not a real fork** — same caveat `phase-8b.md` already
  recorded for run-now's PAT deep-link. I do not have a second real GitHub account/fork to round-trip against
  in this session. Before relying on this in production, try it once for real: create a token via the deep
  link, commit, cause a real conflict (edit `config.yaml` on GitHub between loading Configure and committing),
  and confirm the Versions panel's "On GitHub" list matches what's actually in the repo's commit history.
- GitHub's Contents API requires the *entire* file content on every PUT (no partial patch); `config.yaml` is
  small (a handful of KB even with many rules), so this is not a practical size concern.
- The commit message is a single free-text field with a fixed default ("Update config.yaml via Configure");
  no attempt was made to auto-generate a more descriptive message from what changed — not asked for, and
  the existing local-Versions "summary" field (rule/playlist counts) already serves that role for local saves.

## 6. Next
Master's call on whether Phase 7's "On GitHub" versions list should also gain a delete/prune affordance for
old commits (not asked for here, and commit history on GitHub is not really "prunable" the way local versions
are), and whether the run-now/Save-to-GitHub PAT flows should eventually be verified against a real second
fork before the project is presented as production-ready to strangers.
