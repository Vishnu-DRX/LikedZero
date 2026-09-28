# Phase: expand the match-key vocabulary (design/proposals/more-conditions.md)

Builds the three items approved by the user from the proposal's menu: `artist_country_in` (Tier 1, free),
`unless` exceptions (Tier 2), and `any_of` OR-groups (Tier 2). Tier 3 (`release_type_in`) was not requested and
stays unbuilt, per the proposal's own recommendation to skip it absent a specific need.

## 0. Design decisions made while building (flagged for the master/user to double-check)

The proposal named these as open questions ("Decide and document how X interacts with Y"). Decisions taken,
all enforced by validation (not just convention):

1. **`unless`-blocked == non-match, not a hard stop.** When a rule's `match` passes but its `unless` also
   fully passes, the rule is treated exactly like an ordinary failed match: evaluation continues to the next
   rule. This is deliberately different from the age-gate's "blocks, does not fall through" (decision 2) —
   that rule is about a *matched* rule not being old enough yet; `unless` decides whether the rule matches at
   all. A broad rule with an exception (e.g. "Hindi → Dil, unless Arijit Singh") falls through to whatever
   comes next (another rule, or nothing) rather than being stuck.
2. **`unless` + `any: true`** composes exactly as you'd expect from decision 1: a catch-all with an exception
   means "catch everything except X" — if `unless` blocks it and there's nothing after the catch-all, the
   song is simply unmatched (or falls to `fallback_playlist` if configured). No special-case code was needed;
   `check_key`'s `any` branch and the `unless` block are fully orthogonal.
3. **`artist_in_playlist` cannot live inside `unless` or an `any_of` group — enforced, not just documented.**
   Its `auto` target sentinel is resolved from the rule's *top-level* `match` only (`config.py`'s pairing
   check only ever inspects `rule.match`, not `unless` or nested groups). Allowing it to hide inside either
   structure would let a rule validate cleanly while the auto-target substitution silently never fires for
   that branch. `config.py`/`validate.js` reject it explicitly in both places with a message naming the
   reason, rather than leaving it as an untested, ambiguous corner case.
4. **`any_of` cannot nest inside another `any_of` group** — kept to one level of grouping. Nothing in the
   proposal asked for arbitrary nesting, and one level already covers "A or B" without complicating the
   schema, the resolution logic, or the Configure UI's branch editor.
