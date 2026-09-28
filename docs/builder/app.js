// LikedZero Configure: guided stepper form -> config object -> validation + YAML preview + versions.
// Vanilla JS. Depends on jsyaml (vendored), SpotiLang, SpotiValidate (validate.js), SpotiSchema (schema.js),
// SpotiUI (assets/ui.js) and SpotiShell (assets/shell.js, for the header/footer only).
(function () {
  'use strict';

  var Lang = window.SpotiLang;
  var V = window.SpotiValidate;
  var UI = window.SpotiUI;

  // ---------------------------------------------------------------- namespacing (decision 28)
  function deriveOwnerRepo() {
    try {
      var host = location.hostname; // "<owner>.github.io"
      var owner = /\.github\.io$/i.test(host) ? host.replace(/\.github\.io$/i, '') : 'local';
      var seg = location.pathname.split('/').filter(Boolean)[0];
      var repo = seg || 'LikedZero';
      return owner + '/' + repo;
    } catch (e) { return 'local/LikedZero'; }
  }
  var NS = 'likedzero:' + deriveOwnerRepo();
  var KEY_DRAFT = NS + ':draft';
  var KEY_VERSIONS = NS + ':versions';
  var KEY_ADVANCED = NS + ':advanced';

  // ---------------------------------------------------------------- storage (try/catch, in-memory fallback)
  var memoryStore = {};
  var storageBlocked = false;
  function storageOk() {
    try {
      var k = '__likedzero_probe__';
      window.localStorage.setItem(k, '1');
      window.localStorage.removeItem(k);
      return true;
    } catch (e) { return false; }
  }
  storageBlocked = !storageOk();
  var Store = {
    get: function (key) {
      if (!storageBlocked) {
        try { return window.localStorage.getItem(key); } catch (e) { storageBlocked = true; }
      }
      return Object.prototype.hasOwnProperty.call(memoryStore, key) ? memoryStore[key] : null;
    },
    set: function (key, value) {
      if (!storageBlocked) {
        try { window.localStorage.setItem(key, value); return; } catch (e) { storageBlocked = true; }
      }
      memoryStore[key] = value;
    }
  };

  // ---------------------------------------------------------------- condition metadata
  var COND = {
    artist_in: { label: 'Artist is one of', kind: 'list', hint: 'Any credited artist, case-insensitive. Press Enter or Add after each name.' },
    genre_contains: { label: 'Genre contains any of', kind: 'list', hint: 'Substring match against the artist’s genres. Press Enter or Add after each entry.' },
    language_in: { label: 'Language is one of', kind: 'list', hint: 'Names, ISO codes or native names; stored as the English name (hi becomes hindi).' },
    release_year_before: { label: 'Released before year', kind: 'year', hint: 'A year from 1 to 9999.' },
    release_year_after: { label: 'Released after year', kind: 'year', hint: 'A year from 1 to 9999.' },
    explicit: { label: 'Explicit flag', kind: 'bool', hint: 'true = explicit songs only, false = clean songs only. Remove the condition to ignore it.' },
    track_name_contains: { label: 'Track name contains', kind: 'text', hint: 'Case-insensitive substring.' },
    album_name_contains: { label: 'Album name contains', kind: 'text', hint: 'Case-insensitive substring.' },
    artist_in_playlist: {
      label: 'Artist has a confident home playlist (auto-routed)', kind: 'flag',
      hint: 'No value to enter here — uses the min_tracks/min_dominance settings above the rule list. Set Target playlist to "auto".'
    },
    any: {
      label: 'Catch-all (matches every song)', kind: 'flag',
      hint: 'Matches unconditionally. Put this rule LAST — everything above it is tried first, and this only catches what nothing else did.'
    },
    artist_country_in: {
      label: 'Artist’s MusicBrainz country is one of', kind: 'list',
      hint: '2-letter ISO country codes (e.g. IN, US, JP). An exact field lookup, but still a weak signal like country defaults — informational, not a strong signal.'
    },
    any_of: {
      label: 'Match any of these groups (OR)', kind: 'anyof',
      hint: 'At least one branch must fully match; conditions within one branch are ANDed. Cannot contain "Artist has a confident home playlist" or nest another "any of".'
    }
  };
  // design/proposals/more-conditions.md: keys allowed inside an any_of branch or an unless block -- same
  // exclusion in both places (artist_in_playlist's auto target only resolves from the rule's top-level match).
  var NESTED_ALLOWED_KEYS = Object.keys(COND).filter(function (k) { return k !== 'artist_in_playlist'; });
  var ANY_OF_BRANCH_ALLOWED_KEYS = NESTED_ALLOWED_KEYS.filter(function (k) { return k !== 'any_of'; });

  function englishLabel(cond) {
    var d = COND[cond.key];
    if (cond.key === 'any_of') {
      return 'match any of: (' + cond.value.map(function (branch) {
        return branch.length ? branch.map(englishLabel).join(' and ') : 'nothing yet';
      }).join(') or (') + ')';
    }
    if (d.kind === 'list') return d.label.toLowerCase() + ' ' + cond.value.join(', ');
    if (cond.key === 'explicit') return cond.value === 'true' ? 'are explicit' : 'are not explicit';
    if (cond.key === 'release_year_before') return 'released before ' + cond.value;
    if (cond.key === 'release_year_after') return 'released after ' + cond.value;
    if (cond.key === 'track_name_contains') return 'have "' + cond.value + '" in the title';
    if (cond.key === 'album_name_contains') return 'are on an album with "' + cond.value + '" in the title';
    if (cond.key === 'any') return 'are anything (catch-all)';
    return d.label;
  }

  function describeUnless(rule) {
    if (!rule.unless.length) return '';
    return ' unless ' + rule.unless.map(englishLabel).join(' and ');
  }

  function defaultCondValue(def) {
    if (def.kind === 'list') return [];
    if (def.kind === 'bool') return 'true';
    if (def.kind === 'flag') return true;
    if (def.kind === 'anyof') return [[]];
    return '';
  }

  function describeRule(rule, defaultDays) {
    if (!rule.match.length) return (rule.name.trim() || 'Untitled rule') + ': no conditions yet.';
    var days = rule.days.trim() !== '' ? rule.days.trim() : defaultDays;
    var parts = rule.match.map(englishLabel);
    var lead = 'Songs older than ' + days + ' day' + (String(days) === '1' ? '' : 's') + ' that ' + parts.join(' and ');
    var target = rule.target.trim() || 'an unnamed playlist';
    var status = rule.enabled ? '' : ' (disabled)';
    return lead + describeUnless(rule) + ' go to ' + target + status + '.';
  }

  // ---------------------------------------------------------------- state
  var nextId = 1;
  function blankState() {
    return {
      defaultDays: '14', fallback: '', inboxSince: '', musicbrainz: true, englishDefault: false, includeTrackNames: false,
      aipEnabled: false, aipMinTracks: '3', aipMinDominance: '0.9', aipExclude: [],
      langPlaylists: [], rules: [], revealAll: false
    };
  }
  function newRule() {
    return { id: nextId++, pristine: true, name: '', enabled: true, target: '', days: '', create: false, position: 'bottom', collapsed: false, match: [], unless: [] };
  }
  function newLp() { return { id: nextId++, name: '', lang: '' }; }

  var state = blankState();
  var advanced = Store.get(KEY_ADVANCED) === '1';
  var lastRemoved = null;
  var currentStep = 1;
  var savedSnapshot = null; // yaml text of last saved version, for the dirty check
  var yamlEditSyncing = false;

  // ---------------------------------------------------------------- undo/redo
  var history = [];
  var historyIndex = -1;
  var restoringHistory = false;
  function snapshotState() { return JSON.stringify({ nextId: nextId, state: state }); }
  function pushHistory() {
    if (restoringHistory) return;
    var snap = snapshotState();
    if (history[historyIndex] === snap) return;
    history = history.slice(0, historyIndex + 1);
    history.push(snap);
    if (history.length > 100) history.shift();
    historyIndex = history.length - 1;
  }
  function applySnapshot(snap) {
    var parsed = JSON.parse(snap);
    nextId = parsed.nextId;
    state = parsed.state;
    restoringHistory = true;
    syncGlobalControls();
    renderLp();
    renderRules();
    update();
    restoringHistory = false;
  }
  function undo() { if (historyIndex > 0) { historyIndex--; applySnapshot(history[historyIndex]); } }
  function redo() { if (historyIndex < history.length - 1) { historyIndex++; applySnapshot(history[historyIndex]); } }

  // ---------------------------------------------------------------- DOM helpers
  function $(id) { return document.getElementById(id); }
  function h(tag, attrs) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === false || v === null || v === undefined) return;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    });
    (function add(list) {
      list.forEach(function (c) {
        if (c === null || c === undefined || c === false) return;
        if (Array.isArray(c)) add(c);
        else el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      });
    })(Array.prototype.slice.call(arguments, 2));
    return el;
  }
  // Single place that pushes `state`'s global (non-rule) fields into their form controls. Called
  // whenever `state` is replaced wholesale (snapshot restore, YAML/import parse, template, init) so
  // the DOM never drifts from state in just one of those paths.
  function syncGlobalControls() {
    $('g-days').value = state.defaultDays;
    $('g-fallback').value = state.fallback;
    $('g-inbox-since').value = state.inboxSince;
    $('g-mb').checked = state.musicbrainz;
    $('g-en').checked = state.englishDefault;
    $('g-log').checked = state.includeTrackNames;
    $('g-log').setAttribute('aria-checked', String(state.includeTrackNames));
    $('g-aip-enabled').checked = state.aipEnabled;
    $('g-aip-enabled').setAttribute('aria-checked', String(state.aipEnabled));
    $('g-aip-min-tracks').value = state.aipMinTracks;
    $('g-aip-min-dominance').value = state.aipMinDominance;
    renderAipExclude();
  }

  function fid(rule, field) { return 'r' + rule.id + '-' + field.replace('.', '-'); }
  function announceRule(msg) { var n = $('rule-notice'); n.textContent = msg; n.className = 'notice' + (msg ? ' show' : ''); return n; }
  function debounce(fn, ms) { var t; return function () { var a = arguments; clearTimeout(t); t = setTimeout(function () { fn.apply(null, a); }, ms); }; }

  // ---------------------------------------------------------------- state -> config object
  function toInt(text) {
    var t = String(text).trim();
    return /^-?\d+$/.test(t) ? Number(t) : text;
  }
  function toNum(text) {
    var t = String(text).trim();
    return t !== '' && isFinite(Number(t)) ? Number(t) : text;
  }
  function langOut(v) { var n = Lang.normalize(v); return n === null ? v : n; }
  function countryOut(v) { return String(v).toUpperCase(); }

  // ---- generic condition <-> {key,value} list conversions, shared by rule.match, rule.unless and any_of
  // branches (design/proposals/more-conditions.md). A condition is {key, value}; `value`'s shape depends on
  // COND[key].kind: list/list, year -> int, bool -> boolean, flag -> true, anyof -> list<list<condition>>.
  function condValueOut(key, value) {
    var def = COND[key];
    if (def.kind === 'list') return value.map(key === 'language_in' ? langOut : (key === 'artist_country_in' ? countryOut : String));
    if (def.kind === 'year') return toInt(value);
    if (def.kind === 'bool') return value === 'true';
    if (def.kind === 'flag') return true;
    if (def.kind === 'anyof') return value.map(matchListToDict);
    return value;
  }
  function matchListToDict(list) {
    var out = {};
    list.forEach(function (c) { out[c.key] = condValueOut(c.key, c.value); });
    return out;
  }
  function condValueIn(key, raw) {
    var def = COND[key];
    if (!def) return undefined;
    if (def.kind === 'list') {
      return Array.isArray(raw) ? raw.map(function (x) {
        var s = String(x);
        if (key === 'language_in') return langOut(s);
        if (key === 'artist_country_in') return countryOut(s);
        return s;
      }) : [];
    }
    if (def.kind === 'bool') return raw === false ? 'false' : 'true';
    if (def.kind === 'flag') return true;
    if (def.kind === 'anyof') return Array.isArray(raw) ? raw.map(dictToMatchList) : [[]];
    return raw === undefined || raw === null ? '' : String(raw);
  }
  function dictToMatchList(m) {
    var list = [];
    if (m && typeof m === 'object' && !Array.isArray(m)) {
      Object.keys(m).forEach(function (k) {
        if (!COND[k]) return;
        list.push({ key: k, value: condValueIn(k, m[k]) });
      });
    }
    return list;
  }

  function toData() {
    var extra = [];
    var data = {};
    if (state.defaultDays.trim() !== '') data.default_days_threshold = toInt(state.defaultDays);

    var lp = {};
    state.langPlaylists.forEach(function (row) {
      if (row.name === '' && row.lang === '') return;
      if (Object.prototype.hasOwnProperty.call(lp, row.name)) {
        extra.push({ msg: "'language_playlists': duplicate playlist name " + JSON.stringify(row.name), short: 'duplicate playlist name', rule: null, field: 'language_playlists', lpRow: row.id });
        return;
      }
      lp[row.name] = langOut(row.lang);
    });
    data.language_playlists = lp;
    data.enrichment = { musicbrainz: state.musicbrainz, english_default: state.englishDefault };
    data.logging = { include_track_names: state.includeTrackNames };
    data.fallback_playlist = state.fallback === '' ? null : state.fallback;
    data.inbox_since = state.inboxSince.trim() === '' ? null : state.inboxSince.trim();
    if (state.aipEnabled) {
      var aip = {};
      if (state.aipMinTracks.trim() !== '') aip.min_tracks = toInt(state.aipMinTracks);
      if (state.aipMinDominance.trim() !== '') aip.min_dominance = toNum(state.aipMinDominance);
      if (state.aipExclude.length) aip.exclude_playlists = state.aipExclude.slice();
      data.artist_in_playlist = aip;
    }
    data.rules = state.rules.map(function (r) {
      var out = { name: r.name, enabled: r.enabled, match: matchListToDict(r.match), target_playlist: r.target };
      if (r.unless && r.unless.length) out.unless = matchListToDict(r.unless);
      if (r.days.trim() !== '') out.days_threshold = toInt(r.days);
      out.create_missing_playlists = r.create;
      out.target_position = r.position;
      return out;
    });
    return { data: data, extra: extra };
  }

  function dumpYaml(data) {
    var body = window.jsyaml.dump(data, { lineWidth: -1, flowLevel: 4, quotingType: '"', noRefs: true });
    return '# LikedZero config - generated by Configure\n' + body;
  }

  // ---------------------------------------------------------------- derived output
  var current = { errors: [], visible: [], yaml: '' };

  function targetIdFor(e) {
    if (e.lpRowId) return 'lp' + e.lpRowId + '-name';
    if (e.rule !== null && e.rule !== undefined) {
      var r = state.rules[e.rule];
      if (!r) return null;
      var f = e.field;
      if (!f) return null;
      if (f === 'match') return r.match.length ? null : 'r' + r.id + '-add-cond';
      if (f === 'unless') return r.unless.length ? null : 'r' + r.id + '-add-unless-cond';
      return fid(r, f);
    }
    return {
      default_days_threshold: 'g-days', fallback_playlist: 'g-fallback', inbox_since: 'g-inbox-since',
      'enrichment.musicbrainz': 'g-mb', 'enrichment.english_default': 'g-en', 'logging.include_track_names': 'g-log',
      'artist_in_playlist.min_tracks': 'g-aip-min-tracks', 'artist_in_playlist.min_dominance': 'g-aip-min-dominance',
      'artist_in_playlist.exclude_playlists': 'aip-exclude-add'
    }[e.field] || null;
  }
  function slotIdFor(e) {
    if (e.lpRowId) return 'err-lp' + e.lpRowId;
    if (e.rule !== null && e.rule !== undefined) {
      var r = state.rules[e.rule];
      if (!r || !e.field) return null;
      return 'err-' + fid(r, e.field);
    }
    return {
      default_days_threshold: 'err-g-days', fallback_playlist: 'err-g-fallback', inbox_since: 'err-g-inbox-since',
      'artist_in_playlist.min_tracks': 'err-g-aip-min-tracks', 'artist_in_playlist.min_dominance': 'err-g-aip-min-dominance',
      'artist_in_playlist.exclude_playlists': 'err-g-aip-exclude'
    }[e.field] || null;
  }

  var debouncedAutosave = debounce(function () { saveDraft(); }, 400);

  function update() {
    var built = toData();
    var errors = V.validateConfig(built.data).errors.concat(built.extra);
    errors.forEach(function (e) {
      if (e.field === 'language_playlists') {
        if (e.lpRow) e.lpRowId = e.lpRow;
        else if (e.lpName !== undefined) {
          var row = state.langPlaylists.filter(function (x) { return x.name === e.lpName; })[0];
          if (row) e.lpRowId = row.id;
        }
      }
    });
    var visible = errors.filter(function (e) {
      if (state.revealAll) return true;
      if (e.rule !== null && e.rule !== undefined && state.rules[e.rule] && state.rules[e.rule].pristine) return false;
      return true;
    });

    document.querySelectorAll('.err').forEach(function (n) { n.textContent = ''; });
    document.querySelectorAll('[aria-invalid]').forEach(function (n) { n.removeAttribute('aria-invalid'); });
    var slots = {};
    visible.forEach(function (e) {
      var slot = slotIdFor(e);
      if (!slot) return;
      (slots[slot] = slots[slot] || []).push(e.short);
      var input = $(slot.replace(/^err-/, ''));
      if (input) input.setAttribute('aria-invalid', 'true');
      if (e.lpRowId) { var ln = $('lp' + e.lpRowId + '-lang'); if (ln && /language/.test(e.short)) ln.setAttribute('aria-invalid', 'true'); }
    });
    Object.keys(slots).forEach(function (id) { var n = $(id); if (n) n.textContent = slots[id].join(' '); });

    current.errors = errors;
    current.visible = visible;
    current.yaml = dumpYaml(built.data);

    ['yaml-out', 'yaml-preview'].forEach(function (id) {
      var out = $(id);
      if (!out) return;
      out.querySelector('code').textContent = current.yaml;
      out.classList.toggle('stale', errors.length > 0);
    });
    if (advanced && document.activeElement !== $('yaml-edit') && !yamlEditSyncing) {
      $('yaml-edit').value = current.yaml;
    }

    ['plain-summary', 'plain-summary-side'].forEach(function (id) {
      var ul = $(id);
      if (!ul) return;
      ul.innerHTML = '';
      if (!state.rules.length) { ul.appendChild(h('li', { class: 'empty', text: 'No rules yet.' })); return; }
      state.rules.forEach(function (r) { ul.appendChild(h('li', { text: describeRule(r, state.defaultDays.trim() || '14') })); });
    });

    var summary = $('error-summary');
    summary.innerHTML = '';
    if (visible.length) {
      summary.hidden = false;
      summary.appendChild(h('h3', { text: visible.length + (visible.length === 1 ? ' problem' : ' problems') + ' to fix' }));
      var ul = h('ul');
      visible.forEach(function (e) {
        var target = targetIdFor(e);
        var li = h('li');
        if (target) {
          li.appendChild(h('a', { href: '#' + target, text: e.msg, onclick: function (ev) {
            ev.preventDefault();
            var t = $(target);
            if (t) { t.focus(); if (t.scrollIntoView) t.scrollIntoView({ block: 'center' }); }
          } }));
        } else li.textContent = e.msg;
        ul.appendChild(li);
      });
      summary.appendChild(ul);
    } else summary.hidden = true;

    var status = $('status');
    if (errors.length === 0) {
      status.textContent = 'Valid. The YAML below matches what the sorter accepts.';
      status.className = 'status ok';
    } else {
      status.textContent = errors.length + (errors.length === 1 ? ' problem' : ' problems') + ' to fix before you can copy, download or save.';
      status.className = 'status bad';
    }
    var dbtn = $('download-btn');
    if (dbtn) { if (errors.length) dbtn.setAttribute('aria-disabled', 'true'); else dbtn.removeAttribute('aria-disabled'); }
    var sbtn = $('save-btn');
    if (sbtn) { if (errors.length) sbtn.setAttribute('aria-disabled', 'true'); else sbtn.removeAttribute('aria-disabled'); }

    debouncedAutosave();
  }

  function blocked(action) {
    if (current.errors.length === 0) return false;
    state.revealAll = true;
    update();
    var n = current.errors.length;
    $('action-status').textContent = 'Cannot ' + action + ': ' + n + (n === 1 ? ' problem' : ' problems') + ' to fix.';
    var s = $('error-summary');
    s.hidden = false;
    s.focus();
    return true;
  }

  // ---------------------------------------------------------------- rendering: language playlists
  function renderLp() {
    var list = $('lp-list');
    list.innerHTML = '';
    state.langPlaylists.forEach(function (row, i) {
      var n = i + 1;
      var name = h('input', { id: 'lp' + row.id + '-name', class: 'input', type: 'text', autocomplete: 'off', 'aria-describedby': 'err-lp' + row.id });
      name.value = row.name;
      name.addEventListener('input', function () { row.name = name.value; update(); });
      name.addEventListener('change', pushHistory);
      var lang = h('input', { id: 'lp' + row.id + '-lang', class: 'input', type: 'text', list: 'lang-options', autocomplete: 'off', 'aria-describedby': 'err-lp' + row.id });
      lang.value = row.lang;
      lang.addEventListener('input', function () { row.lang = lang.value; update(); });
      lang.addEventListener('change', function () {
        var c = Lang.normalize(lang.value);
        if (c) { lang.value = c; row.lang = c; update(); }
        pushHistory();
      });
      list.appendChild(h('li', { class: 'row' },
        h('div', { class: 'field' }, h('label', { class: 'label', for: name.id, text: 'Playlist name' }), name),
        h('div', { class: 'field' }, h('label', { class: 'label', for: lang.id, text: 'Language' }), lang),
        h('button', { type: 'button', class: 'btn btn-ghost btn-sm', 'aria-label': 'Remove playlist mapping ' + n, onclick: function () {
          state.langPlaylists.splice(i, 1);
          renderLp();
          update();
          pushHistory();
          $('lp-add').focus();
        }, text: 'Remove' }),
        h('p', { class: 'err', id: 'err-lp' + row.id })
      ));
    });
  }

  // Advanced-only exclude_playlists chip list for artist_in_playlist. Vault_drx is always shown, first, with
  // no remove button (design/proposals/artist_in_playlist.md: permanently excluded, not just by default).
  function renderAipExclude() {
    var list = $('aip-exclude-chips');
    if (!list) return;
    list.innerHTML = '';
    list.appendChild(h('li', { class: 'chip', title: 'Always excluded — cannot be removed here.' }, h('span', { text: 'Vault_drx' })));
    state.aipExclude.forEach(function (name, i) {
      list.appendChild(h('li', { class: 'chip' },
        h('span', { text: name }),
        h('button', { type: 'button', class: 'chip-x', 'aria-label': 'Remove ' + name, onclick: function () {
          state.aipExclude.splice(i, 1);
          renderAipExclude();
          update();
          pushHistory();
          $('aip-exclude-add').focus();
        }, text: '×' })
      ));
    });
  }

  // ---------------------------------------------------------------- rendering: rules
  // `listName` is 'match' or 'unless' -- the two rule-level condition lists that share this exact widget
  // (design/proposals/more-conditions.md: unless uses the same vocabulary/UI as match).
  function chipList(rule, cond, listName) {
    listName = listName || 'match';
    var ul = h('ul', { class: 'chips', 'aria-label': COND[cond.key].label + ' (entries)' });
    cond.value.forEach(function (val, i) {
      var bad = cond.key === 'language_in' && Lang.normalize(val) === null;
      ul.appendChild(h('li', { class: 'chip' + (bad ? ' bad' : '') },
        h('span', { text: val }),
        h('button', { type: 'button', class: 'chip-x', 'aria-label': 'Remove ' + val, onclick: function () {
          cond.value.splice(i, 1);
          rule.pristine = false;
          var fresh = chipList(rule, cond, listName);
          ul.replaceWith(fresh);
          update();
          pushHistory();
          $(fid(rule, listName + '.' + cond.key)).focus();
        }, text: '×' })
      ));
    });
    return ul;
  }

  function condRow(rule, cond, listName) {
    listName = listName || 'match';
    var def = COND[cond.key];
    var id = fid(rule, listName + '.' + cond.key);
    var errId = 'err-' + id;
    var hintId = id + '-hint';
    var label = h('label', { class: 'label', for: id }, def.label + ' ', h('code', { text: cond.key }));
    var body;
    if (def.kind === 'list') {
      var input = h('input', { id: id, class: 'input', type: 'text', autocomplete: 'off', 'aria-describedby': hintId + ' ' + errId });
      if (cond.key === 'language_in') input.setAttribute('list', 'lang-options');
      var ul = chipList(rule, cond, listName);
      var commit = function () {
        var text = input.value.trim();
        if (!text) return;
        var val = cond.key === 'language_in' ? langOut(text) : cond.key === 'artist_country_in' ? countryOut(text) : text;
        var dup = cond.value.some(function (x) { return x.toLowerCase() === val.toLowerCase(); });
        if (!dup) cond.value.push(val);
        input.value = '';
        rule.pristine = false;
        var fresh = chipList(rule, cond, listName);
        ul.replaceWith(fresh);
        ul = fresh;
        update();
        pushHistory();
        input.focus();
      };
      input.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); commit(); } });
      body = h('div', { class: 'chip-entry' }, ul, h('div', { class: 'chip-add' }, input,
        h('button', { type: 'button', class: 'btn btn-secondary', onclick: commit, 'aria-label': 'Add to ' + def.label, text: 'Add' })));
    } else if (def.kind === 'flag') {
      body = h('p', { class: 'hint', text: 'On — resolved per song at run time.' });
    } else if (def.kind === 'bool') {
      var sel = h('select', { id: id, class: 'select', 'aria-describedby': hintId + ' ' + errId },
        h('option', { value: 'true', text: 'true (explicit only)' }), h('option', { value: 'false', text: 'false (clean only)' }));
      sel.value = cond.value;
      sel.addEventListener('change', function () { cond.value = sel.value; rule.pristine = false; update(); pushHistory(); });
      body = sel;
    } else if (def.kind === 'anyof') {
      if (!cond.value || !cond.value.length) cond.value = [[]];
      body = anyOfEditor(cond, id, function () { rule.pristine = false; update(); pushHistory(); });
    } else {
      var inp = h('input', { id: id, class: 'input', type: 'text', autocomplete: 'off', 'aria-describedby': hintId + ' ' + errId });
      if (def.kind === 'year') inp.setAttribute('inputmode', 'numeric');
      inp.value = cond.value;
      inp.addEventListener('input', function () { cond.value = inp.value; rule.pristine = false; update(); });
      inp.addEventListener('change', pushHistory);
      body = inp;
    }
    return h('div', { class: 'cond' },
      h('div', { class: 'cond-head' }, label,
        h('button', { type: 'button', class: 'btn btn-ghost btn-sm', 'aria-label': 'Remove condition ' + def.label, onclick: function () {
          rule[listName] = rule[listName].filter(function (c) { return c !== cond; });
          rule.pristine = false;
          renderRules();
          update();
          pushHistory();
          var focusId = listName === 'unless' ? fid(rule, 'add-unless-cond') : fid(rule, 'add-cond');
          var f = $(focusId);
          if (f) f.focus();
        }, text: 'Remove' })),
      body,
      h('p', { class: 'hint', id: hintId, text: def.hint }),
      h('p', { class: 'err', id: errId }));
  }

  // ---- generic nested condition-list editor, used only for any_of branches (a branch is not `rule.match` or
  // `rule.unless`, it's an arbitrary array living inside one any_of condition's `value`). Deliberately a
  // simpler, separate implementation from condRow/chipList above (which stay focused on the two rule-level
  // lists) rather than a further-generalized shared one -- keeps the well-tested match/unless widget untouched.
  function xChipList(cond, idPrefix, onMutate) {
    var ul = h('ul', { class: 'chips', 'aria-label': COND[cond.key].label + ' (entries)' });
    cond.value.forEach(function (val, i) {
      var bad = cond.key === 'language_in' && Lang.normalize(val) === null;
      ul.appendChild(h('li', { class: 'chip' + (bad ? ' bad' : '') },
        h('span', { text: val }),
        h('button', { type: 'button', class: 'chip-x', 'aria-label': 'Remove ' + val, onclick: function () {
          cond.value.splice(i, 1);
          var fresh = xChipList(cond, idPrefix, onMutate);
          ul.replaceWith(fresh);
          onMutate();
        }, text: '×' })
      ));
    });
    return ul;
  }

  function xCondRow(list, cond, idPrefix, onMutate) {
    var def = COND[cond.key];
    var id = idPrefix + '-' + cond.key;
    var hintId = id + '-hint';
    var label = h('label', { class: 'label', for: id }, def.label + ' ', h('code', { text: cond.key }));
    var body;
    if (def.kind === 'list') {
      var input = h('input', { id: id, class: 'input', type: 'text', autocomplete: 'off', 'aria-describedby': hintId });
      if (cond.key === 'language_in') input.setAttribute('list', 'lang-options');
      var ul = xChipList(cond, idPrefix, onMutate);
      var commit = function () {
        var text = input.value.trim();
        if (!text) return;
        var val = cond.key === 'language_in' ? langOut(text) : cond.key === 'artist_country_in' ? countryOut(text) : text;
        var dup = cond.value.some(function (x) { return x.toLowerCase() === val.toLowerCase(); });
        if (!dup) cond.value.push(val);
        input.value = '';
        var fresh = xChipList(cond, idPrefix, onMutate);
        ul.replaceWith(fresh);
        ul = fresh;
        onMutate();
        input.focus();
      };
      input.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); commit(); } });
      body = h('div', { class: 'chip-entry' }, ul, h('div', { class: 'chip-add' }, input,
        h('button', { type: 'button', class: 'btn btn-secondary', onclick: commit, 'aria-label': 'Add to ' + def.label, text: 'Add' })));
    } else if (def.kind === 'bool') {
      var sel = h('select', { id: id, class: 'select', 'aria-describedby': hintId },
        h('option', { value: 'true', text: 'true (explicit only)' }), h('option', { value: 'false', text: 'false (clean only)' }));
      sel.value = cond.value;
      sel.addEventListener('change', function () { cond.value = sel.value; onMutate(); });
      body = sel;
    } else if (def.kind === 'flag') {
      body = h('p', { class: 'hint', text: 'On — resolved per song at run time.' });
    } else {
      var inp = h('input', { id: id, class: 'input', type: 'text', autocomplete: 'off', 'aria-describedby': hintId });
      if (def.kind === 'year') inp.setAttribute('inputmode', 'numeric');
      inp.value = cond.value;
      inp.addEventListener('input', function () { cond.value = inp.value; });
      inp.addEventListener('change', onMutate);
      body = inp;
    }
    return h('div', { class: 'cond cond-nested' },
      h('div', { class: 'cond-head' }, label,
        h('button', { type: 'button', class: 'btn btn-ghost btn-sm', 'aria-label': 'Remove condition ' + def.label, onclick: function () {
          var idx = list.indexOf(cond);
          if (idx !== -1) list.splice(idx, 1);
          onMutate();
        }, text: 'Remove' })),
      body,
      h('p', { class: 'hint', id: hintId, text: def.hint }));
  }

  // `cond` is the any_of condition itself ({key:'any_of', value: [branch, ...]}); each branch is an array of
  // {key,value} conditions (AND-combined), and any one branch passing satisfies the whole any_of.
  function anyOfEditor(cond, idPrefix, outerOnMutate) {
    var list = h('ol', { class: 'any-of-branches' });
    function onMutate() { paint(); outerOnMutate(); }
    function paint() {
      list.innerHTML = '';
      cond.value.forEach(function (branch, bi) {
        var bPrefix = idPrefix + '-b' + bi;
        var used = branch.map(function (c) { return c.key; });
        var sel = h('select', { id: bPrefix + '-add', class: 'select' }, h('option', { value: '', text: 'Choose a condition…' }));
        ANY_OF_BRANCH_ALLOWED_KEYS.forEach(function (k) {
          if (used.indexOf(k) === -1) sel.appendChild(h('option', { value: k, text: COND[k].label + ' (' + k + ')' }));
        });
        var addBtn = h('button', {
          type: 'button', class: 'btn btn-secondary btn-sm', text: 'Add branch condition', onclick: function () {
            if (!sel.value) { sel.focus(); return; }
            var def = COND[sel.value];
            branch.push({ key: sel.value, value: defaultCondValue(def) });
            onMutate();
          }
        });
        var branchBody = h('div', { class: 'any-of-branch-conds' },
          branch.length ? branch.map(function (c) { return xCondRow(branch, c, bPrefix, onMutate); }) : h('p', { class: 'hint' }, 'No conditions yet.'));
        var removeBranchBtn = cond.value.length > 1
          ? h('button', {
              type: 'button', class: 'btn btn-ghost btn-sm', 'aria-label': 'Remove branch ' + (bi + 1), text: 'Remove branch',
              onclick: function () { cond.value.splice(bi, 1); onMutate(); }
            })
          : null;
        var addRowLabel = h('label', { class: 'label', for: sel.id, text: 'Add a condition to branch ' + (bi + 1) });
        list.appendChild(h('li', { class: 'any-of-branch card' },
          h('div', { class: 'any-of-branch-head' }, h('strong', { text: 'Branch ' + (bi + 1) }), removeBranchBtn),
          branchBody,
          used.length >= ANY_OF_BRANCH_ALLOWED_KEYS.length ? null : h('div', { class: 'add-cond' }, addRowLabel, sel, addBtn)));
      });
    }
    paint();
    return h('div', { class: 'any-of-editor' },
      h('p', { class: 'hint' }, 'At least one branch below must fully match. Conditions within one branch are ANDed.'),
      list,
      h('button', {
        type: 'button', class: 'btn btn-secondary', text: 'Add another branch (OR)',
        onclick: function () { cond.value.push([]); onMutate(); }
      }));
  }

  function textField(rule, field, label, prop, hint, extraAttrs) {
    var id = fid(rule, field);
    var attrs = { id: id, class: 'input', type: 'text', autocomplete: 'off', 'aria-describedby': (hint ? id + '-hint ' : '') + 'err-' + id };
    if (extraAttrs) Object.keys(extraAttrs).forEach(function (k) { attrs[k] = extraAttrs[k]; });
    var input = h('input', attrs);
    input.value = rule[prop];
    input.addEventListener('input', function () {
      rule[prop] = input.value;
      rule.pristine = false;
      if (prop === 'name') {
        var t = $('rule-' + rule.id + '-title');
        if (t) t.textContent = input.value.trim() || 'Untitled rule';
      }
      update();
    });
    input.addEventListener('change', pushHistory);
    return h('div', { class: 'field' }, h('label', { class: 'label', for: id, text: label }), input,
      hint ? h('p', { class: 'hint', id: id + '-hint', text: hint }) : null,
      h('p', { class: 'err', id: 'err-' + id }));
  }

  function switchField(rule, prop, label, hint, id) {
    id = id || fid(rule, prop);
    var cb = h('input', { id: id, type: 'checkbox', class: 'switch-input', role: 'switch', 'aria-checked': String(rule[prop]) });
    cb.checked = rule[prop];
    cb.addEventListener('change', function () { rule[prop] = cb.checked; cb.setAttribute('aria-checked', String(cb.checked)); rule.pristine = false; update(); pushHistory(); });
    return h('label', { class: 'switch' }, cb, h('span', { class: 'switch-ui', 'aria-hidden': 'true' }), h('span', { class: 'switch-label', text: label }));
  }

  function checkField(rule, prop, label, hint) {
    var id = fid(rule, prop);
    var cb = h('input', { id: id, type: 'checkbox', class: 'check', 'aria-describedby': id + '-hint' });
    cb.checked = rule[prop];
    cb.addEventListener('change', function () { rule[prop] = cb.checked; rule.pristine = false; update(); pushHistory(); });
    return h('div', { class: 'field check-row-field', 'data-advanced-only': true }, h('label', { class: 'check-row' }, cb, label), h('p', { class: 'hint', id: id + '-hint', text: hint }));
  }

  function positionField(rule) {
    var id = fid(rule, 'position');
    var sel = h('select', { id: id, class: 'select', 'aria-describedby': id + '-hint' },
      h('option', { value: 'bottom', text: 'Bottom (default)' }),
      h('option', { value: 'top', text: 'Top' }));
    sel.value = rule.position;
    sel.addEventListener('change', function () { rule.position = sel.value; rule.pristine = false; update(); pushHistory(); });
    return h('div', { class: 'field', 'data-advanced-only': true }, h('label', { class: 'label', for: id, text: 'Insert position' }), sel,
      h('p', { class: 'hint', id: id + '-hint', text: 'target_position: Top means new songs go to the top; existing order kept.' }));
  }

  function move(index, delta, which) {
    var to = index + delta;
    if (to < 0 || to >= state.rules.length) return;
    var r = state.rules.splice(index, 1)[0];
    state.rules.splice(to, 0, r);
    renderRules();
    update();
    pushHistory();
    var btn = document.querySelector('#rule-' + r.id + ' .' + which);
    if (btn.disabled) btn = document.querySelector('#rule-' + r.id + ' .' + (which === 'up' ? 'down' : 'up'));
    btn.focus();
    announceRule('Moved rule ' + (r.name.trim() ? '“' + r.name.trim() + '”' : 'Untitled') + ' to position ' + (to + 1) + ' of ' + state.rules.length + '.');
  }

  function duplicateRule(index) {
    var src = state.rules[index];
    var copy = JSON.parse(JSON.stringify(src));
    copy.id = nextId++;
    copy.name = (src.name || 'Untitled') + ' (copy)';
    state.rules.splice(index + 1, 0, copy);
    renderRules();
    update();
    pushHistory();
    announceRule('Duplicated rule to position ' + (index + 2) + '.');
    var f = $(fid(copy, 'name'));
    if (f) f.focus();
  }

  function renderRule(rule, index, total) {
    var title = rule.name.trim() || 'Untitled rule';
    var used = rule.match.map(function (c) { return c.key; });
    var sel = h('select', { id: fid(rule, 'add-cond'), class: 'select' },
      h('option', { value: '', text: 'Choose a condition…' }));
    V.MATCH_KEYS.forEach(function (k) {
      if (used.indexOf(k) === -1) sel.appendChild(h('option', { value: k, text: COND[k].label + ' (' + k + ')' }));
    });
    var addCond = function () {
      if (!sel.value) { sel.focus(); return; }
      var def = COND[sel.value];
      var cond = { key: sel.value, value: defaultCondValue(def) };
      rule.match.push(cond);
      if (sel.value === 'artist_in_playlist' && !rule.target.trim()) rule.target = 'auto';
      rule.pristine = false;
      renderRules();
      update();
      pushHistory();
      var f = $(fid(rule, 'match.' + cond.key));
      if (f) f.focus();
    };
    var addRow = used.length >= V.MATCH_KEYS.length ? null :
      h('div', { class: 'add-cond' },
        h('label', { class: 'label', for: sel.id, text: 'Add a condition' }), sel,
        h('button', { type: 'button', class: 'btn btn-secondary', onclick: addCond, text: 'Add condition' }));

    // design/proposals/more-conditions.md: exceptions (unless) -- same vocabulary as match, minus
    // artist_in_playlist (its auto target only resolves from the rule's top-level match, see NESTED_ALLOWED_KEYS).
    var usedUnless = rule.unless.map(function (c) { return c.key; });
    var selU = h('select', { id: fid(rule, 'add-unless-cond'), class: 'select' }, h('option', { value: '', text: 'Choose a condition…' }));
    NESTED_ALLOWED_KEYS.forEach(function (k) {
      if (usedUnless.indexOf(k) === -1) selU.appendChild(h('option', { value: k, text: COND[k].label + ' (' + k + ')' }));
    });
    var addUnlessCond = function () {
      if (!selU.value) { selU.focus(); return; }
      var def = COND[selU.value];
      var cond = { key: selU.value, value: defaultCondValue(def) };
      rule.unless.push(cond);
      rule.pristine = false;
      renderRules();
      update();
      pushHistory();
      var f = $(fid(rule, 'unless.' + cond.key));
      if (f) f.focus();
    };
    var addUnlessRow = usedUnless.length >= NESTED_ALLOWED_KEYS.length ? null :
      h('div', { class: 'add-cond' },
        h('label', { class: 'label', for: selU.id, text: 'Add an exception condition' }), selU,
        h('button', { type: 'button', class: 'btn btn-secondary', onclick: addUnlessCond, text: 'Add exception' }));
    var unlessFieldset = h('fieldset', { class: 'conds unless-conds', 'data-advanced-only': true },
      h('legend', { text: 'Exceptions (unless this also matches)' }),
      h('p', { class: 'hint' }, 'If ALL of these are also true, this rule is skipped even though its conditions above matched — evaluation moves on to the next rule.'),
      rule.unless.length ? null : h('p', { class: 'hint' }, 'No exceptions — this rule never gets blocked.'),
      rule.unless.map(function (c) { return condRow(rule, c, 'unless'); }),
      h('p', { class: 'err', id: 'err-' + fid(rule, 'unless') }),
      addUnlessRow);

    var body = h('div', { class: 'rule-body' },
      textField(rule, 'name', 'Rule name', 'name', 'Unique, case-insensitive.'),
      textField(rule, 'target_playlist', 'Target playlist', 'target',
        rule.match.some(function (c) { return c.key === 'artist_in_playlist'; })
          ? 'Type "auto" — with the artist-routing condition, the real target is resolved per song.'
          : 'Name of an existing playlist you own.'),
      h('div', { class: 'field check-row-field' },
        h('label', { class: 'check-row' }, (function () {
          var cb = h('input', { type: 'checkbox', class: 'check', id: fid(rule, 'enabled') });
          cb.checked = rule.enabled;
          cb.addEventListener('change', function () {
            rule.enabled = cb.checked;
            var badge = $('rule-' + rule.id + '-badge');
            if (badge) badge.hidden = rule.enabled;
            update(); pushHistory();
          });
          return cb;
        })(), 'Enabled'),
        h('p', { class: 'hint', text: 'Disabled rules are skipped.' })),
      checkField(rule, 'create', 'Create playlist if missing', 'create_missing_playlists. Off means the rule only uses playlists that already exist.'),
      positionField(rule),
      h('div', { 'data-advanced-only': true },
        textField(rule, 'days_threshold', 'Days threshold override', 'days', 'Optional. Blank uses the global default.', { inputmode: 'numeric' })),
      h('fieldset', { class: 'conds' },
        h('legend', { text: 'Match conditions (all must match)' }),
        rule.match.length ? null : h('p', { class: 'hint', text: 'No conditions yet. A rule needs at least one.' }),
        rule.match.map(function (c) { return condRow(rule, c, 'match'); }),
        h('p', { class: 'err', id: 'err-' + fid(rule, 'match') }),
        addRow),
      unlessFieldset);

    var handle = h('button', { type: 'button', class: 'btn btn-icon drag-handle', 'aria-label': 'Drag to reorder rule ' + (index + 1) + ', or use the buttons after it', draggable: 'true' }, '☰');
    var collapseBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', 'aria-expanded': String(!rule.collapsed), 'aria-controls': 'rule-' + rule.id + '-body', onclick: function () {
      rule.collapsed = !rule.collapsed;
      renderRules();
    }, text: rule.collapsed ? 'Expand' : 'Collapse' });

    var li = h('li', { class: 'rule card' + (rule.collapsed ? ' is-collapsed' : ''), id: 'rule-' + rule.id, draggable: 'false' },
      h('div', { class: 'rule-head' },
        handle,
        h('h3', { id: 'rule-' + rule.id + '-h' }, 'Rule ' + (index + 1) + ': ', h('span', { id: 'rule-' + rule.id + '-title', text: title }),
          h('span', { id: 'rule-' + rule.id + '-badge', class: 'badge', hidden: rule.enabled, text: 'disabled' })),
        h('div', { class: 'rule-tools', role: 'group', 'aria-label': 'Rule ' + (index + 1) + ' actions' },
          collapseBtn,
          h('button', { type: 'button', class: 'btn btn-secondary btn-sm up', disabled: index === 0, 'aria-label': 'Move rule ' + (index + 1) + ' up', onclick: function () { move(index, -1, 'up'); }, text: 'Up' }),
          h('button', { type: 'button', class: 'btn btn-secondary btn-sm down', disabled: index === total - 1, 'aria-label': 'Move rule ' + (index + 1) + ' down', onclick: function () { move(index, 1, 'down'); }, text: 'Down' }),
          h('button', { type: 'button', class: 'btn btn-secondary btn-sm', 'aria-label': 'Duplicate rule ' + (index + 1), onclick: function () { duplicateRule(index); }, text: 'Duplicate' }),
          h('button', { type: 'button', class: 'btn btn-danger btn-sm remove', 'aria-label': 'Remove rule ' + (index + 1), onclick: function () { removeRule(index); }, text: 'Remove' }))),
      h('div', { id: 'rule-' + rule.id + '-body', hidden: rule.collapsed }, body));

    handle.addEventListener('dragstart', function (ev) { ev.dataTransfer.setData('text/plain', String(index)); ev.dataTransfer.effectAllowed = 'move'; li.classList.add('dragging'); });
    handle.addEventListener('dragend', function () { li.classList.remove('dragging'); });
    li.addEventListener('dragover', function (ev) { ev.preventDefault(); ev.dataTransfer.dropEffect = 'move'; });
    li.addEventListener('drop', function (ev) {
      ev.preventDefault();
      var from = Number(ev.dataTransfer.getData('text/plain'));
      if (isNaN(from) || from === index) return;
      var r = state.rules.splice(from, 1)[0];
      state.rules.splice(index, 0, r);
      renderRules();
      update();
      pushHistory();
      announceRule('Moved rule to position ' + (index + 1) + ' of ' + state.rules.length + '.');
    });
    handle.addEventListener('keydown', function (ev) {
      if (ev.altKey && ev.key === 'ArrowUp') { ev.preventDefault(); move(index, -1, 'up'); }
      else if (ev.altKey && ev.key === 'ArrowDown') { ev.preventDefault(); move(index, 1, 'down'); }
    });
    return li;
  }

  function renderRules() {
    var ol = $('rules');
    ol.innerHTML = '';
    state.rules.forEach(function (r, i) {
      ol.appendChild(renderRule(r, i, state.rules.length));
    });
    $('rules-empty').hidden = state.rules.length > 0;
    applyAdvancedVisibility();
    if (UI) UI.init(ol);
  }

  function removeRule(index) {
    var r = state.rules.splice(index, 1)[0];
    lastRemoved = { rule: r, index: index };
    renderRules();
    update();
    pushHistory();
    var n = announceRule('Removed rule ' + (r.name.trim() ? '“' + r.name.trim() + '”' : 'Untitled') + '. ');
    n.appendChild(h('button', { type: 'button', class: 'btn btn-secondary btn-sm', id: 'undo-remove', onclick: function () {
      if (!lastRemoved) return;
      state.rules.splice(Math.min(lastRemoved.index, state.rules.length), 0, lastRemoved.rule);
      var restored = lastRemoved.rule;
      lastRemoved = null;
      renderRules();
      update();
      pushHistory();
      announceRule('Restored rule.');
      var f = $(fid(restored, 'name'));
      if (f) f.focus();
    }, text: 'Undo' }));
    var next = state.rules[Math.min(index, state.rules.length - 1)];
    var target = next ? $(fid(next, 'name')) : $('rule-add');
    if (target) target.focus();
  }

  // ---------------------------------------------------------------- Basic/Advanced mode
  function applyAdvancedVisibility() {
    document.querySelectorAll('[data-advanced-only]').forEach(function (el) { el.hidden = !advanced; });
  }
  function setAdvanced(v) {
    advanced = v;
    Store.set(KEY_ADVANCED, v ? '1' : '0');
    $('advanced-toggle').checked = v;
    $('advanced-toggle').setAttribute('aria-checked', String(v));
    applyAdvancedVisibility();
    update();
  }

  // ---------------------------------------------------------------- YAML <-> form sync (advanced)
  function applyParsedToState(raw) {
    var next = blankState();
    next.defaultDays = raw.default_days_threshold === undefined || raw.default_days_threshold === null ? '' : String(raw.default_days_threshold);
    next.fallback = raw.fallback_playlist === undefined || raw.fallback_playlist === null ? '' : String(raw.fallback_playlist);
    if (raw.inbox_since === undefined || raw.inbox_since === null) next.inboxSince = '';
    else if (raw.inbox_since instanceof Date) next.inboxSince = raw.inbox_since.toISOString().slice(0, 10);
    else next.inboxSince = String(raw.inbox_since);
    if (raw.enrichment && typeof raw.enrichment === 'object' && typeof raw.enrichment.musicbrainz === 'boolean') next.musicbrainz = raw.enrichment.musicbrainz;
    if (raw.enrichment && typeof raw.enrichment === 'object' && typeof raw.enrichment.english_default === 'boolean') next.englishDefault = raw.enrichment.english_default;
    if (raw.logging && typeof raw.logging === 'object' && typeof raw.logging.include_track_names === 'boolean') next.includeTrackNames = raw.logging.include_track_names;
    var ai = raw.artist_in_playlist;
    if (ai && typeof ai === 'object' && !Array.isArray(ai)) {
      next.aipEnabled = true;
      next.aipMinTracks = ai.min_tracks === undefined || ai.min_tracks === null ? '3' : String(ai.min_tracks);
      next.aipMinDominance = ai.min_dominance === undefined || ai.min_dominance === null ? '0.9' : String(ai.min_dominance);
      next.aipExclude = Array.isArray(ai.exclude_playlists)
        ? ai.exclude_playlists.map(String).filter(function (n) { return n.toLowerCase().trim() !== 'vault_drx'; })
        : [];
    }
    var lp = raw.language_playlists;
    if (lp && typeof lp === 'object' && !Array.isArray(lp)) {
      Object.keys(lp).forEach(function (k) {
        var row = newLp();
        row.name = k;
        row.lang = lp[k] === null || lp[k] === undefined ? '' : (Lang.normalize(String(lp[k])) || String(lp[k]));
        next.langPlaylists.push(row);
      });
    }
    var rules = Array.isArray(raw.rules) ? raw.rules : [];
    rules.forEach(function (rr) {
      if (rr === null || typeof rr !== 'object' || Array.isArray(rr)) return;
      var rule = newRule();
      rule.pristine = false;
      rule.name = rr.name === undefined || rr.name === null ? '' : String(rr.name);
      rule.enabled = rr.enabled !== false;
      rule.target = rr.target_playlist === undefined || rr.target_playlist === null ? '' : String(rr.target_playlist);
      rule.days = rr.days_threshold === undefined || rr.days_threshold === null ? '' : String(rr.days_threshold);
      rule.create = rr.create_missing_playlists === true;
      rule.position = rr.target_position === 'top' ? 'top' : 'bottom';
      rule.match = dictToMatchList(rr.match);
      rule.unless = dictToMatchList(rr.unless);
      next.rules.push(rule);
    });
    next.revealAll = true;
    state = next;
    lastRemoved = null;
    syncGlobalControls();
    renderLp();
    renderRules();
    update();
    pushHistory();
  }

  function loadYamlText(text) {
    var status = $('import-status');
    var raw;
    try {
      raw = window.jsyaml.load(text);
    } catch (e) {
      status.className = 'notice show bad';
      status.textContent = 'Not valid YAML: ' + String(e.message).split('\n')[0];
      return false;
    }
    if (raw === null || raw === undefined) raw = {};
    if (typeof raw !== 'object' || Array.isArray(raw)) {
      status.className = 'notice show bad';
      status.textContent = 'Import failed: top level must be a mapping';
      return false;
    }
    var problems = V.validateConfig(raw).errors.map(function (e) { return e.msg; });
    applyParsedToState(raw);
    announceRule('');
    status.textContent = '';
    status.className = 'notice show' + (problems.length ? ' warn' : ' ok');
    status.appendChild(h('p', { text: 'Loaded ' + state.rules.length + (state.rules.length === 1 ? ' rule' : ' rules') + ' into the form.' + (problems.length ? ' The file has problems; unknown keys were left out, and other values are marked in the form:' : '') }));
    if (problems.length) status.appendChild(h('ul', null, problems.map(function (p) { return h('li', { text: p }); })));
    return true;
  }

  // Handles typing directly into the Advanced YAML editor.
  var syncYamlEdit = debounce(function () {
    var text = $('yaml-edit').value;
    var errBox = $('yaml-edit-err');
    var raw;
    try {
      raw = window.jsyaml.load(text);
    } catch (e) {
      errBox.textContent = 'YAML parse error: ' + String(e.message).split('\n')[0];
      return;
    }
    errBox.textContent = '';
    if (raw === null || raw === undefined) raw = {};
    if (typeof raw !== 'object' || Array.isArray(raw)) { errBox.textContent = 'Top level must be a mapping.'; return; }
    yamlEditSyncing = true;
    applyParsedToState(raw);
    yamlEditSyncing = false;
  }, 500);

  // ---------------------------------------------------------------- copy / download
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = h('textarea', { 'aria-hidden': 'true', class: 'sr-only' });
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy') ? resolve() : reject(new Error('copy failed')); } catch (e) { reject(e); } finally { ta.remove(); }
    });
  }
  function downloadText(text, filename) {
    var blob = new Blob([text], { type: 'text/yaml;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = h('a', { href: url, download: filename });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  // ---------------------------------------------------------------- versions (decision 28)
  function loadVersions() {
    try { return JSON.parse(Store.get(KEY_VERSIONS) || '[]'); } catch (e) { return []; }
  }
  function storeVersions(list) { Store.set(KEY_VERSIONS, JSON.stringify(list)); }
  function summarize() {
    var built = toData();
    var ruleCount = built.data.rules.length;
    var lpCount = Object.keys(built.data.language_playlists).length;
    return ruleCount + (ruleCount === 1 ? ' rule' : ' rules') + ', ' + lpCount + ' language playlist' + (lpCount === 1 ? '' : 's');
  }

  function saveVersion() {
    if (blocked('save')) return;
    var list = loadVersions();
    var doSave = function () {
      var v = { id: 'v' + Date.now() + '-' + Math.random().toString(36).slice(2, 7), savedAt: new Date().toISOString(), label: '', summary: summarize(), yaml: current.yaml };
      list.push(v);
      if (list.length > 5) list = list.slice(list.length - 5);
      storeVersions(list);
      savedSnapshot = current.yaml;
      renderVersions();
      $('action-status').textContent = 'Saved a version locally (' + list.length + ' of 5 kept). Use Download or Copy to get it into your fork.';
      if (UI) UI.toast('Configuration saved as a local version.', { type: 'success' });
    };
    if (list.length >= 5) {
      if (UI && UI.confirm) {
        UI.confirm({ title: 'Drop the oldest version?', message: 'You already have 5 saved versions, the maximum kept. Saving now will permanently drop the oldest one.', confirmLabel: 'Save and drop oldest', danger: true })
          .then(function (ok) { if (ok) doSave(); });
      } else if (window.confirm('Saving will drop the oldest of your 5 versions. Continue?')) doSave();
    } else doSave();
  }

  function lineDiff(a, b) {
    var A = a.split('\n'), B = b.split('\n');
    var n = A.length, m = B.length;
    var dp = new Array(n + 1);
    for (var i = 0; i <= n; i++) { dp[i] = new Array(m + 1).fill(0); }
    for (i = n - 1; i >= 0; i--) {
      for (var j = m - 1; j >= 0; j--) {
        dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    var out = [];
    i = 0; j = 0;
    while (i < n && j < m) {
      if (A[i] === B[j]) { out.push({ type: 'same', text: A[i] }); i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: 'removed', text: A[i] }); i++; }
      else { out.push({ type: 'added', text: B[j] }); j++; }
    }
    while (i < n) { out.push({ type: 'removed', text: A[i++] }); }
    while (j < m) { out.push({ type: 'added', text: B[j++] }); }
    return out;
  }

  function ruleNames(yamlText) {
    try {
      var d = window.jsyaml.load(yamlText) || {};
      return (d.rules || []).map(function (r) { return r && r.name; }).filter(Boolean);
    } catch (e) { return []; }
  }

  function openCompare(version) {
    var tbody = document.querySelector('#compare-rules-table tbody');
    tbody.innerHTML = '';
    var before = ruleNames(version.yaml), after = ruleNames(current.yaml);
    var all = [];
    before.forEach(function (n) { if (all.indexOf(n) === -1) all.push(n); });
    after.forEach(function (n) { if (all.indexOf(n) === -1) all.push(n); });
    all.forEach(function (name) {
      var inBefore = before.indexOf(name) !== -1, inAfter = after.indexOf(name) !== -1;
      var status = inBefore && inAfter ? 'kept' : inBefore ? 'removed' : 'added';
      tbody.appendChild(h('tr', null, h('td', { text: name }), h('td', null, h('span', { class: 'badge' + (status === 'added' ? ' badge-success' : status === 'removed' ? ' badge-danger' : ''), text: status }))));
    });
    var diff = lineDiff(version.yaml, current.yaml);
    var pre = $('compare-yaml-diff');
    pre.innerHTML = '';
    diff.forEach(function (d) {
      var prefix = d.type === 'added' ? '+ ' : d.type === 'removed' ? '- ' : '  ';
      pre.appendChild(h('div', { class: 'diff-line diff-' + d.type, text: prefix + d.text }));
    });
    if (UI) UI.open('compare-modal');
  }

  function renderVersions() {
    var list = loadVersions();
    var ul = $('versions-list');
    ul.innerHTML = '';
    $('versions-empty').hidden = list.length > 0;
    list.slice().reverse().forEach(function (v) {
      var labelInput = h('input', { class: 'input input-inline', type: 'text', 'aria-label': 'Label for version saved ' + v.savedAt, placeholder: 'Add a label…' });
      labelInput.value = v.label || '';
      labelInput.addEventListener('change', function () {
        v.label = labelInput.value;
        var all = loadVersions().map(function (x) { return x.id === v.id ? v : x; });
        storeVersions(all);
      });
      var li = h('li', { class: 'card version-card' },
        h('div', { class: 'version-meta' }, h('strong', { text: new Date(v.savedAt).toLocaleString() }), h('span', { class: 'hint', text: v.summary })),
        labelInput,
        h('div', { class: 'actions' },
          h('button', { type: 'button', class: 'btn btn-secondary btn-sm', onclick: function () { openCompare(v); }, text: 'Compare with current' }),
          h('button', { type: 'button', class: 'btn btn-secondary btn-sm', onclick: function () { restoreVersion(v); }, text: 'Restore' }),
          h('button', { type: 'button', class: 'btn btn-secondary btn-sm', onclick: function () { downloadText(v.yaml, 'config.yaml'); }, text: 'Download' })));
      ul.appendChild(li);
    });
  }

  function isDirty() { return current.yaml !== savedSnapshot; }

  function restoreVersion(v) {
    var doRestore = function () {
      var raw = window.jsyaml.load(v.yaml) || {};
      applyParsedToState(raw);
      savedSnapshot = null; // restoring loads it as a *draft*; only becomes a version again once saved
      if (UI) UI.close('versions-drawer');
      if (UI) UI.toast('Restored version from ' + new Date(v.savedAt).toLocaleString() + '. Save again to keep it.', { type: 'info' });
    };
    if (isDirty() && UI && UI.confirm) {
      UI.confirm({ title: 'Discard unsaved changes?', message: 'Restoring this version replaces your current unsaved draft.', confirmLabel: 'Restore', danger: true })
        .then(function (ok) { if (ok) doRestore(); });
    } else doRestore();
  }

  function downloadAllVersions() {
    var list = loadVersions();
    list.forEach(function (v, i) { setTimeout(function () { downloadText(v.yaml, 'config.' + v.id + '.yaml'); }, i * 300); });
  }

  // ---------------------------------------------------------------- Save to GitHub (Phase 7, decision 39/41)
  // Reuses the shared PAT component (assets/github-pat.js) built for the dashboard's run-now button --
  // same deep-link-and-paste flow, same sessionStorage-only token, just Contents: write instead of +Actions.
  // P1-5: this exact scope set is also this feature's own sessionStorage key, so it can never collide with
  // run-now's Contents+Actions token even in the same tab.
  var GH_SCOPES = [{ name: 'contents', level: 'write' }];

  function ownerRepoParts() {
    var onPages = /\.github\.io$/i.test(location.hostname);
    var owner = onPages ? location.hostname.replace(/\.github\.io$/i, '') : null;
    var seg = location.pathname.split('/').filter(Boolean)[0];
    var repo = onPages && seg ? seg : null;
    return { owner: owner, repo: repo, real: !!(owner && repo) };
  }

  function ghSaveBody() {
    var body = $('github-save-body');
    body.innerHTML = '';
    (function add(list) {
      list.forEach(function (c) { if (c) body.appendChild(c); });
    })(Array.prototype.slice.call(arguments));
    return body;
  }

  function b64EncodeUtf8(str) { return window.btoa(unescape(encodeURIComponent(str))); }
  function b64DecodeUtf8(b64) { return decodeURIComponent(escape(window.atob(String(b64 || '').replace(/\n/g, '')))); }

  function openGithubSave() {
    if (blocked('save to GitHub')) return;
    var rr = ownerRepoParts();
    if (UI) UI.open('github-save-dialog');
    if (!rr.real) {
      ghSaveBody(h('p', { text: 'This only works once the site is published on GitHub Pages, at <you>.github.io/<your-fork>/ -- it could not tell which repository to save to from this address.' }));
      return;
    }
    var token = window.GithubPAT.get(rr.owner, rr.repo, GH_SCOPES);
    if (token) renderGithubCommitForm(rr, token); else renderGithubConnect(rr);
  }

  function renderGithubConnect(rr) {
    var url = window.GithubPAT.tokenUrl({
      owner: rr.owner, name: 'LikedZero Configure (' + rr.repo + ')',
      description: 'Lets Configure commit config.yaml to ' + rr.owner + '/' + rr.repo + '. Delete this token any time.',
      scopes: GH_SCOPES,
    });
    var status = h('p', { class: 'status', role: 'status' });
    var input = h('input', { class: 'input', id: 'gh-token', type: 'password', autocomplete: 'off', spellcheck: 'false', placeholder: 'github_pat_…' });
    ghSaveBody(
      h('ol', { class: 'steps' },
        h('li', null, h('a', { href: url, target: '_blank', rel: 'noopener', text: 'Create a token on GitHub' }), ' — name, description and the Contents permission are pre-filled.'),
        h('li', { text: 'Under Repository access, choose "Only select repositories" and pick ' + rr.owner + '/' + rr.repo + ' (GitHub does not let a link pre-select the repository).' }),
        h('li', { text: 'Confirm the permission still shows "Contents: Read and write", then click Generate token.' }),
        h('li', { text: 'Paste the token below. It stays only in this browser tab (sessionStorage), never written to disk.' })),
      h('div', { class: 'field' }, h('label', { class: 'label', for: 'gh-token', text: 'Fine-grained personal access token' }), input),
      status,
      h('button', {
        type: 'button', class: 'btn btn-primary', text: 'Save & verify',
        onclick: function () {
          var tok = input.value.trim();
          if (!tok) { status.textContent = 'Paste a token first.'; return; }
          status.textContent = 'Checking with GitHub…';
          window.GithubPAT.verify(rr.owner, rr.repo, tok, GH_SCOPES).then(function (res) {
            if (!res.ok) { status.textContent = res.message; return; }
            window.GithubPAT.set(rr.owner, rr.repo, GH_SCOPES, tok);
            renderGithubCommitForm(rr, tok);
          });
        },
      })
    );
  }

  function githubGetFile(rr, token) {
    return fetch('https://api.github.com/repos/' + rr.owner + '/' + rr.repo + '/contents/config.yaml', {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    }).then(function (r) {
      if (r.status === 404) return { exists: false };
      return r.json().then(function (data) {
        if (!r.ok) throw new Error('HTTP ' + r.status + (data && data.message ? ': ' + data.message : ''));
        return { exists: true, sha: data.sha, content: b64DecodeUtf8(data.content) };
      });
    });
  }

  function githubPutFile(rr, token, message, sha) {
    // decision 46/P2: no `branch` field -- GitHub's Contents API defaults a PUT to the repo's real default
    // branch when it's omitted, same as the GET above already does. Hardcoding "main" here forced a write to
    // the wrong branch on any fork whose default branch is something else.
    var body = { message: message, content: b64EncodeUtf8(current.yaml) };
    if (sha) body.sha = sha;
    return fetch('https://api.github.com/repos/' + rr.owner + '/' + rr.repo + '/contents/config.yaml', {
      method: 'PUT',
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().then(function (data) { return { status: r.status, ok: r.ok, data: data }; }); });
  }

  function renderGithubCommitForm(rr, token) {
    var msgInput = h('input', { class: 'input', id: 'gh-commit-msg', type: 'text', value: 'Update config.yaml via Configure' });
    var status = h('p', { class: 'status', role: 'status' });
    ghSaveBody(
      h('p', { class: 'hint', text: 'Commits config.yaml straight to ' + rr.owner + '/' + rr.repo + ' (its default branch).' }),
      h('div', { class: 'field' }, h('label', { class: 'label', for: 'gh-commit-msg', text: 'Commit message' }), msgInput),
      status,
      h('div', { class: 'actions' },
        h('button', { type: 'button', class: 'btn btn-primary', text: 'Commit', onclick: function () { doGithubCommit(rr, token, msgInput.value, null); } }),
        h('button', {
          type: 'button', class: 'btn btn-secondary btn-sm', text: 'Forget token',
          onclick: function () { window.GithubPAT.clear(rr.owner, rr.repo, GH_SCOPES); renderGithubConnect(rr); },
        }))
    );
  }

  function doGithubCommit(rr, token, msg, forcedSha) {
    var status = document.querySelector('#github-save-body .status');
    msg = (msg || '').trim() || 'Update config.yaml via Configure';
    if (status) status.textContent = 'Committing…';
    var go = function (sha) {
      return githubPutFile(rr, token, msg, sha).then(function (res) {
        if (res.ok) {
          if (UI) UI.toast('config.yaml committed to GitHub.', { type: 'success' });
          $('action-status').textContent = 'Saved to GitHub: ' + rr.owner + '/' + rr.repo + '.';
          loadGithubVersions(rr, token);
          if (UI) setTimeout(function () { UI.close('github-save-dialog'); }, 700);
        } else if (res.status === 409) {
          renderGithubConflict(rr, token, msg);
        } else if (res.status === 401) {
          window.GithubPAT.clear(rr.owner, rr.repo, GH_SCOPES);
          renderGithubConnect(rr);
          var s = document.querySelector('#github-save-body .status');
          if (s) s.textContent = 'GitHub rejected the token (invalid or expired). Reconnect above.';
        } else if (status) {
          status.textContent = 'GitHub returned HTTP ' + res.status + (res.data && res.data.message ? ': ' + res.data.message : '') + '.';
        }
      });
    };
    var onError = function (e) { if (status) status.textContent = 'Could not reach GitHub (' + (e && e.message ? e.message : 'network error') + ').'; };
    if (forcedSha !== null) { go(forcedSha).catch(onError); return; }
    githubGetFile(rr, token).then(function (f) { return go(f.exists ? f.sha : undefined); }).catch(onError);
  }

  function renderGithubConflict(rr, token, msg) {
    ghSaveBody(h('p', { class: 'status', text: 'Checking what changed…' }));
    githubGetFile(rr, token).then(function (f) {
      var diff = lineDiff(f.content || '', current.yaml);
      var pre = h('pre', { class: 'yaml' });
      diff.forEach(function (d) {
        var prefix = d.type === 'added' ? '+ ' : d.type === 'removed' ? '- ' : '  ';
        pre.appendChild(h('div', { class: 'diff-line diff-' + d.type, text: prefix + d.text }));
      });
      ghSaveBody(
        h('p', null, h('strong', { text: 'Someone (or something) changed config.yaml on GitHub since you last loaded it.' }),
          ' Overwriting replaces their version with yours below — nothing is merged automatically.'),
        pre,
        h('div', { class: 'actions' },
          h('button', { type: 'button', class: 'btn btn-primary', text: "Overwrite GitHub's version with mine", onclick: function () { doGithubCommit(rr, token, msg, f.sha); } }),
          h('button', { type: 'button', class: 'btn btn-secondary', text: 'Cancel', onclick: function () { renderGithubCommitForm(rr, token); } }))
      );
    }).catch(function (e) {
      ghSaveBody(h('p', { class: 'status', text: 'Could not reach GitHub (' + (e && e.message ? e.message : 'network error') + ').' }));
    });
  }

  // ---- "On GitHub" section of the Versions drawer: last 5 commits to config.yaml, lazy-loaded on open.
  function githubFileAtRef(rr, token, ref) {
    return fetch('https://api.github.com/repos/' + rr.owner + '/' + rr.repo + '/contents/config.yaml?ref=' + encodeURIComponent(ref), {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (b) { throw new Error('HTTP ' + r.status + (b && b.message ? ': ' + b.message : '')); });
      return r.json();
    }).then(function (data) { return b64DecodeUtf8(data.content); });
  }

  function compareGithubCommit(rr, token, sha) {
    githubFileAtRef(rr, token, sha).then(function (yaml) { openCompare({ yaml: yaml, savedAt: new Date().toISOString() }); })
      .catch(function (e) { if (UI) UI.toast('Could not load that commit: ' + (e && e.message ? e.message : 'network error'), { type: 'danger' }); });
  }

  function restoreGithubCommit(rr, token, sha) {
    githubFileAtRef(rr, token, sha).then(function (yaml) { restoreVersion({ yaml: yaml, savedAt: new Date().toISOString() }); })
      .catch(function (e) { if (UI) UI.toast('Could not load that commit: ' + (e && e.message ? e.message : 'network error'), { type: 'danger' }); });
  }

  function loadGithubVersions(rr, token) {
    var list = $('versions-github-list'), hint = $('versions-github-hint');
    if (!list || !hint) return;
    rr = rr || ownerRepoParts();
    if (!rr.real) { hint.textContent = 'Only available once this site is published on GitHub Pages.'; list.innerHTML = ''; return; }
    token = token || window.GithubPAT.get(rr.owner, rr.repo, GH_SCOPES);
    if (!token) {
      hint.innerHTML = '';
      hint.appendChild(document.createTextNode('Connect via '));
      var b = h('button', { type: 'button', class: 'btn btn-secondary btn-sm', text: 'Save to GitHub', onclick: function () { if (UI) UI.close('versions-drawer'); openGithubSave(); } });
      hint.appendChild(b);
      hint.appendChild(document.createTextNode(' to see commit history here.'));
      list.innerHTML = '';
      return;
    }
    hint.textContent = 'The last 5 commits to config.yaml on ' + rr.owner + '/' + rr.repo + '.';
    list.innerHTML = '';
    list.appendChild(h('li', { class: 'hint', text: 'Loading…' }));
    fetch('https://api.github.com/repos/' + rr.owner + '/' + rr.repo + '/commits?path=config.yaml&per_page=5', {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    }).then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (commits) {
        list.innerHTML = '';
        if (!commits.length) { list.appendChild(h('li', { class: 'hint', text: 'No commits to config.yaml yet.' })); return; }
        commits.forEach(function (c) {
          var when = new Date(c.commit.author.date).toLocaleString();
          var msg = c.commit.message.split('\n')[0];
          list.appendChild(h('li', { class: 'card version-card' },
            h('div', { class: 'version-meta' }, h('strong', { text: when }), h('span', { class: 'hint', text: msg })),
            h('div', { class: 'actions' },
              h('button', { type: 'button', class: 'btn btn-secondary btn-sm', text: 'Compare with current', onclick: function () { compareGithubCommit(rr, token, c.sha); } }),
              h('button', { type: 'button', class: 'btn btn-secondary btn-sm', text: 'Restore', onclick: function () { restoreGithubCommit(rr, token, c.sha); } }))));
        });
      }).catch(function (e) {
        list.innerHTML = '';
        list.appendChild(h('li', { class: 'hint', text: 'Could not load GitHub history: ' + (e && e.message ? e.message : 'network error') }));
      });
  }

  // ---------------------------------------------------------------- autosave draft + beforeunload
  function saveDraft() {
    var payload = JSON.stringify({ nextId: nextId, state: state, advanced: advanced });
    Store.set(KEY_DRAFT, payload);
  }
  function loadDraft() {
    var raw = Store.get(KEY_DRAFT);
    if (!raw) return false;
    try {
      var parsed = JSON.parse(raw);
      nextId = parsed.nextId;
      state = parsed.state;
      return true;
    } catch (e) { return false; }
  }
  window.addEventListener('beforeunload', function (ev) {
    if (isDirty()) { ev.preventDefault(); ev.returnValue = ''; return ''; }
  });

  // ---------------------------------------------------------------- stepper navigation
  function goStep(n) {
    currentStep = n;
    for (var i = 1; i <= 4; i++) {
      $('step-' + i).hidden = i !== n;
      var tab = $('step-tab-' + i);
      tab.classList.toggle('is-done', i < n);
      if (i === n) tab.setAttribute('aria-current', 'step'); else tab.removeAttribute('aria-current');
    }
    var active = $('step-' + n);
    var heading = active.querySelector('h2');
    if (heading) heading.setAttribute('tabindex', '-1');
    if (heading) heading.focus();
  }

  // ---------------------------------------------------------------- templates
  function applyTemplate(name) {
    var next = blankState();
    if (name === 'language') {
      var lp = newLp(); lp.name = 'Chill Hindi'; lp.lang = 'hindi';
      next.langPlaylists.push(lp);
      var r = newRule(); r.pristine = false; r.name = 'Hindi to Dil'; r.target = 'Dil'; r.match = [{ key: 'language_in', value: ['hindi'] }];
      next.rules.push(r);
    } else if (name === 'artist') {
      var r2 = newRule(); r2.pristine = false; r2.name = 'Favorite chill artists'; r2.target = 'Chillhop Favorites'; r2.match = [{ key: 'artist_in', value: ['Bonobo', 'Tycho'] }];
      next.rules.push(r2);
    }
    state = next;
    $('templates').hidden = true;
    $('wizard').hidden = false;
    syncGlobalControls();
    renderLp();
    renderRules();
    update();
    pushHistory();
    saveDraft();
    goStep(1);
  }

  // ---------------------------------------------------------------- schema drawer
  function renderSchema() {
    var tbody = document.querySelector('#schema-table tbody');
    if (!tbody || !window.SpotiSchema) return;
    tbody.innerHTML = '';
    window.SpotiSchema.SCHEMA.forEach(function (row) {
      tbody.appendChild(h('tr', null, h('td', null, h('code', { text: row.key })), h('td', { text: row.type }), h('td', { text: row.def }), h('td', { text: row.note })));
    });
  }

  // ---------------------------------------------------------------- wiring
  function wire() {
    $('g-days').addEventListener('input', function (e) { state.defaultDays = e.target.value; update(); });
    $('g-days').addEventListener('change', pushHistory);
    $('g-fallback').addEventListener('input', function (e) { state.fallback = e.target.value; update(); });
    $('g-fallback').addEventListener('change', pushHistory);
    $('g-inbox-since').addEventListener('input', function (e) { state.inboxSince = e.target.value; update(); });
    $('g-inbox-since').addEventListener('change', pushHistory);
    $('g-mb').addEventListener('change', function (e) { state.musicbrainz = e.target.checked; update(); pushHistory(); });
    $('g-en').addEventListener('change', function (e) { state.englishDefault = e.target.checked; update(); pushHistory(); });
    $('g-log').addEventListener('change', function (e) {
      state.includeTrackNames = e.target.checked;
      e.target.setAttribute('aria-checked', String(e.target.checked));
      update(); pushHistory();
    });
    $('g-aip-enabled').addEventListener('change', function (e) {
      state.aipEnabled = e.target.checked;
      e.target.setAttribute('aria-checked', String(e.target.checked));
      update(); pushHistory();
    });
    $('g-aip-min-tracks').addEventListener('input', function (e) { state.aipMinTracks = e.target.value; update(); });
    $('g-aip-min-tracks').addEventListener('change', pushHistory);
    $('g-aip-min-dominance').addEventListener('input', function (e) { state.aipMinDominance = e.target.value; update(); });
    $('g-aip-min-dominance').addEventListener('change', pushHistory);
    (function () {
      var input = $('aip-exclude-add');
      var commit = function () {
        var text = input.value.trim();
        if (!text || text.toLowerCase() === 'vault_drx') { input.value = ''; return; }
        var dup = state.aipExclude.some(function (x) { return x.toLowerCase() === text.toLowerCase(); });
        if (!dup) state.aipExclude.push(text);
        input.value = '';
        renderAipExclude();
        update();
        pushHistory();
        input.focus();
      };
      input.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); commit(); } });
      $('aip-exclude-add-btn').addEventListener('click', commit);
    })();
    $('lp-add').addEventListener('click', function () {
      var row = newLp();
      state.langPlaylists.push(row);
      renderLp();
      update();
      pushHistory();
      $('lp' + row.id + '-name').focus();
    });
    $('rule-add').addEventListener('click', function () {
      var r = newRule();
      state.rules.push(r);
      renderRules();
      update();
      pushHistory();
      announceRule('Added rule ' + state.rules.length + '.');
      $(fid(r, 'name')).focus();
    });

    document.querySelectorAll('[data-next]').forEach(function (btn) { btn.addEventListener('click', function () { goStep(Math.min(4, currentStep + 1)); }); });
    document.querySelectorAll('[data-back]').forEach(function (btn) { btn.addEventListener('click', function () { goStep(Math.max(1, currentStep - 1)); }); });
    document.querySelectorAll('#stepper li').forEach(function (li) {
      var btn = li.querySelector('button');
      btn.addEventListener('click', function () { goStep(Number(li.getAttribute('data-step'))); });
    });

    $('advanced-toggle').addEventListener('change', function (e) { setAdvanced(e.target.checked); });

    $('tpl-language').addEventListener('click', function () { applyTemplate('language'); });
    $('tpl-artist').addEventListener('click', function () { applyTemplate('artist'); });
    $('tpl-blank').addEventListener('click', function () { applyTemplate('blank'); });

    $('import-btn').addEventListener('click', function () {
      var text = $('import-text').value;
      $('import-status').innerHTML = '';
      if (!text.trim()) { $('import-status').className = 'notice show bad'; $('import-status').textContent = 'Paste some YAML, drop a file, or choose one first.'; return; }
      loadYamlText(text);
    });
    $('import-file').addEventListener('change', function (e) {
      var file = e.target.files && e.target.files[0];
      if (!file) return;
      $('import-status').innerHTML = '';
      file.text().then(function (text) { $('import-text').value = text; loadYamlText(text); });
    });
    var dropZone = $('import-drop');
    ['dragenter', 'dragover'].forEach(function (evt) { dropZone.addEventListener(evt, function (e) { e.preventDefault(); dropZone.classList.add('drag-over'); }); });
    ['dragleave', 'drop'].forEach(function (evt) { dropZone.addEventListener(evt, function () { dropZone.classList.remove('drag-over'); }); });
    dropZone.addEventListener('drop', function (e) {
      e.preventDefault();
      var file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (!file) return;
      file.text().then(function (text) { $('import-text').value = text; loadYamlText(text); });
    });

    $('yaml-edit').addEventListener('input', syncYamlEdit);

    $('save-btn').addEventListener('click', saveVersion);
    $('save-github-btn').addEventListener('click', openGithubSave);
    document.addEventListener('ui:open', function (e) { if (e.detail && e.detail.id === 'versions-drawer') loadGithubVersions(); });
    var dbtn = $('download-btn');
    if (dbtn) dbtn.addEventListener('click', function () {
      if (blocked('download')) return;
      downloadText(current.yaml, 'config.yaml');
      $('action-status').textContent = 'Downloaded config.yaml.';
    });

    document.addEventListener('keydown', function (ev) {
      var mod = ev.ctrlKey || ev.metaKey;
      if (!mod) return;
      var t = ev.target;
      if (t && (t.id === 'yaml-edit' || t.id === 'import-text')) return; // native undo inside raw text areas
      if (ev.key === 'z' || ev.key === 'Z') { ev.preventDefault(); if (ev.shiftKey) redo(); else undo(); }
      else if (ev.key === 'y' || ev.key === 'Y') { ev.preventDefault(); redo(); }
    });
  }

  function init() {
    var dl = $('lang-options');
    Lang.CANONICAL.forEach(function (n) { dl.appendChild(h('option', { value: n })); });
    if (storageBlocked) $('storage-banner').hidden = false;

    renderSchema();
    wire();

    var versions = loadVersions();
    var hadDraft = loadDraft();
    if (!hadDraft && versions.length === 0) {
      $('templates').hidden = false;
      $('wizard').hidden = true;
    } else {
      $('templates').hidden = true;
      $('wizard').hidden = false;
      goStep(1);
    }

    syncGlobalControls();
    setAdvanced(advanced);
    renderLp();
    renderRules();
    renderVersions();
    update();
    pushHistory();
    if (versions.length) savedSnapshot = versions[versions.length - 1].yaml;

    if (UI) UI.init(document);

    window.__spotiBuilder = { ready: true };
    if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
      navigator.serviceWorker.register('../sw.js').catch(function () { /* offline support is optional */ });
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
