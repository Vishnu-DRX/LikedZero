# SpotiSort: end-to-end review (2026-09-27)

Scope: the whole repo at `b07a0db` (Phase 7 "Save to GitHub" included). That covers the Python core (rules engine, planner,
apply/restore, guardian, enrichment), the three CI workflows plus `sync.yml`, the Pages site (Home, Setup guide,
Configure, Dashboard, run-now/PAT), and the committed logs. It also compares the product with how email inbox rules
work (Gmail filters, Outlook rules/Sweep, SaneBox-style trained sorting).

Evidence: `python -m pytest -q` gives **1525 passed, 2 skipped**. CI on `main` was green up to `7164f50` and still
running for `b07a0db`. I could not run the e2e suite locally because no browser launched, so 175 tests skipped
(see finding P2-5).

---

## Verdict in one paragraph

The **safety core is excellent**. It adds, confirms, journals, removes, reconciles and restores, and it is dry-run by
default with a hard move cap and failure-injection tests. The explain/shadowed-rule/backtest tooling goes beyond what
Gmail or Outlook offer. The problems are elsewhere. **(1) The "inbox" never runs on its own.** A scheduled run can only
dry-run, and nothing stops a future unattended run from touching the 773 legacy songs except the fact that today's rules
happen not to match them. **(2) Public logs reveal the whole library** even with titles hidden. **(3) Two
site features share one token** in a way that breaks run-now. **(4) The rule language lacks several email-rule basics**
that matter here: exceptions, copy vs. move, "keep in inbox", a clean catch-all/archive, and "new items only".

---

## P1: fix before turning on a schedule

### P1-1. Scheduled runs can never apply, and the hook the comment promises does not exist
`sync.yml` has only `workflow_dispatch`. A `schedule:` event has no inputs, so `DRY_RUN` is empty and
`${DRY_RUN:-true}` makes it a dry run. The file header says to "set the repository variable
`SPOTISORT_SCHEDULED_APPLY=true`", but nothing reads that variable (grep: only the comment). Live runs also demand
`newest`, which a schedule cannot supply, and `--allow-unselected` is deliberately never passed (asserted in
`tests/test_workflows.py:63`). So the product as shipped is a manual tool. The README's "It runs on a schedule via GitHub
Actions" is not true yet.
**Fix:** implement the variable. On `schedule` with `vars.SPOTISORT_SCHEDULED_APPLY == 'true'`, pass
`--apply --allow-unselected --max-moves …`, together with P1-2's inbox start date (never without it).

### P1-2. There is no "inbox start date": an unattended run would evaluate the 773 legacy songs
Master decision 12 ("never operate on the existing library") is enforced only by the manual `--newest` selector. The
config has no equivalent. The moment a schedule uses `--allow-unselected`, the planner evaluates the whole library.
Today nothing moves only because 641 of 774 songs have no resolved language and the enabled rules are Hindi/Malayalam.
Enabling the English rule or the Vault catch-all would put hundreds of legacy songs in the plan.
**Fix:** add a config key `inbox_since: 2026-09-20` (the Gmail analogue is "apply to new mail only"). Enforce it in the
planner, show it in Configure and on the Overview, and require it whenever `--allow-unselected` is used.

### P1-3. `--max-moves` overflow aborts silently and would jam the inbox every day
In `src/sync.py`, `TooManyMoves` returns `EXIT_TOO_MANY` **before** any log, `runs.json` entry or guardian snapshot is
written. The dashboard then shows the previous run as current, and only the Actions tab is red. For a scheduled inbox
this repeats on every run until someone raises the cap. A holiday or a big liking spree can do it: 60 songs aged past
14 days with the default cap of 50.
**Fix:** always write the run log with `verdict: "aborted_too_many"` and the plan counts, so the dashboard states it
plainly. For scheduled runs, consider a "process oldest N, carry the rest over" mode as the alternative to aborting.
Outlook's "Run rules now" processes a backlog in batches; it does not refuse.

### P1-4. Hiding titles does not make logs private: URIs plus dates publish the whole library
With `include_track_names: false` (the fork default), `logs/latest-plan.json` still carries every liked song's
`spotify:track:` URI, `added_at`, language and genres. That is 774 entries and 1.4 MB, in a public repo, on every run.
Anyone can turn a URI into a title in one request (open.spotify.com/track/ID). The "private by default" claim in
Configure and the Setup guide is therefore misleading.
**Fix (pick one):** (a) when titles are hidden, drop URIs too and keep counts and the decision per anonymous row, or
salt-hash the ids; (b) stop committing `latest-plan.json` and ship it only as an Actions artifact. Either way, reword the
UI copy. A related detail: artifacts on a **public** repo can be downloaded by any signed-in GitHub user, so the "private
Actions artifact" wording in `sync.yml` and decision 33 is also inaccurate.

