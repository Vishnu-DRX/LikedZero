# LikedZero — Build Spec (phase by phase)

> **2026-09-29: the project is renamed from "SpotiSort" to "LikedZero"** (name collision with an unrelated
> existing project, plus "Spoti-" prefixes generally risk Spotify's trademark-enforcement pattern — see
> Master decisions 13 below). The GitHub repo is renamed (`github.com/Vishnu-DRX/LikedZero`), Pages now serves
> at `vishnu-drx.github.io/LikedZero/`. **Do not confuse this with the Spotify playlists literally named
> "SpotiSort Test" and "SpotiSort Sink"** — those are real playlist names already created in the user's account
> and are unaffected by the project rename; every reference to them in this doc, `config.yaml`, and the code
> stays exactly as-is.

Read `CLAUDE.md` and `IMPLEMENTATION_PLAN.md` (incl. its **Revision 2 errata**) first. API ground truth is
`spotify-api-explore/FINDINGS.md` (kept outside the repo, contains account data — never commit it).
Where this spec and the original plan conflict, **this spec wins**.

## How to work (implementation session)
- Work **one phase at a time, in order**. A phase is done only when every *Success criterion* has its
  *Proof* attached in the phase report `design/reports/phase-N.md` (commands run + output excerpts).
- Use **background agents for grunt work** (fixture generation, test writing, MusicBrainz coverage runs,
  Playwright tests, README). Keep design decisions and safety-critical code (anything that writes to
  Spotify) in the main session. Give agents a narrow file scope; review their diffs before committing.
- Run the `spec-reviewer` agent (`.claude/agents/spec-reviewer.md`) at the end of each phase.
- Do not exceed a phase's scope. If reality contradicts the spec, stop, write the deviation into the phase
  report, and ask the master session. Do not silently redesign.
- Commit per logical unit; push to `main` at the end of each phase. Never force-push.
- Never read/print `.env`. Never run `--apply` against the real library except as Phase 4 prescribes.

## Master decisions (after Phase 1 review) — these are binding
1. **Playlist drift 30 vs 29 is fine** (the `SpotiSort Test` playlist was created after the findings run).
2. **Age gate blocks, it does not fall through.** Rules are matched on their conditions first-match-wins; if the
   matched rule's threshold (rule override, else default) is not yet met, the song is **left in Liked Songs and
   evaluation stops** (a too-young match must not leak into a later, broader rule). Change the engine and its
   tests (`test_younger_earlier_rule_falls_through_to_later_rule` etc.) accordingly.
3. Stricter config validation is accepted.
4. **Config schema gains `language_playlists` (map playlist-name → language) and `enrichment` (`musicbrainz:
   bool`) as the first Phase 2 task, then the schema is frozen** (Phase 6 builds against it).
5. **Language values are lowercase English names** (`hindi`, `malayalam`, `tamil`, `telugu`, `kannada`,
   `bengali`, `punjabi`, `marathi`, `english`, `japanese`, `korean`, `spanish`, …). Provide one alias table in
   `src/enrichment/languages.py` mapping ISO 639-1/-3 codes and native names to these; `language_in` in config is
   normalised through it (so `hi` works but is stored as `hindi`).
6. `genre_cache.py` is to be removed (no shim needed if nothing imports it).
7. **`--apply` deny rule:** the master has added `python -m src.sync --apply` variants to `.claude/settings.json`
   and fixed CLAUDE.md. Always invoke as `python -m src.<module>`.
8. Phase 3 must add a live **read-only** check that `contains` works with percent-encoded `uris` as `requests`
   sends them (`:` → `%3A`, `,` → `%2C`), so the encoding risk is closed before any write.
9. Phase 4 writers must return **per-batch results** (which batches committed) and never raise away that
   information on a mid-way failure; reconciliation must use it.
10. Investigate the stray `sync.yml` push-run failure ("workflow file issue", 0 s) in Phase 4 when rewriting it.
11. Add a `.gitattributes` (`* text=auto eol=lf`) in Phase 2 to end the CRLF warnings.

## Autonomy & gates (how to power through)
Run **Phases 2 → 3 → 5 → 6 back-to-back without waiting** for the master, writing `design/reports/phase-N.md`
at the end of each, pushing, and starting the next immediately. Use parallel background agents (e.g. Phase 6
UI + Playwright while Phase 2/3 code is being written). Stop only for these **hard gates**:
- **G1 (Phase 2 decision gate):** if genre coverage < 60 % of unique artists or language coverage < 85 % of
  tracks, finish the phase, report, and stop.
- **G2 (before Phase 4):** needs the **user**: designate 3 test songs, run `scripts/set_secrets.ps1`, confirm cron
  time, and hand-verify the first `--apply` in Spotify. Phase 4 also needs master sign-off of a real dry-run log.
  Do everything in Phase 4 that does not touch the real library first (failure-injection tests, workflow
  rewrite, `--restore`), then stop and ask.
- **G3:** any deviation from a "binding" decision or cross-cutting rule → stop and ask.
Phases 7–8 follow Phase 4. A phase report is required even when you do not stop.

## Master decisions 2 (product reality) — binding, override earlier text where they conflict
The user's *current* Liked Songs (773) is a stale archive (last archived to `Vault_drx` in 2023). **The tool is
designed for a fresh, near-empty Liked Songs inbox.** Therefore:
12. **Never operate on the existing library.** Reads for analysis/backtests are fine; no `--apply` may ever touch
    the 773 legacy songs. Hard guards: `--apply` requires an explicit selector (`--only-uris`, `--newest N`) for the
    first live tests, and a **`--max-moves N` cap (default 50)** that aborts (exit non-zero) if a plan exceeds it. The
    Actions workflow uses the same cap. Coverage numbers on the legacy library are informational only.
