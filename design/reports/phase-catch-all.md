# Phase: the real catch-all (Master decisions 12 / decision 51)

Builds Q6, the proper `fallback_playlist`/catch-all, replacing the `release_year_after: 1900` hack.

## 0. Which playlist is the real target — resolved, not asked

The cross-session directive asked me to flag the Vault_drx-vs-SpotiSort-Sink ambiguity back to the master
rather than guess. Before doing that, I re-read `design/BUILD_SPEC.md`'s decision 51, which had already been
updated (evidently by the master session, ahead of the directive reaching me) to say explicitly: *"Confirmed
done: the user created this empty playlist on 2026-09-27... Ship the real config pointed at `SpotiSort Sink`."*
That's authoritative and settles it — no question needed. Live-confirmed the playlist itself: real, owned,
writable, currently empty (`items_total: 0`), id `2rN8TYZ6WcVvGRcCl1iK7m`.

## 1. Mechanism choice: `match: {any: true}` rule, not an extended `fallback_playlist`

Decision 51 offered two options and left the choice to me. Went with a new **`any: true` match key** on a
normal rule, not extending `fallback_playlist` to `{playlist, target_position}`. Reasoning:

- Decision 51 itself also asks for "sensible Rules-view / shadowing treatment, same as `artist_in_playlist`
  got." `fallback_playlist` is a bare string special-cased entirely outside the rules list — it has no name, no
  explain-trace entry, and structurally cannot appear in the Rules view or participate in shadowing detection.
  Only a real rule can satisfy that requirement.
- `artist_in_playlist` already proved that reusing the generic rule engine (rather than special-casing a new
  top-level concept) needs almost no new code and inherits explain/shadowing/position/threshold-override for
  free. The same applies here even more directly, since `any` doesn't need a resolved-target substitution step
  at all — it's the simplest possible match key.
- "Evaluated only after every other enabled rule has failed to match" is exactly first-match-wins semantics for
  a rule placed last — no new ordering mechanism needed, the existing engine already guarantees it.

The existing `fallback_playlist` config key is **untouched and still works** exactly as before — it's a
separate, simpler, already-shipped mechanism (no explain trace, no position, uses the default threshold only)
that nobody asked to remove. `any: true` is the new, "proper" way to build a full-featured catch-all rule.

## 2. Schema (`config.py` + `validate.js`)

`any` added to the existing `TRUE_ONLY_MATCH_KEYS` set both sides (the same category `artist_in_playlist`
already uses: must be literally `true`, `false` has no defined meaning and errors). No sentinel-pairing rule
needed — `any`'s `target_playlist` stays a normal literal playlist name, unlike `artist_in_playlist`'s `auto`.
Combining `any` with other conditions is allowed (redundant — anything else just narrows what's already
unconditional — but not forbidden, since disallowing it would need a bespoke validation rule for a harmless
edge case nobody would realistically write).

**Proof:**
```
python -m pytest tests/test_config.py -q                                        → 188 passed
python -m pytest tests/e2e/test_builder.py -k matches_python -q -m e2e           → 35 passed
```
4 new config.py cases (valid, must-be-true, no auto-target requirement, combines with other keys); 3 new
parity cases against the real `validate.js` (valid rule, `any: false` error, combined with `explicit`).

## 3. Resolution logic (`rules_engine`)

One line in `check_key()`: `if key == "any": return True, True, True`. That's the entire engine change —
`_match_keys`, `first_match`, `explain`, `decide`, `build_plan`, `targets_needed` needed **zero** modifications,
since `any` needs no data beyond "always pass," unlike `artist_in_playlist` which needed the `Enrichment`
plumbing. Verified end-to-end offline (a catch-all rule placed after a specific one only fires when nothing
else did; placed before one, it correctly shadows it — both directions tested) and live (§6).

**Proof:**
```
python -m pytest tests/test_rules_engine.py tests/test_planner.py -q   → 131 + 84 = 215 passed
```
11 new cases across both files: unconditional match with/without enrichment or artists, last-resort behind a
specific rule, `check_key`'s trivial `actual`/hit values, explain-trace shadowing both directions,
`decide()`'s too-young handling, and `build_plan()` correctly routing the unclaimed track to the catch-all
(with its own `target_position`) while the claimed one goes to its specific rule's target.

## 4. Dashboard: Rules-view / shadowing + explain wording (decision 51's own ask)