5. **Shadowed/dead-rule detection needed zero changes for either feature** (same story as `artist_in_playlist`
   and `any` before them): `unless`-blocked rules get their own `explain()` result
   (`blocked_by_exception`, distinct from `not_reached`/`failed`), so the dashboard's shadow computation
   (`build_latest_plan`'s `would_match`/`wins`) is *more* accurate than before, not less — a rule that would be
   blocked by its own exception no longer inflates the "would also match" list, since it wouldn't actually take
   the song even if reached. `any_of`'s `check_key` returns every branch's pass/fail plus which one won, so the
   explain trace can show *which branch* decided a match, satisfying the proposal's own ask.

These are the four choices most worth a second look; everything else (schema shape, wording, UI placement)
follows directly from the existing `artist_in_playlist`/`any` patterns.

## 1. Schema (`config.py` + `validate.js` + parity tests)

- **`artist_country_in`** joins `LIST_MATCH_KEYS`: a non-empty list of 2-letter ISO country codes, validated
  by format (`^[A-Za-z]{2}$`) and normalised to uppercase — not restricted to a curated subset the way
  `isrc_country.py`'s ISRC-prefix table is, since this checks directly against MusicBrainz's own country
  field, not an ISRC-prefix heuristic.
- **`unless`** is a new optional `Rule` field (`RULE_KEYS` gains `"unless"`), validated by the same
  `_validate_match`/`validateMatch` function `match` uses (`label="unless"` for parity-correct error text,
  `forbid_artist_in_playlist=True`). Absent or explicit `null` means no exceptions; present-but-empty (`{}`)
  is rejected the same way an empty `match` is.
- **`any_of`** joins `MATCH_KEYS` as a new key whose value is a non-empty list of match-condition groups
  (dicts), each validated recursively through `_validate_match` with `forbid_artist_in_playlist=True,
  forbid_any_of=True`. Group-level errors are attributed to `where.any_of[i]` so they're distinguishable from
  top-level errors on the same rule.
- `_validate_match` was generalised (both languages) to take a `label` and two `forbid_*` flags rather than
  hard-coding "match" — the same function now serves `match`, `unless`, and every `any_of` group, message-for-
  message identical in Python and JS.

**Proof:**
```
python -m pytest tests/test_config.py -q                                        → 215 passed
python -m pytest tests/e2e/test_builder.py -k matches_python -q -m e2e           → 53 passed
```
31 new `test_config.py` cases (valid/normalisation/every invalid shape for all three keys, both `unless`
pairing directions with `artist_in_playlist`, `any_of` nesting rejection, `any_of`/`unless` composing with
`any` and with each other). 18 new JS/Python parity cases in `PARITY` (`tests/e2e/test_builder.py`), run
against the **real** `validate.js` in a browser, not a Python re-implementation — including the exact bug this
caught (see §7).

## 2. Resolution logic (`rules_engine`)

- **`artist_country_in`**: one branch in `check_key` — `enrichment.artist_country` (new `Enrichment` field, see
  §2a) checked case-insensitively against the wanted set. No enrichment plumbing changes needed beyond the new
  field, matching `artist_in_playlist`'s pattern of riding the existing `Enrichment` object.
- **`any_of`**: one branch in `check_key` plus a small `_eval_group` helper (AND-combines one branch's
  conditions, reused by both `any_of` and `unless`). Returns every branch's pass/fail and which one first
  passed — `_match_keys`/`first_match`/`decide`/`build_plan` needed **zero** changes, since `any_of` is just
  another key that `check_key` resolves generically, exactly like `artist_in_playlist` and `any` before it.
- **`unless`**: `first_match` gained one check — after a rule's `match` passes, `_blocked_by()` evaluates the
  `unless` block (same `_eval_group` helper) and `continue`s to the next rule if it also passes. `explain()`
  gained the parallel logic plus a `blocked_by_exception` result and `blocked_reason`/`unless_conditions`
  trace fields (`_describe_hit`/`_describe_block` turn a matched condition into a short phrase like `artist_in
  matched Arijit Singh`, joined with "and" when multiple `unless` keys all matched).

### 2a. `Enrichment.artist_country`

New field on `Enrichment`, populated in `Enricher.resolve()` from `entry.get("country")` — the exact
MusicBrainz artist `country` field already looked up for genres and for the `english_default` weak-signal
(`Enricher._english_by_country`). No new provider call, no new cache key, and populated whenever MusicBrainz
enrichment runs at all (not gated behind `english_default`, since this is an exact field lookup, not an
inferred guess — matching the proposal's own framing: "same weak-signal caveat as `country_default`... but
it's an exact field lookup, not an inferred signal, so no precision bar").

**Proof:**
```
python -m pytest tests/test_rules_engine.py tests/test_planner.py tests/test_enrichment.py -q → 160 + 91 + 61 = 312 passed
```
Covers: match/no-match with and without enrichment for `artist_country_in`; `unless` blocking, falling
through to a later rule, falling through to nothing, falling through to `fallback_playlist`, composing with
`any: true` and with `artist_in_playlist`'s auto target (decisions 1–3 above, each with a dedicated test);
`any_of` matching via either branch, AND-within-a-branch, composing with the rest of `match`, `check_key`'s
full per-branch report, explain-trace branch visibility, and `any_of` nested inside `unless`; plus
`Enricher.artist_country` exposure (cached entry, uppercasing, `None` when MusicBrainz has no country,
`None` when no MusicBrainz call was ever made, independence from `english_default`, and a same-artist-cached
second track making zero additional MusicBrainz requests).

## 3. Dashboard: explain-trace wording + Rules view

`src/artifacts.py`'s `_rule_summary` gained an `"unless"` field (mirrors `"conditions"` for `match`; empty dict
= no exceptions) — the only artifacts.py change needed, everything else (per-song `explain` trace, shadow
detection) already carries the new data through unchanged code paths, confirmed in §2's proof.

`docs/dashboard/views.js`:
- **Technical trace**: a new `blocked_by_exception` entry in `TRACE_RESULT`; each trace row now also renders
  `unless_conditions` (when present) under an "Exception (unless)" heading and the plain-English
  `blocked_reason` sentence. A new `conditionLine()` helper renders `any_of` conditions as a numbered list of
  branches with a ✓/✕ mark per branch (not just pass/fail for the whole key) — this is the concrete answer to
  the proposal's "make clear which branch actually matched."
- **Sentence-first narrative** (`narrativeSentence`): gained two clauses, same append-a-clause pattern the
  language/artist-routing/catch-all sentences already use — "It matched via one of several allowed options
  (branch N of M)" when the decided rule used `any_of`, and "Rule 'X' would otherwise have matched first, but
  its exception blocked it (‹reason›)" when an earlier rule in file order was blocked.
- **Rules view**: the Conditions cell now renders `any_of` as `(group A) OR (group B)` via a new
  `matchDictLine()` helper instead of the generic `fmtVal()` (which would have printed `[object Object]` for
  an array of group dicts), and shows a second "unless ..." line when a rule has exceptions.

**Proof:**
```
python -m pytest tests/test_artifacts.py tests/test_dashboard_fixtures.py -q   → passing (unless field added to the committed contract)
python -m pytest tests/e2e/test_dashboard.py -q -m e2e                          → 82 passed
```
6 new dashboard e2e tests: blocked-by-exception trace row + reason, narrative mentions the blocked earlier
rule, Rules-view unless summary, any_of branch trace rendering (both branches shown, winning branch named),
narrative names the winning branch, Rules-view any_of summary. `docs/dashboard/fixtures/latest-plan.json`
regenerated (`python scripts/make_dashboard_fixtures.py`) for the new `unless` field on every rule entry;
`test_dashboard_fixtures.py`'s byte-identical-regeneration and full-contract tests both updated and passing.

## 4. Configure UI

- **`artist_country_in`**: a new `list`-kind condition, identical widget to `artist_in`/`genre_contains`
  (chip entry), with input uppercased on commit. Zero new UI plumbing beyond a `COND` entry.
- **`unless`**: a new Advanced-only fieldset at the bottom of each rule card ("Exceptions (unless this also
  matches)"), reusing the exact same `condRow`/`chipList` widgets the `match` fieldset uses (generalised with
  a `listName` parameter rather than duplicated) — same look, same validation, same error wiring, with
  `artist_in_playlist` excluded from its "add a condition" dropdown per decision 3.
