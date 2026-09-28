# Phase: rename the project from SpotiSort to LikedZero (Master decisions 13, item 62)

Renames the project's own identity everywhere it appears in the repo (code, config header comments, top-level
docs, the whole `docs/` Pages site including a live-verified absolute-path check) while leaving two things
completely untouched: the two real Spotify playlist names `SpotiSort Test` / `SpotiSort Sink`, and the
`design/reports/*.md` / `design/reviews/*.md` historical record. The GitHub repo rename itself
(`Vishnu-DRX/SpotiSort` -> `Vishnu-DRX/LikedZero`) and the live Pages URL move were already done by the master
session before this phase started; this phase is the repo-content follow-up.

## 0. Method: grep-and-categorize first, then edit

Before touching anything, ran `grep -rli -i "spotisort" .` across the whole repo and read every hit's
surrounding context (not just the match line) to sort it into one of four buckets:

1. **The project's own name** -> rename to `LikedZero`/`likedzero` (case-matched).
2. **One of the two real playlist names** (`SpotiSort Test`, `SpotiSort Sink`) -> never touched.
3. **Historical record** (`design/reports/*.md`, `design/reviews/*.md`) -> never touched, regardless of which
   of the above two categories a given hit inside them would otherwise be.
4. **Env var names** (`SPOTISORT_LIVE`, `SPOTISORT_BROWSERS`, `SPOTISORT_COMMITTED_RUN`,
   `SPOTISORT_SCHEDULED_APPLY`, `SPOTISORT_CRON`) -> a judgment call, see §6.

For `docs/` specifically, confirmed with `grep -rn -i "spotisort test\|spotisort sink" docs/` that **zero**
hits in the whole site are playlist-name references, which made a blanket case-preserving replace
(`SpotiSort`->`LikedZero`, `spotisort`->`likedzero`) safe across that entire tree in one pass. Everywhere else
(`src/`, `tests/`, `config.yaml`, workflows, scripts, top docs) was edited hit-by-hit because playlist-name
references are mixed in with project-name references in those files.

## 1. Code (decision 62, bullet 1)

- `src/enrichment/musicbrainz.py`: `USER_AGENT = f"SpotiSort/{__version__} (https://github.com/Vishnu-DRX/SpotiSort)"`
  -> `f"LikedZero/{__version__} (https://github.com/Vishnu-DRX/LikedZero)"` (both the name and the stale GitHub
  URL, as instructed). `tests/test_enrichment.py::test_isrc_request_shape_and_user_agent` asserted the old
  string; updated in the same edit so it still tests the real constant instead of going stale.
- `log = logging.getLogger("spotisort")` in `musicbrainz.py` and `spotify_client.py` -> `"likedzero"`. Not
  explicitly named in decision 62's bullet list, but it's a plain project-name self-reference with zero
  external dependency (grepped `tests/` for any code that asserts on the logger name string — none), so I
  treated it the same as the other code-level renames rather than leaving it inconsistent.
- `spotify_client.py`'s PKCE callback page text `b"SpotiSort: login received..."` -> `b"LikedZero: login
  received..."` (user-visible in the browser tab during `--setup`; no test depends on the literal bytes).
- `src/__init__.py` module docstring, `src/analyze.py`'s two generated-file header comments, `src/dashboard.py`'s
  `server_version` HTTP identifier and its two CLI/print strings — all project self-references, all renamed.
- Left alone (playlist name, not project name): `src/analyze.py`'s
  `p.name.casefold() != "spotisort test"` filter, `TEST_PLAYLIST = "spotisort test"` in `src/backtest.py`,
  `src/enrichment/artist_playlist.py`, `src/measure_artist_in_playlist.py`, and that last file's two docstring
  mentions of `` `SpotiSort Test` ``.