### P1-5. Configure and run-now share one sessionStorage token slot with different scopes
`GithubPAT.get/set` key on `owner/repo` only. Configure's "Save to GitHub" mints a token with **Contents: write** only.
If the user then opens run-now in the same tab, it finds that token, skips the connect step, and the dispatch fails with
403. The failure handler matches `/token|401|403/` and **clears the token**, which also logs Configure out.
**Fix:** request one scope set (Contents + Actions) in both flows, or key the storage by feature/scope. Also check
the scope in `verify()` and don't only test repo read.

### P1-6. The PAT is powerful and long-lived for what it does
A token with Contents: write can edit `src/*.py` or `config.yaml`, and `sync.yml` then runs that code with the Spotify
refresh token in its environment. The token lives 90 days, is pasted into a page that renders third-party strings (song
titles and artists from the logs), and sits in sessionStorage where any script on the page can read it. Escaping is
consistently applied (`esc()` in `views.js`), so I found no XSS. The blast radius is what's worth shrinking:
**Fix:** default `expires_in` to 7 days, and tell the user in the Setup guide to protect `main` or at least watch the
commits. Run-now needs only **Actions: write**, so a separate lower-scope token is better if P1-5 splits the slots.

### P1-7. The guardian cannot tell "Spotify dropped it" from "I un-liked it", and its baseline silently expires
In inbox terms, un-liking a song is the user *deleting a message*, a normal action. `find_vanished` reports it as a
vanish anyway, so false alarms are guaranteed. Separately, `actions/cache` evicts entries unused for 7 days. With
manual runs, a week's gap loses the snapshot, the next run loads `{}`, and it reports "0 vanished" instead of "no
baseline".
**Fix:** write `guardian: {baseline: "missing" | "ok", previous_run: …}` to the log and show it on Safety. Word the
warning as "no longer liked (you or Spotify)". Treat it as a signal to review, not an alarm.

---

## P2: quality, docs, hygiene

1. **Docs drift.** The README says the tool runs on a schedule, that "`--apply` is not available yet", calls the page
   "config builder" (decision 21 renamed it to Configure) and mentions "In Phase 2". The Setup guide talks about "the
   scheduled workflow" and lacks the step forks always need: **Actions tab → "I understand my workflows, enable them"**,
   because GitHub disables workflows on new forks.
2. **`latest-plan.json` (1.4 MB) is committed on every run.** It grows repo history and is the first thing Repo-mode
   dashboards download on phones. Consider slimming it (drop the full explain trace for `no_match` rows and build
   it on demand), or see P1-4(b).
3. **`main` is hardcoded** in the Repo raw URL (`data.js:64`), the dispatch `ref` (`run-now.js`) and the Contents
   `PUT` (`builder/app.js:1006`), while the Contents `GET` uses the default branch. A fork with another default branch
   reads one branch and writes to another. Use `GET /repos/{o}/{r}` → `default_branch`.
4. **CSV export formula injection.** In the Inbox CSV, a title starting with `= + - @` executes in Excel/Sheets.
   Prefix such cells with `'`.
5. **The e2e suite passes with zero browsers.** `SPOTISORT_BROWSERS=auto` skips any browser that fails to launch. Locally
   that meant 2 passed and 175 skipped, still "green". CI should set `SPOTISORT_BROWSERS=chromium,firefox,webkit` so a
   missing browser fails the job.
6. **The `.claude/settings.json` deny rule is prefix-based.** `python -m src.sync --config x.yaml --apply` and
   `--newest 3 --apply` are not denied. Add `Bash(python -m src.sync:* --apply*)`-style patterns or rely on a hook.
7. **Actions pinned by tag, not SHA** (`treosh/lighthouse-ci-action@v11`, `actions/*@v4`), and Lighthouse uses
   `temporaryPublicStorage: true`. That is low risk for a personal repo, but forks inherit it.
8. **Coverage reality.** In the last cloud dry run, 641 of 774 songs (83 %) had **no language**. With language-first
   rules and no fallback, most of a Western-heavy inbox will sit in Liked Songs forever. That is the Q3 "unmatched
   queue" below.

---

## Liked Songs as an inbox: comparison with email rules

### Concept map