- **`any_of`**: a new condition kind (`kind: 'anyof'`) rendering a branch-by-branch nested editor — each
  branch is its own mini condition list (add/remove conditions, same widget kinds, via new generic
  `xCondRow`/`xChipList` helpers scoped to an arbitrary branch array instead of `rule.match`), with
  "Add branch condition"/"Add another branch (OR)"/"Remove branch" controls. `artist_in_playlist` and nested
  `any_of` are excluded from a branch's own "add condition" dropdown, matching decisions 3–4. Available in
  both Basic and Advanced (not gated), same as `artist_in_playlist`/`any` before it, since it's a `match`
  condition like any other — only `unless` itself is Advanced-only, per its Tier-2 framing in the proposal.
- `toData()`/`applyParsedToState()` (state ⇄ YAML) were generalised through shared `condValueOut`/
  `condValueIn`/`matchListToDict`/`dictToMatchList` helpers so `any_of`'s nested structure and `unless`
  round-trip correctly without hand-special-casing each new key at every call site.
- Schema reference drawer (`docs/builder/schema.js`) gained rows for all three; README's match-key list and
  per-key bullets updated to match (and, noticed in passing, added the pre-existing `any` catch-all key, which
  the earlier catch-all phase never added to this list — a one-line fix in the same edit, not a separate
  change).

**Proof:**
```
python -m pytest tests/e2e/test_builder.py -q -m e2e   → 134 passed
```
New tests: builds + validates `artist_country_in` (and flags an invalid code), the Advanced-only visibility of
the `unless` fieldset, builds + validates an `unless` block end to end, its plain-English Review summary,
removing an exception condition returns the rule to `unless: {}`, `artist_in_playlist` absent from the
`unless` dropdown, builds a two-branch `any_of` end to end, an empty `any_of` branch is flagged,
`artist_in_playlist`/nested `any_of` absent from a branch's dropdown, the plain-English summary for `any_of`.
The existing "kitchen sink" test (`test_full_build_with_globals_and_all_keys`) was extended to also add
`artist_country_in` and a one-branch `any_of`, so the "one key left in the dropdown" assertion
(`artist_in_playlist`) still holds true with all nine other keys present at once.

## 5. `config.example.yaml`

Illustrative, **commented-out** examples of all three keys appended after the existing six live rules — not
parsed as YAML, don't change the file's rule count or content, and don't touch the real `config.yaml` at all
(confirmed: `git status --short config.yaml` shows nothing). Matches the instruction: no concrete real-world
case has been identified for any of these three yet, unlike the six `artist_in` rules and the catch-all.