13. **Backtest instead of judging on the legacy inbox:** `python -m src.backtest` simulates an inbox from the user's
    owned playlists (each track's true home = the playlist it is in), runs the real planner with the given config, and
    reports per-playlist precision/recall and top confusions. Repo output is counts-only; detail goes to git-ignored
    `logs/backtest-detail.md`. This is the master's sign-off evidence for rule quality (replaces "review a real
    dry-run log"). Per-signal precision (script / hint / country_default) is computed from the same ground truth.
14. **Insert position (needed for `Vault_drx`, whose existing order must be preserved and newer songs go on top):**
    new per-rule key **`target_position: top | bottom`** (default `bottom`). `top` sends `position: 0` in the
    `POST /playlists/{id}/items` body (existing order untouched). Ordering rule: within a run, songs bound for the
    same playlist are ordered **newest liked first**; for `top`, insert the batches **oldest chunk first** so the
    newest ends up at index 0 (batches of ≤100; inserting chunks newest-first would invert order). The `position`
    body field is **unverified live** — verify on `SpotiSort Test` in G2 (add 3 tracks to top, read back, confirm
    order and that pre-existing items kept their relative order). Extend `config.py`, `docs/builder/validate.js`,
    the builder UI, sync tests (the JS/Python parity tests must stay green). This is a deliberate exception to the
    schema freeze.
15. **G2 test protocol changes:** the user does NOT designate legacy songs. They **like 3 fresh songs** in Spotify right
    before the test; the session runs `--apply --newest 3` with a test rule (`days_threshold: 0`, target
    `SpotiSort Test`, `target_position: top`) and verifies add → journal → remove → reconcile, then `--restore`.
    Existing liked songs are never in scope.
16. **Optional later phase (do not build yet): "Liked-songs guardian".** Spotify has silently dropped some liked
    songs for this user. Keep a snapshot of liked ids from each run (private `actions/cache`, not committed); if an id
    vanishes and the tool did not remove it, warn in the run log (and offer `--restore-vanished`).
17. One-off **legacy-to-Vault migration** (liked since 2023 → top of `Vault_drx`, ordered newest first) is out of scope
    now; decision 14 makes it a trivial follow-up run later.

## Master decisions 3 — VISIBILITY FIRST (binding; reorders the phases)
User requirement: *"I cannot control something I cannot see and measure."* **No live `--apply` of any kind until the
user has looked at the dashboard with real (dry-run + backtest) data and said so.** G2 now also requires that.
New order: **8a Visibility (dashboard + data artifacts) → backtest → 4 (non-live pieces, then live at G2) → 7 → 8b.**
18. **Every run emits machine-readable artifacts** (dry-run and apply alike, local and Actions):
    - `logs/YYYY-MM-DD.json` per run (extends the §8 format) and `logs/runs.json`, a rolling index of the last 90 runs
      (time, mode, counts, errors, warnings, liked before/after, duration, verdict).
    - `logs/latest-plan.json`: the **inbox snapshot** — every song currently in Liked Songs with: title, artists, added_at,
      age_days, decision (`will_move | too_young | no_match | target_problem | blocked`), matched rule, target playlist,
      `eligible_on` date, `target_position`, resolved language/genres each with **source tier + confidence**, and an
      **explain trace** (every rule in order: which conditions passed/failed, and why evaluation stopped).
    - Enrichment coverage/accuracy and backtest results as counts-only JSON.
    Real-run files are git-ignored locally; the workflow force-adds them (user accepted a public repo).
19. **Dashboard (`docs/dashboard/`, part of the same PWA, static, no build step)** with two data sources, switchable:
    *Local* (`python -m src.dashboard` serves `logs/` on localhost and opens the browser; nothing leaves the machine) and
    *Repo* (GitHub raw URLs of the user's fork). Views, each answering one question:
    1. **Overview** — is it healthy? last run status/time, next scheduled run, liked count, pending count, moves this week,
       errors/warnings, safety verdict (reconcile OK / mismatch), one-line "what will happen next".
    2. **Inbox** — what's waiting and why? sortable/filterable table of the snapshot; columns above; click a song → **Explain
       drawer** showing the rule-by-rule trace and the signals (with tier/confidence) that fed it.
    3. **Rules** — what does each rule do? matches (last run / 30 days), last matched, **dead rules (0 matches)**,
       **shadowed rules** (never reached because an earlier broader rule takes everything — computed from the plan),
       rules using weak signals flagged.
    4. **Playlists** — every target: resolved / missing / not writable / ambiguous, size, moves in/out.
    5. **Runs** — history table + per-run detail (moved, skipped, errors, journal), diff between two runs.
    6. **Safety** — journal of removals, restore command per run, reconcile results, liked-count timeline,
       vanished-song warnings (decision 16 when built).
    7. **Signals** — enrichment coverage and per-signal precision (script / hint / country_default / playlist / MusicBrainz).
    8. **Backtest** — per-playlist precision/recall, confusion table, top misroutes (counts, or names when in Local mode).
    Requirements: works offline from fixtures, clear empty/error states (no data, stale data older than 2 days = warning
    banner), dark/light, 375 px + 1280 px usable, keyboard accessible, no runtime external requests except the
    configured GitHub raw source. Also show a **data-freshness stamp** everywhere.
20. **Proof for 8a:** Playwright e2e over fixtures for every view and the Explain drawer; the dashboard renders the
    user's **real** dry-run + backtest data locally (screenshots saved git-ignored in `logs/screens/`, described in the
    report without song names); a written **"how to read it"** section in the README; master reviews by opening the
    local dashboard with the user.

## Master decisions 4 — PRODUCT-QUALITY SITE (binding; do this BEFORE the dashboard so it inherits the design system)
The `.github.io` site is the product's face: forks publish it to their own users. It must look and behave like a real web
product, not a dev tool. Order: **U1 design system + site shell → U2 Configure → U3 dashboard (decision 19 views)**.
21. **Naming:** the builder is now **"Configure"** (nav label, page title, headings). Primary action is **"Save
    configuration"**. Never say "config builder" in user-facing text.
22. **Brand/visual system (Spotify-inspired, not Spotify-branded):** design tokens in one `docs/assets/tokens.css`:
    background `#121212`, surface `#181818`, elevated `#282828`, hover `#2A2A2A`, borders `#333`, text `#FFFFFF`, secondary
    `#B3B3B3`, muted `#7A7A7A`, accent green `#1DB954` (hover `#1ED760`, pressed `#169C46`), danger `#E5484D`, warning
    `#F5A623`, info `#3E8EDE`. Dark is default; a light theme (white/`#F6F6F6`, same green, contrast-checked) and a
    theme toggle that respects `prefers-color-scheme`. Type scale, 4/8 px spacing scale, radii, shadows and motion tokens
    (respect `prefers-reduced-motion`). Contrast WCAG AA everywhere (green text on dark must pass; use white-on-green
    for filled buttons only if it passes, else black-on-green as Spotify does). **Do NOT use the Spotify logo or wordmark;**
    footer states "SpotiSort is an independent open-source project, not affiliated with or endorsed by Spotify."
23. **Component library (vanilla CSS/JS, no build step):** buttons (primary pill, secondary, ghost, danger, icon, loading,
    disabled), inputs/selects/checkboxes/switches/segmented controls/tag inputs, cards, tabs, modal/drawer, toasts,
    tooltip, popover, badge/chip, table, empty state, skeleton, banner, stepper, code/YAML view. **All native controls
    restyled to match:** custom scrollbars (`scrollbar-color`/`scrollbar-width` + `::-webkit-scrollbar`, thin green-on-dark
    thumb), styled focus rings (visible, 2 px green offset), selection colour, `accent-color`, `color-scheme`, styled
    `<select>`/file input/number input/checkbox/radio. One demo page `docs/assets/kitchen-sink.html` shows every component in
    every state (used for screenshots and review).
24. **Tooltips done right:** appear on hover AND keyboard focus, dismiss on Esc, reachable on touch (tap the "?" icon),
    `role="tooltip"` + `aria-describedby`, never contain essential info alone. Every non-obvious field in Configure gets a
    plain-language tooltip plus, where useful, an inline example ("e.g. Bonobo, Tycho").
25. **Site shell & pages:** sticky header (logo mark of our own, nav: Home · Configure · Dashboard · Setup guide · GitHub),
    responsive mobile menu, footer. **Home:** hero (what it does in one line, primary CTA "Set up your sorter", secondary
    "View on GitHub"), 3-step "How it works" with a small illustration/diagram (SVG), feature grid (language-first rules,
    safe by default/dry-run, runs free on GitHub Actions, your data stays in your fork), a screenshot/mock of the dashboard,
    FAQ (Premium needed, is it safe, what is a dry run, why fork), trust bar (open source, MIT/licence, no servers).
    **Setup guide page:** numbered walkthrough with copy buttons for every command/URL: Spotify Developer app → fork →
    secrets → Actions permission → first dry run → read the dashboard → go live, with "you should see…" checkpoints.
    404 page. Favicon set, `<meta>` description, Open Graph/Twitter card image, canonical URL, `lang`, semantic landmarks,
    skip-to-content link, print stylesheet not needed.
26. **GitHub & socials:** header/footer/hero link to the **canonical upstream repo `https://github.com/Vishnu-DRX/LikedZero`**
    ("Star / Fork on GitHub" with live star count fetched at runtime, failing silently). In Repo mode the site also derives the
    visitor's own fork from `location` (`<owner>.github.io/<repo>` → `github.com/<owner>/<repo>`) and shows an "Your fork"
    link. Author credit ("Built by <name>") + social icons are read from ONE file, `docs/site.config.json`. **For now ONLY
    GitHub is shown** (`{"name": "Vishnu-DRX", "github": "https://github.com/Vishnu-DRX"}`); the renderer supports optional
    linkedin/x/instagram/website/youtube keys but renders nothing for missing/null ones, so no empty icons or placeholders
    appear. Icons are inline SVG. Forks keep the upstream credit line but may edit that file.
27. **Configure (formerly config builder) UX:**
    - A guided **stepper**: 1 *Basics* (how many days a song waits, fallback playlist) → 2 *Languages* (map your playlists to
      languages) → 3 *Rules* (what goes where) → 4 *Review & save*. Each step has a one-paragraph explanation, what-good-looks-
      like example, and a "Why does this matter?" popover. Steps are also reachable from a sidebar/tabs; progress is shown;
      validation is inline and per step; **Next is never blocked** but errors are summarised on Review.
    - **Templates** on first visit: "Sort by language", "Sort by artist", "Start blank". **Live preview** panel showing the
      YAML plus a plain-English summary ("Songs older than 14 days that are Hindi go to *Dil*").
    - **Basic vs Advanced mode toggle** (persisted). Basic hides: per-rule day overrides, `target_position`,
      `create_missing_playlists`, weak-signal switches, YAML editing, import/export. **Advanced** reveals them, plus an editable
      YAML view (bidirectional sync with the form, error markers), import by file/paste/drag-drop, download, schema reference
      drawer, and the versions diff view.
    - Rule cards: drag-and-drop **and** keyboard reorder, duplicate, enable/disable switch, collapse, per-rule validation, and
      a note that order = priority (first match wins). Undo/redo (Ctrl+Z / Ctrl+Y) within a session. Debounced autosave of an
      unsaved *draft*; a "leave with unsaved changes" guard.
28. **Versioned configurations — keep the last 5 saved versions:** **Save configuration** creates a version
    `{id, savedAt, label(optional), summary("3 rules · 2 language playlists"), yaml}`; the list is capped at **5** (the oldest
    is dropped, and the UI warns before dropping it). A **Versions** panel lists them with timestamp, summary and *Compare with
    current* (rule-level diff + YAML text diff), **Restore** (confirm dialog; restoring loads it as the working draft and, when
    saved, becomes the newest version — nothing is lost silently), **Download** one/all, **Label**/rename. Storage: browser
    `localStorage` namespaced by `<owner>/<repo>`, wrapped in try/catch with an in-memory fallback and a visible warning if
    storage is blocked. Later (Phase 7) the **Repo** save path commits `config.yaml` to the user's repo and the Versions panel
    also lists the last 5 commits of `config.yaml` via the GitHub API for revert; the local and repo lists are shown side by
    side and clearly labelled. Until Phase 7, "Save configuration" saves a version locally and offers **Download / Copy** with a
    short note on where to put the file.
29. **Save-to-GitHub feasibility (do first in Phase 7):** verify whether GitHub's OAuth device-flow endpoints work from a browser
    (CORS). If not, implement a guided **fine-grained personal access token** flow (deep link to the token page with the exact
    permission: Contents read/write on this repo only; token kept in `sessionStorage`, never persisted, never logged) and document
    the trade-off. Record the finding in the phase report.
30. **Quality gates for the site (proof required in the report):** axe-core accessibility scan with **0 serious/critical**
    violations on every page and state; Lighthouse (CI via `treosh/lighthouse-ci-action`) **≥ 90** for Performance,
    Accessibility, Best Practices, SEO on Home/Configure/Dashboard (mobile profile); Playwright on **Chromium, Firefox and
    WebKit** at 375, 768 and 1280 px; screenshots of every page in dark and light saved to `docs/screenshots/` (committed
    for the marketing pages) for master review; keyboard-only walkthrough test of the full Configure flow; PWA installable
    (real Lighthouse this time); total transferred JS/CSS budget stated and met (target < 250 KB excluding vendored js-yaml).

## Master decisions 5 — dashboard is the web page only; readability revamp (binding)
31. **No localhost server in the product.** The dashboard is part of the Pages site. Data sources: **Repo** (default when served
    from `*.github.io`; reads the fork's committed logs via GitHub raw/API), **Demo** (fixtures, for visitors), and **Open local
    files** (drag-and-drop or file picker of `logs/*.json`, parsed entirely in the browser, nothing uploaded — the private path for
    song titles). `python -m src.dashboard` is demoted to a developer-only tool: removed from the README user path, kept only if
    tests use it. The source switcher remembers the last choice; the page states plainly which source it is showing.
32. **Titles opt-out for public logs:** new config key `logging.include_track_names` (bool, **default false** = private-by-default for
    forks; the user's own config sets true). When false, committed run logs/plan snapshots carry URIs and counts only, and the
    dashboard shows "Title hidden — open local files to see titles" where relevant; local files always carry titles. Surface it in
    Configure (Basic mode, with a plain-language tooltip) and Setup guide. This is another deliberate schema exception: update
    `config.py`, `validate.js`, builder, workflow, artifacts, and parity tests.
33. **Journal durability:** the workflow uploads the run journal as a private Actions artifact (`actions/upload-artifact`,
    `if: always()`, 90-day retention) in addition to the committed log.
34. **Dashboard readability revamp (part of U3):**
    - Every view opens with a one-line **question it answers** and a "What does this mean?" popover; a glossary drawer explains terms
      (inbox, eligible, shadowed rule, signal tier, precision). No internal identifiers in user-facing text (`will_move`, `P01`, `R03`):
      use plain labels ("Will move on 30 Sep", "Too new — waits 4 more days", "No rule matched", "Blocked: playlist not writable").
    - Status is never colour-only (icon + text + colour). Charts follow the `dataviz` skill (accessible palette, direct labels, no
      chart junk, tabular numbers), including light/dark.
    - Tables: sticky header, sortable with visible indicators, filter **chips** (decision, rule, playlist, language, source),
      search, column show/hide, density toggle (comfortable/compact, persisted), sensible truncation with tooltips, keyboard
      navigation, and a **card layout on phones** instead of horizontal scrolling. CSV export of the current Inbox view.
    - **Explain drawer as a sentence-first narrative** ("Matched *Hindi → Dil* (rule 2) because the language is Hindi — learned
      from your playlist *Dil*, high confidence. It was too new for rule 1."), then the technical trace collapsed below.
    - Overview leads with one **"what happens next" sentence** and 4 KPI cards with deltas; empty/first-run state with a short
      guided tour; stale-data banner.
    - "Playlists → moves out" column and the Overview `schedule` field are filled in (workflow writes `schedule` from the cron).
    - Reuse the U1 components and tokens only; the dashboard gets the same axe/Lighthouse/3-browser gates (decision 30).
35. **Order of work:** U1 (design system + shell + Home + Setup guide) → U2 (Configure) → U3 (dashboard revamp + decisions 31-34) →
    **G2a** (user runs `scripts/set_secrets.ps1`; the session triggers **cloud dry-runs only**, so Repo mode gets real logs; the user
    reviews the dashboard from the public site) → **G2b** (live `SpotiSort Test` protocol, then one real run, then the confirmed
    cron) → Phase 7 (save to GitHub) → 8b (run-now button, guardian). No writes to Spotify before G2b.

## Master decisions 6 (after gate G2 review) — binding
G2a/G2b reviewed: **accepted**, including the recorded deviation (user explicitly chose to skip the staged
`SpotiSort Test` step; the session correctly refused to run `--apply` itself and only handed over the command
after stating the risk). Accepted as a one-off, not a precedent for skipping future verification steps.
36. **Close the live-proof gap cheaply, now:** run the originally-specified staged protocol post-hoc at low stakes —
    like one throwaway song, `--apply --newest 1` with a test rule (`target_playlist: "SpotiSort Test"`,
    `target_position: top`, `days_threshold: 0`) targeting ONLY that disposable playlist, verify add + order in
    Spotify, then `--restore`, verify the song is back in Liked Songs and gone from the test playlist. This proves
    `--restore` and `top` insertion live for the first time. Do not touch any real target playlist for this proof.
37. **`config.yaml` (the user's real, live config) is updated:** remove the `days_threshold: 0` override — real rules
    use the normal default (14 days, i.e. no per-rule override) now that the mechanism is proven. Enable the
    **Hindi → Dil** draft alongside the already-enabled Malayalam → NewAgeMadrasMail rule, both at the default
    threshold. Japanese, English and the catch-all stay disabled (recall/precision too low or wrong signal type for
    English; catch-all/Vault ordering is unresolved product, decision 17). Re-run a cloud dry-run after committing so
    the dashboard reflects the real live rule set.
38. **Cron: stay manual-only for now** (user's choice) — `sync.yml` keeps `workflow_dispatch` only, no `schedule:`
    trigger, Overview keeps showing "Not scheduled" honestly rather than a guessed time. Revisit once the user has
    watched a few manual runs.
39. **Next body of work is Phase 8b before Phase 7:** run-now button (dispatch `workflow_dispatch` from the site) and
    the liked-songs vanished-song guardian (decision 16) add real safety/visibility value now; Phase 7 (GitHub
    write-back) is a convenience on top of already-working local Download/Copy and introduces a new auth surface
    (PAT flow, per the CORS finding) — do it after. The run-now button needs a way to trigger `workflow_dispatch`
    without a broad token: use the same guided fine-grained-PAT pattern planned for Phase 7 (Contents + Actions:write
    on this repo only), so build that auth component once and share it between 8b and Phase 7 rather than duplicating it.

## Master decisions 7 (UI cleanup pass, across the whole site) — binding, do before/alongside Phase 7
User feedback: buttons that look like underlined links, doubts about fork-genericness, and an overwhelming
dashboard ("he won't read or understand shit"). Applies site-wide (Home, Setup guide, Configure, Dashboard).
40. **Action vs navigation audit.** Any element that *performs an action* (run now, save configuration, restore a
    version, connect a token, dismiss, copy, download, open a drawer) must use the button component (filled/pill,
    secondary, ghost or icon per decision 23) — never a bare underlined link. An element that *navigates* (to
    another page, an anchor, an external site like GitHub) stays a link, but nav-bar/menu links use the nav
    component style, not inline underlined text. Produce a short table in the phase report: every clickable
    control, its purpose, and which component it now uses; grep for stray `<a>`/`text-link`-styled elements that
    trigger JS actions and fix each one.
41. **Fork-genericness audit (make every flow work for a stranger's fork, not just this account).** Grep the
    entire `docs/` tree for the literal strings `Vishnu-DRX` and `SpotiSort` outside of: (a) `docs/site.config.json`
    (the author-credit file, intentionally the maintainer's), and (b) the canonical "upstream" star/credit link
    required by decision 26. Every other reference — Repo-mode data source, run-now, Phase 7's save-to-GitHub,
    the Setup guide's example commands, screenshot alt text used as a fallback — must be derived at runtime from
    where the page is actually served/configured (owner/repo from `location.hostname`+`pathname` on `*.github.io`,
    or an explicit override for local testing), never hardcoded. Add an automated test that serves the built site
    under a **second, fake origin** (e.g. `someoneelse.github.io/their-fork/`) and asserts: Repo mode reads from
    that owner/repo, run-now and Phase 7's save target that owner/repo, and the upstream credit link still points
    at the real canonical repo unchanged. This test is required proof, not optional.
42. **Dashboard simplification (progressive disclosure).** Add a **Simple / Detailed** toggle (same persisted-
    preference pattern as Configure's Basic/Advanced; Simple is the default for a first-time visitor). Simple mode
    shows only: Overview's one-sentence status + 4 KPI cards, Inbox with 3 columns (song, status in plain words,
    why — opens the existing Explain drawer) and no raw tables of numbers, and a single "Everything looks fine /
    needs attention" banner in place of the Signals/Backtest/Runs views. Detailed mode is everything already built
    (all 8 views, unchanged). Every metric/label that isn't plain English gets a tooltip (decision 24's pattern) in
    BOTH modes — this is on top of the toggle, not instead of it, since Detailed users still need the glossary.
    Add one dismissible first-visit callout pointing at the mode toggle ("Prefer more detail? Switch to Detailed").
    Proof: a fresh-viewer Playwright test asserting Simple is the default and readable without opening the glossary;
    axe/Lighthouse gates (decision 30) re-run on both modes.
43. Re-run the full quality gate suite (decision 30: axe, Lighthouse, 3-browser Playwright) after this pass, since
    layout/DOM changes can regress CLS/contrast that were already fixed once (see the two CLS fixes in the last
    implementation round).

## Master decisions 8 (after the 2026-09-27 end-to-end review) — binding
An external review (`design/reviews/2026-09-27-end-to-end-review.md`) audited the whole repo. Master spot-checked its
three sharpest claims directly against source and confirmed all three are real: (1) `SPOTISORT_SCHEDULED_APPLY` is
read nowhere, only mentioned in a comment; (2) a `TooManyMoves` abort in `sync.py` returns before any log/`runs.json`/
guardian write, so the dashboard would show a stale "last run" as current while only the Actions tab is red; (3) the
PAT cache key is `owner/repo` only (no scope), so Configure's write-only token and run-now's dispatch-only token
collide. The review's edit to `phase-U2.md` (walking back a verified-true CI claim to "unverified, check CI") was
itself over-cautious and has been superseded by the merge — the original claim was checked against the real run ids
and is true; no report correction needed. Read the review in full; the priority order below is binding.

44. **Fix now (before anything else), all four together — these make committed logs actually private and the two
    token flows actually independent, both already shipped and live:**
    - P1-3: on `TooManyMoves` (and any other abort before `apply_moves` returns), still write the run log
      (`verdict: "aborted_too_many"`, plan counts, no journal) and update `runs.json`/guardian before returning the
      non-zero exit code, so the dashboard states the abort plainly instead of showing stale data.
    - P1-4: when `include_track_names` is false, `redact_plan`/`redact_log` must also drop or salt-hash the `uri`
      (and any other song-identifying field surviving in the explain trace), not just title/artist — a bare URI
      resolves to a real song in one request. Reword every "private by default" claim in Configure/Setup guide to
      match reality once fixed. Also correct the `sync.yml`/decision-33 wording: an artifact on a public repo is
      downloadable by any signed-in GitHub user, not private.
    - P1-5 + P1-6: split the PAT cache key by required scope set (or request the union of scopes both flows need
      and store one token), so Configure and run-now never silently steal/invalidate each other's token; default
      `expires_in` to 7 days instead of 90; verify() should check the granted scope, not just repo readability.
    - P1-7: distinguish "no baseline yet" from "0 vanished" in the guardian (write `guardian.baseline: "missing"|"ok"`
      to the log), and reword the Safety warning to "no longer liked (by you or Spotify)" rather than implying an
      alarm — an intentional un-like must not be reported as a loss.
45. **Fix next: P1-1 + P1-2 together, as one change (do not enable a schedule without both):** add config key
    `inbox_since` (date; the email analogue is "apply to new mail only"), enforce it in the planner so nothing before
    that date is ever evaluated regardless of selector, surface it in Configure and the Overview, and require it
    whenever a run passes `--allow-unselected`. Only then implement reading `SPOTISORT_SCHEDULED_APPLY` in `sync.yml`
    for a future `schedule:` trigger. Per decision 38 no schedule is being enabled yet, so this has no live urgency,
    but must land before a schedule is ever turned on.
46. **P2 hygiene, do in the same pass:** fix README/Setup-guide drift (decision 21 renamed the page "Configure"; the
    tool does not yet run on a schedule; forks must be told to enable Actions on first visit — GitHub disables them
    by default); derive `main` from the repo's actual `default_branch` everywhere instead of hardcoding it (data.js,
    run-now.js, builder/app.js); prefix CSV cells starting with `= + - @` with `'` (formula-injection fix); set
    `SPOTISORT_BROWSERS=chromium,firefox,webkit` (not `auto`) in CI so a missing browser fails the job instead of
    silently skipping 175 tests; harden the `--apply` deny pattern in `.claude/settings.json` for arg orderings like
    `--config x.yaml --apply`; consider slimming the committed `latest-plan.json` (1.4 MB, grows every run) once P1-4
    is decided.
47. **Deferred, schema-changing, needs master sign-off when we get there (do not build without asking first):**
    Q1 `artist_in_playlist` (highest value — reuses the existing playlist-learning machinery, covers most of the 83%
    of the library with no resolved language, no MusicBrainz needed), Q6 a proper `fallback_playlist`/catch-all
    (drops the `release_year_after: 1900` hack, needed for the eventual Vault use case), Q3 an "unmatched, needs a
    rule" queue on the dashboard (reuses `analyze.py`'s per-playlist stats). Lower priority: Q2 `unless:` exceptions,
    Q4 `action: keep`, Q5 `action: copy` (multi-label), Q7 `artist_id_in`, Q8 a run digest (`$GITHUB_STEP_SUMMARY`),
    Q9 deliberate re-liked-song handling. Bring a short recommendation back to the master before implementing any of
    these; each needs config.py + validate.js + parity tests together (schema is otherwise frozen).

## Master decisions 9 (2026-09-27) — remove the guardian entirely
User decision: drop the liked-songs guardian feature (decision 16, built in Phase 8a/8b) completely, not just
fix its wording. Reasoning: it structurally cannot distinguish an intentional un-like from Spotify silently
dropping a song, its `actions/cache` baseline evaporates after 7 days of inactivity (reporting "0 vanished"
misleadingly even after the P1-7 fix distinguished "missing" from "ok"), and the user's planned Liked-Songs
reset to a fresh, empty inbox (decisions 12-17) would otherwise fire a ~774-song false-alarm on its very first
run. It is not being replaced by anything.
48. **Remove:** `src/guardian.py` and its call sites in `src/sync.py` (snapshot write, `log["guardian"]`,
    `log["vanished"]`), the `runs.json` `vanished` count (`src/artifacts.run_entry`), the Safety view's
    vanished-song section and baseline-status UI in the dashboard, the `.github/workflows/sync.yml` steps that
    restore/save the guardian's `actions/cache` snapshot, `tests/test_guardian.py`, and every other reference
    (fixtures, `DATA.md`, README/Setup guide, `redact_log`'s vanished-redaction branch). Grep for `guardian` and
    `vanished` across the whole repo and remove every hit rather than leaving a dead code path or a dashboard
    section with nothing behind it.
49. Full test suite and quality gates (decision 30) re-run after removal, since it touches the run log schema,
    `runs.json`, dashboard fixtures/contract tests, and the workflow. Confirm no reference to the removed
    feature survives in docs or the Setup guide.

## Master decisions 10 (2026-09-27) — precision over coverage; a real catch-all; a proper playlist audit
User's framing, which now governs this whole area: **100% coverage is not the goal, reliable precision is.**
With a wide, discovery-heavy taste, most songs genuinely have no repeat-artist pattern yet, and that is expected,
not a gap to engineer away. `artist_in_playlist` is confirmed valuable specifically because some playlists are
dedicated to one or two artists (e.g. a Linkin Park playlist, a 21 Pilots playlist) — an overwhelming-margin case,
not the weak "3-vs-2 split" case that dragged the general sweep's precision down to ~80%. The 90% precision bar
used everywhere else in this project is NOT being relaxed to buy coverage; instead, only a confident slice should
ever auto-apply, and everything else stays visibly in the inbox (or the Q3 unmatched queue) for the user.

50. **Re-measure `artist_in_playlist` with a dominance margin, not just a raw count.** Gate on BOTH a small
    `min_tracks` floor AND the top playlist being a clear multiple ahead of the runner-up (e.g. `margin: 2.0` =
    top count >= 2x second place; sweep a couple of margin values same as the min_tracks sweep did). Report,
    per candidate margin/min_tracks combination: coverage, precision, recall — and specifically call out
    single/near-single-artist playlists (an artist whose tracked-playlist tracks are >=90% in one playlist) as
    their own row, since that's the paradigm case the user just confirmed matters. Only combinations clearing
    ~90% precision are candidates to actually build; report which do, even if coverage is small.
51. **A real catch-all, name decided: "SpotiSort Sink."** This is Q6 (proper `fallback_playlist`/catch-all,
    dropping the `release_year_after: 1900` hack) made concrete. **Confirmed done: the user created this empty
    playlist on 2026-09-27** (was pending, now cleared — approved to build). Design it properly: `fallback_playlist`
    accepts `{playlist, target_position}` (or a `match: {any: true}` rule — pick whichever fits the existing engine
    more cleanly, your call, document the choice), evaluated only after every other enabled rule has failed to
    match (including `artist_in_playlist`, now built). Ship the real config pointed at `SpotiSort Sink`, disabled
    by default like every other rule reaching this config, for the user to review and enable.
52. **A proper playlist audit, not just the 4 already-mapped language playlists.** Analyze every owned/
    collaborative playlist (reuse/extend `analyze.py`'s existing per-playlist profiling) and classify each one
    by its dominant organizing factor — the three that matter, per the user: **language, genre, artist**. For
    each playlist report (counts/labels only, `P01..` convention, no names in the committed file): dominant
    artist share (is it effectively a single/few-artist "home" playlist?), dominant language share, dominant
    genre share (of tagged tracks), and a suggested classification (artist-home / language-pure / genre-pure /
    mixed-no-clear-pattern). This is analysis to inform which playlists get which rule type — not a rule-writing
    or auto-config step. Bring the classification table back for the master/user to turn into real rules.

## Master decisions 11 (2026-09-27) — approve artist_in_playlist (simplified), six rules landed directly
Measurement round 2 confirmed the paradigm case: restricted to artists whose tracked-playlist tracks are >=90%
in one playlist, precision is 94-98% (see `design/proposals/artist_in_playlist.md`, now updated with the
simplified single-dominance-ratio schema — the separate margin knob was redundant and is dropped).

53. **Six explicit `artist_in` rules added directly to `config.yaml`** (no new mechanism needed — these are
    already-obvious cases, confirmed live): Anavae -> Anavae binge list, Linkin Park -> Dead Dreams' Disco,
    Queen -> Her Highness, Twenty One Pilots -> Riffs in the air, Klasey Jones -> The Klasey Universe, The
    Midnight -> Midnight Mixer. Validated with `load_config` locally; pull main before your next config edit to
    avoid clobbering this. Run a cloud dry-run after pulling so the dashboard reflects the real live rule set.
54. **Build `artist_in_playlist` per the simplified proposal**: `min_tracks` + `min_dominance` (default 3 / 0.9),
    `exclude_playlists` (always includes `Vault_drx`), `target_playlist: auto` sentinel. Full pipeline:
    `config.py`/`validate.js` schema + parity tests, `rules_engine`/`planner` resolution logic, a backtest-
    integration test reproducing the measured 94-98% precision numbers with the real shipped code (not just the
    standalone measurement script), dashboard explain-trace wording ("routed to X — N of the artist's M tracks
    are already there"), Configure UI (Basic mode: a simple on/off + the two numeric defaults; Advanced: the
    exclude list). **Ship it in `config.yaml` disabled by default** (`enabled: false`, a single draft rule) —
    the master/user turns it on after reviewing a dry-run with it enabled, same pattern as every other rule that
    reached this project's live config.
55. Confirm the interaction/shadowing check (proposal's remaining item 1) actually surfaces on the dashboard
    once built, and confirm decision 54's item on Vault_drx exclusion holds on the real library.

## Master decisions 12 (2026-09-27) — "Analyze my library" onboarding (Option B, server-side)
Goal: any fork's user should get a personalized draft config the same way the master session hand-built one for
the primary user, without a live human/LLM in the loop making judgment calls. What's automatable is the
*analysis and draft*, not the judgment calls that got made in conversation (e.g. excluding Vault_drx, choosing
`min_dominance`) — the output stays a reviewable draft, never auto-applied, same as `analyze.py` already
promises. Option A (a "Connect Spotify" browser-side OAuth for pre-fork, instant onboarding) is a real, larger
feature, deliberately deferred — write it up as its own `design/proposals/` doc, same treatment as
`artist_in_playlist.md`, but do not build it now.

56. **Upgrade `analyze.py`'s classification to match what's now proven**, incorporating the measured thresholds
    from `measure_round_2.py`/decision 52 (artist-dominance detection matching `artist_in_playlist`'s own
    `min_tracks`/`min_dominance` bar, so a near-single-artist playlist is suggested as a plain `artist_in: [...]`
    rule the way the six real ones were hand-written) and language/genre-pure detection consistent with the
    same audit. Keep the existing era/explicit-refine-only behavior. This is a quality upgrade to already-shipped
    code, not a new mechanism.
57. **First-pass "Analyze my library" runs without a live MusicBrainz enrichment pass**, relying on
    artist/language signals (script detection, already-cached genre if any) only — a fresh fork's cache is empty,
    and a full MusicBrainz pass is ~15-25 min, a bad first-run experience. Genre-based draft suggestions are
    therefore best-effort on a brand-new fork and improve automatically once the user's first real sync (or a
    later re-analyze) has populated the enrichment cache. State this plainly in the UI/Setup guide rather than
    silently under-delivering on genre. If measured runtime without network is still slow, report that number
    and revisit.
58. **Trigger mechanism reuses run-now's existing PAT component and scope exactly** (`Actions: write` only — no
    `Contents: write` needed on the user's token, since the commit-back happens via the workflow's own
    `GITHUB_TOKEN` inside Actions, same as every other commit-back in this project). New, separate workflow
    `analyze.yml` (not a mode on `sync.yml` — different risk shape: this workflow never touches Liked Songs or
    playlist contents at all, only reads playlists and writes one file, so keep its guards simple and distinct
    from `sync.yml`'s). It writes/overwrites a committed `config.draft.yaml` at the repo root (public, no
    secrets, same threat model as `config.yaml` already being public).
59. **Site UI**: an "Analyze my library" option on the Configure page, alongside the existing templates
    (Sort by language / Sort by artist / Start blank) — dispatches `analyze.yml` via the shared PAT/run-now
    machinery, shows a running/polling state, and once complete offers "Import my draft" which pulls
    `config.draft.yaml` via the existing import-by-file mechanism into the Configure editor as an unsaved draft —
    it never touches the live `config.yaml` until the user explicitly hits Save. Reuse `docs/assets/github-pat.js`
    and `run-now.js`'s polling pattern rather than building new dispatch/poll logic from scratch.
60. Update the README/Setup guide to mention this as the recommended first step after secrets are set, before
    hand-writing any rules. Full quality gate suite (decision 30) re-run — new UI surface on Configure.

## Master decisions 13 (2026-09-29) — rename to LikedZero
Reasons (both real, both checked, not just one): (1) a direct name collision — `alessiocelentano/spotisort`
already exists as an unrelated project. (2) A "Spoti-" prefix (the user's own first suggestion, "Spoti-inbox")
carries the same problem `SpotiSort` did, not a different one — Spotify's own developer naming guidelines
explicitly bar a name "similar to Spotify in sound or spelling," and they have real enforcement precedent (won
a 2022 trademark case against an app called "Potify" on exactly that basis). **"LikedZero" was chosen instead**:
plays on "Inbox Zero," which is the metaphor this whole project has used since its first design doc ("Liked
Songs = inbox"), has no relationship to "Spotify" in sound or spelling, and no collision was found.

**Already done by the master session (do not redo):** GitHub repo renamed
(`gh repo rename LikedZero --repo Vishnu-DRX/SpotiSort -y`) — confirmed live at
`https://github.com/Vishnu-DRX/LikedZero` and `https://vishnu-drx.github.io/LikedZero/` (200 OK, Pages
auto-updated). Local git remote `origin` updated to match. This doc's own title, intro banner, and the
canonical-repo URL in decision 26 are already fixed.

61. **Critical distinction, get this right:** the Spotify playlists literally named **"SpotiSort Test"** and
    **"SpotiSort Sink"** are real playlists the user already created in their account — they are NOT the
    project's name and must NEVER be touched, renamed, or have their string value changed anywhere (`config.yaml`,
    tests, fixtures, dashboard data, docs). Every other occurrence of "SpotiSort"/"spotisort" refers to the
    *project* and should become "LikedZero"/"likedzero" (match case/casing convention of the surrounding text).
    Grep first, categorize every hit into "project name" vs "playlist name" before changing anything.
62. **Scope of the rename pass:**
    - Code: `src/enrichment/musicbrainz.py`'s `USER_AGENT` constant (currently embeds both the old name and the
      old GitHub URL — fix both), any other docstrings/comments naming the project, `.github/workflows/*.yml`
      comments/step names.
    - Config: `config.yaml`'s and `config.example.yaml`'s header comment line ("# SpotiSort live config.") —
      NOT any `target_playlist` value.
    - Top-level docs: `README.md`, `CLAUDE.md`, `IMPLEMENTATION_PLAN.md` (its title/intro, not its dated
      "Revision 2 errata" history), remaining forward-facing mentions in `BUILD_SPEC.md` (historical/completed-
      phase narrative text describing what already ran, e.g. Phase 1's `gh api repos/Vishnu-DRX/SpotiSort/...`
      example commands, may stay as historical record — your judgment, note what you left and why).
    - `design/reports/*.md` and `design/reviews/*.md`: **leave untouched**, historical record (same exclusion
      this project has always used).
    - The site (`docs/`): every page's `<title>`/meta description/OG+Twitter card tags/canonical URL, the PWA
      manifest (`name`, `short_name`, `description`), the service worker (cache-key/version — bump it, since
      cached assets are changing), `docs/site.config.json` if it names the project anywhere (it mainly holds
      author credit — check), README-embedded badges/links, the Setup guide's copy-paste commands and example
      URLs, favicon/OG image alt text.
    - **CRITICAL, verify live, not just by inspection:** the Pages URL path changed from `/SpotiSort/` to
      `/LikedZero/`. Any **absolute** path (not relative) hardcoded anywhere — service worker `scope`, manifest
      `start_url`/`scope`, an `<a href="/SpotiSort/...">`, a JS-constructed URL — will silently 404 on the live
      site if not updated. Grep specifically for `/SpotiSort/` and `Vishnu-DRX/SpotiSort` as literal path/URL
      fragments, separately from the general name-audit above, and confirm every hit is fixed.
    - Reuse/extend the existing fork-genericness test (decision 41) rather than writing a new one — it already
      greps for the literal strings `Vishnu-DRX`/`SpotiSort`; update what it checks for to the new identity
      strings, keeping its actual purpose (derive at runtime, don't hardcode) intact.
63. **Not in scope, deliberately:** the local folder path (`T:\Development Space\SpotiSort`) is NOT being
    renamed — it's shared with another active session and renaming it risks breaking that session's working
    directory mid-task. Leave it. Also not required: renaming the Spotify Developer Dashboard app's own display
    name (cosmetic, the user's own account, only they can do it, not part of this repo).
64. Full quality gate suite (decision 30) re-run — this touches nearly every page and asset. After pushing,
    live-verify the actual deployed site (curl or fetch Home/Configure/Dashboard on the new
    `vishnu-drx.github.io/LikedZero/` URL, confirm 200 and no broken absolute-path asset references) — this
    is a case where "tests pass locally" is not sufficient proof, the real deployed path changed.

## Verified write shapes (live-tested 2026-09-21 on `SpotiSort Test`; liked count 773 preserved)
- Add to playlist: `POST /playlists/{id}/items`, JSON body `{"uris":["spotify:track:..."]}` → **201**
  `{"snapshot_id"}`. Max 100 (101 → 400).
- Remove from playlist: `DELETE /playlists/{id}/items`, JSON body `{"items":[{"uri":"..."}]}` (optional
  `"snapshot_id"`) → **200** `{"snapshot_id"}`.
- Save/remove liked: `PUT` / `DELETE /me/library?uris=spotify:track:A,spotify:track:B` — URIs in the **query
  string** (JSON body → 400) → **200**, empty body. Max **40**. `GET /me/library/contains?uris=...` max 40.
- **Read-after-write lag:** a GET straight after a write can be stale. Use the `snapshot_id` returned by the
  previous *write* (never one from a fresh GET), and verify with a short poll (e.g. up to 5 tries, 1 s apart)
  before concluding a write failed.
- **Re-saving an already-liked track resets its `added_at`.** Therefore never `PUT` tracks that are already
  liked (skip via `contains` first); `--restore` is the only path that re-saves, and it is expected to reset dates.
- Not verified: writes to followed playlists (reads already 403, so expect failure — treat any non-2xx as
  "do not remove from Liked Songs"). 429 `Retry-After` never occurred live; keep the unit-tested handling.

## Cross-cutting rules (apply to every phase)
1. **No liked song may be lost.** Before ANY removal from Liked Songs: (a) the track was confirmed present in
   the target playlist by re-reading it; (b) a **journal** entry `{uri, name, artists, original_added_at,
   target_playlist_id}` has been written to `logs/YYYY-MM-DD.json` *before* the DELETE call; (c) after the
   DELETE, `/me/library/contains` confirms removal, and totals reconcile (`before - removed == after`).
   Any mismatch → abort run, re-add via `PUT /me/library`, exit non-zero. Note: re-saving a track resets its
   `added_at` to now; the journal keeps the original for reference.
2. Dry-run is default; every write path has a dry-run branch that performs zero write HTTP calls (tested by
   asserting the HTTP layer is never called with PUT/POST/DELETE).
3. Only `spotify:track:` URIs may be sent to `/me/library` (that endpoint also unfollows albums/playlists).
4. Skip `is_local`, null `item`, and non-track (`episode`) entries everywhere.
5. Secrets never logged; `Authorization` headers and tokens redacted in any debug output (unit-tested).
6. Batch limits: `/me/library` + `contains` **40**, playlist items **100**, `/me/tracks` page **50**,
   `/me/playlists` page **50**, `/playlists/{id}/items` page **100**.
7. Tests must run offline (fixtures) with `python -m pytest -q`; live tests are marked `@pytest.mark.live`
   and skipped unless `SPOTISORT_LIVE=1`.

---

## Phase 1 — Foundation (offline core + GitHub setup + live site)
**Goal:** a tested, offline-capable core (auth client, config loader, rules engine) and a repo whose CI, Pages
site and Actions settings are configured — no Spotify writes, no sorting yet.

**Deliverables**
1. `src/spotify_client.py`: `.env` loader (tiny parser, no dependency, env vars win); PKCE-based
   `--setup` login (localhost:8888, S256, prints nothing secret, writes `SPOTIFY_REFRESH_TOKEN` to `.env`
   only); `SpotifyClient` with refresh-token → access-token exchange (client_id only; secret optional and
   used if present), token auto-refresh on 401 once, 429 `Retry-After` sleep/retry (max 5), paging
   helpers (`iter_saved_tracks`, `iter_my_playlists`, `iter_playlist_items`) that normalise to plain
   dataclasses (`Track`, `Playlist`), write methods (`add_playlist_items`, `remove_playlist_items`,
   `save_tracks`, `remove_saved_tracks`, `contains_saved`) that **refuse** to run when `dry_run=True` and
   enforce batch limits + track-URI-only validation. Request shapes per FINDINGS.md §4/§6.
2. `src/config.py`: load + validate `config.yaml` against schema §6 of the plan **plus** `language` match key
   (see Revision 2). Clear error messages with rule name/index. Unknown keys rejected.
3. `src/rules_engine.py`: pure `evaluate(track, enrichment, rules, now) -> Match|None`; first-match-wins;
   AND within a rule; keys: `artist_in`, `genre_contains`, `language_in`, `release_year_before/after`,
   `explicit`, `track_name_contains`, `album_name_contains`. Case-insensitive; artist match on any credited
   artist; year parses `release_date` at `year|month|day` precision; per-rule `days_threshold` override;
   disabled rules skipped. Missing enrichment ⇒ genre/language conditions are simply *false*, never errors.
4. `tests/`: unit tests for the engine (≥ 30 cases incl. precision edge cases, empty lists, disabled rules,
   threshold override, multi-artist), config validation, client behaviours using a fake HTTP session
   (429, 401-refresh, batch splitting, dry-run refusal, token redaction), fixtures built from a sanitised
   subset of `liked_all.json`/`playlists.json` (strip account ids; commit only sanitised fixtures).
5. `.github/workflows/tests.yml`: on push/PR run pytest on Python 3.12 — the required CI.
6. GitHub setup via CLI (record commands in `design/reports/phase-1.md`):
   - confirm Pages: `gh api repos/Vishnu-DRX/SpotiSort/pages` → source `main:/docs`, `https_enforced`.
   - `gh api -X PUT repos/Vishnu-DRX/SpotiSort/actions/permissions/workflow -f default_workflow_permissions=write`
     (needed for log commit-back).
   - repo description + topics via `gh repo edit`; enable issues; disable wiki.
   - `scripts/set_secrets.ps1`: reads `.env`, calls `gh secret set SPOTIFY_CLIENT_ID` and
     `SPOTIFY_REFRESH_TOKEN` via stdin (never echoing values); **user runs it once**, not the session.
   - update `docs/index.html` placeholder to a real landing page (what it is, status, link to repo) so the
     `.github.io` site is visibly live.
7. `README.md`: prerequisites (Premium), Developer-app setup, `.env`, `--setup`, status.

**Success criteria & proof**
| # | Criterion | Proof |
|---|---|---|
| 1 | Unit tests pass offline | `python -m pytest -q` output, ≥ 60 tests, 0 fail |
| 2 | Engine correctness | test list showing each match key + precedence cases |
| 3 | No write can happen in dry-run | test asserting fake session saw only GETs |
| 4 | Secrets never leak | test feeding a fake token through error paths and asserting absence in logs/exceptions |
| 5 | CI green on `main` | `gh run list --workflow tests.yml -L 1` shows success |
| 6 | Pages live | `curl -sI https://vishnu-drx.github.io/SpotiSort/` → 200, page contains project name |
| 7 | Live read smoke test (`SPOTISORT_LIVE=1`) | `python -m src.spotify_client --smoke` prints counts: 773 liked, 29 owned + 3 collab playlists, no secrets |
| 8 | Repo settings applied | `gh api` outputs captured in report |

**After Phase 1 you have:** a verified core library, green CI, a live (placeholder-quality) Pages site, correct
Actions permissions, secrets script ready. **Nothing sorts yet** and no metadata enrichment exists.

---

## Phase 2 — Enrichment: language + genre (MusicBrainz) and cache
**Goal:** resolve language and genre for every liked track cheaply and cache the results.

**Deliverables**
1. `src/enrichment/` (replace `genre_cache.py`; keep a thin shim if imports demand): `Enricher` combining
   providers behind one interface `resolve(track) -> Enrichment{genres[], language, sources[]}`:
   - `musicbrainz.py`: ISRC → recording → artist (`/ws/2/isrc/{isrc}?inc=artists+releases`, then artist
     `inc=tags+genres`); User-Agent `SpotiSort/<ver> (https://github.com/Vishnu-DRX/SpotiSort)`; ≤ 1 req/s;
     retry on 503; fallback to artist name search only if ISRC has no hit (with score threshold).
   - `playlist_language.py`: **learned language map** — `artist_id → language` derived from the user's owned
     playlists whose config maps them to a language (see `language_playlists` in config: e.g.
     `{"Chill Hindi": "hindi", "Malayalam ...": "malayalam"}`); strongest signal.
   - `script_detect.py`: Unicode-script detection on track/album/artist names (Devanagari→hi/mr,
     Malayalam, Tamil, Telugu, Kannada, Bengali, Gurmukhi, Japanese kana, Hangul, CJK, Cyrillic, Arabic).
   - `isrc_country.py`: ISRC prefix → country (weak hint, only used to break ties / label `region`).
   Resolution order for `language`: playlist-learned > script > MusicBrainz release/work language > None.
2. Cache `.cache/enrichment.json` keyed by artist id (genres, area) and ISRC (language hints), with
   `fetched_at` and 90-day staleness; atomic writes; committed by the workflow.
3. `python -m src.enrich --report`: coverage report over all liked tracks — % with genres, % with language,
   top unresolved artists, per-source hit counts. Writes `logs/enrichment-coverage.json`.
4. Config: `language_playlists` mapping + `enrichment.musicbrainz: true/false`.

**Success criteria & proof**
| # | Criterion | Proof |
|---|---|---|
| 1 | Provider unit tests offline (recorded MB fixtures) | pytest output |
| 2 | Rate limit obeyed | test with fake clock asserting ≥ 1.0 s spacing; live run log shows no 503 storms |
| 3 | Cache hit avoids network | test: second run makes 0 MB calls |
| 4 | Coverage measured on the real library | committed sanitised `logs/enrichment-coverage.json` with numbers |
| 5 | **Decision gate:** genre coverage ≥ 60 % of unique artists, language coverage ≥ 85 % of tracks | else report and master decides on adding Last.fm |
| 6 | Script detection accuracy | test table of ≥ 25 real-looking titles across scripts |

---

## Phase 3 — Sync in dry-run
**Goal:** full pipeline, zero writes, an honest preview on the real account.

**Deliverables:** `src/sync.py` — auth → fetch liked → filter by age → enrich → evaluate → resolve targets by name
among **owned or collaborative** playlists only (case-insensitive exact match, warn on duplicates/ambiguity, skip
+ log when missing; `create_missing_playlists` honoured only when true) → build plan → print + write
`logs/YYYY-MM-DD.json` (schema §8 of the plan plus `journal`, `warnings`, `dry_run`). Idempotent: songs already in
the target playlist are still "moved" (only the removal happens) and flagged `already_in_target`.
Also `--limit N`, `--since`, `--rule NAME` filters for safe partial runs.

**Success criteria & proof**
| # | Criterion | Proof |
|---|---|---|
| 1 | Dry-run on real library performs 0 write calls | HTTP audit log (methods histogram) in report |
| 2 | Plan is explainable | each planned move records the matching rule + which fields matched |
| 3 | Missing/ambiguous playlist handled | tests + a live case with a deliberately wrong name |
| 4 | Runtime | full dry-run < 3 min with warm cache |
| 5 | Master review of a real dry-run log | report includes log excerpt; master signs off before Phase 4 |

---

## Phase 4 — Apply (guarded) + Actions automation
**Goal:** safe writes, proven on `SpotiSort Test` first, then scheduled.

**Deliverables:** `--apply` path implementing cross-cutting rule 1 exactly (add → verify in playlist → journal →
remove → verify gone → reconcile); `python -m src.sync --restore logs/<file>.json` re-adds journaled removals;
`sync.yml` wired (`python -m src.sync --apply`, concurrency group so runs don't overlap, commit-back of `logs/`
and `.cache/` with bot identity, `[skip ci]`), cron confirmed with user, `workflow_dispatch` input `dry_run`
(default true) so the first cloud run is a dry-run.

**Test protocol (mandatory order)**
1. Local `--apply` with a config whose only rule targets `SpotiSort Test` and `--limit 3` on 3 *test* songs the
   user has designated; verify each by hand-check in Spotify UI (ask the user).
2. `--restore` those 3, confirm they're back in Liked Songs and out of the test playlist.
3. Failure injection tests (unit, fake session): playlist add fails → track NOT removed; removal call fails
   → reconcile aborts and reports; partial batch failure → only confirmed tracks removed.
4. `gh secret set` (user runs `scripts/set_secrets.ps1`), then
   `gh workflow run sync.yml -f dry_run=true`, inspect via `gh run view --log`, then one real run.

**Success criteria & proof**
| # | Criterion | Proof |
|---|---|---|
| 1 | Liked count preserved except intended moves | before/after counts + journal in report |
| 2 | Injected failures never lose a song | failure-injection test output |
| 3 | Restore works | log + Spotify confirmation from user |
| 4 | Cloud dry-run then real run succeed | `gh run list` outputs, committed log files |
| 5 | Secrets absent from logs | `gh run view --log` grep for token patterns returns nothing |

---

## Phase 5 — Analyze mode
**Goal:** draft `config.yaml` from existing playlists.
**Deliverables:** `src/analyze.py` reading owned + collaborative playlists only (403 on followed → skipped and
reported); per playlist: top genres, top artists, language distribution, year spread/era, explicit ratio;
draft rules all `enabled: false` with rationale comments; `language_playlists` suggestions (a playlist whose
dominant language ≥ 70 %). Never writes to Spotify or applies config.
**Proof:** unit tests on synthetic playlists; a real run producing `config.draft.yaml` that passes
`config.py` validation; master reviews sample rationale quality.

---

## Phase 6 — Pages: config builder (PWA)  *(can run in parallel with 2–5 once Phase 1 config schema is frozen)*
**Goal:** form-based rule editor → live YAML → copy/download; installable PWA; offline.
**Deliverables:** `docs/` static app (no build step, vanilla JS + js-yaml from cdn.jsdelivr pinned with SRI or
vendored), manifest + service worker + icons, schema-driven validation mirroring `config.py`, import existing
YAML, dark/light, mobile layout. Use the `artifact-design`-style rigor: accessible, keyboard-usable.
**Proof:** Playwright tests (`tests/e2e`, run in CI): builds each rule type, YAML round-trips through Python
`config.py` validation (test invokes the real validator on downloaded output); Lighthouse PWA installable
check; screenshot at 375px and 1280px.

## Phase 7 — Pages: GitHub write-back
GitHub device-flow login (client id of a GitHub OAuth App owned by the user; document creation via `gh`/UI),
commit `config.yaml` via Contents API, token kept in `sessionStorage`. Proof: Playwright with mocked GitHub API
+ one manual live round trip; `git log` shows the commit made from the UI. No secrets in the site.

## Phase 8 — Pages: dashboard
Reads `logs/*.json` through the GitHub API/raw URLs: last run status, moves per playlist, warnings, journal, and a
"run now" button (dispatches `workflow_dispatch` via the API, needs Phase 7 auth). Proof: Playwright against
fixture logs; a live render of the real logs.

---

## Definition of done for the whole project
Fork → set 2 secrets → set config → daily run moves songs correctly; README lets a stranger do this in
< 20 min; CI green; site live; no known way for a run to lose a liked song (failure-injection tested).
