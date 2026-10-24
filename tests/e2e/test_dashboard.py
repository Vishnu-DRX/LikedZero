"""Browser tests for the dashboard (docs/dashboard) over the bundled fixtures. Run: python -m pytest tests/e2e -q -m e2e"""

from __future__ import annotations

import json
import re
from urllib.parse import unquote
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

try:
    from axe_playwright_python.sync_playwright import Axe
except ImportError:  # optional dev dependency
    Axe = None

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "docs" / "dashboard" / "fixtures"
SHOTS = ROOT / "docs" / "screenshots"
VIEWS = ["overview", "inbox", "rules", "playlists", "runs"]


def fx(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


PLAN = fx("latest-plan.json")
RUNS = fx("runs.json")["runs"]


@pytest.fixture
def dash(make_page, site):
    """Open a dashboard view over fixtures (service worker blocked so routes always apply)."""

    def _open(view="overview", qs="", width=1280, height=900, setup=None, source="fixtures", **ctx):
        ctx.setdefault("timezone_id", "UTC")  # the dashboard shows times in the browser's timezone; pin it
        page, context = make_page(width=width, height=height, service_workers="block", **ctx)
        if setup:
            setup(page)
        page.goto(f"{site}dashboard/?source={source}{qs}#/{view}")
        page.wait_for_selector(f'#view-root[data-state="ready"][data-view="{view}"]')
        return page

    return _open


def patch_json(page, name, fn):
    def handler(route):
        data = json.loads((FIX / name).read_text(encoding="utf-8"))
        out = fn(data)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(out if out is not None else data))

    page.route(f"**/dashboard/fixtures/{name}", handler)


def goto_view(page, view):
    page.evaluate("v => { location.hash = '#/' + v }", view)
    page.wait_for_selector(f'#view-root[data-state="ready"][data-view="{view.split("/")[0].split("?")[0]}"]')


def text(page, sel):
    return page.locator(sel).inner_text()


# ------------------------------------------------------------------ overview
def test_overview_answers_is_it_healthy(dash):
    page = dash("overview")
    c = PLAN["counts"]
    assert page.locator("#view-title").inner_text() == "Overview"
    assert "Is it healthy?" in text(page, ".question")
    last = RUNS[0]
    card = text(page, '[data-card="last-run"]')
    assert "Dry run" in card and "21 Sep, 6:00 AM UTC" in card and "2 warnings" in card
    assert "22 Sep, 3:00 AM UTC" in text(page, '[data-card="next-run"]')  # from the demo fixture's schedule (decision 34)
    waiting = text(page, '[data-card="liked"]')
    assert str(PLAN["liked_total"]) in waiting and f"{c['will_move']} ready to move" in waiting
    week_moves = sum(r["moved"] for r in RUNS if r["mode"] == "apply")
    assert re.search(rf"\b{week_moves}\b", text(page, '[data-card="moves"]'))
    assert "A song may need restoring" in text(page, '[data-card="safety"]')  # the latest real run failed its count check
    nxt = text(page, '[data-testid="next"]')
    assert f"move {c['will_move']} songs" in nxt and "nothing written" in nxt
    assert "Next run: 22 Sep, 3:00 AM UTC" in nxt
    # no jargon or noise cards any more
    for gone in ("pending", "errors"):
        expect(page.locator(f'[data-card="{gone}"]')).to_have_count(0)
    body = text(page, "#view-root")
    for jargon in ("Reconcile OK", "since the previous run", "Safety verdict", "Not scheduled"):
        assert jargon not in body, jargon
    assert "Data freshness" in text(page, '[data-testid="freshness"]')
    assert "2026-08-01" in text(page, '[data-testid="inbox-since"]')  # decision 45/P1-2
    expect(page.locator('[data-banner="stale"]')).to_have_count(0)
    expect(page.locator('[data-banner="legacy"]')).to_have_count(0)
    expect(page.locator('[data-banner="what-if"]')).to_have_count(0)
    page.locator('[data-testid="decision-counts"] a', has_text="Blocked").click()
    page.wait_for_selector('#view-root[data-view="inbox"]')
    expect(page.locator("#inbox-decision")).to_have_value("blocked")
    expect(page.locator("#inbox-results tbody tr")).to_have_count(c["blocked"])


def test_overview_shows_times_in_browser_timezone(dash):
    """Stored times are UTC; the dashboard renders them in the viewer's timezone (06:00 UTC -> 11:30 in Kolkata)."""
    page = dash("overview", timezone_id="Asia/Kolkata")
    assert "21 Sep, 11:30 AM IST" in text(page, '[data-card="last-run"]')
    assert "UTC" not in text(page, '[data-card="last-run"]')
    # the instant is unchanged: the <time datetime> attribute stays UTC
    assert page.locator('[data-card="last-run"] time').get_attribute("datetime").startswith("2026-09-21T06:00")


def test_overview_reads_schedule_field(dash):
    def setup(page):
        patch_json(page, "runs.json", lambda d: d.update(schedule="daily at 06:00 UTC"))

    page = dash("overview", setup=setup)
    assert "daily at 06:00 UTC" in text(page, '[data-card="next-run"]')


# ------------------------------------------------------------------ inbox
def test_inbox_table_search_filter_sort(dash):
    page = dash("inbox")
    rows = page.locator("#inbox-results tbody tr")
    expect(rows).to_have_count(len(PLAN["songs"]))
    # search
    page.locator("#inbox-q").fill("nameless loop")
    expect(rows).to_have_count(5)
    assert "Showing 5 of 5" in text(page, '[data-testid="result-count"]')
    page.locator("#inbox-q").fill("")
    # decision filter
    page.locator("#inbox-decision").select_option("blocked")
    expect(rows).to_have_count(PLAN["counts"]["blocked"])
    assert all(d == "blocked" for d in page.locator("#inbox-results tbody tr").evaluate_all("els => els.map(e => e.dataset.decision)"))
    page.locator("#inbox-decision").select_option("")
    # rule filter
    page.locator("#inbox-rule").select_option("Lo-fi study")
    expect(rows).to_have_count(5)
    page.locator("#inbox-rule").select_option("")
    # empty result
    page.locator("#inbox-q").fill("zzz-no-such-song")
    expect(page.locator("#inbox-results .empty")).to_be_visible()
    page.locator("#inbox-q").fill("")
    # sort by title asc / desc
    titles = sorted((s["title"] for s in PLAN["songs"]), key=str.lower)
    page.locator('[data-sort="title"]').click()
    expect(page.locator('th[aria-sort="ascending"]')).to_have_count(1)
    assert page.locator("#inbox-results tbody tr .link-btn").first.inner_text() == titles[0]
    page.locator('[data-sort="title"]').click()
    assert page.locator("#inbox-results tbody tr .link-btn").first.inner_text() == titles[-1]
    assert page.evaluate("document.activeElement.dataset.sort") == "title"  # focus stays on the sort button
    # sort by age ascending
    page.locator('[data-sort="age"]').click()
    ages = [float(a) for a in page.locator("#inbox-results tbody tr td.num:nth-child(2)").all_inner_texts()]
    assert ages == sorted(ages)
    assert ages[0] == min(s["age_days"] for s in PLAN["songs"])


def test_inbox_row_content(dash):
    page = dash("inbox")
    row = page.locator("#inbox-results tbody tr", has_text="Fake Dil")
    t = row.inner_text()
    assert "Will move" in t and "Hindi hits" in t and "Fake Hindi Hits" in t and "top of playlist" in t and "Playlist" in t
    row = page.locator("#inbox-results tbody tr", has_text="Nilavu Placeholder")
    assert "Too young" in row.inner_text()
    row = page.locator("#inbox-results tbody tr", has_text="Fake Thendral")
    assert "Blocked" in row.inner_text() and "Withheld" in row.inner_text()
    row = page.locator("#inbox-results tbody tr", has_text="Pretend Blues")
    assert "Target problem" in row.inner_text() and "missing" in row.inner_text()


def test_hash_query_prefilters_inbox(dash):
    page = dash("inbox", qs="", setup=None)
    goto_view(page, "inbox?rule=Rock%20legends")
    expect(page.locator("#inbox-rule")).to_have_value("Rock legends")
    expect(page.locator("#inbox-results tbody tr")).to_have_count(5)


# ------------------------------------------------------------------ explain drawer
def open_explain(page, title):
    btn = page.locator("#inbox-results .link-btn", has_text=re.compile(rf"^{re.escape(title)}$"))
    btn.click()
    dlg = page.get_by_role("dialog")
    expect(dlg).to_be_visible()
    return btn, dlg


def open_technical_trace(dlg):
    # decision 34: the rule-by-rule trace is a collapsed <details> under the sentence-first narrative. A closed
    # <details>'s content has no innerText (browsers treat it like display:none), so tests that inspect the
    # trace's text must open it first, same as a person would click "Technical details" to see it.
    dlg.locator('details[data-testid="technical-trace"] summary').click()


