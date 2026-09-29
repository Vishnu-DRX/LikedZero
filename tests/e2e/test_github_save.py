"""Browser tests for Configure's "Save to GitHub" (Phase 7). Run: python -m pytest tests/e2e -q -m e2e

Served under a fake `someoneelse.github.io/their-fork/` origin via `serve_fake_origin` (conftest.py) so the
save target is genuinely derived from `location`, not mocked -- the same technique the required decision-41
fork-genericness test uses.
"""

from __future__ import annotations

import base64
import json

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from conftest import serve_fake_origin  # noqa: E402
from test_builder import add_chips, add_rule, goto_review, start_blank  # noqa: E402

pytestmark = pytest.mark.e2e

ORIGIN = "https://someoneelse.github.io"
BASE_PATH = "/their-fork/"
OWNER, REPO = "someoneelse", "their-fork"


def open_fork_builder(page):
    serve_fake_origin(page, ORIGIN, BASE_PATH)
    page.goto(f"{ORIGIN}{BASE_PATH}builder/")
    page.wait_for_function("window.__spotiBuilder && window.__spotiBuilder.ready")


def draft_a_rule(page):
    start_blank(page)
    add_chips(add_rule(page, "Chill", "Chill Vault"), "genre_contains", "chill")
    goto_review(page)


def b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def test_save_to_github_button_offers_deep_link_scoped_to_this_fork(make_page, site):
    page, _ = make_page()
    open_fork_builder(page)
    draft_a_rule(page)
    page.get_by_role("button", name="Save to GitHub").click()
    expect(page.locator("#github-save-dialog")).to_be_visible()
    href = page.locator("#github-save-body a").first.get_attribute("href")
    assert href.startswith("https://github.com/settings/personal-access-tokens/new?")
    assert f"target_name={OWNER}" in href and "contents=write" in href
    # Master decisions 15 (2026-09-29): Configure now requests the same union of scopes run-now does, so the
    # one token this deep link creates also covers dispatching the Sync workflow.
    assert "actions=write" in href
    assert "expires_in=7" in href  # P1-6: 7-day default, not 90


def test_save_to_github_verify_rejects_a_read_only_token(make_page, site):
    """P1-5/P1-6: GET /repos/{o}/{r} alone proves almost nothing about a token's actual scope on a public
    repo; verify() must check the real granted permission (permissions.push) before trusting it."""
    page, _ = make_page()
    open_fork_builder(page)
    draft_a_rule(page)
    page.get_by_role("button", name="Save to GitHub").click()
    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"permissions": {"push": False}})))
    page.locator("#gh-token").fill("github_pat_read_only_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("text=no write access")
    expect(page.locator("#gh-token")).to_be_visible()


def test_save_to_github_reuses_run_now_token(make_page, site):
    """Master decisions 15 (2026-09-29): supersedes P1-5's deliberate separation. run-now's Contents+Actions
    token and Configure's own (now identical) scope request share one sessionStorage slot keyed by owner/repo
    alone, so connecting via either entry point covers the other. Simulate run-now having already connected in
    this tab, then prove Configure skips straight to its own commit form instead of asking to reconnect."""
    page, _ = make_page()
    open_fork_builder(page)
    draft_a_rule(page)
    page.evaluate(
        "window.GithubPAT.set('someoneelse', 'their-fork', [{name:'contents',level:'write'},{name:'actions',level:'write'}], 'github_pat_run_now_token')"
    )
    page.get_by_role("button", name="Save to GitHub").click()
    expect(page.locator("#gh-commit-msg")).to_be_visible()
    expect(page.locator("#gh-token")).to_have_count(0)


def test_not_on_pages_shows_a_clear_message_instead_of_guessing(make_page, site):
    page, _ = make_page()
    page.goto(site + "builder/")  # 127.0.0.1 host: no owner/repo can be derived
    page.wait_for_function("window.__spotiBuilder && window.__spotiBuilder.ready")
    draft_a_rule(page)
    page.get_by_role("button", name="Save to GitHub").click()
    expect(page.locator("#github-save-dialog")).to_be_visible()
    assert "GitHub Pages" in page.locator("#github-save-body").inner_text()


def test_connect_verify_commit_first_time_creates_the_file(make_page, site):
    page, _ = make_page()
    open_fork_builder(page)
    draft_a_rule(page)
    yaml_text = page.locator("#yaml-out code").text_content()

    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"permissions": {"push": True}})))
    # Master decisions 15: verify() now also checks Actions access, since Configure requests the same
    # Contents+Actions union of scopes run-now does.
    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"workflows": []})))
    page.get_by_role("button", name="Save to GitHub").click()
    page.locator("#gh-token").fill("github_pat_fake_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("#gh-commit-msg")

    puts = []

    def handle_contents(route):
        if route.request.method == "GET":
            route.fulfill(status=404, content_type="application/json", body="{}")
            return
        body = json.loads(route.request.post_data)
        puts.append(body)
        route.fulfill(status=201, content_type="application/json",
                      body=json.dumps({"content": {"sha": "newsha123"}, "commit": {"sha": "c1", "html_url": "https://github.com/x"}}))

    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}/contents/config.yaml", handle_contents)
    page.get_by_role("button", name="Commit").click()
    page.wait_for_selector("text=Saved to GitHub")

    assert len(puts) == 1
    assert puts[0]["message"] == "Update config.yaml via Configure"
    assert "sha" not in puts[0]  # first-time create: no sha
    assert base64.b64decode(puts[0]["content"]).decode("utf-8") == yaml_text
    # decision 46/P2: no explicit branch -- GitHub commits to the repo's real default branch on its own,
    # so a fork whose default branch isn't "main" is never written to the wrong place.
    assert "branch" not in puts[0]