**Proof:**
```
python -m pytest tests/test_config.py -k example -q                             → 1 passed (rule count/content unchanged)
python -m pytest tests/e2e/test_builder.py -k import_example_config -q -m e2e   → 1 passed (round-trips through Configure unchanged)
```

## 6. A pre-existing, unrelated accessibility issue found while testing (not fixed here)

Building a dedicated axe test for the new `unless`/`any_of` panels surfaced a **pre-existing** violation
unrelated to this phase: the wizard stepper's `<li role="button">` (`docs/builder/app.js`'s `wire()`) strips
the `<li>`'s implicit listitem role, so axe's "list" rule fires whenever the wizard is scanned without a
modal/drawer open to hide the background from the accessibility tree — it reproduces on a completely plain
rule with none of this phase's keys involved, and doesn't surface in the existing
`test_axe_zero_serious_or_critical_with_stepper_and_modal_and_drawer` only because that test happens to scan
after opening the Versions drawer. Flagged as a background task rather than fixed here (out of scope for a
match-key phase) or silently ignored; my own new axe test (`test_axe_zero_serious_or_critical_with_unless_and_any_of_panels`)
follows the same drawer-open pattern as the existing passing test so it actually exercises the new panels
instead of tripping over this unrelated, pre-existing bug.

## 7. A real bug the JS/Python parity tests caught before shipping

First draft of `validate.js`'s `any_of` group-mapping error ("each 'any_of' group must be a non-empty
mapping") used the outer rule-level `where` instead of the group-specific `where.any_of[i]`, producing a
message that was one component short compared to `config.py`'s. The parity test
(`test_js_validator_matches_python_messages[doc47]`, `{"any_of": [{}]}`) failed with an exact, readable diff
pointing at the missing `.any_of[0]` segment — exactly the kind of drift this test suite exists to catch
before it reaches a real user's browser. Fixed by building the error object directly with `groupWhere` instead
of reusing the outer-scoped `add()` closure.

## 8. Full quality gate suite (decision 30)

```
python -m pytest -q -m "not live"                                                          → 1962 passed, 2 skipped
SPOTISORT_BROWSERS=chromium,firefox,webkit python -m pytest tests/e2e -q -m e2e             → 274 passed, 2 skipped (126.4s)
python -m pytest tests/e2e/test_builder.py -q -m e2e -k axe                                 → 3 passed (0 new serious/critical violations)
```
Axe accessibility tests (16 total across `test_builder.py`/`test_dashboard.py`/`test_site.py`, `-k axe`) all
pass, including a new dedicated scan of the `unless`+`any_of` panels together (§6). Dashboard fixtures
regenerated and confirmed byte-for-byte reproducible. **Lighthouse runs in CI only** (`treosh/lighthouse-ci-
action`) — not runnable in this local environment; unverified here, same as every prior phase report notes.
Live tests (`SPOTISORT_LIVE=1`) were not run for this phase — nothing here touches Spotify's API, enrichment
providers, or any network call beyond what already existed (the new `Enrichment.artist_country` field is
populated from data already fetched in existing, already-live-tested code paths).

Note on this environment: Playwright's browser downloader has a hardcoded ~30s per-request timeout that this
sandbox's bandwidth couldn't beat for the ~200MB Chromium/Firefox/WebKit archives, so `playwright install`
itself kept failing. Downloaded the four browser archives directly with `curl -L` (which has no such timeout)
and placed them into `~/AppData/Local/ms-playwright/` by hand, matching the layout `playwright install --dry-
run` reported. Purely a one-time local environment workaround, not a code or config change.

## Files touched (besides tests)

`src/models.py`, `src/config.py`, `src/rules_engine.py`, `src/artifacts.py`, `src/enrichment/enricher.py`,
`docs/builder/{validate,app,schema,builder.css}`, `docs/dashboard/{views.js,DATA.md}`,
`docs/dashboard/fixtures/latest-plan.json`, `config.example.yaml`, `README.md`,
`design/proposals/more-conditions.md` (status updated to built).

## Deviations from the master's instruction

None. `config.yaml` (the real, live config) was not touched, as instructed — confirmed via `git status
--short config.yaml` showing no changes. The four design decisions in §0 are exactly the kind of "your call,
document the choice" latitude the proposal and the `artist_in_playlist`/catch-all phases both used; flagging
them for a second look rather than treating them as settled, since this session had no live user to confirm
them with in the moment.