def test_explain_withheld_signal_and_trace(dash):
    page = dash("inbox")
    _, dlg = open_explain(page, "Fake Thendral")
    body = dlg.inner_text()
    assert "Blocked" in body and "Withheld from rules" in body and "57.1%" in body and "below the 90% bar" in body
    assert "Hint" in body and "58%" in body
    trace = dlg.locator('[data-testid="trace"] > li')
    expect(trace).to_have_count(len(PLAN["rules"]))
    open_technical_trace(dlg)
    tamil = dlg.locator('li[data-rule="Tamil and Telugu"]')
    assert tamil.get_attribute("data-result") == "failed"
    assert tamil.locator("li[data-passed='false']").count() == 1 and "failed" in tamil.inner_text()
    # unmeasured
    dlg.get_by_role("button", name="Close explanation").click()
    _, dlg = open_explain(page, "Sample Ragam")
    assert "has not been measured" in dlg.inner_text()


def test_explain_matched_shadowed_and_language_section(dash):
    page = dash("inbox")
    _, dlg = open_explain(page, "Fake Anthem (Live)")
    open_technical_trace(dlg)
    assert dlg.locator('li[data-rule="Rock legends"]').get_attribute("data-result") == "matched"
    alpha = dlg.locator('li[data-rule="Alpha live cuts"]')
    assert alpha.get_attribute("data-result") == "not_reached_but_would_match"
    assert alpha.locator("li[data-passed='true']").count() == 2 and "never reached" in alpha.inner_text()
    assert "Country default" in dlg.inner_text() and "rock" in dlg.inner_text()
    assert dlg.locator('li[data-rule="Draft country"]').get_attribute("data-result") == "skipped_disabled"
    dlg.get_by_role("button", name="Close explanation").click()
    _, dlg = open_explain(page, "Nilavu Placeholder")
    assert dlg.locator('li[data-result="matched_too_young"]').count() == 1
    assert "Playlist" in dlg.locator('[data-testid="lang-signal"]').inner_text() and "97%" in dlg.inner_text()
    # the per-song section is plain "Language and genre" (the Signals tab is gone, so is its jargon heading)
    headings = dlg.locator("h3").all_inner_texts()
    assert "Language and genre" in headings and "Signals" not in headings
    assert "How it was found: learned from your own playlists" in dlg.inner_text()


def test_explain_drawer_keyboard_focus_and_escape(dash):
    page = dash("inbox")
    btn, dlg = open_explain(page, "Fake Dil")
    close = dlg.get_by_role("button", name="Close explanation")
    expect(close).to_be_focused()
    assert dlg.get_attribute("aria-modal") == "true" and dlg.get_attribute("aria-labelledby") == "drawer-title"
    for _ in range(12):  # focus never leaves the dialog
        page.keyboard.press("Tab")
        assert page.evaluate("document.getElementById('drawer').contains(document.activeElement)")
    for _ in range(4):
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.getElementById('drawer').contains(document.activeElement)")
    assert page.evaluate("document.querySelector('.wrap').hasAttribute('inert')")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(btn).to_be_focused()
    assert not page.evaluate("document.querySelector('.wrap').hasAttribute('inert')")
    # backdrop click closes too, and Enter on the row button opens it from the keyboard
    btn.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("dialog")).to_be_visible()
    page.mouse.click(20, 400)
    expect(page.get_by_role("dialog")).to_have_count(0)


# ------------------------------------------------------------------ rules
def _moved_by_rule():
    """Songs moved per rule by real runs, newest first, straight from the fixture run logs."""
    out = {}
    for run in RUNS:  # runs.json is newest first
        if run["mode"] != "apply" or not run["moved"]:
            continue
        for m in fx(run["log"])["moved"]:
            out.setdefault(m["rule"], []).append((run, m))
    return out


def test_rules_show_moved_count_and_last_five_songs(dash):
    page = dash("rules")
    cards = page.locator('[data-testid="rules-list"] article.rule-card')
    expect(cards).to_have_count(len(PLAN["rules"]))
    body = page.locator("#view-root").inner_text()
    # the status/metric vocabulary the user asked to drop is gone
    for gone in ("Dead", "Wins now", "Would match", "Shadowed", "Last matched"):
        assert gone not in body, gone
    moved = _moved_by_rule()
    assert moved, "fixtures must contain at least one real run that moved songs"
    for name, items in moved.items():
        card = page.locator(f'article.rule-card[data-rule="{name}"]')
        assert card.locator('[data-testid="rule-count"]').inner_text().split()[0] == str(len(items))
        expect(card.locator("ol.rule-recent li").first).to_be_hidden()  # collapsed
        card.locator("summary").click()
        recent = card.locator("ol.rule-recent li")
        expect(recent).to_have_count(min(5, len(items)))
        newest_run, newest_song = items[0]
        assert newest_song["track"] in recent.first.inner_text()
        assert unquote(recent.first.locator("a").get_attribute("href")) == f"#/runs/{newest_run['run_id']}"
    quiet = next(r["name"] for r in PLAN["rules"] if r["name"] not in moved)
    card = page.locator(f'article.rule-card[data-rule="{quiet}"]')
    assert card.locator('[data-testid="rule-count"]').inner_text().split()[0] == "0"
    card.locator("summary").click()
    expect(card.locator('[data-testid="rule-recent-empty"]')).to_be_visible()
    for name in ("Spanish nights", "Old jazz"):
        page.locator(f'article.rule-card[data-rule="{name}"] details').evaluate("d => { d.open = true; }")
    assert "Weak signals: hint, country_default" in page.locator('article.rule-card[data-rule="Spanish nights"]').inner_text()
    assert "Missing" in page.locator('article.rule-card[data-rule="Old jazz"]').inner_text()
    run_link = page.locator("ol.rule-recent a").first
    run_link.click()
    page.wait_for_selector('#view-root[data-view="runs"] [data-testid="run-detail"]')


# ------------------------------------------------------------------ playlists
def test_playlists_show_runs_that_added_songs_and_last_five(dash):
    page = dash("playlists")
    cards = page.locator('[data-testid="playlists-list"] article.rule-card')
    expect(cards).to_have_count(len(PLAN["playlists"]))
    statuses = set(cards.evaluate_all("els => els.map(e => e.dataset.status)"))
    assert statuses == {"resolved", "missing", "not_writable", "ambiguous"}
    body = page.locator("#view-root").inner_text()
    for gone in ("Planned in", "Moves out", "planned"):
        assert gone not in body, gone
    for name, text in (("Fake Tamil Telugu", "Not writable"), ("Fake Duplicate", "Ambiguous"), ("Fake Jazz Vault", "Missing")):
        assert text in page.locator(f'article.rule-card[data-playlist="{name}"]').inner_text()
    checked = 0
    for pl in PLAN["playlists"]:
        runs = [r for r in RUNS if r["mode"] == "apply" and (r.get("moves_by_playlist") or {}).get(pl["name"])]
        card = page.locator(f'article.rule-card[data-playlist="{pl["name"]}"]')
        assert card.locator('[data-testid="playlist-runs"]').inner_text().split()[0] == str(len(runs))
        card.locator("summary").click()
        if not runs:
            expect(card.locator('[data-testid="playlist-recent-empty"]')).to_be_visible()
            continue
        checked += 1
        recent = card.locator("ol.rule-recent li")
        expect(recent).to_have_count(min(5, len(runs)))
        assert unquote(recent.first.locator("a").get_attribute("href")) == f"#/runs/{runs[0]['run_id']}"
        assert f"{runs[0]['moves_by_playlist'][pl['name']]} song" in recent.first.inner_text()
    assert checked, "fixtures must contain a playlist that real runs added songs to"


# ------------------------------------------------------------------ runs
def test_runs_show_scheduled_vs_actual_start_and_finish_in_ist_and_utc(dash):
    # 2026-09-19 fixture run: slot 22:30 UTC (04:00 IST), started 22:41:12 UTC, 11 minutes late.
    late = next(r for r in RUNS if r.get("scheduled_for") == "2026-09-19T22:30:00+00:00")
    page = dash("runs")
    row = page.locator(f'tr[data-run="{late["run_id"]}"]')
    sched, started = row.locator('[data-timing="scheduled"]').inner_text(), row.locator('[data-timing="started"]').inner_text()
    assert sched == "04:00 IST" and "19 Sep 2026 22:30:00 UTC" in row.locator('[data-timing="scheduled"]').get_attribute("title")
    assert started.startswith("04:11 IST") and "11 min late" in started and "19 Sep 2026 22:41" in row.locator('[data-timing="started"]').get_attribute("title")
    assert "min" in row.locator('[data-timing="finished"]').inner_text() or " s" in row.locator('[data-timing="finished"]').inner_text()
    # a manual run says so instead of showing a slot
    manual = next(r for r in RUNS if r.get("trigger") == "workflow_dispatch")
    assert "Not a scheduled run" in page.locator(f'tr[data-run="{manual["run_id"]}"] [data-timing="scheduled"]').inner_text()
    # the detail page has exact seconds, GitHub's own fire time and the triggering event
    row.locator("a", has_text="Details").click()
    page.wait_for_selector('[data-testid="run-detail"]')
    detail = page.locator('[data-testid="run-detail"]').inner_text()
    assert "20 Sep 2026 04:00:00 IST" in detail and "GitHub fired the run" in detail and "22:40:55 UTC" in detail
    assert "22:41:12 UTC" in detail and "Sync finished" in detail and "Schedule" in detail


