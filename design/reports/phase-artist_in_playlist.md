# Phase: build `artist_in_playlist` (Master decisions 11 / decision 54)

Implements the simplified `artist_in_playlist` proposal (`design/proposals/artist_in_playlist.md`, margin knob
dropped, just `min_tracks` + `min_dominance` now): schema, resolution logic, dashboard wording, Configure UI,
and a live backtest-integration proof — shipped in `config.yaml` as one **disabled** draft rule.

## 1. Schema (`config.py` + `validate.js` + parity tests)

New top-level `artist_in_playlist` block: `min_tracks` (int ≥ 1, default 3), `min_dominance` (0 < n ≤ 1,
default 0.9), `exclude_playlists` (list of strings, default `[]`). New match key `artist_in_playlist` (must be
literally `true`; `false` has no defined meaning and errors). New `target_playlist: "auto"` sentinel
(case-insensitive), valid **only** paired with `match: {artist_in_playlist: true}`, and required whenever that
key is present — both directions are validated (`rules_engine`/`planner` would otherwise silently do nothing
useful with a mismatched pairing).

`Vault_drx` is **not** merged into `Config.artist_in_playlist_exclude_playlists` by the parser — that field
carries exactly what the user configured. The hardcoded exclusion instead lives at the point of use
(`src/enrichment/artist_playlist.py`'s `excluded_playlist_names()`, always ORs in `{"vault_drx"}`), so it holds
even for a `Config` built directly, bypassing `parse_config` (decision 54's "don't rely on config alone").

**Proof:** `tests/test_config.py` — 20 new cases (defaults, valid block+rule, every invalid `min_tracks`/
`min_dominance`/`exclude_playlists` value, unknown key, both pairing-mismatch directions, case-insensitive
`AUTO`, combining with other match keys, two `auto` rules). JS/Python parity: 15 new cases in
`tests/e2e/test_builder.py::test_js_validator_matches_python_messages`, all passing against the real
`validate.js`, not a Python re-implementation.

```
python -m pytest tests/test_config.py -q            → 184 passed
python -m pytest tests/e2e/test_builder.py -k matches_python -q -m e2e  → 32 passed
```

## 2. Resolution logic (`rules_engine` / `planner`)

New module `src/enrichment/artist_playlist.py`: `ArtistPlaylistMap` learns, per **primary (first-credited)
artist**, a track count per candidate playlist (the same primary-artist-only, leave-one-out convention the
round-1/round-2 measurements used, so the shipped precision matches what was proven, not a variant). `.resolve()`
returns a home only when the top playlist clears `min_tracks` **and** `min_dominance`, and a genuine tie is
never guessed at regardless of how low `min_dominance` is configured (mathematically, a true tie can only clear
>50% dominance if the runner-up trails by exactly one track out of a near-total sum, so this mostly backstops a
permissive `min_dominance`, not the shipped default).

The resolved playlist name is folded into `Enrichment` (three new fields: `artist_home_playlist`,
`artist_home_track_count`, `artist_home_total`) rather than threaded as a new parameter everywhere — this is
the same object genre/language already ride on through `check_key`/`decide`/`explain`/`build_plan`, so the
generic first-match/explain/shadowed-rule machinery needed **zero** changes to support the new key.
`rules_engine.check_key()` gained one new branch; `planner.decide()` gained one `if target == "auto":
target = enrichment.artist_home_playlist` substitution (with a defensive `no_match` fallback if that's ever
`None`, which config.py's pairing rule makes unreachable in practice).

`src/sync.py` builds the `ArtistPlaylistMap` (via `src/enrich.py`'s new `build_artist_playlist_map`) only when
some **enabled** rule's match actually uses `artist_in_playlist` — checked post-what-if-transform so
`--what-if-enable-all` still previews the shipped disabled draft, but a normal run costs nothing while it stays
off. Verified live: a real `python -m src.sync` dry-run against the actual account made **30** `GET` calls
(same as before this phase), not the ~30+ extra full-playlist-content reads the feature would need once
enabled — confirming the gate actually gates. (This was a real bug I introduced and caught before shipping: my
first version of the gate checked match-key presence only, ignoring `enabled`, which would have made *every*
dry run pay the full-library-scan cost the moment the disabled draft rule landed in `config.yaml`. Fixed by
moving the check after the what-if transform and requiring `r.enabled`.) `src/backtest.py` got the same fix.

**Proof:**
```
python -m pytest tests/test_rules_engine.py tests/test_planner.py tests/test_artist_playlist.py -q
→ 125 + 81 + 17 = 223 passed
```
Covers: match/no-match with and without enrichment, `check_key`'s `actual` payload, combining with other
conditions, explain-trace `matched`/shadowed results, `decide()`'s auto-resolution (including the too-young and
defensive-None cases), `build_plan()` moving to the *resolved* name (never literal `"auto"`),
`targets_needed()`, `ArtistPlaylistMap` (no-signal, below-floor, below-dominance, confident-home, leave-one-out,
genuine-tie-never-guesses, both inclusive boundaries), and `build_artist_playlist_map`'s Vault_drx/test-playlist/
unusable-playlist/configured-exclude filtering.

## 3. Backtest-integration proof (real shipped code, real library)

`tests/test_artist_in_playlist_live.py` (`@pytest.mark.live`, `SPOTISORT_LIVE=1`): builds the **actual shipped**
`ArtistPlaylistMap` (not the standalone `measure_artist_in_playlist.py` script) against the real library,
restricted to the same "effectively single-playlist artist" subset the round-2 measurement used (reusing only
that subset-classification helper, not any prediction logic), and asserts precision reproduces the measured
94.1% / 95.8% / 98.4% (min_tracks 2/3/5) within a 5-point tolerance for real-world library drift since the
2026-09-27 measurement.

```
SPOTISORT_LIVE=1 python -m pytest tests/test_artist_in_playlist_live.py -v -m live
→ test_shipped_artist_playlist_map_reproduces_measured_precision PASSED
→ test_vault_drx_is_never_an_auto_target_on_the_real_library PASSED
(2 passed in 47.6s)
```
This is the proof that the min_tracks+min_dominance simplification (dropping the margin knob) didn't change the
measured result — confirmed with the real shipped resolution code, not a re-derivation.

## 4. Explain trace wording + dashboard interaction check (decision 55)

`docs/dashboard/views.js`'s `narrativeSentence()` gained one new sentence, shown whenever a song's artist has a
resolved home (regardless of which rule actually decided the song, same pattern as the language sentence):
> Routed to "Fuel" — 9 of the artist's 10 tracked tracks are already there.

**Shadowed-rule/interaction detection**: confirmed it **already generalizes** with no code change — the
mechanism (`build_latest_plan`'s per-rule `would_match`/`wins` count, driven by the generic explain trace)
works off `result` values (`matched`/`not_reached_but_would_match`) that `artist_in_playlist` produces exactly
like every other match key. Proof: `tests/test_artifacts.py::test_auto_rule_shadowing_is_detected` (an earlier
`artist_in_playlist` rule correctly shows `status: "ok"`, a later overlapping `artist_in` rule correctly shows
`status: "shadowed"`) plus a dashboard e2e test (`test_rules_view_shows_dynamic_badge_for_auto_rule`) confirming
it renders. `Vault_drx` exclusion confirmed live (§3 above, second test).

Two artifacts.py fixes were needed so an `auto` rule doesn't misreport on the dashboard: `_rule_summary`'s
target-status resolution would otherwise call `resolve_target("auto", playlists)` and wrongly report
`"missing"` for a working rule — it now reports a new `target_status: "dynamic"` (rendered as a "Resolved per
song" badge). The Playlists view's per-target grouping skips `auto` rules entirely (there's no single fixed
target to report a size/planned_in count against — each song's real resolved target already appears under its
own name via `songs[].target_playlist`).

**Proof:**
```
python -m pytest tests/test_artifacts.py -q                                    → 89 passed
python -m pytest tests/e2e/test_dashboard.py -k "artist_routing or dynamic_badge" -q -m e2e  → 3 passed
```

## 5. Configure UI

New panel at the top of the Rules step: Basic-visible on/off toggle ("Enable artist-based routing") + two
numeric fields (min_tracks, min_dominance, pre-filled with the defaults 3/0.9) — matches decision 54's "Basic
mode gets a simple on/off toggle + the two numeric defaults" exactly. Advanced-only: an `exclude_playlists`
chip list where `Vault_drx` is always shown first with no remove button (non-removable, per decision 54), and
user-added exclusions are addable/removable normally. `artist_in_playlist` is a new selectable rule condition
(a `flag`-kind entry, no value to enter); selecting it auto-fills `target_playlist` to `auto` when that field
is still empty, and the field's hint text changes to explain why. Full YAML/import round-trip supported.

**Proof (`tests/e2e/test_builder.py`, all against the real `docs/builder/app.js`/`validate.js`, 3 browsers):**
```
python -m pytest tests/e2e/test_builder.py -q -m e2e   → 99 passed
```
6 new tests: Basic toggle + defaults + on/off block presence, rule condition auto-fills `auto` and validates
clean, a mismatched literal target is flagged with the right error text, Vault_drx chip is non-removable while
a user-added exclusion is, and a full YAML-import round-trip (including that Vault_drx is correctly *not*
duplicated into the re-serialized `exclude_playlists`, since the UI shows it separately). One pre-existing test
(`test_full_build_with_globals_and_all_keys`, the "kitchen sink" rule exercising every match key at once) was
updated: `artist_in_playlist` can't join that rule (it requires `target_playlist: auto`, incompatible with the
rule's literal target), so the assertion now confirms it's specifically the one key left in the "add condition"
dropdown, rather than asserting the dropdown is empty.

## 6. Shipped config

`config.yaml` gained the `artist_in_playlist:` block (min_tracks 3, min_dominance 0.9, `exclude_playlists:
["Vault_drx"]`) and one draft rule, **`enabled: false`**, matching the existing Japanese/English draft style:
```yaml
- name: "Route to artist's home playlist (draft)"
  enabled: false
  match:
    artist_in_playlist: true
  target_playlist: auto
```
Confirmed live via a real local dry-run: `python -m src.sync` evaluated 775 liked songs, the six already-live
explicit `artist_in` rules correctly matched (Anavae ×4, Riffs in the air ×1, The Klasey Universe ×1, Midnight
Mixer ×1), and the disabled draft made no difference to the HTTP call count (§2 above).

**Note on git history:** this session and the master/design session share the same local working directory.
While this phase was in progress, the master session committed two of its own config.yaml edits (`d0144a1` —
the six explicit `artist_in` rules, `bd619b8` — `target_position: top` on Hindi→Dil) directly to this repo; the
second of those commits' diff also happened to include this phase's in-progress, not-yet-committed
`artist_in_playlist:` block and draft rule (both sessions were editing the same working-tree file
concurrently). The content is correct and intentional — verified by `git show bd619b8 -- config.yaml` — just
attributed to a commit message that doesn't mention it. Flagging for transparency, not asking anyone to rewrite
history over it.

## 7. Full quality gate suite (decision 30)

```
python -m pytest -q                                              → 1602 passed, 4 skipped
SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e   → 233 passed, 2 skipped (117.8s)
SPOTISORT_LIVE=1 python -m pytest tests/test_artist_in_playlist_live.py tests/test_live_readonly.py -q -m live → 3 passed
```
Axe accessibility tests (bundled in the e2e run above, `-k axe` selects 16 of them across `test_builder.py`/
`test_dashboard.py`/`test_site.py`) all pass — the new Configure panel introduced 0 new serious/critical
violations. Dashboard fixtures regenerated (`python scripts/make_dashboard_fixtures.py`) for the new
`artist_routing` song field; `test_fixtures_regenerate_identically` confirms byte-for-byte reproducibility.
Lighthouse runs in CI only (`treosh/lighthouse-ci-action`); confirmed on the pushed commit, see the CI run
linked in the summary to the user.

## Files touched (besides tests)

`src/models.py`, `src/config.py`, `src/rules_engine.py`, `src/planner.py`, `src/enrich.py`, `src/sync.py`,
`src/backtest.py`, `src/enrichment/artist_playlist.py` (new), `docs/builder/{validate,app,schema}.js`,
`docs/builder/index.html`, `docs/dashboard/views.js`, `docs/dashboard/DATA.md`, `config.yaml`,
`design/proposals/artist_in_playlist.md` (status updated to built), `README.md` (match-key list + a short
`artist_in_playlist` explainer).

## Deviations from the master's instruction

None. Decision 51 (SpotiSort Sink / `fallback_playlist`) was explicitly not touched — it waits on the user
confirming the playlist exists.
