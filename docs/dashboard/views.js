/* Dashboard views. Each view answers one question. All data is escaped before it reaches the DOM. */
(function () {
  'use strict';
  var D = window.DashData;

  // ------------------------------------------------------------------ helpers
  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtVal(v) {
    if (v === null || v === undefined) return '(none)';
    if (Array.isArray(v)) return v.length ? v.join(', ') : '(empty)';
    if (typeof v === 'boolean') return v ? 'yes' : 'no';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  }
  function pct(v, digits) { return v == null ? 'n/a' : (v * 100).toFixed(digits == null ? 1 : digits) + '%'; }
  // design/proposals/more-conditions.md: one condition line, key + what was wanted/found. `any_of`'s `wanted`
  // is a list of match-condition groups and its `actual` is the per-branch pass/fail list produced by
  // rules_engine.check_key -- rendered so it's clear which branch (if any) actually matched, not just that
  // the whole any_of key passed or failed.
  function conditionLine(c) {
    if (c.key === 'any_of') {
      var branches = c.actual || [];
      var groups = c.wanted || [];
      var parts = groups.map(function (group, i) {
        var b = branches[i] || {};
        var groupText = Object.keys(group).map(function (k) { return esc(k) + '=' + esc(fmtVal(group[k])); }).join(' &amp; ');
        var mark = b.passed ? '<span class="ct-ok">✓</span>' : '<span class="ct-no">✕</span>';
        return '<li>' + mark + ' branch ' + (i + 1) + ': ' + groupText + '</li>';
      });
      return '<code>any_of</code> — at least one branch must match:<ol class="any-of-trace">' + parts.join('') + '</ol>';
    }
    return '<code>' + esc(c.key) + '</code> wants ' + esc(fmtVal(c.wanted)) + '; song has ' + esc(fmtVal(c.actual));
  }
  function num(v) { return v == null ? '—' : String(v); }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : (many || one + 's')); }

  var ICON = { ok: '✓', warn: '▲', bad: '✕', info: '●', neutral: '–' };
  // Maps this file's own internal badge/banner "kind" vocabulary onto the shared component library's actual
  // modifier classes (assets/components.css: badge-success/-warning/-danger/-info, banner-success/-warning/
  // -danger; plain .banner/.badge with no modifier already render as neutral/info, their defaults) -- so every
  // status colour on the dashboard comes from the one shared stylesheet instead of dashboard.css's own copies.
  var BADGE_CLASS = { ok: 'success', warn: 'warning', bad: 'danger', info: 'info', neutral: '' };
  function badgeClass(kind) { return 'badge' + (BADGE_CLASS[kind] ? ' badge-' + BADGE_CLASS[kind] : ''); }
  function badge(kind, text, extra) {
    return '<span class="' + badgeClass(kind) + '"' + (extra || '') + '><span aria-hidden="true">' + ICON[kind] + '</span> ' + esc(text) + '</span>';
  }
  var DECISIONS = {
    will_move: ['ok', 'Will move'], too_young: ['info', 'Too young'], no_match: ['neutral', 'No match'],
    target_problem: ['bad', 'Target problem'], blocked: ['warn', 'Blocked']
  };
  var DECISION_ORDER = ['will_move', 'too_young', 'blocked', 'target_problem', 'no_match'];
  // After a real (apply) run the plan file is the inbox as it was when that run STARTED, so "Will move" would
  // read as a promise about the future; say what it means instead.
  function decisionLabel(d, p) { return d === 'will_move' && p && p.mode === 'apply' ? 'Due to move' : (DECISIONS[d] || [null, d])[1]; }
  function decisionBadge(d, p) { var m = DECISIONS[d] || ['neutral', d]; return badge(m[0], decisionLabel(d, p)); }
  var VERDICTS = { ok: ['ok', 'OK'], dry_run: ['info', 'Dry run'], mismatch: ['bad', 'Mismatch'], error: ['bad', 'Error'], aborted_too_many: ['bad', 'Stopped: too many moves'] };
  function modeLabel(mode) { return mode === 'apply' ? 'Real run' : 'Dry run'; }
  function verdictBadge(v) { var m = VERDICTS[v] || ['neutral', v]; return badge(m[0], m[1]); }
  var TARGET = { resolved: ['ok', 'Found'], missing: ['bad', 'Missing'], not_writable: ['bad', 'Not writable'], ambiguous: ['warn', 'Ambiguous'], dynamic: ['info', 'Resolved per song'] };
  function targetBadge(s) { var m = TARGET[s] || ['neutral', s || 'unknown']; return badge(m[0], m[1]); }
  var TIERS = { playlist: ['ok', 'Playlist'], script: ['ok', 'Script'], hint: ['warn', 'Hint'], country_default: ['warn', 'Country default'] };
  function tierBadge(s) { if (!s) return ''; var m = TIERS[s] || ['neutral', s]; return badge(m[0], m[1]); }
  function posText(p) { return p === 'top' ? 'top of playlist' : 'bottom of playlist'; }
  // decision 31/32: whenever a plan/log has titles_hidden, a public Repo-mode log has song titles/artists
  // redacted (logging.include_track_names: false). Show a plain explanation instead of blank/null text.
  var TITLE_HIDDEN_NOTE = 'Song titles are hidden in logs published on GitHub (that is the default, to keep your music private). To see them, choose Open local files under Change source and open the logs folder from your own computer.';
  // "Song 3 of 4 (title hidden)": still tells songs apart without naming them. `n` may be omitted.
  function hiddenSongText(i, n) { return i ? 'Song ' + i + (n ? ' of ' + n : '') + ' (title hidden)' : 'A song (title hidden)'; }
  function titleOrHidden(name, hidden, i, n) {
    return hidden || name == null ? '<span class="muted" data-testid="title-hidden">' + esc(hiddenSongText(i, n)) + '</span>' : esc(name);
  }
  function likedText(iso) { return iso ? 'liked ' + D.fmtTime(iso) : ''; }
  // a date and time are kept on one line (a phone must not break "2026-10-16" in the middle)
  function nowrap(t) { return '<span class="nowrap">' + esc(t) + '</span>'; }

  function ok(f) { return f && f.status === 'ok'; }
  function plan(ctx) { return ok(ctx.files.plan) ? ctx.files.plan.data : null; }
  function runsOf(ctx) { return ok(ctx.files.runs) ? (ctx.files.runs.data.runs || []) : []; }

  function emptyState(key, files) {
    var cmd = D.COMMANDS[key];
    var file = D.FILES[key];
    return '<section class="empty" data-empty="' + key + '"><h3>No ' + esc(D.LABELS[key].toLowerCase()) + ' yet</h3>' +
      '<p><code>' + esc(file) + '</code> was not found in this data source.</p>' +
      '<p>Create it by running <code class="cmd">' + esc(cmd) + '</code>, then choose <strong>Reload data</strong>.</p></section>';
  }
  function errorState(key, message) {
    return '<section class="errorbox" role="alert" data-error="' + key + '"><h3>Could not load ' + esc(D.LABELS[key].toLowerCase()) + '</h3>' +
      '<p>' + esc(message || 'Unknown error') + '</p>' +
      '<button type="button" class="btn btn-secondary btn-sm" data-action="reload">Try again</button></section>';
  }
  /** Problem cards for every listed file that is missing or broken; '' when all are fine. */
  function problems(ctx, keys) {
    var out = '';
    keys.forEach(function (k) {
      var f = ctx.files[k];
      if (f.status === 'missing') out += emptyState(k);
      else if (f.status === 'error') out += errorState(k, f.message);
    });
    return out;
  }

  var BANNER_CLASS = { ok: 'success', warn: 'warning', bad: 'danger', info: '' };
  function banner(kind, icon, html, attrs) {
    var cls = 'banner' + (BANNER_CLASS[kind] ? ' banner-' + BANNER_CLASS[kind] : '');
    return '<div class="' + cls + '" ' + (attrs || '') + '><span class="ico" aria-hidden="true">' + icon + '</span><div>' + html + '</div></div>';
  }

  // ------------------------------------------------------------------ plain-language "what does this mean?" per view
  var VIEW_EXPLAIN = {
    overview: 'A health check for the whole sorter: did the last run go cleanly, how many songs are waiting, how many have been moved this week, and when it runs next.',
    inbox: 'The songs in Liked Songs, and what LikedZero decided (or will decide) to do with each one, and why. After a real run this is the list as it was when that run started.',
    rules: 'Your rules, in the order they run. A song goes to the first rule it matches. For each rule you can see how many songs it has moved and, once opened, the last five songs and the runs that moved them.',
    playlists: 'Every playlist a rule sends songs to, whether LikedZero can actually write to it, how many real runs have added songs to it, and (once opened) the last five of those runs.',
    runs: 'The history of every time the sorter has run, dry or real. Open a run to see which songs moved to which playlist, and by which rule.'
  };
  function helpBtn(text) {
    return '<button type="button" class="help" data-tip="' + esc(text) + '" aria-label="What does this mean?">?</button>';
  }

  function viewHead(ctx, view, key) {
    var out = '<div class="view-head"><h2 id="view-title" tabindex="-1">' + esc(view.label) + '</h2><p class="question">' + esc(view.question) + ' ' + helpBtn(VIEW_EXPLAIN[key] || view.question) + '</p>';
    var stamps = [], stale = [];
    view.files.forEach(function (k) {
      var iso = D.stampOf(ctx.files[k]);
      if (!iso) return;
      stamps.push('<span data-stamp="' + k + '"><span class="lbl">' + esc(D.LABELS[k]) + ':</span> <time datetime="' + esc(iso) + '">' + esc(D.fmtTime(iso)) + '</time> (' + esc(D.rel(iso)) + ')</span>');
      if (D.isStale(iso)) stale.push(D.LABELS[k] + ' (' + D.fmtTime(iso) + ')');
    });
    out += '<p class="stamp" data-testid="freshness">' + (stamps.length ? '<span class="lbl">Data freshness</span>' + stamps.join('') : '<span class="lbl">Data freshness: no data loaded from this source</span>') + '</p>';
    if (stale.length) {
      out += banner('warn', '▲', '<p><strong>This data is more than 2 days old.</strong> ' + esc(stale.join('; ')) +
        '. The sorter may have stopped running. Check your GitHub Actions runs, or run <code>python -m src.sync</code> again.</p>', 'role="status" data-banner="stale"');
    }
    var p = plan(ctx);
    // Only when no inbox start date is set: with `inbox_since` the run is a live inbox (older songs are never
    // touched), so a plan file that still carries the old "legacy_library" label (written before sync set the
    // label from the config) must not be believed.
    if (p && p.inbox_kind === 'legacy_library' && !p.inbox_since) {
      out += banner('info', '●', '<p><strong>No inbox start date is set, so your whole Liked Songs library is in scope.</strong> LikedZero is meant to run on a fresh, nearly empty Liked Songs list. Set an inbox start date in <a href="../builder/">Configure</a> so older songs are never touched; until then, treat this as a preview of how your rules behave, not a to-do list.</p>', 'role="status" data-banner="legacy"');
    }
    if (p && p.what_if) {
      out += banner('warn', '▲', '<p><strong>What-if preview.</strong> Disabled rules were treated as enabled. This is not what a normal run would do.</p>', 'role="status" data-banner="what-if"');
    }
    return out + '</div>';
  }

  function card(label, value, sub, extra, tip) {
    return '<div class="card"' + (extra || '') + '><p class="metric-label">' + esc(label) + (tip ? helpBtn(tip) : '') + '</p><p class="metric-value">' + value + '</p>' + (sub ? '<p class="metric-sub">' + sub + '</p>' : '') + '</div>';
  }

  function tableWrap(html, cards) { return '<div class="table-wrap' + (cards ? ' cards' : '') + '">' + html + '</div>'; }

  // design/proposals/more-conditions.md: one line for the Rules-view Conditions/Exceptions cells. any_of's
  // value is a list of match-condition groups (dicts), rendered as "(A) OR (B)" rather than the generic
  // fmtVal() (which would just join objects into unreadable "[object Object]" text).
  function matchDictLine(key, value) {
    if (key === 'any_of' && Array.isArray(value)) {
      return '<code>any_of</code> (' + value.map(function (group) {
        return Object.keys(group).map(function (k) { return esc(k) + '=' + esc(fmtVal(group[k])); }).join(' &amp; ');
      }).join(') <span class="small muted">OR</span> (') + ')';
    }
    return '<code>' + esc(key) + '</code> ' + esc(fmtVal(value));
  }

  // ------------------------------------------------------------------ explain drawer content
  var TRACE_RESULT = {
    matched: ['ok', 'Matched: this rule decided the song'],
    matched_too_young: ['info', 'Matched, but the song is too young: evaluation stops here'],
    failed: ['neutral', 'Did not match'],
    not_reached: ['neutral', 'Not reached: an earlier rule already decided'],
    not_reached_but_would_match: ['warn', 'Would match, but never reached (an earlier rule wins)'],
    // design/proposals/more-conditions.md: the rule's own conditions passed, but its `unless` exception also
    // fully matched, so it is blocked -- treated exactly like a non-match, evaluation continues to the next rule.
    blocked_by_exception: ['warn', 'Blocked by an exception: it matched, but an "unless" condition also matched'],
    skipped_disabled: ['neutral', 'Skipped: rule is disabled'],
    skipped_empty: ['neutral', 'Skipped: rule has no conditions']
  };

  var TIER_PLAIN = { playlist: 'learned from your own playlists', script: "the title's script", hint: 'a weaker hint', country_default: "a country default" };
  function confWord(c) { return c == null ? '' : (c >= 0.85 ? 'high confidence' : (c >= 0.6 ? 'medium confidence' : 'low confidence')); }
  // decision 34: the Explain drawer opens with a sentence-first plain narrative, built from the same trace data
  // as the technical accordion below it, before any internal identifiers or rule-by-rule detail.
  function narrativeSentence(song, p) {
    var lang = song.language || {};
    var base;
    if (song.decision === 'will_move') {
      var into = song.target_playlist ? ' into ' + esc(song.target_playlist) : '';
      base = 'Matched ' + (song.rule ? '“' + esc(song.rule) + '”' : 'a rule') + (song.target_playlist ? ' → ' + esc(song.target_playlist) : '') +
        (p && p.mode === 'apply'
          ? '. It was old enough, so the run that took this snapshot was due to move it' + into + ' (see Runs for what actually moved).'
          : '. It is old enough now, so the next run will move it' + into + '.');
    } else if (song.decision === 'too_young') {
      base = (song.rule ? '“' + esc(song.rule) + '” matched' : 'A rule matched') + ', but the song is too new' +
        (song.eligible_on ? ' — it becomes eligible on ' + esc(D.fmtDate(song.eligible_on)) : '') + '.';
    } else if (song.decision === 'target_problem') {
      base = 'A rule matched and wanted to send this to “' + esc(song.target_playlist || '') + '”, but that playlist is ' +
        esc((song.target_status || 'unavailable').replace(/_/g, ' ')) + '.';
    } else if (song.decision === 'blocked') {
      base = 'A rule would otherwise match on ' + esc(lang.value || 'a language') + ', but that language guess is not trusted enough yet to act on — it is only shown, not used.';
    } else {
      base = 'No enabled rule matched this song.';
    }
    if (lang.value && song.decision !== 'blocked') {
      base += ' The language is ' + esc(lang.value) + ' (' + esc(TIER_PLAIN[lang.source] || lang.source || 'an unknown source') + (lang.confidence != null ? ', ' + confWord(lang.confidence) : '') + ').';
    }
    var ar = song.artist_routing;
    // design/proposals/artist_in_playlist.md: shown whenever the artist has a resolved home, regardless of
    // which rule actually decided the song -- same pattern as the language sentence above.
    if (ar && ar.playlist) {
      base += ' Routed to “' + esc(ar.playlist) + '” — ' + esc(ar.track_count) + ' of the artist’s ' + esc(ar.artist_total) + ' tracked tracks are already there.';
    }
    var trace = (song.explain && song.explain.trace) || [];
    // decision 51: the real catch-all (match: {any: true}) always trivially passes its own condition, so its
    // usual sentence ("Matched X, it is old enough...") reads as if something specific was found -- add the
    // context that nothing more specific matched first.
    var decidedEntry = trace.filter(function (e) { return e.rule === song.rule; })[0];
    var isCatchAll = decidedEntry && (decidedEntry.conditions || []).some(function (c) { return c.key === 'any'; });
    if (isCatchAll && (song.decision === 'will_move' || song.decision === 'too_young')) {
      base += ' Nothing more specific matched first, so it falls to this catch-all.';
    }
    // design/proposals/more-conditions.md: when the deciding rule matched via an any_of OR-group, say which
    // branch actually won -- otherwise "Matched X" reads as a single specific condition when it was really one
    // of several alternatives.
    var anyOfCond = decidedEntry && (decidedEntry.conditions || []).filter(function (c) { return c.key === 'any_of'; })[0];
    if (anyOfCond && anyOfCond.passed) {
      var branches = anyOfCond.actual || [];
      var winner = branches.filter(function (b) { return b.passed; })[0];
      if (winner) base += ' It matched via one of several allowed options (branch ' + (winner.branch + 1) + ' of ' + branches.length + ').';
    }
    var shadow = trace.filter(function (e) { return e.result === 'not_reached_but_would_match'; }).map(function (e) { return e.rule; });
    var tooYoungEarlier = trace.filter(function (e) { return e.result === 'matched_too_young' && e.rule !== song.rule; }).map(function (e) { return e.rule; });
    // design/proposals/more-conditions.md: rules that would otherwise have matched first, but were blocked by
    // their own `unless` exception -- distinct from "shadowed" (which never even got their own conditions to
    // fully pass) and from "too young" (an age-gate reason, not an exception).
    var blockedEarlier = trace.filter(function (e) { return e.result === 'blocked_by_exception'; });
    if (shadow.length) base += ' It would also match ' + shadow.map(esc).join(', ') + ', but ' + (shadow.length > 1 ? 'those rules run' : 'that rule runs') + ' later and never get' + (shadow.length > 1 ? '' : 's') + ' the chance.';
    if (tooYoungEarlier.length) base += ' It was too new for ' + tooYoungEarlier.map(esc).join(', ') + '.';
    if (blockedEarlier.length) {
      base += ' ' + (blockedEarlier.length > 1 ? 'Rules ' : 'Rule ') + blockedEarlier.map(function (e) { return '“' + esc(e.rule) + '”'; }).join(', ') +
        ' would otherwise have matched first, but ' + (blockedEarlier.length > 1 ? 'their exceptions blocked them' : 'its exception blocked it') +
        ' (' + blockedEarlier.map(function (e) { return esc(e.blocked_reason || ''); }).join('; ') + ').';
    }
    return base;
  }

  function explainHtml(song, p) {
    var out = '';
    var lang = song.language || {};
    out += '<h3>What happened</h3><p class="callout" data-testid="explain-narrative">' + narrativeSentence(song, p) + '</p>';
    out += '<h3>Decision</h3><p>' + decisionBadge(song.decision, p) + '</p><p>' + esc(song.reason) + '</p>';
    var bits = [];
    if (song.rule) bits.push('Rule: <strong>' + esc(song.rule) + '</strong>');
    if (song.target_playlist) bits.push('Target: <strong>' + esc(song.target_playlist) + '</strong> (' + esc(posText(song.target_position)) + ')');
    if (song.age_days != null) bits.push('Age: ' + esc(song.age_days) + ' days');
    if (song.eligible_on) bits.push('Eligible on: ' + esc(D.fmtDate(song.eligible_on)));
    if (bits.length) out += '<p class="small muted">' + bits.join(' &middot; ') + '</p>';

    out += '<details data-testid="technical-trace"><summary>Technical details: rule-by-rule trace</summary>';
    var tr = (song.explain && song.explain.trace) || [];
    if (song.explain && song.explain.decided_by) out += '<p class="small">Decided by <strong>' + esc(song.explain.decided_by) + '</strong>. Rules run top to bottom and the first match wins.</p>';
    else out += '<p class="small">No rule decided this song. Rules run top to bottom and the first match wins.</p>';
    out += '<ol class="trace" data-testid="trace">';
    tr.forEach(function (e) {
      var m = TRACE_RESULT[e.result] || ['neutral', e.result];
      out += '<li class="t-' + esc(e.result) + '" data-rule="' + esc(e.rule) + '" data-result="' + esc(e.result) + '"><div class="t-head"><span class="t-name">' + esc(e.rule) + '</span>' + badge(m[0], m[1]) + '</div>';
      out += '<p class="small muted" style="margin:4px 0 0">Waits ' + esc(e.threshold_days) + ' days' + (e.enabled ? '' : ' &middot; disabled') + '</p>';
      if (e.conditions && e.conditions.length) {
        out += '<ul>';
        e.conditions.forEach(function (c) {
          out += '<li data-passed="' + (c.passed ? 'true' : 'false') + '"><span class="' + (c.passed ? 'ct-ok' : 'ct-no') + '">' + (c.passed ? '✓ passed' : '✕ failed') + '</span><span>' + conditionLine(c) + '</span></li>';
        });
        out += '</ul>';
      }
      // design/proposals/more-conditions.md: only present when this rule's own match passed AND it has an
      // `unless` block -- shows exactly which exception condition(s) blocked it, not just that it "failed".
      if (e.unless_conditions && e.unless_conditions.length) {
        out += '<p class="small" data-testid="unless-heading"><strong>Exception (unless)' + (e.result === 'blocked_by_exception' ? ' — blocked this rule' : '') + ':</strong></p><ul data-testid="unless-conditions">';
        e.unless_conditions.forEach(function (c) {
          out += '<li data-passed="' + (c.passed ? 'true' : 'false') + '"><span class="' + (c.passed ? 'ct-ok' : 'ct-no') + '">' + (c.passed ? '✓ matched' : '✕ did not match') + '</span><span>' + conditionLine(c) + '</span></li>';
        });
        out += '</ul>';
      }
      if (e.blocked_reason) {
        out += '<p class="small" data-testid="blocked-reason">' + esc(e.blocked_reason) + '.</p>';
      }
      out += '</li>';
    });
    out += '</ol></details>';

    out += '<h3>Language and genre</h3><h4 class="small">Language</h4>';
    if (lang.value) {
      var c = lang.confidence;
      out += '<p data-testid="lang-signal"><strong>' + esc(lang.value) + '</strong> ' + tierBadge(lang.source) + ' ' +
        (lang.used_for_rules ? badge('ok', 'Used for rules') : badge('warn', 'Not used for rules')) + '</p>' +
        (TIER_PLAIN[lang.source] ? '<p class="small muted">How it was found: ' + esc(TIER_PLAIN[lang.source]) + '.</p>' : '');
      if (c != null) out += '<div class="conf"><span class="small muted">Confidence</span><div class="bar" role="img" aria-label="Confidence ' + Math.round(c * 100) + ' percent"><span style="--w:' + Math.round(c * 100) + '%"></span></div><span class="small">' + Math.round(c * 100) + '%</span></div>';
    } else {
      out += '<p>No language could be determined.</p>';
    }
    if (lang.withheld) {
      var w = lang.withheld;
      out += '<div class="banner banner-warning" data-testid="withheld"><span class="ico" aria-hidden="true">▲</span><div><p><strong>Withheld from rules:</strong> ' + esc(w.language) + ' from the ' + esc(w.source) + ' signal. ' +
        (w.reason === 'unmeasured' ? 'This kind of language guess has not been measured for this language yet.' : 'Its measured precision is ' + esc(pct(w.precision)) + ', below the 90% bar.') +
        ' Samples: ' + esc(w.samples) + '. Run <code>python -m src.backtest</code> to measure it.</p></div></div>';
    }
    var g = song.genres || {};
    out += '<h4 class="small">Genres</h4>';
    if (g.values && g.values.length) {
      out += '<ul class="chips">' + g.values.map(function (x) { return '<li class="chip">' + esc(x) + '</li>'; }).join('') + '</ul>';
      out += '<p class="small muted" style="margin-top:8px">Source: ' + esc(g.source || 'unknown') + (g.confidence != null ? ' &middot; confidence ' + Math.round(g.confidence * 100) + '%' : '') + '</p>';
    } else {
      out += '<p>No genres known for this artist.</p>';
    }
    return out;
  }

  // ------------------------------------------------------------------ views
  var V = {};

  // ---- shared plan/run reading (Overview + Inbox + Playlists)
  // The plan file is rewritten by every run. After a REAL run (mode 'apply') it is the inbox as it was when that
  // run started, i.e. BEFORE the moves, so it is not the queue that is waiting now; the run's own `liked_after`
  // is. After a dry run nothing changed, so the plan is still the live queue.
  function planIsBeforeMoves(p) { return !!p && p.mode === 'apply'; }
  /** Songs sitting in Liked Songs now, as far as the data knows: {count, asOf (ISO)|null}, or null. */
  function waitingNow(ctx) {
    var p = plan(ctx), last = runsOf(ctx)[0];
    if (planIsBeforeMoves(p) || !p) return last ? { count: last.liked_after, asOf: last.time } : null;
    return { count: p.liked_total, asOf: p.generated_at || null };
  }
  function schedOf(ctx) { return ok(ctx.files.runs) ? ctx.files.runs.data.schedule : undefined; }
  /** 'at 2026-10-17 08:00 GMT+5:30' when the schedule data holds a future time, else ''. */
  function nextRunTime(sched) {
    if (!sched || typeof sched !== 'object' || !sched.next_run) return '';
    return Date.parse(sched.next_run) > D.now() ? D.fmtTime(sched.next_run) : '';
  }
  function capFirst(t) { return t ? t.charAt(0).toUpperCase() + t.slice(1) : t; }
  function problemsText(r) {
    if (!r.errors && !r.warnings) return 'no problems';
    var parts = [];
    if (r.errors) parts.push(plural(r.errors, 'error'));
    if (r.warnings) parts.push(plural(r.warnings, 'warning'));
    return parts.join(', ');
  }

  // ---- Overview
  V.overview = {
    label: 'Overview', question: 'Is it healthy?', files: ['plan', 'runs'],
    render: function (ctx) {
      var p = plan(ctx), runs = runsOf(ctx), now = D.now();
      // decision 34: a brand-new fork with zero runs gets a short guided tour instead of two separate
      // "file not found" empty states, so the very first thing a new user sees is what to do next.
      if (ctx.files.plan.status === 'missing' && ctx.files.runs.status === 'missing' && ctx.source !== 'files') {
        return '<section class="empty" data-empty="first-run" data-testid="first-run-tour"><h3>Nothing here yet — let’s get your first data</h3>' +
          '<p>This fork has not produced any run data yet. Three steps get you your first Overview:</p>' +
          '<ol><li><strong>Configure</strong> — open <a href="../builder/">Configure</a> and set up your rules for at least one language or playlist.</li>' +
          '<li><strong>Save configuration</strong> — on the Review step, save it, then commit the downloaded <code>config.yaml</code> to your fork’s repository root.</li>' +
          '<li><strong>Run the Sync workflow</strong> — in your fork on GitHub, open the <strong>Actions</strong> tab, choose <strong>Sync</strong>, and run it once (leave “Dry run” ticked). It will commit <code>logs/</code> files back to your repo.</li></ol>' +
          '<p>Once that run finishes, reload this page (or wait for GitHub Pages to redeploy) and this Overview will show your real data.</p></section>';
      }
      var html = problems(ctx, ['plan', 'runs']);
      var last = runs[0];
      var weekAgo = now - 7 * 86400000;
      var movesWeek = runs.filter(function (r) { return Date.parse(r.time) >= weekAgo && r.mode === 'apply'; })
        .reduce(function (a, r) { return a + (r.moved || 0); }, 0);
      var lastApply = runs.filter(function (r) { return r.mode === 'apply'; })[0];
      var mismatches = runs.filter(function (r) { return r.verdict === 'mismatch'; }).length;

      var health;
      if (!last) health = badge('neutral', 'No runs yet');
      else if (last.verdict !== 'ok' && last.verdict !== 'dry_run') health = badge('bad', 'Needs attention');
      else if (last.errors || last.warnings || mismatches) health = badge('warn', 'Healthy, with warnings');
      else health = badge('ok', 'Healthy');
      var healthHtml = '<p class="callout" data-testid="health"><strong>Overall:</strong> ' + health + '</p>', sinceHtml = '', runHtml = '';
      // decision 45/P1-2: inbox_since is the one guard that would stop a schedule from reaching the whole
      // legacy library, so it is surfaced here in plain words.
      if (p && p.inbox_since) {
        sinceHtml = '<p class="small muted" data-testid="inbox-since">Sorting songs liked since <strong>' + esc(p.inbox_since) + '</strong>' + helpBtn('Songs liked before this date are never evaluated or touched.') + '</p>';
      } else if (p) {
        sinceHtml = '<p class="small" data-testid="inbox-since">' + badge('neutral', 'No inbox start date') + ' ' + helpBtn('Every song in Liked Songs is in scope. Set a start date in Configure before turning on automatic runs.') + ' <a class="btn btn-secondary btn-sm" href="../builder/">Configure</a></p>';
      }
      if (ctx.source === 'repo') {
        runHtml = '<p class="run-now-row"><button type="button" class="btn btn-primary" data-open="run-now-dialog" data-testid="run-now-btn">Run now</button> ' +
          helpBtn('Starts the Sync workflow on GitHub using your own token.') + '</p>';
      }

      var sched = schedOf(ctx);
      var nextTime = nextRunTime(sched);
      var waiting = waitingNow(ctx);

      // Card 1: did the last run go well?
      var lastT = last ? runTiming(last, null) : null;
      var lastTimingSub = lastT && lastT.scheduled
        ? '<br><span data-timing="overview">Due ' + esc(istShort(lastT.scheduled, lastT.started)) + ' &middot; started ' + esc(istShort(lastT.started, lastT.started)) + ' ' + lateBadge(lastT.lateStarted) + '</span>'
        : '';
      var lastRunCard = last
        ? card('Last run', verdictBadge(last.verdict), esc(modeLabel(last.mode)) + (last.what_if ? ' (what-if)' : '') + ' &middot; <time datetime="' + esc(last.time) + '">' + esc(D.fmtTime(last.time)) + '</time> (' + esc(D.rel(last.time)) + ') &middot; ' + esc(problemsText(last)) + lastTimingSub, ' data-card="last-run"')
        : card('Last run', '<span class="muted">None</span>', 'No runs yet', ' data-card="last-run"');
      // Card 2: when does it run next? Only shown when the run history actually carries a schedule.
      var nextRunCard = '';
      if (typeof sched === 'string' && sched) {
        nextRunCard = card('Next run', esc(sched), '', ' data-card="next-run"');
      } else if (sched && typeof sched === 'object') {
        var desc = capFirst(sched.description || '') || (sched.cron ? 'Cron ' + sched.cron : '');
        if (nextTime) nextRunCard = card('Next run', esc(nextTime), esc(desc), ' data-card="next-run"', 'The time of the next automatic run, shown in your browser’s time zone.');
        else if (sched.next_run) nextRunCard = card('Next run', 'Due now', esc(desc) + '. If it did not start, check the Actions tab of your fork on GitHub.', ' data-card="next-run"');
        else if (desc) nextRunCard = card('Next run', esc(desc), '', ' data-card="next-run"');
      }
      // Card 3: how many songs are waiting right now?
      var waitSub = '';
      if (waiting && p && !planIsBeforeMoves(p)) {
        waitSub = esc(p.counts.will_move) + ' ready to move, ' + esc(p.counts.too_young) + ' too new';
      } else if (waiting) {
        waitSub = 'After the last run (' + esc(D.rel(waiting.asOf)) + ')';
      }
      var waitingCard = card('Waiting in Liked Songs', waiting ? esc(waiting.count) : '—', waitSub, ' data-card="liked"',
        'The songs in Liked Songs that LikedZero has not moved yet. Zero means everything has been sorted.');
      // Card 4: what has it done this week?
      var movesCard = card('Moved this week', last ? esc(movesWeek) : '—', 'Last 7 days, real runs', ' data-card="moves"',
        'Songs moved out of Liked Songs by real runs in the last 7 days. A dry run only shows what would move, so it is not counted.');
      // Card 5: is every song accounted for?
      var safety, safetySub;
      if (lastApply) {
        safety = lastApply.verdict === 'ok' ? badge('ok', 'All songs accounted for') : (lastApply.verdict === 'mismatch' ? badge('bad', 'A song may need restoring') : verdictBadge(lastApply.verdict));
        safetySub = 'Checked ' + esc(D.fmtDate(lastApply.time)) + (mismatches > 1 ? ' &middot; ' + esc(plural(mismatches, 'run')) + ' failed the check' : '') +
          '<br><a class="btn btn-secondary btn-sm" href="#/runs/' + encodeURIComponent(lastApply.run_id) + '">See that run</a>';
      } else {
        safety = badge('info', 'No real run yet');
        safetySub = 'Dry runs only so far';
      }
      var safetyTip = 'After every real run LikedZero counts your Liked Songs: the number before, minus the songs it moved, should equal the number left. “All songs accounted for” means the numbers matched. Otherwise a song may have gone missing and the run page shows how to restore it.';
      var safetyCard = card('Last real run', safety, safetySub, ' data-card="safety"', safetyTip);

      // "What happens next": one plain sentence.
      var nextHtml = '', tail = '';
      if (nextTime) tail = ' Next run: ' + nextTime + '.';
      else if (sched === null) tail = ' No automatic runs set up.';
      if (p) {
        var c = p.counts, next;
        if (planIsBeforeMoves(p) && last) {
          var lastBy = last.moves_by_playlist || {}, nPl = Object.keys(lastBy).length;
          if (last.verdict === 'aborted_too_many') {
            next = 'Last run stopped: it planned more moves than the safety limit allows. Nothing changed.' + tail;
          } else if (last.verdict === 'error' || last.verdict === 'mismatch') {
            next = 'Last run hit a problem. Open it under Runs.' + tail;
          } else {
            var left = [];
            if (c.too_young) left.push(c.too_young + ' too new');
            if (c.no_match) left.push(c.no_match + ' matched no rule');
            if (c.blocked) left.push(c.blocked + ' blocked');
            if (c.target_problem) left.push(plural(c.target_problem, 'song') + ' with a playlist problem');
            next = (waiting.count === 0 ? 'Nothing waiting.' : plural(waiting.count, 'song') + ' waiting' + (left.length ? ' (' + left.join(', ') + ')' : '') + '.') +
              ' Last run moved ' + (last.moved ? plural(last.moved, 'song') + (nPl ? ' into ' + plural(nPl, 'playlist') : '') : 'nothing') + '.' + tail;
          }
        } else {
          var targets = {};
          p.songs.forEach(function (s) { if (s.decision === 'will_move') targets[s.target_playlist] = 1; });
          var n = Object.keys(targets).length, rest = [];
          if (c.too_young) rest.push(c.too_young + ' still too new');
          if (c.no_match) rest.push(c.no_match + ' match no rule');
          if (c.blocked) rest.push(c.blocked + ' blocked');
          if (c.target_problem) rest.push(plural(c.target_problem, 'song') + ' with a playlist problem');
          next = (c.will_move ? 'Next run would move ' + plural(c.will_move, 'song') + ' into ' + plural(n, 'playlist') + '.' : 'Next run would move nothing.') +
            (rest.length ? ' ' + rest.join(', ') + '.' : '') + ' Dry run: nothing written to Spotify.' + (p.what_if ? ' (What-if: disabled rules counted as enabled.)' : '') + tail;
        }
        var nextEsc = esc(next);
        if (nextTime) nextEsc = nextEsc.replace(esc(nextTime), nowrap(nextTime));  // keep the date and time on one line
        nextHtml += '<p class="callout" data-testid="next"><strong>What happens next:</strong> ' + nextEsc + '</p>';
        nextHtml += '<h3 class="small chips-title">' + (planIsBeforeMoves(p) ? 'Inbox when the last run started, by decision' : 'Inbox by decision') + '</h3><ul class="chips" data-testid="decision-counts">' +
          DECISION_ORDER.map(function (d) { return '<li>' + '<a class="' + badgeClass(DECISIONS[d][0]) + '" href="#/inbox?decision=' + d + '" style="text-decoration:none">' + esc(decisionLabel(d, p)) + ': ' + c[d] + '</a></li>'; }).join('') + '</ul>';
      }
      html += healthHtml + nextHtml + runHtml + '<div class="grid">' + lastRunCard + nextRunCard + waitingCard + movesCard + safetyCard + '</div>';
      return html + sinceHtml;
    }
  };

  // ---- Inbox
  V.inbox = {
    label: 'Inbox', question: 'What is waiting, and why?', files: ['plan'],
    render: function (ctx) {
      var bad = problems(ctx, ['plan']);
      if (bad) return bad;
      var p = plan(ctx);
      var st = ctx.state.inbox = ctx.state.inbox || { q: '', decision: '', rule: '', sort: 'age', dir: 'desc', shown: 100 };
      var q = ctx.query;
      if (q.has('decision')) st.decision = q.get('decision');
      if (q.has('rule')) st.rule = q.get('rule');
      if (q.has('q')) st.q = q.get('q');
      var rules = p.rules.map(function (r) { return r.name; });
      var opts = '<option value="">All decisions</option>' + DECISION_ORDER.map(function (d) {
        return '<option value="' + d + '"' + (st.decision === d ? ' selected' : '') + '>' + esc(decisionLabel(d, p)) + ' (' + p.counts[d] + ')</option>';
      }).join('');
      var ropts = '<option value="">All rules</option>' + rules.map(function (r) { return '<option value="' + esc(r) + '"' + (st.rule === r ? ' selected' : '') + '>' + esc(r) + '</option>'; }).join('');
      var notice = '';
      if (planIsBeforeMoves(p)) {
        var w = waitingNow(ctx);
        notice = banner('info', '●', '<p><strong>Inbox as the last run saw it</strong> (<time datetime="' + esc(p.generated_at) + '">' + esc(D.fmtTime(p.generated_at)) + '</time>)' +
          helpBtn('Songs marked “Due to move” were handled by that run. The Runs tab shows what actually moved.') +
          (w ? '<br>Waiting now: <strong>' + esc(w.count) + '</strong>' : '') + '</p>', 'role="status" data-banner="inbox-snapshot"');
      }
      if (p.titles_hidden) notice += '<p class="small muted" data-testid="titles-hidden-note">' + esc(TITLE_HIDDEN_NOTE) + '</p>';
      return notice + '<div class="toolbar" role="search">' +
        '<div class="field grow"><label for="inbox-q">Search title, artist, rule, playlist</label><input id="inbox-q" class="input" type="search" value="' + esc(st.q) + '" autocomplete="off" /></div>' +
        '<div class="field"><label for="inbox-decision">Decision</label><select id="inbox-decision" class="select">' + opts + '</select></div>' +
        '<div class="field"><label for="inbox-rule">Rule</label><select id="inbox-rule" class="select">' + ropts + '</select></div>' +
        '<button type="button" class="btn btn-secondary btn-sm" id="inbox-csv" data-testid="inbox-csv">Export CSV</button></div>' +
        '<div id="inbox-results"></div>';
    },
    bind: function (root, ctx) {
      var p = plan(ctx);
      if (!p) return;
      var st = ctx.state.inbox;
      var COLS = [
        ['title', 'Song'], ['age', 'Age (days)', 'num'], ['decision', 'Decision'], ['rule', 'Rule'],
        ['target', 'Target playlist'], ['eligible', 'Eligible on'], ['language', 'Language']
      ];
      function keyOf(s, k) {
        switch (k) {
          case 'title': return (s.title || '').toLowerCase();
          case 'age': return s.age_days == null ? null : s.age_days;
          case 'decision': return DECISION_ORDER.indexOf(s.decision);
          case 'rule': return (s.rule || '').toLowerCase() || null;
          case 'target': return (s.target_playlist || '').toLowerCase() || null;
          case 'eligible': return s.eligible_on || null;
          case 'language': return ((s.language && s.language.value) || '').toLowerCase() || null;
        }
      }
      function paint() {
        var term = st.q.trim().toLowerCase();
        var rows = [];
        p.songs.forEach(function (s, i) {
          if (st.decision && s.decision !== st.decision) return;
          if (st.rule && s.rule !== st.rule) return;
          if (term) {
            var hay = [s.title, D.joinArtists(s.artists, ' '), s.rule, s.target_playlist, s.language && s.language.value].join(' ').toLowerCase();
            if (hay.indexOf(term) < 0) return;
          }
          rows.push({ s: s, i: i });
        });
        rows.sort(function (a, b) {
          var x = keyOf(a.s, st.sort), y = keyOf(b.s, st.sort);
          if (x === y) return a.i - b.i;
          if (x === null) return 1;
          if (y === null) return -1;
          return (x < y ? -1 : 1) * (st.dir === 'asc' ? 1 : -1);
        });
        var shown = rows.slice(0, st.shown);
        var h = '<p class="result-count" role="status" data-testid="result-count">Showing ' + shown.length + ' of ' + rows.length + ' songs' + (rows.length !== p.songs.length ? ' (filtered from ' + p.songs.length + ')' : '') + '</p>';
        if (!rows.length) {
          h += '<div class="empty"><h3>No songs match</h3><p>Try clearing the search or filters.</p></div>';
        } else {
          h += '<div class="table-wrap cards"><table class="table stack" data-testid="inbox-table"><thead><tr>';
          COLS.forEach(function (c) {
            var active = st.sort === c[0];
            h += '<th scope="col" class="' + (c[2] || '') + '" aria-sort="' + (active ? (st.dir === 'asc' ? 'ascending' : 'descending') : 'none') + '"><button type="button" class="sort-btn" data-sort="' + c[0] + '">' + esc(c[1]) + '<span aria-hidden="true">' + (active ? '<span class="chev' + (st.dir === 'asc' ? ' chev-up' : '') + '"></span>' : '') + '</span></button></th>';
          });
          h += '</tr></thead><tbody>';
          var hidden = !!p.titles_hidden;
          shown.forEach(function (r) {
            var s = r.s, l = s.language || {}, noName = hidden || s.title == null;
            h += '<tr data-decision="' + esc(s.decision) + '"><td class="cell-main"><button type="button" class="link-btn" data-explain="' + r.i + '" aria-haspopup="dialog">' + titleOrHidden(s.title, hidden, r.i + 1, p.songs.length) + '</button><div class="small muted">' + (noName ? esc(likedText(s.added_at)) : esc(D.joinArtists(s.artists))) + '</div></td>' +
              '<td class="num cell-extra" data-label="Age (days)">' + esc(num(s.age_days)) + '</td>' +
              '<td data-label="Decision">' + decisionBadge(s.decision, p) + '</td>' +
              '<td class="cell-extra" data-label="Rule">' + (s.rule ? esc(s.rule) : '<span class="muted">—</span>') + '</td>' +
              '<td data-label="Target">' + (s.target_playlist ? esc(s.target_playlist) + '<div class="small muted">' + esc(posText(s.target_position)) + (s.target_status && s.target_status !== 'resolved' ? ' &middot; ' + esc(s.target_status.replace('_', ' ')) : '') + '</div>' : '<span class="muted">—</span>') + '</td>' +
              '<td data-label="Eligible on">' + (s.decision === 'will_move' ? 'Ready now' : (s.eligible_on ? esc(D.fmtDate(s.eligible_on)) : '<span class="muted">—</span>')) + '</td>' +
              '<td class="cell-extra" data-label="Language">' + (l.value ? esc(l.value) + ' ' + tierBadge(l.source) : '<span class="muted">unknown</span>') + (l.withheld ? ' ' + badge('warn', 'Withheld') : '') + '</td></tr>';
          });
          h += '</tbody></table></div>';
          if (rows.length > shown.length) h += '<p><button type="button" class="btn btn-secondary" data-more="1">Show ' + Math.min(100, rows.length - shown.length) + ' more</button></p>';
        }
        root.querySelector('#inbox-results').innerHTML = h;
        lastRows = rows;
      }
      var lastRows = [];
      function csvCell(v) {
        var s = String(v == null ? '' : v);
        // decision 46/P2: a cell starting with = + - @ executes as a formula in Excel/Sheets when the CSV
        // is opened -- prefix with a literal quote character so it's read as text instead.
        if (/^[=+\-@]/.test(s)) s = "'" + s;
        return '"' + s.replace(/"/g, '""') + '"';
      }
      function exportCsv() {
        var hidden = !!p.titles_hidden;
        var head = ['Song', 'Artists', 'Age (days)', 'Decision', 'Rule', 'Target playlist', 'Eligible on', 'Language'];
        var lines = [head.map(csvCell).join(',')];
        lastRows.forEach(function (r) {
          var s = r.s;
          lines.push([
            hidden || s.title == null ? hiddenSongText(r.i + 1, p.songs.length) : s.title,
            hidden ? '' : D.joinArtists(s.artists, '; '),
            s.age_days == null ? '' : s.age_days,
            decisionLabel(s.decision, p),
            s.rule || '', s.target_playlist || '',
            s.decision === 'will_move' ? 'Ready now' : (s.eligible_on || ''),
            (s.language && s.language.value) || ''
          ].map(csvCell).join(','));
        });
        var blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = 'likedzero-inbox.csv';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      }
      paint();
      root.querySelector('#inbox-q').addEventListener('input', function (e) { st.q = e.target.value; st.shown = 100; paint(); });
      root.querySelector('#inbox-decision').addEventListener('change', function (e) { st.decision = e.target.value; st.shown = 100; paint(); });
      root.querySelector('#inbox-rule').addEventListener('change', function (e) { st.rule = e.target.value; st.shown = 100; paint(); });
      var csvBtn = root.querySelector('#inbox-csv');
      if (csvBtn) csvBtn.addEventListener('click', exportCsv);
      root.querySelector('#inbox-results').addEventListener('click', function (e) {
        var b = e.target.closest('[data-sort]');
        if (b) {
          var k = b.getAttribute('data-sort');
          if (st.sort === k) st.dir = st.dir === 'asc' ? 'desc' : 'asc'; else { st.sort = k; st.dir = 'asc'; }
          paint();
          var again = root.querySelector('[data-sort="' + k + '"]');
          if (again) again.focus();
          return;
        }
        if (e.target.closest('[data-more]')) { st.shown += 100; paint(); }
      });
    }
  };

  // ---- Rules
  var RECENT_SONGS = 5;
  // What each rule actually did: read from the per-run logs of real runs that moved something (a run that moved
  // nothing cannot contribute, so its log is never fetched). Dry runs are ignored: they move nothing.
  function ruleHistory(ctx, runs) {
    var real = runs.filter(function (r) { return r.mode === 'apply'; });
    var withMoves = real.filter(function (r) { return r.moved > 0 && r.log; });
    return Promise.all(withMoves.map(function (r) { return D.fetchLog(ctx.base, r.log); })).then(function (logs) {
      var h = { real: real.length, since: real.length ? real[real.length - 1].time : null, unreadable: 0, count: {}, last: {} };
      withMoves.forEach(function (run, i) {
        var l = logs[i];
        if (!l || l.status !== 'ok') { h.unreadable++; return; }
        (l.data.moved || []).forEach(function (m) {
          h.count[m.rule] = (h.count[m.rule] || 0) + 1;
          var list = h.last[m.rule] = h.last[m.rule] || [];
          if (list.length < RECENT_SONGS) list.push({ run: run, m: m, hidden: !!l.data.titles_hidden });
        });
      });
      return h;
    });
  }
  function ruleCard(r, i, h) {
    var n = h.count[r.name] || 0, recent = h.last[r.name] || [];
    var conds = Object.keys(r.conditions || {}).map(function (k) { return '<div>' + matchDictLine(k, r.conditions[k]) + '</div>'; }).join('') +
      (r.unless && Object.keys(r.unless).length ? '<div class="small" data-testid="unless-summary">unless ' + Object.keys(r.unless).map(function (k) { return matchDictLine(k, r.unless[k]); }).join(' &amp; ') + '</div>' : '');
    var weak = r.weak_signals_possible && r.weak_signals_possible.length
      ? '<p>' + badge('warn', 'Weak signals: ' + r.weak_signals_possible.map(function (s) { return s.replace('language_in:', ''); }).join(', ')) + '</p>' : '';
    var list = recent.length
      ? '<ol class="rule-recent" data-testid="rule-recent">' + recent.map(function (x) {
          return '<li><div>' + titleOrHidden(x.m.track, x.hidden) + (x.m.artist ? ' <span class="muted">&middot; ' + esc(x.m.artist) + '</span>' : '') + '</div>' +
            '<div class="small muted">to ' + esc(x.m.playlist) + ' &middot; ' + nowrap(D.fmtTime(x.run.time)) + '</div><a class="btn btn-secondary btn-sm" href="#/runs/' + encodeURIComponent(x.run.run_id) + '">Run log</a></li>';
        }).join('') + '</ol>'
      : '<p class="small muted" data-testid="rule-recent-empty">' + (h.real ? 'This rule has not moved any songs yet.' : 'No real run yet, so nothing has been moved.') + '</p>';
    return '<article class="card rule-card" data-rule="' + esc(r.name) + '" data-enabled="' + (r.enabled ? 'true' : 'false') + '">' +
      '<div class="rule-title"><span class="rule-pos">' + (i + 1) + '</span><strong>' + esc(r.name) + '</strong>' + (r.enabled ? '' : badge('neutral', 'Off')) + '</div>' +
      '<p class="rule-meta"><span data-testid="rule-count"><strong>' + n + '</strong> ' + (n === 1 ? 'song' : 'songs') + ' moved</span> &middot; to ' + esc(r.target_playlist) + '</p>' +
      '<details><summary class="btn btn-secondary btn-sm">Details and last ' + RECENT_SONGS + ' songs</summary>' +
      '<div class="rule-body"><dl class="kv"><dt>Matches</dt><dd>' + (conds || '<span class="muted">every song</span>') + '</dd>' +
      '<dt>Goes to</dt><dd>' + esc(r.target_playlist) + ' <span class="muted">(' + esc(posText(r.target_position)) + ')</span> ' + targetBadge(r.target_status) + '</dd>' +
      '<dt>Waits</dt><dd>' + esc(r.threshold_days) + ' days</dd></dl>' + weak +
      '<h4>Last ' + RECENT_SONGS + ' songs</h4>' + list + '</div></details></article>';
  }
  V.rules = {
    label: 'Rules', question: 'What does each rule do?', files: ['plan', 'runs'],
    render: function (ctx) {
      var bad = problems(ctx, ['plan']);
      if (bad) return bad;
      var p = plan(ctx), runs = runsOf(ctx);
      var intro = ctx.files.runs.status !== 'ok' ? problems(ctx, ['runs']) : '';
      return ruleHistory(ctx, runs).then(function (h) {
        var html = intro + '<p class="small muted">Songs moved by real runs' + (h.real ? ' (' + plural(h.real, 'run') + ' since ' + esc(D.fmtDate(h.since)) + ')' : '') +
          helpBtn('Rules run top to bottom and a song goes to the first rule it matches. Counts come from real runs only; a dry run moves nothing. Open a rule to see its last ' + RECENT_SONGS + ' songs.') + '</p>';
        if (h.unreadable) html += banner('warn', ICON.warn, plural(h.unreadable, 'run log') + ' could not be read, so those runs are missing from the counts.');
        html += '<div class="rule-list" data-testid="rules-list">' + p.rules.map(function (r, i) { return ruleCard(r, i, h); }).join('') + '</div>';
        return html;
      });
    }
  };

  // ---- Playlists
  function playlistCard(x, runs) {
    // Real runs only (a dry run adds nothing), straight from the runs index: no per-run log needed.
    var added = runs.filter(function (r) { return r.mode === 'apply' && ((r.moves_by_playlist || {})[x.name] || 0) > 0; });
    var recent = added.slice(0, RECENT_SONGS);
    var list = recent.length
      ? '<ol class="rule-recent" data-testid="playlist-recent">' + recent.map(function (r) {
          var n = r.moves_by_playlist[x.name];
          return '<li><div>' + nowrap(D.fmtTime(r.time)) + ' <span class="muted">&middot; ' + plural(n, 'song') + ' added</span></div>' +
            '<a class="btn btn-secondary btn-sm" href="#/runs/' + encodeURIComponent(r.run_id) + '">Run log</a></li>';
        }).join('') + '</ol>'
      : '<p class="small muted" data-testid="playlist-recent-empty">No real run has added a song to this playlist yet.</p>';
    var cls = x.status === 'resolved' ? '' : (x.status === 'ambiguous' ? ' row-warn' : ' row-bad');
    return '<article class="card rule-card' + cls + '" data-playlist="' + esc(x.name) + '" data-status="' + esc(x.status) + '">' +
      '<div class="rule-title"><strong>' + esc(x.name) + '</strong>' + targetBadge(x.status) + '</div>' +
      '<p class="rule-meta"><span data-testid="playlist-runs"><strong>' + added.length + '</strong> ' + (added.length === 1 ? 'run' : 'runs') + ' added songs</span>' +
      (x.size != null ? ' &middot; ' + esc(x.size) + ' songs in it' : '') + '</p>' +
      '<details><summary class="btn btn-secondary btn-sm">Last ' + RECENT_SONGS + ' runs</summary>' +
      '<div class="rule-body"><dl class="kv"><dt>Rules that send here</dt><dd>' + ((x.rules || []).map(esc).join(', ') || '<span class="muted">none</span>') + '</dd></dl>' +
      '<h4>Last ' + RECENT_SONGS + ' runs that added songs</h4>' + list + '</div></details></article>';
  }
  V.playlists = {
    label: 'Playlists', question: 'Can every target playlist actually be written to?', files: ['plan', 'runs'],
    render: function (ctx) {
      var bad = problems(ctx, ['plan']);
      if (bad) return bad;
      var p = plan(ctx), runs = runsOf(ctx);
      var okCount = p.playlists.filter(function (x) { return x.status === 'resolved'; }).length;
      var html = ctx.files.runs.status !== 'ok' ? problems(ctx, ['runs']) : '';
      html += '<p class="small muted">' + esc(okCount + ' of ' + p.playlists.length) + ' playlists ready' + helpBtn('Found: an owned or collaborative playlist with exactly this name. Missing: no playlist has this name (LikedZero never creates playlists unless a rule allows it). Not writable: you follow it but do not own it. Ambiguous: more than one playlist has this name. Each playlist shows how many real runs added songs to it; open one to see the last ' + RECENT_SONGS + '.') + '</p>';
      html += '<div class="rule-list" data-testid="playlists-list">' + p.playlists.map(function (x) { return playlistCard(x, runs); }).join('') + '</div>';
      return html;
    }
  };

  // ---- Runs
  var METRICS = [['mode', 'Mode'], ['verdict', 'Verdict'], ['planned_moves', 'Planned moves'], ['moved', 'Moved'], ['too_young', 'Too young'], ['no_match', 'No match'],
    ['blocked', 'Blocked'], ['target_problems', 'Target problems'], ['errors', 'Errors'], ['warnings', 'Warnings'], ['liked_before', 'Liked before'],
    ['liked_after', 'Liked after'], ['duration_seconds', 'Duration (s)']];

  function findRun(runs, id) { return runs.filter(function (r) { return r.run_id === id; })[0]; }
  function listBlock(title, items, empty) {
    if (!items || !items.length) return '<h4>' + esc(title) + '</h4><p class="muted small">' + esc(empty) + '</p>';
    return '<h4>' + esc(title) + ' (' + items.length + ')</h4><ul>' + items.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
  }
  function journalTable(j, hidden) {
    if (!j || !j.length) return '<p class="muted small">No journal entries (a dry run removes nothing).</p>';
    var h = '<div class="table-wrap cards"><table class="table stack" data-testid="journal"><thead><tr><th scope="col">Song</th><th scope="col">Originally liked</th><th scope="col">Target playlist id</th><th scope="col">URI</th></tr></thead><tbody>';
    j.forEach(function (e, i) {
      var noName = hidden || e.name == null;
      h += '<tr><td class="cell-main"><strong>' + titleOrHidden(e.name, hidden, i + 1, j.length) + '</strong><div class="small muted">' + (noName ? '' : esc(D.joinArtists(e.artists))) + '</div></td><td data-label="Originally liked">' + esc(D.fmtTime(e.original_added_at)) + '</td><td data-label="Target playlist id"><code>' + esc(e.target_playlist_id) + '</code></td><td data-label="URI">' + (e.uri ? '<code>' + esc(e.uri) + '</code>' : '<span class="muted">not kept in the public log</span>') + '</td></tr>';
    });
    return h + '</tbody></table></div>';
  }
  function writeCount(audit) {
    var n = 0;
    Object.keys(audit || {}).forEach(function (k) { if (!/^GET\b/.test(k)) n += audit[k]; });
    return n;
  }

  /** "3 to The Simulation Archives, 1 to Dil" from a run's moves_by_playlist (biggest first). */
  function movesText(by) {
    by = by || {};
    return Object.keys(by).sort(function (a, b) { return by[b] - by[a]; }).map(function (k) { return by[k] + ' to ' + k; }).join(', ');
  }
  /** One plain sentence for a run, shared by the Runs list and the top of the run page. */
  function runSummary(r) {
    var by = movesText(r.moves_by_playlist), v = r.verdict, text;
    if (v === 'aborted_too_many') {
      return 'Stopped before moving anything: the plan had ' + plural(r.planned_moves, 'move') + ', more than the safety limit allows. Nothing was changed.';
    }
    if (r.mode !== 'apply') {
      text = r.planned_moves ? 'Would move ' + plural(r.planned_moves, 'song') + (by ? ': ' + by : '') + '. Nothing was changed.' : 'Nothing would move. Nothing was changed.';
      text = (r.what_if ? 'What-if preview: ' : 'Dry run: ') + text.charAt(0).toLowerCase() + text.slice(1);
    } else if (r.moved) {
      text = 'Moved ' + plural(r.moved, 'song') + (by ? ': ' + by : '') + '.';
    } else {
      text = 'Nothing moved.';
    }
    if (v === 'error') text += ' It stopped with an error.';
    if (v === 'mismatch') text += ' The song count check failed, so a song may need restoring.';
    if (r.errors || r.warnings) text += ' ' + capFirst(problemsText(r)) + '.';
    return text;
  }

  /** One song line inside a run page: title + artist, or "Song 2 of 4 (title hidden)", and when it was liked. */
  function songLine(m, i, n, hidden) {
    var named = !hidden && m.track != null;
    var main = named ? '<strong>' + esc(m.track) + '</strong>' + (m.artist ? ' <span class="muted">— ' + esc(m.artist) + '</span>' : '') : titleOrHidden(null, true, i + 1, n);
    var liked = m.original_added_at ? likedText(m.original_added_at) : (m.age_days != null ? 'liked ' + m.age_days + ' days before the run' : '');
    return '<li class="moved-song">' + main + (liked ? ' <span class="small muted">· ' + nowrap(liked) + '</span>' : '') + '</li>';
  }

  /** The heart of a run page: playlist -> songs, with the rule that sent them there. */
  function movedSummary(l, run) {
    var moved = l.moved || [], hidden = !!l.titles_hidden, dry = !!l.dry_run;
    var head = dry ? 'What would move where' : 'What moved where';
    if (!moved.length) return '<h4>' + head + '</h4><p class="muted" data-testid="moved-summary">' + (dry ? 'Nothing would move in this run.' : 'No songs moved in this run.') + '</p>';
    var groups = {}, order = [];
    moved.forEach(function (m, i) {
      if (!groups[m.playlist]) { groups[m.playlist] = []; order.push(m.playlist); }
      groups[m.playlist].push({ m: m, i: i });
    });
    order.sort(function (a, b) { return groups[b].length - groups[a].length; });
    var h = '<h4>' + head + ' (' + moved.length + ')</h4><div data-testid="moved-summary">';
    order.forEach(function (name) {
      var items = groups[name], rules = [], positions = {};
      items.forEach(function (it) { if (it.m.rule && rules.indexOf(it.m.rule) < 0) rules.push(it.m.rule); positions[it.m.target_position] = 1; });
      var pos = Object.keys(positions);
      h += '<section class="moved-group" data-playlist="' + esc(name) + '"><h5>&rarr; ' + esc(name) + ' <span class="muted">(' + plural(items.length, 'song') + ')</span></h5>';
      var facts = [];
      if (rules.length === 1) facts.push('Rule: <strong>' + esc(rules[0]) + '</strong>');
      if (pos.length === 1 && pos[0]) facts.push('Added to the ' + (pos[0] === 'top' ? 'top' : 'bottom') + ' of the playlist');
      if (facts.length) h += '<p class="small">' + facts.join(' &middot; ') + '</p>';
      h += '<ol class="moved-list">';
      items.forEach(function (it, k) {
        var line = songLine(it.m, it.i, moved.length, hidden);
        if (rules.length > 1) line = line.replace('</li>', ' <span class="small">· rule: ' + esc(it.m.rule) + '</span></li>');
        if (it.m.already_in_target) line = line.replace('</li>', ' <span class="small muted">· was already in this playlist</span></li>');
        h += line;
      });
      h += '</ol></section>';
    });
    return h + '</div>';
  }

  // Run timing: the schedule slot, when GitHub fired the run, and when the sync really started and finished. Runs
  // recorded before this existed only have `time` (the start) and `duration_seconds`.
  function runTiming(run, log) {
    var l = (log && log.status === 'ok' && log.data) || {};
    var started = run.started_at || l.started_at || run.time;
    var finished = run.finished_at || l.finished_at ||
      (started && run.duration_seconds != null ? new Date(Date.parse(started) + run.duration_seconds * 1000).toISOString() : null);
    var scheduled = run.scheduled_for || l.scheduled_for || null;
    var fired = run.workflow_started_at || l.workflow_started_at || null;
    var trigger = run.trigger || l.trigger || null;
    return {
      scheduled: scheduled, fired: fired, started: started, finished: finished, trigger: trigger,
      lateFired: scheduled && fired ? D.minutesBetween(scheduled, fired) : null,
      lateStarted: scheduled ? D.minutesBetween(scheduled, started) : null
    };
  }
  function triggerLabel(t) {
    return t === 'schedule' ? 'Schedule' : (t === 'workflow_dispatch' ? 'Started by hand (Run workflow)' : (t ? t : 'Unknown (older run or local)'));
  }
  // "04:11 IST" (plus the date only when it differs from `sameDayAs`); UTC goes in the tooltip, not the row.
  function istParts(iso) { var z = D.fmtZone(iso, 'IST', false, true).split(' '); return { date: z[0] + ' ' + z[1], clock: z[2] + ' ' + z[3] }; }
  function istShort(iso, sameDayAs) {
    var a = istParts(iso), d = sameDayAs ? istParts(sameDayAs).date : null;
    return a.clock.replace(' IST', '') + ' IST' + (d && d !== a.date ? ' (' + a.date + ')' : '');
  }
  function durText(sec) {
    if (sec == null || isNaN(sec)) return '';
    sec = Math.round(sec);
    return sec < 60 ? sec + ' s' : Math.floor(sec / 60) + ' min ' + (sec % 60 ? (sec % 60) + ' s' : '');
  }
  // How far the start was from its slot: green when on time, neutral when a little late, amber when it was really late.
  function lateBadge(min) {
    if (min == null) return '';
    return min < 2 ? badge('ok', 'On time') : badge(min >= 15 ? 'warn' : 'neutral', D.lateText(min));
  }
  /** Compact labelled rows for a run: when it was due, when it started (with a lateness badge) and how long it took. IST only; UTC in tooltips. */
  function timingLines(t) {
    function tip(iso) { return iso ? ' title="' + esc(D.fmtZone(iso, 'UTC', true)) + '"' : ''; }
    var h = '<dl class="timing"><dt>Due</dt><dd data-timing="scheduled"' + tip(t.scheduled) + '>' + (t.scheduled
      ? esc(istShort(t.scheduled, t.started))
      : '<span class="muted">' + (t.trigger === 'schedule' ? 'Not recorded' : 'Not a scheduled run') + '</span>') + '</dd>';
    h += '<dt>Started</dt><dd data-timing="started"' + tip(t.started) + '>' + esc(istShort(t.started, t.started)) + ' ' + lateBadge(t.lateStarted) + '</dd>';
    if (t.finished) h += '<dt>Took</dt><dd data-timing="finished"' + tip(t.finished) + '>' + esc(durText((Date.parse(t.finished) - Date.parse(t.started)) / 1000)) + '</dd>';
    return h + '</dl>';
  }
  function timingRows(run, log) {
    var t = runTiming(run, log);
    function row(label, iso, extra) {
      return '<dt>' + label + '</dt><dd data-timing-row="' + label + '">' + (iso
        ? '<span class="nowrap">' + esc(D.fmtZone(iso, 'IST', true)) + '</span> <span class="muted nowrap">' + esc(D.fmtZone(iso, 'UTC', true)) + '</span>' + (extra || '')
        : '<span class="muted">not recorded</span>') + '</dd>';
    }
    return row('Scheduled for', t.scheduled) +
      row('GitHub fired the run', t.fired, t.lateFired != null ? ' ' + lateBadge(t.lateFired) : '') +
      row('Sync started', t.started, t.lateStarted != null ? ' ' + lateBadge(t.lateStarted) : '') +
      row('Sync finished', t.finished) +
      '<dt>Triggered by</dt><dd>' + esc(triggerLabel(t.trigger)) + '</dd>';
  }

  function runDetail(run, log) {
    var facts = '<dl class="kv">' + timingRows(run, log) + '<dt>Mode</dt><dd>' + esc(modeLabel(run.mode)) + (run.what_if ? ' (what-if preview)' : '') + '</dd>' +
      '<dt>Liked Songs</dt><dd>' + esc(run.liked_before) + ' before, ' + esc(run.liked_after) + ' after</dd>' +
      '<dt>Problems</dt><dd>' + esc(problemsText(run)) + '</dd></dl>';
    var h = '<p><a class="btn btn-secondary btn-sm" href="#/runs">All runs</a></p><div class="card" data-testid="run-detail"><h3>Run of ' + esc(D.fmtTime(run.time)) + ' ' + verdictBadge(run.verdict) + '</h3>' +
      '<p class="callout" data-testid="run-summary">' + esc(runSummary(run)) + '</p>' + facts;
    if (!log) return h + '</div>';
    if (log.status !== 'ok') return h + '</div>' + (log.status === 'missing'
      ? '<div class="empty"><h3>Run log not found</h3><p><code>' + esc(run.log) + '</code> is not in this data source. It is created by <code>python -m src.sync</code>.</p></div>'
      : errorState('runs', log.message));
    var l = log.data, hidden = !!l.titles_hidden;
    h += '</div>';
    if (run.verdict === 'mismatch' || (l.reconcile && !l.reconcile.ok)) {
      h += banner('bad', '✕', '<p><strong>The song count check failed.</strong> After this run the number of Liked Songs did not match what was expected, so a song may have gone missing. The restore command is in the technical details below.</p>', 'role="alert" data-banner="run-mismatch"');
    }
    if (hidden) h += '<p class="small muted" data-testid="titles-hidden-note">' + esc(TITLE_HIDDEN_NOTE) + '</p>';
    // 1. what moved where, by which rule -- the part people actually want
    h += movedSummary(l, run);
    // 2. what stayed behind, and why
    var ty = l.skipped_too_young || [], pm = l.skipped_playlist_missing || [];
    var stay = [];
    if (ty.length) stay.push('<li><strong>' + esc(plural(ty.length, 'song')) + ' too new</strong> — still waiting for their rule’s waiting time:<ul>' + ty.map(function (t, i) { return '<li>' + (hidden || t.track == null ? titleOrHidden(null, true, i + 1, ty.length) : esc(t.track) + (t.artist ? ' — ' + esc(t.artist) : '')) + ' <span class="small muted">(' + esc(t.age_days) + ' of ' + esc(t.threshold_days) + ' days, rule “' + esc(t.rule) + '”)</span></li>'; }).join('') + '</ul></li>');
    if (pm.length) stay.push('<li><strong>' + esc(plural(pm.length, 'song')) + ' not moved: playlist problem</strong>:<ul>' + pm.map(function (t, i) { return '<li>' + (hidden || t.track == null ? titleOrHidden(null, true, i + 1, pm.length) : esc(t.track)) + ' &rarr; ' + esc(t.target_playlist) + ' <span class="small muted">(' + esc(String(t.reason || '').replace(/_/g, ' ')) + ')</span></li>'; }).join('') + '</ul></li>');
    if (l.skipped_no_match) stay.push('<li><strong>' + esc(plural(l.skipped_no_match, 'song')) + '</strong> matched no rule.</li>');
    h += '<h4>Left in Liked Songs</h4>' + (stay.length ? '<ul class="stay-list" data-testid="left-behind">' + stay.join('') + '</ul>' : '<p class="muted small">Nothing was left behind.</p>');
    // 3. problems, only when there are some
    if ((l.errors || []).length) h += listBlock('Errors', l.errors, '');
    if ((l.warnings || []).length) h += listBlock('Warnings', l.warnings, '');
    if (!(l.errors || []).length && !(l.warnings || []).length) h += '<p class="muted small">No errors or warnings.</p>';
    // 4. technical details, collapsed unless something went wrong with the safety check
    var tech = '<dl class="kv"><dt>Run id</dt><dd><code>' + esc(run.run_id) + '</code></dd><dt>Songs checked</dt><dd>' + esc(l.evaluated) + '</dd>' +
      '<dt>Config hash</dt><dd><code>' + esc(l.config_hash) + '</code></dd><dt>Spotify write calls</dt><dd>' + esc(writeCount(l.http_audit)) + (l.mode === 'dry_run' || l.dry_run ? ' (dry run: must be 0)' : '') + '</dd>' +
      '<dt>Duration</dt><dd>' + esc(run.duration_seconds) + ' s</dd></dl>';
    if (l.reconcile) {
      tech += '<h4>Reconcile</h4><p>' + (l.reconcile.ok ? badge('ok', 'Reconcile OK') : badge('bad', 'Mismatch')) + ' expected ' + esc(l.reconcile.expected_after) + ' liked songs after the run, found ' + esc(l.reconcile.actual_after) + '.</p>';
    }
    if (l.restore_command) {
      tech += '<h4>Restore</h4><div class="copy-row"><code>' + esc(l.restore_command) + '</code><button type="button" class="btn btn-secondary btn-sm" data-copy="' + esc(l.restore_command) + '">Copy</button></div>';
      if (l.titles_hidden) tech += '<p class="small muted">The committed log no longer carries the real journal (its uris are redacted, decision 44). Download this run’s <code>journal</code> artifact from the Actions run page first, then run the command above against wherever you saved it.</p>';
    }
    tech += '<details><summary>Journal (' + (l.journal || []).length + ' removals recorded)</summary>' + journalTable(l.journal, hidden) + '</details>';
    if (l.batches) tech += '<details><summary>Batches (' + l.batches.length + ')</summary><ul>' + l.batches.map(function (b) { return '<li><code>' + esc(b.playlist_id || b.target) + '</code>: ' + esc(b.size) + ' songs, ' + (b.committed ? 'committed' : 'NOT committed') + '</li>'; }).join('') + '</ul></details>';
    tech += '<details><summary>HTTP audit</summary><dl class="kv">' + Object.keys(l.http_audit || {}).map(function (k) { return '<dt>' + esc(k) + '</dt><dd>' + esc(l.http_audit[k]) + '</dd>'; }).join('') + '</dl></details>';
    var openTech = run.verdict === 'mismatch' || (l.reconcile && !l.reconcile.ok);
    h += '<details class="tech" data-testid="run-technical"' + (openTech ? ' open' : '') + '><summary>Technical details: safety check, restore command, journal</summary>' + tech + '</details>';
    return h;
  }

  function runDiff(a, b, la, lb) {
    var h = '<p><a class="btn btn-secondary btn-sm" href="#/runs">All runs</a></p><div class="card" data-testid="run-diff"><h3>Compare runs</h3><p class="small muted">Older run on the left, newer run on the right.</p>';
    h += '<div class="table-wrap"><table class="table"><thead><tr><th scope="col">Measure</th><th scope="col">' + esc(D.fmtDate(a.time)) + ' (' + esc(a.mode) + ')</th><th scope="col">' + esc(D.fmtDate(b.time)) + ' (' + esc(b.mode) + ')</th><th scope="col" class="num">Change</th></tr></thead><tbody>';
    METRICS.forEach(function (m) {
      var x = a[m[0]], y = b[m[0]], d = '';
      if (typeof x === 'number' && typeof y === 'number') {
        var diff = Math.round((y - x) * 10) / 10;
        d = diff === 0 ? '0' : '<span class="' + (diff > 0 ? 'delta-up' : 'delta-down') + '">' + (diff > 0 ? '+' : '') + diff + '</span>';
      } else if (x !== y) d = 'changed';
      h += '<tr><th scope="row">' + esc(m[1]) + '</th><td>' + esc(fmtVal(x)) + '</td><td>' + esc(fmtVal(y)) + '</td><td class="num">' + d + '</td></tr>';
    });
    h += '</tbody></table></div>';
    var names = {};
    Object.keys(a.rule_counts || {}).concat(Object.keys(b.rule_counts || {})).forEach(function (k) { names[k] = 1; });
    var rk = Object.keys(names);
    h += '<h4>Rule wins</h4>' + (rk.length ? '<div class="table-wrap"><table class="table"><thead><tr><th scope="col">Rule</th><th scope="col" class="num">Older</th><th scope="col" class="num">Newer</th><th scope="col" class="num">Change</th></tr></thead><tbody>' +
      rk.map(function (k) { var x = (a.rule_counts || {})[k] || 0, y = (b.rule_counts || {})[k] || 0; return '<tr><th scope="row">' + esc(k) + '</th><td class="num">' + x + '</td><td class="num">' + y + '</td><td class="num">' + (y - x > 0 ? '+' : '') + (y - x) + '</td></tr>'; }).join('') + '</tbody></table></div>' : '<p class="muted small">Neither run matched any rule.</p>');
    if (la && lb && la.status === 'ok' && lb.status === 'ok' && (la.data.titles_hidden || lb.data.titles_hidden)) {
      h += '<p class="small muted">Song-level differences are not available: song titles are hidden in these logs, so songs cannot be told apart. ' + esc(TITLE_HIDDEN_NOTE) + '</p>';
    } else if (la && lb && la.status === 'ok' && lb.status === 'ok') {
      var setA = {}, setB = {};
      (la.data.moved || []).forEach(function (m) { setA[m.uri + '|' + m.playlist] = m; });
      (lb.data.moved || []).forEach(function (m) { setB[m.uri + '|' + m.playlist] = m; });
      var onlyA = Object.keys(setA).filter(function (k) { return !setB[k]; }).map(function (k) { return setA[k].track + ' → ' + setA[k].playlist; });
      var onlyB = Object.keys(setB).filter(function (k) { return !setA[k]; }).map(function (k) { return setB[k].track + ' → ' + setB[k].playlist; });
      var both = Object.keys(setA).filter(function (k) { return setB[k]; }).length;
      h += '<h4>Songs</h4><p class="small">' + both + ' in both runs.</p>' + listBlock('Only in the older run', onlyA, 'None.') + listBlock('Only in the newer run', onlyB, 'None.');
    } else {
      h += '<p class="small muted">Song-level differences need both run logs, and at least one was not found.</p>';
    }
    return h + '</div>';
  }

  V.runs = {
    label: 'Runs', question: 'What did each run do?', files: ['runs'],
    render: function (ctx) {
      var bad = problems(ctx, ['runs']);
      if (bad) return bad;
      var runs = runsOf(ctx);
      var arg = ctx.arg;
      if (arg) {
        if (arg.indexOf('~') > 0) {
          var ids = arg.split('~');
          var ra = findRun(runs, ids[0]), rb = findRun(runs, ids[1]);
          if (!ra || !rb) return '<div class="empty"><h3>Run not found</h3><p>One of the runs is no longer in the history.</p><p><a class="btn btn-secondary btn-sm" href="#/runs">Back to all runs</a></p></div>';
          if (Date.parse(ra.time) > Date.parse(rb.time)) { var t = ra; ra = rb; rb = t; }
          return Promise.all([D.fetchLog(ctx.base, ra.log), D.fetchLog(ctx.base, rb.log)]).then(function (l) { return runDiff(ra, rb, l[0], l[1]); });
        }
        var run = findRun(runs, arg);
        if (!run) return '<div class="empty"><h3>Run not found</h3><p>That run is no longer in the history.</p><p><a class="btn btn-secondary btn-sm" href="#/runs">Back to all runs</a></p></div>';
        return D.fetchLog(ctx.base, run.log).then(function (l) { return runDetail(run, l); });
      }
      if (!runs.length) return '<div class="empty"><h3>No runs recorded</h3><p>Run <code>python -m src.sync</code> to record the first one.</p></div>';
      var st = ctx.state.runs = ctx.state.runs || { sel: [] };
      st.sel = st.sel.filter(function (id) { return findRun(runs, id); });
      var h = '<div class="toolbar"><button type="button" class="btn btn-secondary btn-sm" id="compare-btn" disabled>Compare selected runs</button><span class="small muted" id="compare-hint" role="status">Tick two runs to compare them.</span></div>';
      h += '<div class="table-wrap cards"><table class="table stack" data-testid="runs-table"><thead><tr><th scope="col"><span class="sr-only">Compare</span></th><th scope="col">When, and what happened</th><th scope="col">Result</th><th scope="col" class="num">Moved</th><th scope="col" class="num">Liked Songs</th><th scope="col"><span class="sr-only">Details</span></th></tr></thead><tbody>';
      runs.forEach(function (r) {
        var cls = r.verdict === 'error' || r.verdict === 'mismatch' || r.verdict === 'aborted_too_many' ? 'row-bad' : (r.warnings ? 'row-warn' : '');
        h += '<tr class="' + cls + '" data-run="' + esc(r.run_id) + '" data-verdict="' + esc(r.verdict) + '"><td class="check-cell" data-label="Compare"><input type="checkbox" class="check" data-pick="' + esc(r.run_id) + '" aria-label="Select run ' + esc(D.fmtTime(r.time)) + ' for comparison"' + (st.sel.indexOf(r.run_id) >= 0 ? ' checked' : '') + ' /></td>' +
          '<td class="cell-main"><strong>' + esc(D.fmtTime(r.time)) + '</strong> <span class="small muted">· ' + esc(modeLabel(r.mode)) + '</span>' + (r.what_if ? ' ' + badge('warn', 'What-if') : '') +
          '<div class="run-summary small" data-testid="run-summary-line">' + esc(runSummary(r)) + '</div>' + timingLines(runTiming(r, null)) + '</td>' +
          '<td data-label="Result">' + verdictBadge(r.verdict) + '</td>' +
          '<td class="num" data-label="Moved">' + esc(r.moved) + '</td>' +
          '<td class="num" data-label="Liked Songs">' + esc(r.liked_before) + ' &rarr; ' + esc(r.liked_after) + '</td>' +
          '<td data-label="Details"><a class="btn btn-secondary btn-sm" href="#/runs/' + encodeURIComponent(r.run_id) + '" aria-label="Details for run ' + esc(D.fmtTime(r.time)) + '">Details</a></td></tr>';
      });
      return h + '</tbody></table></div>';
    },
    bind: function (root, ctx) {
      var btn = root.querySelector('#compare-btn');
      if (!btn) return;
      var st = ctx.state.runs;
      function sync() {
        btn.disabled = st.sel.length !== 2;
        root.querySelector('#compare-hint').textContent = st.sel.length === 2 ? 'Ready to compare.' : (st.sel.length > 2 ? 'Pick exactly two runs.' : 'Tick two runs to compare them (' + st.sel.length + ' selected).');
      }
      root.addEventListener('change', function (e) {
        var c = e.target.closest('[data-pick]');
        if (!c) return;
        var id = c.getAttribute('data-pick');
        st.sel = st.sel.filter(function (x) { return x !== id; });
        if (c.checked) st.sel.push(id);
        if (st.sel.length > 2) { var drop = st.sel.shift(); var box = root.querySelector('[data-pick="' + drop + '"]'); if (box) box.checked = false; }
        sync();
      });
      btn.addEventListener('click', function () { if (st.sel.length === 2) ctx.go('#/runs/' + st.sel.map(encodeURIComponent).join('~')); });
      sync();
    }
  };

  window.DashViews = { VIEWS: V, ORDER: ['overview', 'inbox', 'rules', 'playlists', 'runs'], viewHead: viewHead, explainHtml: explainHtml, esc: esc };
})();