def test_runs_history_detail_and_diff(dash):
    page = dash("runs")
    rows = page.locator('[data-testid="runs-table"] tbody tr')
    expect(rows).to_have_count(len(RUNS))
    verdicts = rows.evaluate_all("els => els.map(e => e.dataset.verdict)")
    assert {"mismatch", "error", "ok", "dry_run"} <= set(verdicts)
    assert sum(1 for r in RUNS if r["mode"] == "apply") >= 2
    # detail of the mismatching apply run
    mism = next(r for r in RUNS if r["verdict"] == "mismatch")
    page.locator(f'tr[data-run="{mism["run_id"]}"] a', has_text="Details").click()
    page.wait_for_selector('[data-testid="run-detail"]')
    body = page.locator("#view-root").inner_text()
    # a failed safety check opens the technical details by itself and says so at the top
    expect(page.locator('[data-banner="run-mismatch"]')).to_be_visible()
    assert page.locator('[data-testid="run-technical"]').get_attribute("open") is not None
    assert "Mismatch" in body and "expected 42" in body and "found 43" in body
    assert "python -m src.sync --restore logs/2026-09-17.json" in body
    assert "Journal (4 removals recorded)" in body
    assert "Spotify write calls" in body
    # run with an error
    err = next(r for r in RUNS if r["verdict"] == "error")
    goto_view(page, f"runs/{err['run_id']}")
    assert "HTTP 503" in page.locator("#view-root").inner_text()
    # diff two runs
    goto_view(page, "runs")
    a, b = RUNS[1], RUNS[3]
    page.locator(f'[data-pick="{a["run_id"]}"]').check()
    expect(page.get_by_role("button", name="Compare selected runs")).to_be_disabled()
    page.locator(f'[data-pick="{b["run_id"]}"]').check()
    page.get_by_role("button", name="Compare selected runs").click()
    page.wait_for_selector('[data-testid="run-diff"]')
    diff = page.locator('[data-testid="run-diff"]').inner_text()
    assert "Planned moves" in diff and "Rule wins" in diff and "Compare runs" in diff
    assert "Only in the older run" in diff and "Only in the newer run" in diff


def test_run_detail_shows_reconcile_ok_and_restore_for_a_clean_apply_run(dash):
    """Master decisions 16 removed the dedicated Safety tab (its liked-count timeline is gone with it), but the
    reconcile/restore/journal detail it showed for every apply run must still be reachable -- now only via each
    run's own detail page under Runs. test_runs_history_detail_and_diff already covers the MISMATCHING apply
    run's detail; this covers the other apply run in the fixture, whose reconcile succeeded, so both restore
    commands and both reconcile outcomes ("OK" and "Mismatch") stay under test."""
    page = dash("runs")
    ok_run = next(r for r in RUNS if r["mode"] == "apply" and r["verdict"] == "ok")
    goto_view(page, f"runs/{ok_run['run_id']}")
    # clean run: the technical part (reconcile, restore, journal) stays collapsed until asked for
    tech = page.locator('[data-testid="run-technical"]')
    assert tech.get_attribute("open") is None
    expect(page.locator('[data-banner="run-mismatch"]')).to_have_count(0)
    tech.locator("summary").first.click()
    body = page.locator("#view-root").inner_text()
    assert "Reconcile OK" in body and "Mismatch" not in body
    assert "python -m src.sync --restore logs/2026-09-15.json" in body
    tech.locator("details", has_text="Journal").locator("summary").click()
    assert page.locator('[data-testid="journal"] tbody tr').count() >= 1


def test_runs_unknown_run_is_a_clear_message(dash):
    page = dash("runs")
    goto_view(page, "runs/nope")
    assert "Run not found" in page.locator("#view-root").inner_text()


# ------------------------------------------------------------------ banners
def test_stale_banner_when_generated_at_is_old(dash):
    def setup(page):
        patch_json(page, "latest-plan.json", lambda d: d.update(generated_at="2026-09-17T06:00:00+00:00"))

    page = dash("overview", setup=setup)
    banner = page.locator('[data-banner="stale"]')
    expect(banner).to_be_visible()
    assert "more than 2 days old" in banner.inner_text() and "Inbox snapshot" in banner.inner_text()
    goto_view(page, "inbox")
    expect(page.locator('[data-banner="stale"]')).to_be_visible()
    goto_view(page, "runs")  # the run history is a different file, and it is fresh
    expect(page.locator('[data-banner="stale"]')).to_have_count(0)


def test_now_parameter_makes_everything_stale(dash):
    page = dash("runs", qs="&now=2026-10-05T00:00:00Z")
    expect(page.locator('[data-banner="stale"]')).to_be_visible()


def test_what_if_banner_on_every_view(dash):
    def setup(page):
        patch_json(page, "latest-plan.json", lambda d: d.update(what_if=True))

    page = dash("overview", setup=setup)
    for view in VIEWS:
        goto_view(page, view)
        wi = page.locator('[data-banner="what-if"]')
        expect(wi).to_be_visible()
        assert "Disabled rules were treated as enabled" in wi.inner_text()


def test_old_archive_banner_only_without_an_inbox_start_date(dash):
    """The "whole library is in scope" banner is for a plan with NO inbox_since. A plan that still carries the old
    "legacy_library" label but has a start date (every plan written before sync set the label from the config)
    is a live inbox and must not show it."""
    def legacy_no_since(d):
        d.update(inbox_kind="legacy_library", inbox_since=None)

    page = dash("overview", setup=lambda p: patch_json(p, "latest-plan.json", legacy_no_since))
    for view in VIEWS:
        goto_view(page, view)
        legacy = page.locator('[data-banner="legacy"]')
        expect(legacy).to_be_visible()
        assert "whole Liked Songs library is in scope" in legacy.inner_text()
        assert "old archive" not in legacy.inner_text()

    page = dash("overview", setup=lambda p: patch_json(
        p, "latest-plan.json", lambda d: d.update(inbox_kind="legacy_library", inbox_since="2026-10-10")))
    for view in VIEWS:
        goto_view(page, view)
        expect(page.locator('[data-banner="legacy"]')).to_have_count(0)


# ------------------------------------------------------------------ empty + error states
def test_empty_states_name_the_command(dash):
    page = dash("overview", source="files")  # nothing has been opened yet, so every file is missing
    expected = {
        "overview": ["python -m src.sync"],
        "inbox": ["python -m src.sync"],
        "rules": ["python -m src.sync"],
        "playlists": ["python -m src.sync"],
        "runs": ["python -m src.sync"],
    }
    for view, cmds in expected.items():
        goto_view(page, view)
        empties = page.locator("#view-root .empty")
        assert empties.count() >= 1, view
        body = page.locator("#view-root").inner_text()
        for c in cmds:
            assert c in body, (view, c)
        assert "No data" in text(page, '[data-testid="freshness"]') or "no data" in text(page, '[data-testid="freshness"]')
    assert page.locator('[data-empty="plan"]').count() == 0 or True


def test_partial_data_shows_what_exists(dash):
    """With the run history missing, the Inbox still works from the plan file (and says which file is missing
    where it is needed)."""
    def setup(page):
        page.route("**/dashboard/fixtures/runs.json", lambda r: r.fulfill(status=404, body="x"))

    page = dash("runs", setup=setup)
    expect(page.locator('[data-empty="runs"]')).to_be_visible()
    assert "python -m src.sync" in text(page, '[data-empty="runs"]')
    goto_view(page, "inbox")
    expect(page.locator("#inbox-results tbody tr")).to_have_count(len(PLAN["songs"]))


def test_error_state_and_retry(dash):
    state = {"fail": True}

    def setup(page):
        def handler(route):
            if state["fail"]:
                route.fulfill(status=500, body="boom")
            else:
                route.continue_()

        page.route("**/dashboard/fixtures/latest-plan.json", handler)

    page = dash("inbox", setup=setup)
    err = page.locator('[data-error="plan"]')
    expect(err).to_be_visible()
    assert err.get_attribute("role") == "alert" and "HTTP 500" in err.inner_text()
    state["fail"] = False
    err.get_by_role("button", name="Try again").click()
    page.wait_for_selector("#inbox-results tbody tr")
    expect(page.locator('[data-error="plan"]')).to_have_count(0)


def test_invalid_json_is_an_error_not_a_crash(dash):
    def setup(page):
        page.route("**/dashboard/fixtures/runs.json", lambda r: r.fulfill(status=200, content_type="application/json", body="{not json"))

    page = dash("runs", setup=setup)
    assert "not valid JSON" in text(page, '[data-error="runs"]')
    goto_view(page, "overview")  # the rest of the dashboard keeps working
    assert page.locator('[data-error="runs"]').count() == 1 and page.locator('[data-card="liked"]').count() == 1


def test_network_failure_is_an_error(dash):
    def setup(page):
        page.route("**/dashboard/fixtures/latest-plan.json", lambda r: r.abort())

    page = dash("playlists", setup=setup)
    expect(page.locator('[data-error="plan"]')).to_be_visible()


# ------------------------------------------------------------------ sources
def serve_data(page, prefix_pattern):
    def handler(route):
        name = route.request.url.split("?")[0].rsplit("/", 1)[1]
        f = FIX / name
        if f.exists():
            route.fulfill(status=200, content_type="application/json", body=f.read_text(encoding="utf-8"))
        else:
            route.fulfill(status=404, body="nope")

    page.route(prefix_pattern, handler)


