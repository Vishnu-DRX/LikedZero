/* Shared fine-grained-PAT auth component (decision 39). Device-flow login was ruled out for a static
   Pages site (no CORS on github.com/login/device/code, see design/reports/phase-U.md), so this deep-links
   the visitor to GitHub's token-creation page, pre-scoped where the page's own URL parameters allow it, and
   holds the pasted token in sessionStorage only -- never localStorage, never logged, gone on tab close.
   Used by the Phase 8b run-now button now; Phase 7's config-commit feature will reuse it later. */
(function () {
  'use strict';

  function keyFor(owner, repo) { return 'spotisort.pat.' + owner + '/' + repo; }

  function get(owner, repo) {
    try { return window.sessionStorage.getItem(keyFor(owner, repo)) || null; }
    catch (e) { return null; }
  }

  function set(owner, repo, token) {
    try { window.sessionStorage.setItem(keyFor(owner, repo), token); } catch (e) { /* storage blocked */ }
  }

  function clear(owner, repo) {
    try { window.sessionStorage.removeItem(keyFor(owner, repo)); } catch (e) { /* storage blocked */ }
  }

  // GitHub's query parameters pre-fill name/description/resource-owner/permissions on first load, but there
  // is no documented parameter for "only select repositories" + which repo (community-confirmed limitation,
  // see design/reports/phase-8b.md) -- the visitor still has to pick the repo by hand once the page opens.
  function tokenUrl(opts) {
    var p = new URLSearchParams();
    p.set('name', opts.name);
    p.set('description', opts.description);
    p.set('target_name', opts.owner);
    p.set('expires_in', String(opts.expiresInDays || 90));
    (opts.scopes || []).forEach(function (s) { p.set(s.name, s.level); });
    return 'https://github.com/settings/personal-access-tokens/new?' + p.toString();
  }

  function verify(owner, repo, token) {
    return fetch('https://api.github.com/repos/' + owner + '/' + repo, {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    }).then(function (r) {
      if (r.status === 200) return { ok: true };
      if (r.status === 401) return { ok: false, message: 'GitHub rejected the token (invalid or expired).' };
      if (r.status === 403) return { ok: false, message: 'GitHub accepted the token but it cannot read this repo (wrong repository or missing Contents permission).' };
      if (r.status === 404) return { ok: false, message: 'This repo is not visible to that token (wrong repository, or it is private and the token lacks access).' };
      return { ok: false, message: 'GitHub returned HTTP ' + r.status + ' while checking the token.' };
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
  };
})();