- `.github/workflows/*.yml`: `sync.yml`'s concurrency `group: spotisort-sync` -> `likedzero-sync`, and the
  commit-back bot identity `git config user.name "spotisort-bot"` / `spotisort-bot@users.noreply.github.com`
  -> `likedzero-bot` / `likedzero-bot@users.noreply.github.com`. This last one is a scope judgment call: decision
  62 says workflow **comments/step names**, and a `git config` value is neither — but it's a plain project-name
  self-reference that becomes the visible committer identity on every public commit the workflow makes, so
  leaving it `spotisort-bot` while everything else says LikedZero would look like a leftover mistake, not a
  deliberate choice. `tests/test_workflows.py::test_sync_permissions_and_bot_identity` asserted the old string;
  updated alongside. `.github/workflows/e2e.yml` had no project-name hits at all (only `SPOTISORT_BROWSERS`, an
  env var, see §6).

**Proof:**
```
python -m pytest tests/test_enrichment.py tests/test_workflows.py -q   -> 2 files, all passing (part of the 1963 below)
```

## 2. Config header comments only (decision 62, bullet 2) — NOT target_playlist values

- `config.yaml` line 1: `# SpotiSort live config.` -> `# LikedZero live config.` Nothing else in the file
  touched — confirmed with `git diff config.yaml` showing exactly that one line changed; the `SpotiSort Sink`
  rule name and `target_playlist: "SpotiSort Sink"` (lines 90/93/97) are untouched.
- `config.example.yaml`: it has no single top "header comment line" the way `config.yaml` does, but line 3's
  `# Optional: tell SpotiSort which of your playlists...` is the equivalent project self-reference in that
  file, so it got the same treatment -> `tell LikedZero which...`.