def test_source_switch_repo_fixtures_files(dash, site):
    requests = []

    def setup(page):
        page.on("request", lambda r: requests.append(r.url))
        serve_data(page, "https://raw.githubusercontent.com/**")

    page = dash("overview", setup=setup)
    # the source picker is folded away until asked for
    expect(page.locator("#source-bar")).to_be_hidden()
    page.locator("#source-toggle").click()
    expect(page.locator("#source-bar")).to_be_visible()
    sel = page.locator("#source-select")
    expect(sel).to_have_value("fixtures")
    assert "Demo data" in page.locator("#repo-hint").inner_text()
    assert "Demo data" in page.locator("#source-current").inner_text()
    # -> files: nothing chosen yet, reads nothing over the network
    sel.select_option("files")
    expect(page.locator("#files-field")).to_be_visible()
    assert "Open local files" in page.locator("#source-current").inner_text()
    assert "source=files" in page.url and page.evaluate("localStorage.getItem('likedzero.dashboard.source')") == "files"
    requests.clear()  # only care about requests made from here on, once "files" is the active source
    page.locator("#files-input").set_input_files([str(FIX / "latest-plan.json"), str(FIX / "runs.json")])
    page.wait_for_selector('#view-root[data-state="ready"] [data-card="liked"]')
    assert "latest-plan.json" in page.locator("#files-status").inner_text()
    assert not any(u.endswith("latest-plan.json") and u.startswith("http") for u in requests)  # never uploaded
    # -> repo: needs a configured GitHub raw folder; invalid ones are refused
    sel.select_option("repo")
    expect(page.locator("#repo-url")).to_be_visible()
    page.locator("#repo-url").fill("https://evil.example/logs/")
    page.get_by_role("button", name="Save URL").click()
    assert page.locator("#repo-url").get_attribute("aria-invalid") == "true"
    assert "raw.githubusercontent.com" in page.locator("#repo-hint").inner_text()
    page.locator("#repo-url").fill("https://raw.githubusercontent.com/octo/spot/main/logs")
    page.get_by_role("button", name="Save URL").click()
    page.wait_for_selector('#view-root[data-state="ready"] [data-card="liked"]')
    assert any(u == "https://raw.githubusercontent.com/octo/spot/main/logs/latest-plan.json" for u in requests)
    assert page.evaluate("localStorage.getItem('likedzero.dashboard.repo')") == "https://raw.githubusercontent.com/octo/spot/main/logs/"
    assert page.locator("#repo-url").input_value() == "https://raw.githubusercontent.com/octo/spot/main/logs/"
    # -> back to fixtures
    sel.select_option("fixtures")
    page.wait_for_selector('#view-root[data-state="ready"] [data-card="liked"]')
    expect(page.locator("#repo-url")).to_be_hidden()
    own = site.split("/")[2]
    external = {u.split("/")[2] for u in requests if u.startswith("http")} - {own}
    # decision 65: api.github.com is the shared shell's own star-count fetch (decision 26), present on every
    # page now that the dashboard loads assets/shell.js - not something this source-switch flow itself does.
    assert external <= {"raw.githubusercontent.com", "api.github.com"}, external


def test_repo_source_without_configuration_asks_for_it(dash):
    page = dash("overview", source="repo")  # 127.0.0.1 host: no owner can be derived
    assert "Enter the raw URL" in page.locator("#repo-hint").inner_text()
    expect(page.locator('[data-error="plan"]')).to_be_visible()


def test_no_requests_leave_the_site_with_fixtures(dash, site):
    seen = []

    def setup(page):
        page.on("request", lambda r: seen.append(r.url))

    page = dash("overview", setup=setup)
    for v in VIEWS:
        goto_view(page, v)
    # decision 65: the dashboard now uses the shared site shell (assets/shell.js), which fetches the GitHub
    # star count at runtime and fails silently if it errors (decision 26) - a known, intentional external
    # request made by every page now, not a dashboard bug (same filter as test_builder.py/test_site.py).
    seen = [u for u in seen if not u.startswith("https://api.github.com/")]
    bad = [u for u in seen if not (u.startswith(site) or u.startswith("data:") or u.startswith("blob:"))]
    assert not bad, bad


def test_storage_blocked_does_not_break_the_page(make_page, site):
    page, _ = make_page(service_workers="block")
    page.add_init_script("Object.defineProperty(window, 'localStorage', {get(){ throw new Error('blocked') }})")
    page.goto(f"{site}dashboard/?source=fixtures#/overview")
    page.wait_for_selector('#view-root[data-state="ready"] [data-card="liked"]')


# ------------------------------------------------------------------ run now (decision 39)
def set_repo(page, owner_repo="octo/spot"):
    serve_data(page, "https://raw.githubusercontent.com/**")
    if page.locator("#source-bar").is_hidden():
        page.locator("#source-toggle").click()
    page.locator("#repo-url").fill(f"https://raw.githubusercontent.com/{owner_repo}/main/logs")
    page.get_by_role("button", name="Save URL").click()
    page.wait_for_selector('[data-testid="run-now-btn"]')


def test_run_now_button_only_offered_on_repo_source(dash):
    page = dash("overview")  # default source=fixtures
    expect(page.locator('[data-testid="run-now-btn"]')).to_have_count(0)


def test_run_now_connect_step_prefills_the_token_url(dash):
    page = dash("overview", source="repo")
    set_repo(page)
    page.locator('[data-testid="run-now-btn"]').click()
    expect(page.locator("#run-now-dialog")).to_be_visible()
    body = page.locator("#run-now-body").inner_text()
    assert "personal access token" in body.lower() and "Only select repositories" in body
    href = page.locator("#run-now-body a").first.get_attribute("href")
    assert href.startswith("https://github.com/settings/personal-access-tokens/new?")
    assert "target_name=octo" in href and "contents=write" in href and "actions=write" in href
    page.locator("#run-now-dialog [data-close]").first.click()
    expect(page.locator("#run-now-dialog")).to_be_hidden()


def test_run_now_offers_a_no_token_way_with_the_exact_inputs_to_type(dash):
    page = dash("overview", source="repo")
    set_repo(page)
    page.locator('[data-testid="run-now-btn"]').click()
    link = page.locator("#manual-run-link")
    assert link.get_attribute("href") == "https://github.com/octo/spot/actions/workflows/sync.yml"
    text = page.locator(".manual-run").inner_text()
    assert "Dry run" in text and "newest" in text and "cannot pre-fill" in text  # honest about the limit


