/* "Run now" dialog (Phase 8b, decision 39): dispatches the Sync workflow via the GitHub REST API, using a
   fine-grained PAT the visitor creates and pastes in themselves (see ../assets/github-pat.js). Nothing here
   ever runs against Spotify directly -- it only asks GitHub Actions to run the same workflow the Actions tab
   already offers, from a token that lives in this tab's sessionStorage alone. */
(function () {
  'use strict';

  var body = document.getElementById('run-now-body');
  var esc = window.DashViews.esc;
  // Master decisions 15 (2026-09-29): this is the union of scopes both run-now and Configure's Save-to-GitHub
  // need, and Configure requests the exact same set -- so the two features share one sessionStorage slot.
  // Connecting via either entry point covers the other: whichever connects first, the other skips straight to
  // its own form instead of asking to reconnect.
  var SCOPES = [{ name: 'contents', level: 'write' }, { name: 'actions', level: 'write' }];

  function render() {
    var rn = window.DashData.repoOwnerName();
    if (!rn) {
      body.innerHTML = '<p>Set the Repo data source above to your fork’s raw GitHub folder URL first, then reopen this.</p>';
      return;
    }
    var token = window.GithubPAT.get(rn.owner, rn.repo, SCOPES);
    if (token) renderRun(rn, token);
    else renderConnect(rn);
  }

  function renderConnect(rn) {
    var url = window.GithubPAT.tokenUrl({
      owner: rn.owner,
      name: 'LikedZero run-now (' + rn.repo + ')',
      description: 'Lets the LikedZero dashboard dispatch the Sync workflow and Configure commit config.yaml on ' + rn.owner + '/' + rn.repo + ' -- one token covers both. Delete this token any time from github.com/settings/tokens?type=beta.',
      scopes: SCOPES,
    });
    body.innerHTML =
      '<ol class="steps">' +
      '<li><a href="' + esc(url) + '" target="_blank" rel="noopener">Create a token on GitHub</a> — name, description and the two permissions below are pre-filled.</li>' +
      '<li>Under <strong>Repository access</strong>, choose <strong>Only select repositories</strong> and pick <code>' + esc(rn.owner + '/' + rn.repo) + '</code> (GitHub does not let a link pre-select the repository).</li>' +
      '<li>Confirm the permissions still show <strong>Contents: Read and write</strong> and <strong>Actions: Read and write</strong>, then click <strong>Generate token</strong>.</li>' +
      '<li>Paste the token below. It stays only in this browser tab (<code>sessionStorage</code>) — never written to disk, never sent anywhere but GitHub’s API, gone when you close the tab. This same token also lets Configure’s Save to GitHub work right away, with no need to connect again.</li>' +
      '</ol>' +
      '<div class="field"><label for="run-now-token">Fine-grained personal access token</label>' +
      '<input class="input" id="run-now-token" type="password" autocomplete="off" spellcheck="false" placeholder="github_pat_…" /></div>' +
      '<p class="small muted" id="run-now-connect-status" role="status"></p>' +
      '<button type="button" class="btn btn-primary" id="run-now-connect-btn">Save &amp; verify</button>';
    document.getElementById('run-now-connect-btn').addEventListener('click', function () {
      var input = document.getElementById('run-now-token');
      var status = document.getElementById('run-now-connect-status');
      var tok = input.value.trim();
      if (!tok) { status.textContent = 'Paste a token first.'; return; }
      status.textContent = 'Checking with GitHub…';
      window.GithubPAT.verify(rn.owner, rn.repo, tok, SCOPES).then(function (res) {
        if (!res.ok) { status.textContent = res.message; return; }
        window.GithubPAT.set(rn.owner, rn.repo, SCOPES, tok);
        if (res.defaultBranch) window.GithubPAT.setDefaultBranch(rn.owner, rn.repo, res.defaultBranch);
        render();
      });
    });
  }

  function renderRun(rn, token) {
    body.innerHTML =
      '<p class="small muted">Connected to <code>' + esc(rn.owner + '/' + rn.repo) + '</code>. ' +
      '<button type="button" class="btn btn-secondary btn-sm" id="run-now-disconnect">Forget token</button></p>' +
      '<div class="field"><label class="check-row"><input type="checkbox" class="check" id="run-now-dry" checked /> Dry run (no writes)</label></div>' +
      '<div class="field"><label for="run-now-newest">Only touch the N newest liked songs (required for a live run)</label>' +
      '<input class="input" id="run-now-newest" type="number" min="1" step="1" /></div>' +
      '<div class="field"><label for="run-now-max">Abort if the plan has more moves than</label>' +
      '<input class="input" id="run-now-max" type="number" min="1" step="1" value="50" /></div>' +
      '<p class="small muted" id="run-now-status" role="status"></p>' +
      '<button type="button" class="btn btn-primary" id="run-now-dispatch">Dispatch the Sync workflow</button>';

    document.getElementById('run-now-disconnect').addEventListener('click', function () {
      window.GithubPAT.clear(rn.owner, rn.repo, SCOPES);
      render();
    });
    document.getElementById('run-now-dispatch').addEventListener('click', function () {
      var dry = document.getElementById('run-now-dry').checked;
      var newest = document.getElementById('run-now-newest').value.trim();
      var maxMoves = document.getElementById('run-now-max').value.trim() || '50';
      var status = document.getElementById('run-now-status');
      if (!dry && !newest) {
        status.textContent = 'A live run needs "N newest liked songs" filled in — it never touches your whole library.';
        return;
      }
      status.textContent = 'Dispatching…';
      window.GithubPAT.dispatchWorkflow({
        owner: rn.owner, repo: rn.repo, workflow: 'sync.yml', ref: window.GithubPAT.getDefaultBranch(rn.owner, rn.repo) || 'main',
        inputs: { dry_run: String(dry), newest: newest, max_moves: maxMoves },
        token: token,
      }).then(function (res) {
        if (res.ok) {
          status.innerHTML = 'Dispatched. Open <a href="https://github.com/' + esc(rn.owner) + '/' + esc(rn.repo) +
            '/actions/workflows/sync.yml" target="_blank" rel="noopener">the Actions tab</a> to watch it run, then reload this dashboard once it finishes.';
        } else {
          status.textContent = res.message;
          if (/token|401|403/i.test(res.message)) {
            window.GithubPAT.clear(rn.owner, rn.repo, SCOPES);
            setTimeout(render, 1500);
          }
        }
      });
    });
  }

  document.addEventListener('ui:open', function (e) {
    if (e.detail && e.detail.id === 'run-now-dialog') render();
  });
})();