def test_conflict_shows_diff_and_never_silently_overwrites(make_page, site):
    page, _ = make_page()
    open_fork_builder(page)
    draft_a_rule(page)

    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"permissions": {"push": True}})))
    # Master decisions 15: verify() now also checks Actions access, since Configure requests the same
    # Contents+Actions union of scopes run-now does.
    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"workflows": []})))
    page.get_by_role("button", name="Save to GitHub").click()
    page.locator("#gh-token").fill("github_pat_fake_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("#gh-commit-msg")

    # Simulates a genuine race: someone else's commit lands between this client's own pre-commit GET and its
    # PUT, so the first PUT 409s with "sha-v1" even though the client sent the sha it had just fetched. The
    # conflict view's own re-fetch then sees the new "sha-v2" + the other person's content; the "Overwrite"
    # retry must use THAT sha (not silently retry the stale one), which is what would actually succeed.
    remote_yaml = "default_days_threshold: 99\nrules: []\n"
    state = {"sha": "sha-v1", "puts": 0}

    def handle_contents(route):
        if route.request.method == "GET":
            route.fulfill(status=200, content_type="application/json",
                           body=json.dumps({"sha": state["sha"], "content": b64(remote_yaml)}))
            return
        state["puts"] += 1
        body = json.loads(route.request.post_data)
        if state["puts"] == 1:
            state["sha"] = "sha-v2"  # the "other" commit that caused the conflict
            route.fulfill(status=409, content_type="application/json", body=json.dumps({"message": "sha mismatch"}))
            return
        assert body.get("sha") == "sha-v2", "overwrite must use the freshly re-fetched sha, not the stale one"
        state["applied"] = body
        route.fulfill(status=201, content_type="application/json", body=json.dumps({"content": {"sha": "sha-v3"}, "commit": {}}))

    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}/contents/config.yaml", handle_contents)
    page.get_by_role("button", name="Commit").click()

    page.wait_for_selector("text=changed config.yaml on GitHub")
    assert "99" in page.locator("#github-save-body pre.yaml").inner_text()  # the remote content is shown, not hidden

    page.get_by_role("button", name="Overwrite GitHub's version with mine").click()
    page.wait_for_selector("text=Saved to GitHub")
    assert state.get("applied") is not None


def test_versions_drawer_shows_github_commits_labelled_separately(make_page, site):
    page, _ = make_page()
    open_fork_builder(page)
    draft_a_rule(page)

    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"permissions": {"push": True}})))
    # Master decisions 15: verify() now also checks Actions access, since Configure requests the same
    # Contents+Actions union of scopes run-now does.
    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"workflows": []})))
    page.get_by_role("button", name="Save to GitHub").click()
    page.locator("#gh-token").fill("github_pat_fake_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("#gh-commit-msg")
    page.locator("#github-save-dialog [data-close]").first.click()

    commits = [
        {"sha": "aaa111", "commit": {"message": "Update config.yaml via Configure", "author": {"date": "2026-09-20T10:00:00Z"}}},
    ]
    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}/commits*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(commits)))

    page.get_by_role("button", name="Versions").click()
    expect(page.locator("#versions-drawer")).to_be_visible()
    page.wait_for_selector('#versions-github-list li:has-text("Update config.yaml via Configure")')
    assert "Saved locally" in page.locator("#versions-drawer").inner_text()
    assert "On GitHub" in page.locator("#versions-drawer").inner_text()