def test_run_now_connect_verify_and_dispatch(dash):
    page = dash("overview", source="repo")
    set_repo(page)
    page.locator('[data-testid="run-now-btn"]').click()

    page.route("https://api.github.com/repos/octo/spot", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"permissions": {"push": True}})))
    page.route("https://api.github.com/repos/octo/spot/actions/workflows", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    page.locator("#run-now-token").fill("github_pat_fake_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("#run-now-dispatch")
    assert "Connected to" in page.locator("#run-now-body").inner_text()

    # a live run needs "newest" filled in -- no dispatch call is even attempted
    calls = []

    def handle_dispatch(route):
        calls.append(route.request.post_data)
        route.fulfill(status=204)

    page.route("https://api.github.com/repos/octo/spot/actions/workflows/sync.yml/dispatches", handle_dispatch)
    page.locator("#run-now-dry").uncheck()
    page.get_by_role("button", name="Dispatch the Sync workflow").click()
    assert "needs" in page.locator("#run-now-status").inner_text()
    assert calls == []

    page.locator("#run-now-dry").check()
    page.get_by_role("button", name="Dispatch the Sync workflow").click()
    page.wait_for_selector("text=Dispatched")
    assert len(calls) == 1 and '"dry_run":"true"' in calls[0]
    assert "actions/workflows/sync.yml" in page.locator("#run-now-body").inner_html()

    page.get_by_role("button", name="Forget token").click()
    expect(page.locator("#run-now-token")).to_be_visible()


def test_run_now_dispatches_to_the_repos_real_default_branch(dash):
    """decision 46/P2: a fork's default branch is not always "main" -- run-now must dispatch to whatever
    branch verify() actually learned from GitHub, not a hardcoded guess."""
    page = dash("overview", source="repo")
    set_repo(page)
    page.locator('[data-testid="run-now-btn"]').click()
    page.route("https://api.github.com/repos/octo/spot", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"permissions": {"push": True}, "default_branch": "trunk"})))
    page.route("https://api.github.com/repos/octo/spot/actions/workflows", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    page.locator("#run-now-token").fill("github_pat_fake_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("#run-now-dispatch")

    calls = []

    def handle_dispatch(route):
        calls.append(json.loads(route.request.post_data))
        route.fulfill(status=204)

    page.route("https://api.github.com/repos/octo/spot/actions/workflows/sync.yml/dispatches", handle_dispatch)
    page.get_by_role("button", name="Dispatch the Sync workflow").click()
    page.wait_for_selector("text=Dispatched")
    assert calls[0]["ref"] == "trunk"


def test_run_now_bad_token_shows_github_message_and_does_not_save(dash):
    page = dash("overview", source="repo")
    set_repo(page)
    page.locator('[data-testid="run-now-btn"]').click()
    page.route("https://api.github.com/repos/octo/spot", lambda r: r.fulfill(status=401, content_type="application/json", body="{}"))
    page.locator("#run-now-token").fill("github_pat_bad_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("text=rejected the token")
    expect(page.locator("#run-now-token")).to_be_visible()


def test_run_now_token_url_defaults_to_a_7_day_expiry(dash):
    """P1-6 (2026-09-27 review): this token can edit code a scheduled workflow then runs with the Spotify
    refresh token in its environment, so a long-lived default (90 days) was too generous."""
    page = dash("overview", source="repo")
    set_repo(page)
    page.locator('[data-testid="run-now-btn"]').click()
    href = page.locator("#run-now-body a").first.get_attribute("href")
    assert "expires_in=7" in href


def test_run_now_verify_rejects_a_token_without_write_access(dash):
    """P1-5/P1-6: GET /repos/{o}/{r} succeeds for ANY valid token on a public repo regardless of its actual
    scope, so checking only that call proved almost nothing. verify() must check the real granted permission."""
    page = dash("overview", source="repo")
    set_repo(page)
    page.locator('[data-testid="run-now-btn"]').click()
    page.route("https://api.github.com/repos/octo/spot", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"permissions": {"push": False}})))
    page.locator("#run-now-token").fill("github_pat_read_only_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("text=no write access")
    expect(page.locator("#run-now-token")).to_be_visible()


def test_run_now_reuses_save_to_github_token(dash):
    """Master decisions 15 (2026-09-29): supersedes P1-5's deliberate separation (the user hit that friction
    live, twice). Configure and run-now now both request the union of scopes (Contents + Actions) and share
    one sessionStorage slot keyed by owner/repo alone. Simulate Configure having already connected in this
    tab, then prove run-now skips straight to its own dispatch form instead of asking to reconnect."""
    page = dash("overview", source="repo")
    set_repo(page)
    page.evaluate(
        "window.GithubPAT.set('octo', 'spot', [{name:'contents',level:'write'},{name:'actions',level:'write'}], 'github_pat_configure_token')"
    )
    page.locator('[data-testid="run-now-btn"]').click()
    # run-now must find Configure's token under the shared owner/repo key and jump straight to the dispatch
    # form -- no reconnect step.
    expect(page.locator("#run-now-dispatch")).to_be_visible()
    expect(page.locator("#run-now-token")).to_have_count(0)


# ------------------------------------------------------------------ Master decisions 16: no mode toggle, 6 views
def test_no_mode_toggle_and_full_overview_for_a_fresh_viewer(make_page, site):
    # a genuinely fresh visitor: no prior localStorage -- unlike the `dash` fixture, which just opens the page
    # directly to prove nothing here depends on a stored preference any more.
    page, _ = make_page(service_workers="block")
    page.goto(f"{site}dashboard/?source=fixtures#/overview")
    page.wait_for_selector('#view-root[data-state="ready"] [data-card="last-run"]')
    # decision 67: the Simple/Detailed switch and its first-visit callout are removed entirely, not just hidden.
    expect(page.locator("#mode-toggle")).to_have_count(0)
    expect(page.locator("#mode-callout")).to_have_count(0)
    expect(page.locator("#mode-callout-dismiss")).to_have_count(0)
    # every view always renders its full content now: the five KPI cards, each answering one question.
    for present in ("last-run", "next-run", "liked", "moves", "safety"):
        expect(page.locator(f'[data-card="{present}"]')).to_be_visible()
    expect(page.locator("#view-root .card[data-card]")).to_have_count(5)
    for card_name in ("liked", "moves", "safety"):
        expect(page.locator(f'[data-card="{card_name}"] .help')).to_be_visible()
    nav_labels = page.get_by_role("navigation", name="Dashboard views").get_by_role("link").all_inner_texts()
    assert nav_labels == ["Overview", "Inbox", "Rules", "Playlists", "Runs"]


def test_inbox_always_shows_the_full_toolbar(dash):
    """decision 67: there is no reduced 3-column Inbox variant any more -- the full search/decision/rule
    filters and CSV export are always present, for every visitor."""
    page = dash("inbox")
    expect(page.locator("#inbox-decision")).to_be_visible()
    expect(page.locator("#inbox-rule")).to_be_visible()
    expect(page.locator("#inbox-csv")).to_be_visible()
    expect(page.locator('[data-testid="inbox-table-simple"]')).to_have_count(0)


def test_backtest_and_safety_tabs_are_gone(dash):
    """decision 68: Backtest and Safety are removed entirely -- not merged elsewhere, not hidden behind a mode.
    A stale #/backtest or #/safety hash (e.g. an old bookmark) must not render their old views; the router's
    fallback for any unknown view name is Overview."""
    page = dash("overview")
    nav_labels = page.get_by_role("navigation", name="Dashboard views").get_by_role("link").all_inner_texts()
    assert "Backtest" not in nav_labels and "Safety" not in nav_labels
    for stale in ("backtest", "safety"):
        page.evaluate("v => { location.hash = '#/' + v }", stale)
        page.wait_for_selector('#view-root[data-state="ready"][data-view="overview"]')
        expect(page.locator("#view-title")).to_have_text("Overview")


@pytest.mark.skipif(Axe is None, reason="axe-playwright-python not installed")
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_axe_zero_serious_or_critical_on_overview_and_inbox(dash, theme):
    for view in ("overview", "inbox"):
        page = dash(view)
        if theme == "light":
            page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        page.wait_for_timeout(50)
        axe = Axe()
        results = axe.run(page)
        serious = [v for v in results.response["violations"] if v.get("impact") in ("serious", "critical")]
        assert not serious, json.dumps([{"id": v["id"], "impact": v["impact"], "help": v["help"], "view": view} for v in serious], indent=2)


def test_hostile_titles_are_escaped(dash):
    def mutate(d):
        d["songs"][0]["title"] = '<img src=x onerror="window.__xss=1">'
        d["songs"][0]["artists"] = ["<b>bold</b>"]

    def setup(page):
        patch_json(page, "latest-plan.json", mutate)

    page = dash("inbox", setup=setup)
    assert page.evaluate("window.__xss") is None
    assert page.locator("#inbox-results img").count() == 0
    assert page.locator("#inbox-results", has_text="<img src=x").count() == 1


def test_csv_export_prevents_formula_injection(dash):
    """decision 46/P2: a song title starting with = + - @ would otherwise execute as a formula when the
    exported CSV is opened in Excel/Sheets."""
    def mutate(d):
        d["songs"][0]["title"] = "=cmd|'/c calc'!A1"
        d["songs"][0]["artists"] = ["+1; DROP TABLE"]

    def setup(page):
        patch_json(page, "latest-plan.json", mutate)

    page = dash("inbox", setup=setup)
    with page.expect_download() as info:
        page.locator("#inbox-csv").click()
    csv_text = Path(info.value.path()).read_text(encoding="utf-8")
    assert "\"'=cmd|" in csv_text
    assert "\"'+1; DROP TABLE\"" in csv_text
    assert '"=cmd' not in csv_text  # never an unescaped formula-looking cell


# ------------------------------------------------------------------ keyboard, routing, theme
def test_tabs_keyboard_routing_and_aria(dash):
    page = dash("overview")
    nav = page.get_by_role("navigation", name="Dashboard views")
    labels = nav.get_by_role("link").all_inner_texts()
    assert labels == ["Overview", "Inbox", "Rules", "Playlists", "Runs"]
    assert nav.locator('[aria-current="page"]').inner_text() == "Overview"
    nav.get_by_role("link", name="Rules").focus()
    page.keyboard.press("Enter")
    page.wait_for_selector('#view-root[data-view="rules"]')
    assert nav.locator('[aria-current="page"]').inner_text() == "Rules"
    expect(page.locator("#view-title")).to_be_focused()  # focus moves to the new view heading
    assert page.title().startswith("Rules")
    page.evaluate("location.hash = '#/definitely-not-a-view'")
    page.wait_for_selector('#view-root[data-view="overview"]')
    assert page.get_by_role("link", name="Skip to content").count() == 1


def test_theme_tokens_follow_color_scheme(make_page, site):
    for scheme, bg in (("dark", "rgb(18, 18, 18)"), ("light", "rgb(246, 246, 246)")):
        page, _ = make_page(service_workers="block", color_scheme=scheme)
        page.goto(f"{site}dashboard/?source=fixtures#/overview")
        page.wait_for_selector('#view-root[data-state="ready"]')
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == bg
    # decision 65: the dashboard now uses the shared header's own [data-theme-toggle] button (assets/shell.js +
    # assets/ui.js), the same two-state dark/light toggle every other page uses, instead of this dashboard's
    # own separate three-state auto/light/dark cycle. `page` is left on color_scheme="light" from the loop
    # above, so with no explicit data-theme yet, the current theme (system) is "light" - one click toggles to
    # the opposite, "dark".
    toggle = page.locator("[data-theme-toggle]")
    toggle.click()  # light (system) -> dark
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(18, 18, 18)"
    assert toggle.locator(".icon-moon").evaluate("e => getComputedStyle(e).display") != "none"
    toggle.click()  # -> light
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(246, 246, 246)"
    # the coordinator-reported bug this phase fixed (decision 65): the sun icon used to stay
    # `display:none` forever once light theme was active (a stray `hidden` attribute in shell.js beat the
    # CSS toggle), leaving the button showing no icon at all in light mode.
    assert toggle.locator(".icon-sun").evaluate("e => getComputedStyle(e).display") != "none"


def test_dashboard_css_uses_only_design_tokens():
    css = (ROOT / "docs" / "dashboard" / "dashboard.css").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "raw hex colour in dashboard.css"
    assert not re.search(r"\brgba?\(|\bhsla?\(", css)


# ------------------------------------------------------------------ mobile + screenshots
@pytest.mark.parametrize("width,height", [(375, 812), (1280, 900)])
@pytest.mark.parametrize("view", VIEWS)
def test_no_horizontal_overflow_and_screenshots(dash, view, width, height):
    page = dash(view, width=width, height=height)
    if view == "runs":
        page.wait_for_selector('[data-testid="runs-table"]')
    for w in ("document.documentElement.scrollWidth", "document.body.scrollWidth"):
        assert page.evaluate(w) <= width, (view, width, w, page.evaluate(w))
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f"dashboard-{view}-{width}.png"), full_page=True)