**Shadowing/Rules-view treatment: confirmed to already generalize, same as `artist_in_playlist`.** No code
change needed in `artifacts.py` — the generic `would_match`/`wins`/`status` computation in `build_latest_plan`
already produces sensible results for a rule whose condition trivially always passes: `would_match` counts
every song reached (since its own condition always "would match"), `wins` counts only the ones it actually
decided, and `status` correctly comes out `shadowed` only if literally nothing reaches it, `ok` otherwise —
verified with 4 new `tests/test_artifacts.py` cases (normal Playlists-view row — unlike `auto`, a literal
target *does* get one; wins some songs; shadowed by being placed first; correctly placed last never shadows
earlier specific rules).

**Explain wording**: `narrativeSentence()` in `docs/dashboard/views.js` detects (via the existing explain trace,
no new song-level field needed) when the deciding rule's conditions include `any`, and appends: *"Nothing more
specific matched first, so it falls to this catch-all."* — same append-a-clause pattern the language and
artist-routing sentences already use.

**Proof:**
```
python -m pytest tests/test_artifacts.py -q                                → 93 passed
python -m pytest tests/e2e/test_dashboard.py -k catch_all -q -m e2e         → 1 passed
```

## 5. Configure UI

`any` reuses the `flag` match-condition kind built for `artist_in_playlist` — genuinely zero new UI plumbing
needed beyond adding the `COND` entry (label, hint) and one clause in `englishLabel()` for a readable
plain-English summary ("...that are anything (catch-all) go to SpotiSort Sink."). No new fields, no new panel.

**Proof:**
```
python -m pytest tests/e2e/test_builder.py -q -m e2e   → 104 passed
```
3 new tests: builds and validates a catch-all rule end to end, the plain-English Review summary reads
correctly, and (updated) the pre-existing "kitchen sink" test now also adds `any` to its all-keys rule (it can
combine with a literal target, unlike `artist_in_playlist`) and asserts it's excluded correctly from the
now-9-key combination while confirming `artist_in_playlist` remains the one truly incompatible key.

## 6. Live proof

`tests/test_catch_all_live.py` (`@pytest.mark.live`):
- `SpotiSort Sink` resolves via the real `resolve_target()` and is `usable` (owned, writable).
- A what-if (every rule force-enabled) run over the first 200 real liked songs reaches a decision for all of
  them via either the catch-all or an earlier rule, confirming the mechanism resolves correctly against real
  data. In this sample all 200 fell to the catch-all (the six artist-specific rules match only ~7 songs total
  across the whole 775-song library, per the sync dry-run below, so a 200-song slice not hitting any of them is
  expected, not a bug) — the *ordering* guarantee itself (a specific rule wins over the catch-all when it
  matches) is exhaustively proven by the offline unit tests in §3, which use fabricated data specifically
  designed to exercise both outcomes.

```
SPOTISORT_LIVE=1 python -m pytest tests/test_catch_all_live.py -v -m live -s
→ test_spotisort_sink_resolves_and_is_writable PASSED
→ test_catch_all_never_overrides_an_earlier_specific_rule PASSED (catch-all wins: 200, earlier-rule wins: 0)
```

A real local `python -m src.sync` dry-run before and after this change produced the **identical** HTTP call
count (30 GETs) and the identical 7 moves — confirming the disabled catch-all rule costs nothing and changes
nothing while off, same discipline as the `artist_in_playlist` gating fix last phase.

## 7. Shipped config

```yaml
- name: "Catch-all -> SpotiSort Sink (draft)"
  enabled: false
  match:
    any: true
  target_playlist: "SpotiSort Sink"
  target_position: top
```
Placed as the **last** rule in `config.yaml` (replacing the old `release_year_after: 1900` "Vault catch-all"
entry in the same position), `enabled: false` — the master/user turns it on after reviewing a dry-run, same
pattern as every other rule that has reached this config.

## 8. Full quality gate suite (decision 30)

```
python -m pytest -q                                                              → 1619 passed, 4 skipped
SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e  → 239 passed, 2 skipped (120.1s)
SPOTISORT_LIVE=1 python -m pytest tests/test_catch_all_live.py -m live -s        → 2 passed
```
No dashboard fixture regeneration was needed this time — `any` adds no new field to any committed JSON schema
(unlike `artist_routing` last phase), it's purely an engine-level match key whose effects are already visible
through the existing explain-trace/rules-status machinery.

## Files touched (besides tests)

`src/config.py`, `src/rules_engine.py`, `docs/builder/{validate,app,schema}.js`, `docs/dashboard/views.js`,
`config.yaml`.

## Deviations from the master's instruction

None — the ambiguity the directive asked me to flag was already resolved in `BUILD_SPEC.md` before I started,
so I proceeded rather than re-asking a settled question (documented in §0 rather than silently skipped).