| Email | SpotiSort today | Notes |
|---|---|---|
| Inbox | Liked Songs | ✓ |
| Message / received date | Song / `added_at` | ✓ Re-saving resets `added_at`, which is handled |
| Sender | Artist | Matched by **name**, exact. Email matches the address, not the display name |
| Subject contains | `track_name_contains` | ✓ |
| Mailing list / thread | Album (`album_name_contains`) | ✓ |
| Folder (move) | Target playlist | ✓ Move only |
| Label (copy, many) | — | Missing |
| Filter/rule order, "stop processing more rules" | First match wins, always stops | Implicit; no "continue" |
| "Except if…" | — | Missing |
| OR between conditions | Only inside lists, else duplicate the rule | Acceptable |
| Archive (everything else) | `fallback_playlist` | Has no `target_position`; the catch-all is a hack (`release_year_after: 1900`) |
| Outlook Sweep / auto-archive "older than N days" | `days_threshold` | ✓ This is the product's core; the age gate blocks rather than falling through, which is correct |
| "Apply filter to existing conversations" / "new mail only" | `--newest` / `--since` CLI only | No config-level inbox start (P1-2) |
| Run rules now | Run-now button / workflow_dispatch | ✓ |
| Server-side rules (always on) vs client-side (only when the app runs) | Needs Actions cron | Currently "client-side" only (P1-1) |
| Test a filter by searching first | Dry run, what-if, backtest, explain trace | **Better than email** |
| Undo | Journal + `--restore` | **Better than email** (Gmail filters have no undo) |
| Conflicting/unused rule warnings | Dead and shadowed rules on the dashboard | **Better than email** |
| Smart categories / SaneBox training | Language learned from your playlists | Good; generalise it (Q1) |
| Digest / notifications | Dashboard only | Missing (Q6) |
| Star / pin / "never archive" | — | Missing (Q4) |

### What email rules teach that SpotiSort should adopt (ranked by value for this user)

**Q1. "Sender already lives in this folder" rules: the SaneBox idea.** The strongest signal the user already has is
*which playlist an artist's other songs are in*. Language learning already uses this, but only to derive a language.
Generalise it into a match key, for example `artist_in_playlist: ["Dil"]`: the song goes where that artist's songs
already are. It works for any playlist, not just language ones, needs no MusicBrainz, and should score very high
precision in the backtest. It directly covers much of the 83 % with unknown language.

**Q2. Exceptions (`unless:`).** Outlook's "except if" is how people keep broad rules safe. Add an optional `unless:` map
using the same keys, e.g. Hindi → Dil `unless: {artist_in: [Arijit Singh]}` (he has his own playlist). The explain
trace already has the structure to show "blocked by exception".

**Q3. An "unmatched" review queue.** Inbox-zero practice treats "nothing matched after N days" as an action item, not a
steady state. On the dashboard, show "Needs a rule: 37 songs older than 2× threshold". Suggest a rule for the top
unmatched artists (`analyze.py` already has the per-playlist statistics to propose one).

**Q4. Keep / pin (star, "never archive").** Some songs should stay in Liked Songs. Today the only way is to write no
rule that matches them. Add `action: keep` on a rule (matching stops and the song stays) plus a per-song `keep_uris` list
that the dashboard can edit through the Configure save path.

**Q5. Copy vs. move (labels).** Gmail's multi-label model fits music well: a song can be both "Malayalam" and "Workout".
Add `action: copy` (add to the playlist, keep liked, continue evaluating) next to the default `move`. Then there is no
reason for the implicit stop to hide a second match, and the first `move` still ends evaluation. Journal copies too.

**Q6. Proper archive/catch-all.** Make `fallback_playlist` accept `{playlist, target_position}`, or allow a rule with
`match: {any: true}`, and drop the `release_year_after: 1900` workaround. The Vault use case (decision 17) needs exactly
this.

**Q7. Sender identity, not display name.** Allow `artist_id_in` (Configure can resolve names to ids with the search it
already has). Name collisions ("Nirvana" UK/US) and renames are the email equivalent of display-name spoofing. Also
offer `artist_contains` for "feat."-style credits.

**Q8. Digest.** Write a `$GITHUB_STEP_SUMMARY` (moved / waiting / needs-a-rule / vanished) on every run, and optionally
open or refresh one GitHub issue when a run errors, aborts (P1-3) or the guardian fires. That covers email-style
notifications with zero new infrastructure.

**Q9. Re-liked songs (the "reply brings the thread back" case).** If the user re-likes a song that is already in its
target, the planner marks it `already_in_target` and removes it from Liked Songs again after the threshold. Email
clients treat a new message in an archived thread as new mail. Decide deliberately: most likely "a re-like means keep"
when the song was already sorted *by SpotiSort* earlier (the journal knows).

### Things SpotiSort already does better than email and should keep
- A too-young match **blocks** instead of leaking into a broader later rule (decision 2). Email rules have no age gate
  per rule; this is the right call.
- Journal-before-remove, verify-after, reconcile by id sets, and restore.
- An explain trace per item, shadowed/dead rule detection, and precision per signal with gating of weak signals.

---

## Suggested order
1. P1-2 inbox start date → P1-1 scheduled apply → P1-3 abort logging (these three together unlock "an inbox that sorts itself").
2. P1-4 privacy of committed logs, P1-5/P1-6 token fixes.
3. Q1 `artist_in_playlist` (biggest coverage win), Q6 catch-all, Q3 unmatched queue.
4. P1-7 guardian wording/baseline, then P2 docs drift and the rest.
5. Q2, Q4, Q5, Q7–Q9 as schema additions. Each is a deliberate schema change, so it needs master sign-off and Python/JS parity tests.