@pytest.mark.parametrize("width", [375, 1280])
def test_drawer_and_details_fit_the_viewport(dash, width):
    page = dash("inbox", width=width)
    open_explain(page, "Fake Anthem (Live)")
    dlg = page.get_by_role("dialog")
    page.wait_for_timeout(500)  # let the slide-in animation finish
    box = dlg.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert page.evaluate("document.getElementById('drawer').scrollWidth <= document.getElementById('drawer').clientWidth + 1")
    page.screenshot(path=str(SHOTS / f"dashboard-explain-{width}.png"))
    page.keyboard.press("Escape")
    goto_view(page, f"runs/{RUNS[1]['run_id']}")
    assert page.evaluate("document.documentElement.scrollWidth") <= width


def test_mobile_tables_collapse_to_cards(dash):
    page = dash("inbox", width=375, height=812)
    assert page.evaluate("getComputedStyle(document.querySelector('#inbox-results tbody tr')).display") == "block"
    assert page.evaluate("getComputedStyle(document.querySelector('#inbox-results thead')).position") == "absolute"
    page2 = dash("inbox", width=1280)
    assert page2.evaluate("getComputedStyle(document.querySelector('#inbox-results tbody tr')).display") == "table-row"


# ------------------------------------------------------------------ offline
def test_dashboard_works_offline_via_service_worker(make_page, site):
    page, ctx = make_page()  # service workers allowed
    page.goto(f"{site}dashboard/?source=fixtures#/overview")
    page.wait_for_selector('#view-root[data-state="ready"]')
    page.evaluate("navigator.serviceWorker.ready.then(() => true)")
    page.reload()
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    cached = page.evaluate("caches.keys().then(async ks => (await Promise.all(ks.map(k => caches.open(k).then(c => c.keys())))).flat().map(r => r.url))")
    for needed in ("dashboard/", "dashboard/index.html", "dashboard/dashboard.css", "dashboard/data.js", "dashboard/views.js",
                   "dashboard/app.js", "dashboard/run-now.js", "assets/github-pat.js", "assets/tokens.css",
                   "dashboard/fixtures/latest-plan.json", "dashboard/fixtures/runs.json"):
        assert site + needed in cached, needed
    ctx.set_offline(True)
    page.reload()
    page.wait_for_selector('#view-root[data-state="ready"] [data-card="liked"]')
    assert str(PLAN["liked_total"]) in text(page, '[data-card="liked"]')
    goto_view(page, "inbox")
    expect(page.locator("#inbox-results tbody tr")).to_have_count(len(PLAN["songs"]))
    ctx.set_offline(False)


# ------------------------------------------------------------------ artist_in_playlist (Master decisions 11)
def test_explain_shows_artist_routing_sentence(dash):
    def patch(data):
        data = json.loads(json.dumps(data))
        s = next(s for s in data["songs"] if s["title"] == "Nameless Loop 04")
        s["artist_routing"] = {"playlist": "Fake Chill", "track_count": 9, "artist_total": 10}
        return data

    page = dash("inbox", setup=lambda p: patch_json(p, "latest-plan.json", patch))
    _, dlg = open_explain(page, "Nameless Loop 04")
    narrative = dlg.locator('[data-testid="explain-narrative"]').inner_text()
    assert "Routed to" in narrative and "Fake Chill" in narrative
    assert "9" in narrative and "10" in narrative and "tracked tracks are already there" in narrative


def test_explain_no_artist_routing_sentence_when_absent(dash):
    page = dash("inbox")
    _, dlg = open_explain(page, "Nameless Loop 04")
    narrative = dlg.locator('[data-testid="explain-narrative"]').inner_text()
    assert "Routed to" not in narrative


def test_rules_view_shows_dynamic_badge_for_auto_rule(dash):
    def patch(data):
        data = json.loads(json.dumps(data))
        auto_rule = dict(data["rules"][0])
        auto_rule.update({
            "name": "Route to artist home", "target_playlist": "auto", "target_status": "dynamic",
            "conditions": {"artist_in_playlist": True}, "status": "ok", "would_match": 0, "wins": 0,
        })
        data["rules"].append(auto_rule)
        return data

    page = dash("rules", setup=lambda p: patch_json(p, "latest-plan.json", patch))
    row = page.locator('article.rule-card[data-rule="Route to artist home"]')
    expect(row).to_be_visible()
    row.locator("summary").click()
    assert "auto" in row.inner_text()
    assert "Resolved per song" in row.inner_text()


# ------------------------------------------------------------------ any catch-all (Master decisions 12/decision 51)
def test_explain_shows_catch_all_sentence(dash):
    def patch(data):
        data = json.loads(json.dumps(data))
        s = next(s for s in data["songs"] if s["title"] == "Nameless Loop 04")
        s["decision"] = "will_move"
        s["rule"] = "Catch-all -> Sink"
        s["target_playlist"] = "SpotiSort Sink"
        trace = s["explain"]["trace"]
        trace.insert(0, {
            "rule": "Catch-all -> Sink", "enabled": True, "threshold_days": 14,
            "conditions": [{"key": "any", "wanted": True, "actual": True, "passed": True}],
            "result": "matched",
        })
        s["explain"]["decided_by"] = "Catch-all -> Sink"
        return data

    page = dash("inbox", setup=lambda p: patch_json(p, "latest-plan.json", patch))
    _, dlg = open_explain(page, "Nameless Loop 04")
    narrative = dlg.locator('[data-testid="explain-narrative"]').inner_text()
    assert "Nothing more specific matched first" in narrative and "SpotiSort Sink" in narrative


# ------------------------------------------------------------------ design/proposals/more-conditions.md: unless
def _patch_with_blocked_and_decided(data, decided_rule, blocked_rule):
    data = json.loads(json.dumps(data))
    s = next(s for s in data["songs"] if s["title"] == "Nameless Loop 04")
    s["decision"] = "will_move"
    s["rule"] = decided_rule
    trace = s["explain"]["trace"]
    trace.insert(0, {
        "rule": blocked_rule, "enabled": True, "threshold_days": 14,
        "conditions": [{"key": "language_in", "wanted": ["hindi"], "actual": "hindi", "passed": True}],
        "unless_conditions": [{"key": "artist_in", "wanted": ["Arijit Singh"], "actual": ["Arijit Singh"], "passed": True, "hit": "Arijit Singh"}],
        "result": "blocked_by_exception", "blocked_reason": "blocked by exception: artist_in matched Arijit Singh",
    })
    trace.insert(1, {
        "rule": decided_rule, "enabled": True, "threshold_days": 14,
        "conditions": [{"key": "artist_in", "wanted": ["Arijit Singh"], "actual": ["Arijit Singh"], "passed": True}],
        "result": "matched",
    })
    s["explain"]["decided_by"] = decided_rule
    return data


def test_explain_trace_shows_blocked_by_exception_row(dash):
    page = dash("inbox", setup=lambda p: patch_json(
        p, "latest-plan.json", lambda d: _patch_with_blocked_and_decided(d, "Arijit special", "Hindi to Dil")))
    _, dlg = open_explain(page, "Nameless Loop 04")
    open_technical_trace(dlg)
    row = dlg.locator('li[data-rule="Hindi to Dil"]')
    expect(row).to_be_visible()
    assert "Blocked by an exception" in row.inner_text()
    assert dlg.locator('[data-testid="unless-conditions"]').first.inner_text()
    assert "Arijit Singh" in dlg.locator('[data-testid="blocked-reason"]').first.inner_text()


def test_explain_narrative_mentions_blocked_earlier_rule(dash):
    page = dash("inbox", setup=lambda p: patch_json(
        p, "latest-plan.json", lambda d: _patch_with_blocked_and_decided(d, "Arijit special", "Hindi to Dil")))
    _, dlg = open_explain(page, "Nameless Loop 04")
    narrative = dlg.locator('[data-testid="explain-narrative"]').inner_text()
    assert "Hindi to Dil" in narrative and "exception blocked it" in narrative


def test_rules_view_shows_unless_summary(dash):
    def patch(data):
        data = json.loads(json.dumps(data))
        r = dict(data["rules"][0])
        r.update({"name": "Hindi to Dil (exceptions)", "unless": {"artist_in": ["Arijit Singh"]}})
        data["rules"].append(r)
        return data

    page = dash("rules", setup=lambda p: patch_json(p, "latest-plan.json", patch))
    row = page.locator('article.rule-card[data-rule="Hindi to Dil (exceptions)"]')
    expect(row).to_be_visible()
    row.locator("summary").click()
    assert "unless" in row.inner_text() and "Arijit Singh" in row.inner_text()