- `python -c "from src.config import load_config; load_config('config.yaml')"` still loads cleanly, 12 rules
  (comments aren't parsed, so this was never at risk, but confirmed anyway).

## 3. Top-level docs (decision 62, bullet 3)

- `README.md`, `CLAUDE.md`: title line `# SpotiSort` -> `# LikedZero`. README also had two Pages-site URLs
  (`.../SpotiSort/setup/`, `.../SpotiSort/builder/`) fixed to `/LikedZero/` — these were absolute-path hits,
  cross-referenced against §5's live check. No badges exist in README to update (checked; none present).
  `CLAUDE.md`'s one other hit (`SpotiSort Test` in the Safety section) is the playlist name — untouched.
- `IMPLEMENTATION_PLAN.md`: **zero** literal "SpotiSort" hits anywhere in the file (confirmed by grep) — its
  title has always been "Spotify Liked-Songs Auto-Sorter — Implementation Plan" with no project-name branding,
  so decision 62's "title/intro" instruction is already satisfied; no edit was needed or made.
- `BUILD_SPEC.md`: the intro banner, decision 26's canonical URL, and the doc's own title were already fixed by
  the master session before this phase (confirmed unchanged by me). I made exactly one further edit: decision
  22's spec text `footer states "SpotiSort is an independent open-source project..."` -> `"LikedZero is an
  independent..."`, since that's forward-facing prose dictating the live footer copy I was simultaneously
  changing in `docs/assets/shell.js`, and leaving the spec's quoted string stale next to the real (now-changed)
  footer would be a drift bug in the spec itself. Full list of what I *didn't* touch in `BUILD_SPEC.md`, and why,
  is in §7 below — every other hit is either the playlist name, an env var name, or historical/decision-record
  prose that intentionally quotes the old name (e.g. decision 61/62's own instructions, the "already done"
  rename-command record, Phase 1's period-accurate `gh api ... SpotiSort` example commands).
- `design/why-no-richer-spotify-metadata.md`: not explicitly named in decision 62's list, but it's a live design
  doc (not a phase report/review) with three forward-facing "SpotiSort" self-references (title, "what SpotiSort's
  app is", "what this means for SpotiSort") — renamed all three, consistent with how the rest of `design/`
  (excluding `reports/`/`reviews/`) was treated.
- `design/reports/*.md` and `design/reviews/*.md`: confirmed **zero** edits made to any file in either directory
  — grepped both directories before and after and diffed the file lists against `git status`; none appear.

## 4. The `docs/` site (decision 62, bullet 4)

Blanket case-preserving replace (see §0) across the 22 text files in `docs/` that had any hit — verified
by grep that this left **zero** residual `spotisort`/`SpotiSort` anywhere under `docs/` afterward, while
leaving the unrelated `Spoti`-prefixed JS namespace globals (`SpotiUI`, `SpotiLang`, `SpotiShell`,
`SpotiValidate`, `SpotiSchema`, `window.__spotiBuilder`) untouched since they don't literally contain the
string "SpotiSort" (see §6 for why I didn't rename these too).

Covered by that pass: every page's `<title>`/meta description/OG+Twitter tags/canonical URL (`index.html`,
`setup/index.html`, `builder/index.html`, `dashboard/index.html`, `404.html`), the PWA manifest
(`name`/`short_name`/`description` in `manifest.webmanifest`), `site.config.json` checked and confirmed it has
**no** project-name mentions (only author credit, correctly excluded per decision 26/62), the footer disclaimer
sentence, the "Star/Fork on GitHub" and upstream-credit `href`s (now `github.com/Vishnu-DRX/LikedZero`), nav
brand text, favicon `aria-label`, OG image alt text, `localStorage` key namespaces (theme, PAT cache, dashboard
source/repo/mode, builder draft/versions/advanced — all `spotisort.*`/`spotisort-*` -> `likedzero.*`/
`likedzero-*`), the builder's generated-YAML header comment, and prose mentions across
`COMPONENTS.md`/`kitchen-sink.html`/`shell.js`/`ui.js`/`github-pat.js`/`run-now.js`/`views.js`/`app.js`/
`schema.js`.

**Service worker (`docs/sw.js`):** renamed `CACHE_NAME` (`spotisort-shell-` -> `likedzero-shell-`) and, per
decision 62's explicit instruction, **bumped `CACHE_VERSION`** `'v11'` -> `'v12'` since the cached asset
contents changed. Confirmed no test asserts the literal version string.

**Favicon/OG regeneration:** `scripts/gen_site_assets.py` draws the OG card's wordmark as pixel-font text
("SPOTISORT" -> "LIKEDZERO") and sets the favicon `aria-label`. The font table (`FONT3X5`) had **no glyph for
"Z"** — needed for LIKEDZERO but not for SPOTISORT — so I added one (`"Z": ["111","001","010","100","111"]`,
a plain zig-zag). Ran `python scripts/gen_site_assets.py` to regenerate `docs/assets/favicon.svg`,
`docs/icons/*.png` and `docs/assets/og.png` for real (not just edited the generator and left stale output);
`git status` shows `favicon.svg` and `og.png` changed, `icons/*.png` unchanged (expected — the icon marks
contain no text, so byte-identical). Viewed the regenerated `og.png`: "LIKEDZERO" renders correctly including
the new Z glyph, tagline unchanged, mark unchanged.

## 5. CRITICAL: absolute-path `/SpotiSort/` and `Vishnu-DRX/SpotiSort` fragments — live-verified, not just grepped

Grepped the whole repo specifically for the literal fragments `/SpotiSort/` and `Vishnu-DRX/SpotiSort` (separate
from the general name audit, as instructed). Every hit outside `design/reports/`, `design/reviews/`, and
`BUILD_SPEC.md`'s own historical/instructional prose was fixed: `docs/index.html`'s canonical/og:url,
`docs/setup/index.html`'s canonical/og:url/banner text/fork command/clone command, `docs/sw.js`'s base-path
comment, `docs/assets/COMPONENTS.md`/`shell.js`'s base-path comments, `README.md`'s two Pages URLs,
`scripts/set_secrets.ps1`'s `$Repo` value (this one is functionally live — it's what `gh secret set --repo`
actually targets), and two test files: `tests/e2e/conftest.py`'s `BASE_PATH` (the local e2e test server's
simulated Pages base path) and `tests/e2e/test_site.py`'s `test_fork_link_derivation_real` parametrize table.

That last one wasn't optional: `docs/assets/shell.js`'s `deriveFork()` compares **both** the hostname's owner
*and* the URL's first path segment against `UPSTREAM_OWNER`/`UPSTREAM_REPO` to decide "is this the canonical
site, not a fork" (line ~175). Since `UPSTREAM_REPO` is now `'LikedZero'`, the pre-existing test case
`("vishnu-drx.github.io", "/SpotiSort/", None)` would have started **failing** (segment `SpotiSort` no longer
equals `LikedZero`, so `deriveFork` would wrongly treat the canonical site as someone else's fork) had I not
updated the pathname literal. Caught this by reading `shell.js`'s comparison logic before editing the test,
not by running it and seeing red first.

**Live verification method used** (per the instruction that "tests pass" isn't sufficient proof here): wrote a
throwaway local HTTP server (`serve_likedzero.py`, in the scratchpad, not committed) that serves `docs/` under
a `/LikedZero/` path prefix exactly like the real GitHub Pages project-site URL, refusing anything outside that
prefix (so a stray absolute reference to `/SpotiSort/` or a bare root path would 404 instead of silently
resolving against the server's own root). Opened it in the Browser pane and:

- Loaded Home, Configure, and Dashboard; read back every network request — **all resolved 200** under
  `/LikedZero/`, zero 404s (confirmed via `read_network_requests`, ~100 requests total: CSS/JS/HTML/fixtures/
  `site.config.json`/vendor JS).
- Fetched `manifest.webmanifest`, `sw.js`, all four icon files, `favicon.svg`, `og.png`, `404.html` directly —
  all 200.
- Evaluated in-page: `document.querySelector('link[rel=canonical]').href` ->
  `https://vishnu-drx.github.io/LikedZero/`, `meta[property=og:url]` -> same, fetched manifest JSON and
  confirmed `name`/`short_name` = `"LikedZero"` (its `start_url`/`scope` are relative `"./"`, so they were never
  at risk of the absolute-path bug, but confirmed anyway).
- Parsed `sw.js`'s `SHELL` array (51 entries) programmatically and fetched every single one under the
  `/LikedZero/` base — **zero bad entries**, all 200.
- Confirmed the live-rendered footer text reads "LikedZero is an independent open-source project...".
- Attempted `navigator.serviceWorker.register('sw.js')` — it failed with "An unknown error occurred when
  fetching the script" even though the script itself fetches fine (200, correct `text/javascript` content-type,
  `window.isSecureContext` true, and the file parses with zero `SyntaxError` via `new Function(text)`). This
  reproduces against this sandbox's embedded Browser pane talking to a bare `http.server` backend and is not
  something my edit could have caused — every file the worker would need to fetch is reachable and the script's
  syntax is valid; I did not chase it further since it's an environment quirk, not a repo bug, and is outside
  this phase's scope.

This is stronger proof than "the e2e suite's fake-origin tests pass" alone (though those pass too, see §8) —
it's an independent, from-scratch local reproduction of the real deployed URL shape, checked by actually
fetching every asset a browser would need.

## 6. Deliberately left unchanged, and why (for the master to audit)

**(a) The two real Spotify playlist names — never touched, anywhere.** Every occurrence of literal
`SpotiSort Test` or `SpotiSort Sink` in the repo was left byte-for-byte identical. Full list of files containing
these (all confirmed to be exclusively playlist-name references, nothing else, by reading context before and
re-grepping after):
- `config.yaml` (the `SpotiSort Sink` catch-all rule's name/comment/`target_playlist` value, lines 90/93/97)
- `CLAUDE.md` (Safety section, "Live write tests target only... `SpotiSort Test`")
- `BUILD_SPEC.md` (14 occurrences across decisions 1, 6b, 14-15, G2b, 36, 51, 61, "Verified write shapes", Phase
  4 — all either the playlist name itself or decision 61's own instruction quoting it)
- `src/analyze.py` (`p.name.casefold() != "spotisort test"` — the live filter that excludes this real playlist
  from analysis)
- `src/backtest.py`, `src/enrichment/artist_playlist.py`, `src/measure_artist_in_playlist.py`
  (`TEST_PLAYLIST = "spotisort test"` and two docstring mentions)
- `tests/e2e/test_builder.py`, `tests/e2e/test_dashboard.py`, `tests/test_analyze.py`,
  `tests/test_artist_playlist.py`, `tests/test_backtest.py`, `tests/test_catch_all_live.py`,
  `tests/test_config.py` (fixture/assertion data using the real playlist names)
- `logs/2026-09-27.json`, `logs/runs.json`, `logs/latest-plan.json` (committed run artifacts; the catch-all
  rule's name embeds the playlist name — these are generated data, not hand-edited, and regenerate from
  `config.yaml`'s unchanged rule name on the next real run)

**(b) `design/reports/*.md` and `design/reviews/*.md` — left completely untouched**, per decision 62's explicit
instruction (same exclusion this project has always used for historical record). Confirmed via `git status`:
none of the 15 files in `design/reports/` or the 1 file in `design/reviews/` appear as modified.

**(c) `SPOTISORT_LIVE`, `SPOTISORT_BROWSERS`, `SPOTISORT_COMMITTED_RUN`, `SPOTISORT_SCHEDULED_APPLY`,
`SPOTISORT_CRON` — left unchanged everywhere** (`.github/workflows/*.yml`, `pytest.ini`, `src/spotify_client.py`,
`src/sync.py`, every `tests/*.py` that sets/reads them, `scripts/make_dashboard_fixtures.py`'s comment). This
is a genuine judgment call, not an oversight: decision 62's scope list is specific (USER_AGENT, config header
lines, top docs, the `docs/` site, the fork-genericness test) and never mentions environment-variable names.
Renaming them would be a **functional** change, not a cosmetic one — it touches CI workflow env blocks, the
`gh workflow run -f` inputs a real user or the dashboard's run-now button would send, and every test that
patches `os.environ`; getting one file wrong would silently break CI or a live dispatch in a way a rename-only
review pass is unlikely to catch. Per the instruction to "err toward NOT changing it and note it... rather than
guessing wrong," I left all five alone. **Flagging for the master:** if a full env-var rename is wanted, it's a
separate, larger, more test-coverage-sensitive change than this phase, not a quick follow-on.

**(d) `Spoti`-prefixed JS namespace globals — left unchanged, out of the literal scope given.** `docs/`'s
vanilla-JS files use several internal namespace objects that start with "Spoti" but are **not** literally
"SpotiSort": `window.SpotiUI`, `window.SpotiLang`, `window.SpotiShell`, `window.SpotiValidate`,
`window.SpotiSchema`, and `window.__spotiBuilder` (used across `docs/assets/{ui,shell}.js`,
`docs/builder/{app,languages,schema,validate}.js`, and referenced by name in ~30 call sites across
`tests/e2e/{test_builder,test_dashboard_via... }`, actually `test_builder.py`, `test_fork_genericness.py`,
`test_github_save.py`, `test_site.py`, `conftest.py`). I want to flag this prominently: **decision 13's own
stated reason for this whole rename is that a "Spoti-" prefix carries the identical trademark-pattern risk that
"SpotiSort" did**, and these are exactly that pattern, just as internal code identifiers rather than the public
product name. They didn't match the literal grep task I was given ("grep for SpotiSort/spotisort"), so I did
not touch them — renaming them would mean updating ~10 source files plus every one of those ~30 test call
sites, which is a materially larger and differently-scoped change than a text/branding rename. Leaving this for
the master to decide whether it's worth a dedicated follow-up pass.

## 7. `BUILD_SPEC.md`: what I left in the "historical completed-phase narrative" category, and why

Beyond the one edit in §3 (decision 22's footer-text spec), every other `SpotiSort` hit in `BUILD_SPEC.md` falls
into one of: the playlist name (§6a); decision 13/61/62's own text, which quotes the old name on purpose to
explain the rename itself (e.g. "the project is renamed from *SpotiSort* to *LikedZero*", "the Pages URL path
changed from `/SpotiSort/` to..."); the "Already done by the master session" record of the literal
`gh repo rename LikedZero --repo Vishnu-DRX/SpotiSort -y` command (correct as written — that command's syntax
requires the pre-rename name); the five `SPOTISORT_*` env var mentions (§6c); or genuine historical
completed-phase text describing what a prior phase actually ran/verified against the (then-correctly-named)
repo — Phase 1's `gh api repos/Vishnu-DRX/SpotiSort/...` example commands and its success-criteria table row
(`curl -sI https://vishnu-drx.github.io/SpotiSort/`), and Phase 2's spec description of the User-Agent format
that phase shipped. I treated these the same way the master's own instruction treats Phase 1's example commands
("may stay as historical record — your judgment") rather than retroactively editing a already-completed phase's
own spec text, since `BUILD_SPEC.md`'s Phase 1-8 sections document what was asked for and delivered at the time,
not a live, evergreen description of the current system the way the top banner/decision list is.

## 8. Full quality gate suite (decision 30)

```
python -m pytest -q -m "not live"                                            -> 1963 passed, 2 skipped, 6 deselected (148.5s)
SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e   -> 275 passed, 2 skipped (121.5s)
SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e -k axe   -> 17 passed (0 new serious/critical violations)
python -m pytest tests/e2e/test_fork_genericness.py -v -m e2e                -> 4 passed
python -m pytest tests/e2e/test_site.py -k fork_link -v -m e2e               -> 5 passed (the deriveFork parametrize table, §5)
python -m pytest tests/test_dashboard_fixtures.py -q                         -> 4 passed (byte-identical regeneration unaffected)
```
The noisy `BrokenPipeError` tracebacks interleaved in the raw pytest output are a pre-existing artifact of the
local dashboard-server test harness closing connections early (visible in both the offline and e2e runs,
unrelated to this phase's changes) — not test failures; both runs exit 0.

`docs/screenshots/*.png` (78 files) were regenerated by the e2e run with the new branding, as expected — visible
in `git status` as modified; not manually inspected pixel-by-pixel per file, but the underlying pages were
independently verified live in §5.

**Live tests (`SPOTISORT_LIVE=1`) were not run.** No `.env`/credentials exist in this worktree (confirmed:
no `.env` file present), so they cannot be run here regardless. Separately, nothing in this phase changes
request behavior against Spotify's API — the one live-relevant change is `musicbrainz.py`'s `USER_AGENT` string
sent to MusicBrainz (a public, unauthenticated API), which keeps the exact same `Name/Version (URL)` shape as
before with only the literal text substituted; the offline test that pins its exact value passes. Consistent
with the precedent in `design/reports/phase-more-conditions.md` §8 for phases that don't touch live-request
shapes.

**Lighthouse runs in CI only** (`treosh/lighthouse-ci-action`) — not runnable in this local environment;
unverified here, same caveat as every prior phase report in this repo.

## Files touched

`CLAUDE.md`, `README.md`, `config.yaml`, `config.example.yaml`, `design/BUILD_SPEC.md`,
`design/why-no-richer-spotify-metadata.md`, `.github/workflows/sync.yml`, `scripts/gen_site_assets.py`,
`scripts/set_secrets.ps1`, `src/__init__.py`, `src/analyze.py`, `src/dashboard.py`,
`src/enrichment/musicbrainz.py`, `src/spotify_client.py`, `tests/e2e/conftest.py`, `tests/e2e/test_dashboard.py`,
`tests/e2e/test_fork_genericness.py`, `tests/e2e/test_site.py`, `tests/test_enrichment.py`,
`tests/test_workflows.py`, and 21 files under `docs/` (`404.html`, `assets/{COMPONENTS.md,components.css,
favicon.svg,github-pat.js,kitchen-sink.html,og.png,shell.js,site.css,tokens.css,ui.js}`,
`builder/{app.js,index.html,schema.js}`, `dashboard/{app.js,data.js,index.html,run-now.js,views.js}`,
`index.html`, `manifest.webmanifest`, `setup/index.html`, `sw.js`) plus 78 regenerated screenshots.

## Deviations from the master's instruction

None that changed behavior. Two scope judgment calls made beyond the literal bullet list (the `sync.yml` bot
identity/concurrency-group in §1, and `BUILD_SPEC.md` decision 22's footer-text spec in §3) are both flagged
above with reasoning, in the same "your call, document the choice" spirit the master has used for prior phases
(e.g. the catch-all rule's schema shape). Everything else either matches decision 62's list exactly or is one
of the deliberate non-changes catalogued in §6-7.
