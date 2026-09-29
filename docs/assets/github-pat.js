/* Shared fine-grained-PAT auth component (decision 39). Device-flow login was ruled out for a static
   Pages site (no CORS on github.com/login/device/code, see design/reports/phase-U.md), so this deep-links
   the visitor to GitHub's token-creation page, pre-scoped where the page's own URL parameters allow it, and
   holds the pasted token in sessionStorage only -- never localStorage, never logged, gone on tab close.
   Used by the Phase 8b run-now button now; Phase 7's config-commit feature will reuse it later. */
(function () {
  'use strict';

  // Master decisions 15 (2026-09-29): supersedes the P1-5 scope-keyed storage below. P1-5's reasoning (keying
  // by the exact scope set so Configure's Contents-only token and run-now's Contents+Actions token could
  // never collide/steal each other's slot) was sound in general, but for this tool's actual threat model --
  // single user, one repo, a token the user creates themselves with a self-chosen (default 7-day) expiry --
  // the repeated "connect again for the other feature" friction outweighed the marginal blast-radius benefit.
  // The user hit it live, twice. Both entry points now request the union of scopes they need (Contents: write
  // + Actions: write) up front, so storage is keyed by owner/repo alone: whichever feature connects first
  // fills the one slot, and every other call -- even one that only needs a subset of what's stored -- reuses
  // it without re-prompting. `scopes` stays a parameter of get/set/clear for call-site compatibility (and in
  // case a future caller ever needs a genuinely narrower, non-shared token again), it just no longer affects
  // the storage key.
  function keyFor(owner, repo) { return 'likedzero.pat.' + owner + '/' + repo; }

  function get(owner, repo, scopes) {
    try { return window.sessionStorage.getItem(keyFor(owner, repo)) || null; }
    catch (e) { return null; }
  }

  function set(owner, repo, scopes, token) {
    try { window.sessionStorage.setItem(keyFor(owner, repo), token); } catch (e) { /* storage blocked */ }
  }

  function clear(owner, repo, scopes) {
    try { window.sessionStorage.removeItem(keyFor(owner, repo)); } catch (e) { /* storage blocked */ }
  }

  // decision 46/P2: cached alongside the token (not the scope-specific slot -- the default branch is a
  // property of the repo, not of which feature connected) so a reopened dialog doesn't need to re-verify
  // just to know it, and a Contents PUT / workflow dispatch never has to guess "main".
  function branchKey(owner, repo) { return 'likedzero.pat.branch.' + owner + '/' + repo; }
  function getDefaultBranch(owner, repo) {
    try { return window.sessionStorage.getItem(branchKey(owner, repo)) || null; } catch (e) { return null; }
  }
  function setDefaultBranch(owner, repo, branch) {
    try { window.sessionStorage.setItem(branchKey(owner, repo), branch); } catch (e) { /* storage blocked */ }
  }

  // GitHub's query parameters pre-fill name/description/resource-owner/permissions on first load, but there
  // is no documented parameter for "only select repositories" + which repo (community-confirmed limitation,
  // see design/reports/phase-8b.md) -- the visitor still has to pick the repo by hand once the page opens.
  // P1-6: 7-day default (was 90) -- this token can edit code that a scheduled workflow then runs with the
  // Spotify refresh token in its environment, so shrinking how long a leaked/forgotten token stays valid
  // matters more than convenience here.
  function tokenUrl(opts) {
    var p = new URLSearchParams();
    p.set('name', opts.name);
    p.set('description', opts.description);
    p.set('target_name', opts.owner);
    p.set('expires_in', String(opts.expiresInDays || 7));
    (opts.scopes || []).forEach(function (s) { p.set(s.name, s.level); });
    return 'https://github.com/settings/personal-access-tokens/new?' + p.toString();
  }

  // P1-5/P1-6: checking only that the token can GET a public repo proves almost nothing -- that endpoint
  // succeeds for any valid token regardless of what it's scoped to, public repos need no permission to read.
  // Check the ACTUAL granted scope instead: `permissions.push` on the repo response reflects real Contents
  // write access, and a dedicated Actions-scoped call (listing workflows) reflects real Actions access.
  function verify(owner, repo, token, scopes) {
    scopes = scopes || [];
    var wantsContentsWrite = scopes.some(function (s) { return s.name === 'contents' && s.level === 'write'; });
    var wantsActions = scopes.some(function (s) { return s.name === 'actions'; });
    return fetch('https://api.github.com/repos/' + owner + '/' + repo, {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    }).then(function (r) {
      if (r.status === 401) return { ok: false, message: 'GitHub rejected the token (invalid or expired).' };
      if (r.status === 404) return { ok: false, message: 'This repo is not visible to that token (wrong repository, or it is private and the token lacks access).' };
      if (r.status !== 200) return { ok: false, message: 'GitHub returned HTTP ' + r.status + ' while checking the token.' };
      return r.json().then(function (body) {
        if (wantsContentsWrite && !(body && body.permissions && body.permissions.push)) {
          return { ok: false, message: 'GitHub accepted the token but it has no write access to this repo -- check the Contents permission, and that "Only select repositories" includes this one.' };
        }
        // decision 46/P2: a fork's default branch is not always "main" -- this is the one authenticated,
        // definitely-correct place to learn it, so callers (dispatchWorkflow, a Contents PUT) don't have to guess.
        var defaultBranch = (body && body.default_branch) || 'main';
        if (!wantsActions) return { ok: true, defaultBranch: defaultBranch };
        return fetch('https://api.github.com/repos/' + owner + '/' + repo + '/actions/workflows', {
          headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
        }).then(function (ar) {
          if (ar.status === 403) return { ok: false, message: 'GitHub accepted the token but it has no Actions access on this repo -- check the Actions permission.' };
          if (ar.status === 401) return { ok: false, message: 'GitHub rejected the token (invalid or expired).' };
          return { ok: true, defaultBranch: defaultBranch };
        });
      });
    }).catch(function (e) {
      return { ok: false, message: 'Could not reach GitHub (' + (e && e.message ? e.message : 'network error') + ').' };
    });
  }

  function dispatchWorkflow(opts) {
    var url = 'https://api.github.com/repos/' + opts.owner + '/' + opts.repo + '/actions/workflows/' + opts.workflow + '/dispatches';
    return fetch(url, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + opts.token,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: opts.ref || 'main', inputs: opts.inputs || {} }),
    }).then(function (r) {
      if (r.status === 204) return { ok: true };
      return r.text().then(function (t) {
        var message = 'GitHub returned HTTP ' + r.status;
        try { var body = JSON.parse(t); if (body && body.message) message += ': ' + body.message; } catch (e) { /* not JSON */ }
        if (r.status === 401) message = 'GitHub rejected the token (invalid or expired).';
        if (r.status === 403) message = 'The token cannot dispatch this workflow (needs Actions: write on this repo).';
        if (r.status === 404) message = 'Workflow or repo not found (wrong repository, or the token cannot see it).';
        return { ok: false, message: message };
      });
    }).catch(function (e) {
      return { ok: false, message: 'Could not reach GitHub (' + (e && e.message ? e.message : 'network error') + ').' };
    });
  }

  window.GithubPAT = {
    get: get, set: set, clear: clear, tokenUrl: tokenUrl, verify: verify, dispatchWorkflow: dispatchWorkflow,
    getDefaultBranch: getDefaultBranch, setDefaultBranch: setDefaultBranch,
  };
})();