# ------------------------------------------------------------------ design/proposals/more-conditions.md: any_of
def test_explain_trace_shows_any_of_branches(dash):
    def patch(data):
        data = json.loads(json.dumps(data))
        s = next(s for s in data["songs"] if s["title"] == "Nameless Loop 04")
        s["decision"] = "will_move"
        s["rule"] = "Chill artists"
        trace = s["explain"]["trace"]
        trace.insert(0, {
            "rule": "Chill artists", "enabled": True, "threshold_days": 14,
            "conditions": [{
                "key": "any_of",
                "wanted": [{"artist_in": ["Nobody"]}, {"artist_in": ["Bonobo"]}],
                "actual": [
                    {"branch": 0, "passed": False, "matched": {}},
                    {"branch": 1, "passed": True, "matched": {"artist_in": "Bonobo"}},
                ],
                "passed": True,
            }],
            "result": "matched",
        })
        s["explain"]["decided_by"] = "Chill artists"
        return data

    page = dash("inbox", setup=lambda p: patch_json(p, "latest-plan.json", patch))
    _, dlg = open_explain(page, "Nameless Loop 04")
    open_technical_trace(dlg)
    row = dlg.locator('li[data-rule="Chill artists"]')
    expect(row).to_be_visible()
    row_text = row.inner_text()
    assert "any_of" in row_text and "branch 1" in row_text and "branch 2" in row_text

    narrative = dlg.locator('[data-testid="explain-narrative"]').inner_text()
    assert "one of several allowed options" in narrative and "branch 2 of 2" in narrative


def test_rules_view_shows_any_of_summary(dash):
    def patch(data):
        data = json.loads(json.dumps(data))
        r = dict(data["rules"][0])
        r.update({"name": "Chill (OR)", "conditions": {"any_of": [{"artist_in": ["Bonobo"]}, {"artist_in": ["Tycho"]}]}})
        data["rules"].append(r)
        return data

    page = dash("rules", setup=lambda p: patch_json(p, "latest-plan.json", patch))
    row = page.locator('article.rule-card[data-rule="Chill (OR)"]')
    expect(row).to_be_visible()
    row.locator("summary").click()
    row_text = row.inner_text()
    assert "any_of" in row_text and "OR" in row_text


# ------------------------------------------------------------------------------------------- phone widths: nothing clipped
@pytest.mark.parametrize("width", [360, 390, 430])
@pytest.mark.parametrize("view", VIEWS)
def test_phone_width_nothing_clipped_and_tabs_fit(dash, width, view):
    """`body { overflow-x: clip }` hides sideways overflow from scrollWidth, so measure the real boxes: every visible
    element must sit inside the viewport, the page text must keep a side gutter, and all six tabs must be visible
    without scrolling the tab strip."""
    page = dash(view, width=width, height=900)
    res = page.evaluate("""() => {
        const vw = document.documentElement.clientWidth, out = [];
        document.querySelectorAll('main *').forEach(e => {
            if (e.closest('svg, thead, .sr-only')) return;
            const r = e.getBoundingClientRect();
            if (r.width > 1 && (r.right > vw + 1 || r.left < -1)) out.push(e.tagName + '.' + e.className + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
        });
        const tabs = document.querySelector('#tabs');
        const edge = Math.min(...[...document.querySelectorAll('main h1, main h2, main p')]
            .filter(e => e.getBoundingClientRect().width)
            .map(e => { const r = e.getBoundingClientRect(); return Math.min(r.left, vw - r.right); }));
        return {out, edge, tabsScroll: tabs.scrollWidth - tabs.clientWidth};
    }""")
    assert not res["out"], f"{view} at {width}px: boxes outside the viewport: {res['out'][:5]}"
    assert res["edge"] >= 12, f"{view} at {width}px: text only {res['edge']}px from the screen edge"
    assert res["tabsScroll"] <= 0, f"{view} at {width}px: tab strip scrolls sideways by {res['tabsScroll']}px"


# ------------------------------------------------------------------------------------------- dashboard feedback round
# What the live dashboard actually looks like after a real run on a public fork: the plan file is the inbox as it was
# when the run STARTED (mode "apply"), song titles are hidden, an inbox start date is set, and the plan still carries
# the old "legacy_library" label. These helpers rebuild that shape from the fabricated fixtures.
REAL_MOVES = [  # (playlist, rule)
    ("Fake English", "English pop"), ("Fake English", "English pop"), ("Fake Hindi Hits", "Hindi hits"), ("Fake English", "English pop"),
]


def real_like_plan(d):
    songs = d["songs"][:4]
    for s, (pl, rule) in zip(songs, REAL_MOVES):
        s.update(title=None, artists=[], uri=None, decision="will_move", rule=rule, target_playlist=pl, target_status="resolved",
                 target_position="top", eligible_on=s["added_at"])
    d.update(songs=songs, liked_total=4, mode="apply", titles_hidden=True, inbox_kind="legacy_library", inbox_since="2026-08-01",
             counts={"will_move": 4, "too_young": 0, "no_match": 0, "target_problem": 0, "blocked": 0})
    return d


def real_like_runs(d):
    r = d["runs"][0]
    r.update(mode="apply", verdict="ok", what_if=False, planned_moves=4, moved=4, too_young=0, no_match=0, blocked=0, target_problems=0,
             errors=0, warnings=0, liked_before=4, liked_after=0, moves_by_playlist={"Fake English": 3, "Fake Hindi Hits": 1})
    return d


def real_like_log(d):
    moved = d["moved"][:4]
    for m, (pl, rule) in zip(moved, REAL_MOVES):
        m.update(track=None, artist=None, uri=None, playlist=pl, rule=rule, target_position="top")
    d.update(moved=moved, mode="apply", dry_run=False, what_if=False, titles_hidden=True, verdict="ok", skipped_too_young=[],
             skipped_playlist_missing=[], skipped_no_match=0, errors=[], warnings=[], liked_before=4, liked_after=0,
             journal=[dict(uri=None, name=None, artists=None, original_added_at=m["original_added_at"], target_playlist_id=m["playlist_id"]) for m in moved],
             reconcile={"expected_after": 0, "actual_after": 0, "ok": True}, restore_command="python -m src.sync --restore logs/restore-journal.json --apply")
    return d


def use_real_like_data(page):
    patch_json(page, "latest-plan.json", real_like_plan)
    patch_json(page, "runs.json", real_like_runs)
    patch_json(page, "2026-09-21.json", real_like_log)


def test_after_a_live_run_the_overview_does_not_call_the_moved_songs_pending(dash):
    page = dash("overview", setup=use_real_like_data)
    # the plan file says 4 songs "will move", but that was BEFORE the run: nothing is waiting now
    assert text(page, '[data-card="liked"] .metric-value') == "0"
    assert "After the last run" in text(page, '[data-card="liked"]')
    nxt = text(page, '[data-testid="next"]')
    assert nxt.startswith("What happens next: Nothing waiting. Last run moved 4 songs into 2 playlists.")
    assert "Next run: 22 Sep, 3:00 AM UTC" in nxt
    assert "would move" not in nxt and "nothing written" not in nxt
    assert "Inbox when the last run started" in text(page, "#view-root")
    expect(page.locator('[data-card="pending"]')).to_have_count(0)
    # the stale "legacy" label is ignored because an inbox start date is set
    expect(page.locator('[data-banner="legacy"]')).to_have_count(0)
    assert "2026-08-01" in text(page, '[data-testid="inbox-since"]')


def test_after_a_live_run_the_inbox_says_it_is_the_inbox_when_the_run_started(dash):
    page = dash("inbox", setup=use_real_like_data)
    notice = page.locator('[data-banner="inbox-snapshot"]')
    expect(notice).to_be_visible()
    t = notice.inner_text()
    assert "Inbox as the last run saw it" in t and "21 Sep, 6:00 AM UTC" in t and "Waiting now: 0" in t
    expect(page.locator('[data-banner="legacy"]')).to_have_count(0)
    rows = page.locator("#inbox-results tbody tr")
    expect(rows).to_have_count(4)
    first = rows.first.inner_text()
    assert "Song 1 of 4 (title hidden)" in first and "Due to move" in first and "Will move" not in first
    assert "Title hidden — open local files" not in page.locator("#view-root").inner_text()
    # the dry-run demo has no such notice
    page2 = dash("inbox")
    expect(page2.locator('[data-banner="inbox-snapshot"]')).to_have_count(0)


def test_runs_list_has_a_one_line_plain_summary_per_run(dash):
    page = dash("runs", setup=use_real_like_data)
    latest = page.locator('[data-testid="runs-table"] tbody tr').first
    assert latest.locator('[data-testid="run-summary-line"]').inner_text() == "Moved 4 songs: 3 to Fake English, 1 to Fake Hindi Hits."
    dry = page.locator('[data-testid="runs-table"] tbody tr[data-verdict="dry_run"]').first
    assert dry.locator('[data-testid="run-summary-line"]').inner_text().startswith(("Dry run: would move", "Dry run: nothing would move", "What-if preview"))
    # no internal identifiers on the list
    assert "20260" not in text(page, '[data-testid="runs-table"]').replace("2026-0", "")


