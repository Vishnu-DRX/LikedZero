"""Decision 41 (Master decisions 7, Part A): required proof that every flow works for a stranger's fork,
not just the maintainer's account. Serves the real built site under a SECOND, FAKE origin
(https://someoneelse.github.io/their-fork/) via `serve_fake_origin` (conftest.py) -- Playwright intercepts
the network request, but the navigated URL is genuinely that origin, so `location.hostname`/`pathname`
inside the page are real, not mocked. This is the strongest test available short of an actual second fork.

Run: python -m pytest tests/e2e -q -m e2e
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from conftest import serve_fake_origin  # noqa: E402
from test_builder import add_chips, add_rule, goto_review, start_blank  # noqa: E402

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "docs" / "dashboard" / "fixtures"
ORIGIN = "https://someoneelse.github.io"
BASE_PATH = "/their-fork/"
OWNER, REPO = "someoneelse", "their-fork"


def open_fork_page(page, path):
    serve_fake_origin(page, ORIGIN, BASE_PATH)
    page.goto(f"{ORIGIN}{BASE_PATH}{path}")


def serve_fork_logs(page):
    """Mock raw.githubusercontent.com for THIS fake fork's owner/repo only, from the bundled fixtures."""
    def handler(route):
        name = route.request.url.split("?")[0].rsplit("/", 1)[1]
        f = FIX / name
        if f.exists():
            route.fulfill(status=200, content_type="application/json", body=f.read_text(encoding="utf-8"))
        else:
            route.fulfill(status=404, body="not found")

    page.route(f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/logs/**", handler)


def test_upstream_credit_link_is_unchanged_on_a_fork(make_page, site):
    page, _ = make_page()
    open_fork_page(page, "index.html")
    page.wait_for_selector(".site-footer-links")  # footer only exists after site.config.json resolves
    # the nav "GitHub" link and the footer's "Upstream repository" link both still point at the real
    # canonical repo, never at this fork
    hrefs = page.locator('a[href*="github.com/Vishnu-DRX/SpotiSort"]').all()
    assert len(hrefs) >= 1
    fork_link = page.locator("#site-fork-link")
    expect(fork_link).to_have_attribute("href", f"https://github.com/{OWNER}/{REPO}")
    for a in page.locator('a[href*="github.com"]').all():
        href = a.get_attribute("href")
        if "Vishnu-DRX" in href or href.rstrip("/") == "https://github.com":
            continue
        # the only other github.com link allowed is "Your fork", which must point at THIS fork
        assert f"github.com/{OWNER}/{REPO}" in href, href


def test_repo_mode_reads_from_the_viewers_own_fork(make_page, site):
    page, _ = make_page()
    serve_fake_origin(page, ORIGIN, BASE_PATH)
    serve_fork_logs(page)  # registered BEFORE navigation: the dashboard fetches its data immediately on load
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(f"{ORIGIN}{BASE_PATH}dashboard/?source=repo")
    page.wait_for_selector('#view-root[data-state="ready"] [data-card="pending"]')
    assert any(u == f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/logs/latest-plan.json" for u in requests)
    assert any(u == f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/logs/runs.json" for u in requests)
    assert page.locator("#repo-url").input_value() == f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/logs/"


def test_run_now_targets_the_viewers_own_fork(make_page, site):
    page, _ = make_page()
    serve_fake_origin(page, ORIGIN, BASE_PATH)
    serve_fork_logs(page)
    page.goto(f"{ORIGIN}{BASE_PATH}dashboard/?source=repo&mode=detailed")
    page.wait_for_selector('[data-testid="run-now-btn"]')
    page.locator('[data-testid="run-now-btn"]').click()
    expect(page.locator("#run-now-dialog")).to_be_visible()
    href = page.locator("#run-now-body a").first.get_attribute("href")
    assert f"target_name={OWNER}" in href and "actions=write" in href


def test_save_to_github_targets_the_viewers_own_fork(make_page, site):
    page, _ = make_page()
    open_fork_page(page, "builder/")
    page.wait_for_function("window.__spotiBuilder && window.__spotiBuilder.ready")
    start_blank(page)
    add_chips(add_rule(page, "Chill", "Chill Vault"), "genre_contains", "chill")
    goto_review(page)
    page.get_by_role("button", name="Save to GitHub").click()
    expect(page.locator("#github-save-dialog")).to_be_visible()
    href = page.locator("#github-save-body a").first.get_attribute("href")
    assert f"target_name={OWNER}" in href
    assert "actions=write" not in href  # Phase 7 only ever asks for Contents, unlike run-now

    page.route(f"https://api.github.com/repos/{OWNER}/{REPO}", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    page.locator("#gh-token").fill("github_pat_fake_token")
    page.get_by_role("button", name="Save & verify").click()
    page.wait_for_selector("#gh-commit-msg")
    assert f"{OWNER}/{REPO}" in page.locator("#github-save-body").inner_text()