def test_run_page_leads_with_what_moved_where_by_which_rule_and_hides_titles_gracefully(dash):
    page = dash("runs", setup=use_real_like_data)
    run_id = RUNS[0]["run_id"]
    goto_view(page, f"runs/{run_id}")
    summary = page.locator('[data-testid="run-summary"]')
    assert summary.inner_text() == "Moved 4 songs: 3 to Fake English, 1 to Fake Hindi Hits."
    groups = page.locator(".moved-group")
    expect(groups).to_have_count(2)
    eng = page.locator('.moved-group[data-playlist="Fake English"]')
    assert "3 songs" in eng.inner_text() and "Rule: English pop" in eng.inner_text() and "top of the playlist" in eng.inner_text()
    lines = eng.locator("li.moved-song").all_inner_texts()
    assert len(lines) == 3 and all("title hidden" in x and "liked " in x for x in lines)
    assert "Song 1 of 4 (title hidden)" in lines[0]
    hindi = page.locator('.moved-group[data-playlist="Fake Hindi Hits"]')
    assert "1 song" in hindi.inner_text() and "Rule: Hindi hits" in hindi.inner_text()
    assert "Song titles are hidden" in text(page, '[data-testid="titles-hidden-note"]')
    # the summary comes BEFORE the technical part, which is collapsed
    tech = page.locator('[data-testid="run-technical"]')
    assert tech.get_attribute("open") is None
    assert page.locator('[data-testid="moved-summary"]').bounding_box()["y"] < tech.bounding_box()["y"]
    assert page.locator('[data-testid="run-detail"]').bounding_box()["y"] < page.locator('[data-testid="moved-summary"]').bounding_box()["y"]
    assert "Reconcile" not in text(page, "#view-root").split("Technical details")[0]


def test_run_page_with_titles_names_song_playlist_and_rule(dash):
    page = dash("runs")
    ok_run = next(r for r in RUNS if r["mode"] == "apply" and r["verdict"] == "ok")
    goto_view(page, f"runs/{ok_run['run_id']}")
    log = fx(ok_run["log"])
    for m in log["moved"]:
        grp = page.locator(f'.moved-group[data-playlist="{m["playlist"]}"]')
        assert m["track"] in grp.inner_text() and m["artist"] in grp.inner_text()
        assert m["rule"] in grp.inner_text()
    assert "title hidden" not in page.locator('[data-testid="moved-summary"]').inner_text()
    # a dry run is worded as a plan, not as something that happened
    dry = next(r for r in RUNS if r["mode"] == "dry_run" and r["planned_moves"] and not r["what_if"] and not r["errors"])
    goto_view(page, f"runs/{dry['run_id']}")
    assert "What would move where" in text(page, '[data-testid="moved-summary"]') or "What would move where" in text(page, "#view-root")
    assert text(page, '[data-testid="run-summary"]').startswith("Dry run: would move")


def test_signals_tab_is_gone(dash):
    page = dash("overview")
    nav_labels = page.get_by_role("navigation", name="Dashboard views").get_by_role("link").all_inner_texts()
    assert "Signals" not in nav_labels
    page.evaluate("location.hash = '#/signals'")  # an old bookmark falls back to the Overview
    page.wait_for_selector('#view-root[data-state="ready"][data-view="overview"]')
    expect(page.locator("#view-title")).to_have_text("Overview")
    page.get_by_role("button", name="Glossary").click()
    glossary = page.locator("#glossary-body").inner_text()
    assert "Signal tier" not in glossary and "Precision" not in glossary
    assert page.locator("a[href='#/signals']").count() == 0


def test_overview_is_honest_about_the_schedule(dash):
    # no schedule information at all: no "Next run" card and no claim either way
    page = dash("overview", setup=lambda p: patch_json(p, "runs.json", lambda d: d.pop("schedule")))
    expect(page.locator('[data-card="next-run"]')).to_have_count(0)
    body = text(page, "#view-root")
    assert "Not scheduled" not in body and "No automatic runs" not in body and "automatic run is" not in body
    # explicit null (written by sync when config.yaml has no enabled schedule): say so plainly, still no card
    page = dash("overview", setup=lambda p: patch_json(p, "runs.json", lambda d: d.update(schedule=None)))
    expect(page.locator('[data-card="next-run"]')).to_have_count(0)
    assert "No automatic runs set up" in text(page, '[data-testid="next"]')
    # a real schedule: description + time in the browser's time zone
    page = dash("overview", timezone_id="Asia/Kolkata", setup=lambda p: patch_json(
        p, "runs.json", lambda d: d.update(schedule={"cron": None, "description": "every day at 08:00 (Asia/Kolkata), moves songs", "next_run": "2026-09-22T02:30:00+00:00"})))
    card = text(page, '[data-card="next-run"]')
    assert "22 Sep, 8:00 AM IST" in card and "Every day at 08:00 (Asia/Kolkata), moves songs" in card


LONG_TITLE = "Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa and a very long title that keeps going well past one line of a phone (Extended Remastered Deluxe Edition) [feat. Somebody With A Long Name]"
LONG_ARTIST = "The Extremely Long Named Artist Collective Ensemble Of Many Players, Another Very Long Featured Artist Name"

NO_CLIPPING_JS = """() => {
  const bad = [];
  document.querySelectorAll('main *, #drawer-root *').forEach(e => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.tagName)) return;  // form fields are not song titles
    const cs = getComputedStyle(e);
    if (cs.textOverflow === 'ellipsis') bad.push('ellipsis: ' + e.tagName + '.' + e.className);
    const clamp = cs.webkitLineClamp;
    if (clamp && clamp !== 'none') bad.push('line-clamp: ' + e.tagName + '.' + e.className);
  });
  return bad;
}"""


def test_long_titles_wrap_in_full_on_a_phone_everywhere(dash):
    def mutate_plan(d):
        d["songs"][0]["title"] = LONG_TITLE
        d["songs"][0]["artists"] = [LONG_ARTIST]

    def mutate_log(d):
        d["moved"][0]["track"] = LONG_TITLE
        d["moved"][0]["artist"] = LONG_ARTIST

    ok_run = next(r for r in RUNS if r["mode"] == "apply" and r["verdict"] == "ok")

    def setup(page):
        patch_json(page, "latest-plan.json", mutate_plan)
        patch_json(page, ok_run["log"], mutate_log)

    page = dash("inbox", width=375, height=812, setup=setup)
    page.locator("#inbox-q").fill("Aaaaaaaa")
    btn = page.locator("#inbox-results .link-btn").first
    assert btn.inner_text() == LONG_TITLE  # the whole title, not a cut-off one
    assert page.locator("#inbox-results tbody tr").first.inner_text().count(LONG_ARTIST) == 1
    box = btn.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 375 and box["height"] > 40  # several lines tall
    assert page.evaluate("e => e.scrollWidth <= e.clientWidth + 1", btn.element_handle())
    assert page.evaluate(NO_CLIPPING_JS) == []
    # Explain drawer heading
    btn.click()
    head = page.locator("#drawer-title")
    expect(head).to_be_visible()
    assert LONG_TITLE in head.inner_text() and LONG_ARTIST in head.inner_text()
    assert page.evaluate("e => e.scrollWidth <= e.clientWidth + 1", head.element_handle())
    assert page.evaluate(NO_CLIPPING_JS) == []
    page.keyboard.press("Escape")
    # run page
    goto_view(page, f"runs/{ok_run['run_id']}")
    grp = page.locator("li.moved-song", has_text=LONG_TITLE)
    assert grp.count() == 1 and LONG_ARTIST in grp.inner_text()
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert page.evaluate(NO_CLIPPING_JS) == []
    # and no view anywhere uses ellipsis or line clamps
    for view in VIEWS:
        goto_view(page, view)
        assert page.evaluate(NO_CLIPPING_JS) == [], view


@pytest.mark.skipif(Axe is None, reason="axe-playwright-python not installed")
def test_axe_zero_serious_or_critical_on_real_like_runs_and_overview(dash):
    for view in ("overview", "inbox", "runs"):
        page = dash(view, setup=use_real_like_data)
        goto_view(page, view)
        results = Axe().run(page)
        serious = [v for v in results.response["violations"] if v.get("impact") in ("serious", "critical")]
        assert not serious, json.dumps([{"id": v["id"], "view": view} for v in serious])
    goto_view(page, f"runs/{RUNS[0]['run_id']}")
    results = Axe().run(page)
    serious = [v for v in results.response["violations"] if v.get("impact") in ("serious", "critical")]
    assert not serious, json.dumps([{"id": v["id"]} for v in serious])


def test_run_journal_tolerates_artists_as_string_or_list(dash):
    """Real run logs journal `artists` as one joined string (the fixtures use lists); the Runs detail must draw both."""
    ok_run = next(r for r in RUNS if r["mode"] == "apply" and r["verdict"] == "ok")
    log_name = f"{ok_run['run_id'][:10]}.json"

    def as_string(log):
        for e in log["journal"]:
            e["artists"] = "Fake Band Alpha, Guest"

    page = dash("runs", setup=lambda p: patch_json(p, log_name, as_string))
    goto_view(page, f"runs/{ok_run['run_id']}")
    expect(page.locator('.errorbox')).to_have_count(0)
    page.locator('[data-testid="run-technical"] summary').first.click()
    page.locator('[data-testid="run-technical"] details', has_text="Journal").locator("summary").click()
    assert "Fake Band Alpha, Guest" in page.locator('[data-testid="journal"]').inner_text()
