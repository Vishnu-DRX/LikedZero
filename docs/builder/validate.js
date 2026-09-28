// Port of src/config.py (parse_config) to JavaScript. Keep in sync with the Python validator:
// same rules, same messages. Returns a list of errors; each error also says which form field it belongs to.
(function (root) {
  'use strict';

  var TOP_LEVEL_KEYS = ['default_days_threshold', 'fallback_playlist', 'rules', 'language_playlists', 'enrichment', 'logging', 'inbox_since', 'artist_in_playlist'];
  var ENRICHMENT_KEYS = ['musicbrainz', 'english_default'];
  var LOGGING_KEYS = ['include_track_names'];
  var ARTIST_IN_PLAYLIST_KEYS = ['min_tracks', 'min_dominance', 'exclude_playlists'];
  var RULE_KEYS = ['name', 'enabled', 'match', 'unless', 'target_playlist', 'days_threshold', 'create_missing_playlists', 'target_position'];
  var AUTO_TARGET = 'auto'; // design/proposals/artist_in_playlist.md: sentinel, valid only with match.artist_in_playlist
  var LIST_MATCH_KEYS = ['artist_in', 'genre_contains', 'language_in', 'artist_country_in'];
  var INT_MATCH_KEYS = ['release_year_before', 'release_year_after'];
  var STR_MATCH_KEYS = ['track_name_contains', 'album_name_contains'];
  var BOOL_MATCH_KEYS = ['explicit'];
  var TRUE_ONLY_MATCH_KEYS = ['artist_in_playlist', 'any']; // no defined meaning for false; only true is a valid gate
  var ANY_OF_KEY = 'any_of'; // design/proposals/more-conditions.md: OR-groups, value is a list of match-condition groups
  var MATCH_KEYS = LIST_MATCH_KEYS.concat(INT_MATCH_KEYS, STR_MATCH_KEYS, BOOL_MATCH_KEYS, TRUE_ONLY_MATCH_KEYS, [ANY_OF_KEY]);
  var COUNTRY_CODE_RE = /^[A-Za-z]{2}$/;

  function has(list, key) { return list.indexOf(key) !== -1; }
  function isInt(v) { return typeof v === 'number' && isFinite(v) && Math.floor(v) === v; }
  function nonemptyStr(v) { return typeof v === 'string' && v.trim() !== ''; }
  function isMap(v) { return v !== null && typeof v === 'object' && !Array.isArray(v) && !(v instanceof Date); }

  function isValidIsoDate(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return false;
    var y = +m[1], mo = +m[2], d = +m[3];
    if (mo < 1 || mo > 12) return false;
    var dim = [31, (y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return d >= 1 && d <= dim[mo - 1];
  }

  // Python repr() of a str, as used in the '!r' messages.
  function pyRepr(s) {
    s = String(s);
    var q = s.indexOf("'") !== -1 && s.indexOf('"') === -1 ? '"' : "'";
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (c === '\\') out += '\\\\';
      else if (c === q) out += '\\' + q;
      else if (c === '\n') out += '\\n';
      else if (c === '\t') out += '\\t';
      else if (c === '\r') out += '\\r';
      else out += c;
    }
    return q + out + q;
  }

  // Shared by rule `match`, rule `unless` (label='unless') and each `any_of` branch (forbidArtistInPlaylist +
  // forbidAnyOf true -- design/proposals/more-conditions.md: `artist_in_playlist`'s `auto` target is resolved
  // from the rule's top-level `match` only, so it cannot hide inside `unless`/`any_of`; nested `any_of` is
  // disallowed to keep the structure to one level). Mirrors src/config.py's `_validate_match` message-for-message.
  function validateMatch(match, where, ri, errors, label, forbidArtistInPlaylist, forbidAnyOf) {
    label = label || 'match';
    function add(field, short) { errors.push({ msg: where + ': ' + short, short: short, rule: ri, field: field }); }
    if (!isMap(match) || Object.keys(match).length === 0) {
      add(label, "'" + label + "' must be a non-empty mapping");
      return {};
    }
    var clean = {};
    Object.keys(match).forEach(function (key) {
      var value = match[key];
      var field = label + '.' + key;
      if (!has(MATCH_KEYS, key)) {
        add(label, "unknown " + label + " key '" + key + "'");
      } else if (key === 'artist_in_playlist' && forbidArtistInPlaylist) {
        add(field, "'artist_in_playlist' is only allowed as a top-level 'match' condition " +
          "(paired with target_playlist: auto), not inside 'unless' or an 'any_of' group");
      } else if (key === ANY_OF_KEY) {
        if (forbidAnyOf) {
          add(field, "'any_of' cannot be nested inside another 'any_of' group");
        } else if (!Array.isArray(value) || value.length === 0) {
          add(field, "'any_of' must be a non-empty list of match-condition groups");
        } else {
          var cleanGroups = [];
          for (var gi = 0; gi < value.length; gi++) {
            var group = value[gi];
            var groupWhere = where + '.any_of[' + gi + ']';
            if (!isMap(group) || Object.keys(group).length === 0) {
              errors.push({ msg: groupWhere + ": each 'any_of' group must be a non-empty mapping", short: "each 'any_of' group must be a non-empty mapping", rule: ri, field: field });
              continue;
            }
            var before = errors.length;
            var cleaned = validateMatch(group, groupWhere, ri, errors, label, true, true);
            if (errors.length === before) cleanGroups.push(cleaned);
          }
          if (cleanGroups.length) clean[key] = cleanGroups;
        }
      } else if (has(LIST_MATCH_KEYS, key)) {
        if (!Array.isArray(value) || value.length === 0 || !value.every(nonemptyStr)) {
          add(field, "'" + key + "' must be a non-empty list of non-empty strings");
        } else if (key === 'language_in') {
          var langOk = true;
          for (var i = 0; i < value.length; i++) {
            if (root.SpotiLang.normalize(value[i]) === null) {
              add(field, 'unknown language ' + pyRepr(value[i]) + " in 'language_in' (e.g. " +
                root.SpotiLang.CANONICAL.slice(0, 6).join(', ') + ', or an ISO code)');
              langOk = false;
              break;
            }
          }
          if (langOk) clean[key] = value.map(function (v) { return root.SpotiLang.normalize(v); });
        } else if (key === 'artist_country_in') {
          var bad = value.filter(function (v) { return !COUNTRY_CODE_RE.test(v.trim()); });
          if (bad.length) {
            add(field, "invalid country code " + pyRepr(bad[0]) + " in 'artist_country_in' (use a 2-letter ISO code, e.g. IN, US)");
          } else {
            clean[key] = value.map(function (v) { return v.trim().toUpperCase(); });
          }
        } else {
          clean[key] = value.slice();
        }
      } else if (has(INT_MATCH_KEYS, key)) {
        if (!isInt(value) || value < 1 || value > 9999) add(field, "'" + key + "' must be a year (integer 1-9999)");
        else clean[key] = value;
      } else if (has(STR_MATCH_KEYS, key)) {
        if (!nonemptyStr(value)) add(field, "'" + key + "' must be a non-empty string");
        else clean[key] = value;
      } else if (has(TRUE_ONLY_MATCH_KEYS, key)) {
        if (value !== true) add(field, "'" + key + "' must be true (there is no defined meaning for false)");
        else clean[key] = true;
      } else if (typeof value !== 'boolean') {
        add(field, "'" + key + "' must be true or false");
      } else {
        clean[key] = value;
      }
    });
    return clean;
  }

  function validateRule(raw, index, errors) {
    if (!isMap(raw)) {
      errors.push({ msg: 'rules[' + index + ']: must be a mapping', short: 'must be a mapping', rule: index, field: null });
      return null;
    }
    var name = raw.name;
    var where = nonemptyStr(name) ? 'rules[' + index + '] (' + pyRepr(name) + ')' : 'rules[' + index + ']';
    function add(field, short) { errors.push({ msg: where + ': ' + short, short: short, rule: index, field: field }); }

    if (!nonemptyStr(name)) add('name', "'name' is required and must be a non-empty string");
    Object.keys(raw).forEach(function (key) {
      if (!has(RULE_KEYS, key)) add(null, "unknown key '" + key + "'");
    });
    if (!nonemptyStr(raw.target_playlist)) add('target_playlist', "'target_playlist' is required and must be a non-empty string");
    var isAutoTarget = nonemptyStr(raw.target_playlist) && raw.target_playlist.trim().toLowerCase() === AUTO_TARGET;
    var enabled = 'enabled' in raw ? raw.enabled : true;
    if (typeof enabled !== 'boolean') add('enabled', "'enabled' must be true or false");
    var create = 'create_missing_playlists' in raw ? raw.create_missing_playlists : false;
    if (typeof create !== 'boolean') add('create_missing_playlists', "'create_missing_playlists' must be true or false");
    var position = 'target_position' in raw ? raw.target_position : 'bottom';
    if (position !== 'top' && position !== 'bottom') add('target_position', "'target_position' must be 'top' or 'bottom'");
    var days = raw.days_threshold;
    if (days !== undefined && days !== null && (!isInt(days) || days < 0)) {
      add('days_threshold', "'days_threshold' must be an integer >= 0");
    }
    validateMatch(raw.match, where, index, errors);
    // Mirrors config.py: `uses_auto_artist` reflects the CLEANED value (only true when the key is literally
    // `true`), so an invalid `artist_in_playlist` value reports its own error plus this pairing error too, same
    // as the Python side.
    var usesAutoArtist = isMap(raw.match) && raw.match.artist_in_playlist === true;
    if (isAutoTarget && !usesAutoArtist) add('target_playlist', "target_playlist '" + AUTO_TARGET + "' is only valid with match: {artist_in_playlist: true}");
    if (usesAutoArtist && !isAutoTarget) add('target_playlist', "match 'artist_in_playlist' requires target_playlist: " + AUTO_TARGET);

    // design/proposals/more-conditions.md: 'unless' is optional -- absent or explicit null means no exceptions.
    if ('unless' in raw && raw.unless !== null && raw.unless !== undefined) {
      validateMatch(raw.unless, where, index, errors, 'unless', true, false);
    }
    return nonemptyStr(name) ? name : null;
  }

  // data: an already-parsed document (what yaml.safe_load would return). Returns {errors: [...]}.
  function validateConfig(data) {
    var errors = [];
    function top(field, msg, extra) {
      var e = { msg: msg, short: msg, rule: null, field: field };
      if (extra) for (var k in extra) e[k] = extra[k];
      errors.push(e);
    }
    if (data === null || data === undefined) data = {};
    if (!isMap(data)) return { errors: [{ msg: 'top level must be a mapping', short: 'top level must be a mapping', rule: null, field: null }] };

    Object.keys(data).forEach(function (key) {
      if (!has(TOP_LEVEL_KEYS, key)) top(null, "unknown top-level key '" + key + "'");
    });

    var days = 'default_days_threshold' in data ? data.default_days_threshold : 14;
    if (!isInt(days) || days < 0) top('default_days_threshold', "'default_days_threshold' must be an integer >= 0");
    var fallback = data.fallback_playlist;
    if (fallback !== undefined && fallback !== null && !nonemptyStr(fallback)) {
      top('fallback_playlist', "'fallback_playlist' must be a playlist name or null");
    }

    var since = data.inbox_since;
    if (since !== undefined && since !== null) {
      var sinceOk = (since instanceof Date && !isNaN(since.getTime())) ||
        (nonemptyStr(since) && isValidIsoDate(since.trim()));
      if (!sinceOk) top('inbox_since', "'inbox_since' must be a date (YYYY-MM-DD) or null");
    }

    var lp = 'language_playlists' in data ? data.language_playlists : {};
    if (lp === null) lp = {};
    if (!isMap(lp)) {
      top('language_playlists', "'language_playlists' must be a mapping of playlist name -> language");
    } else {
      Object.keys(lp).forEach(function (name) {
        var lang = lp[name];
        var canon = root.SpotiLang.normalize(lang);
        if (!nonemptyStr(name)) {
          top('language_playlists', "'language_playlists': playlist names must be non-empty strings", { lpName: name });
        } else if (canon === null) {
          top('language_playlists', "'language_playlists' (" + pyRepr(name) + '): unknown language ' + pyRepr(lang),
            { lpName: name, short: 'unknown language ' + pyRepr(lang) });
        }
      });
    }

    var enrich = 'enrichment' in data ? data.enrichment : {};
    if (enrich === null) enrich = {};
    if (!isMap(enrich)) {
      top('enrichment', "'enrichment' must be a mapping");
    } else {
      Object.keys(enrich).forEach(function (key) {
        if (!has(ENRICHMENT_KEYS, key)) top('enrichment', "unknown key 'enrichment." + key + "'");
      });
      if ('musicbrainz' in enrich && typeof enrich.musicbrainz !== 'boolean') {
        top('enrichment.musicbrainz', "'enrichment.musicbrainz' must be true or false");
      }
      if ('english_default' in enrich && typeof enrich.english_default !== 'boolean') {
        top('enrichment.english_default', "'enrichment.english_default' must be true or false");
      }
    }

    var logging = 'logging' in data ? data.logging : {};
    if (logging === null) logging = {};
    if (!isMap(logging)) {
      top('logging', "'logging' must be a mapping");
    } else {
      Object.keys(logging).forEach(function (key) {
        if (!has(LOGGING_KEYS, key)) top('logging', "unknown key 'logging." + key + "'");
      });
      if ('include_track_names' in logging && typeof logging.include_track_names !== 'boolean') {
        top('logging.include_track_names', "'logging.include_track_names' must be true or false");
      }
    }

    var ai = 'artist_in_playlist' in data ? data.artist_in_playlist : {};
    if (ai === null) ai = {};
    if (!isMap(ai)) {
      top('artist_in_playlist', "'artist_in_playlist' must be a mapping");
    } else {
      Object.keys(ai).forEach(function (key) {
        if (!has(ARTIST_IN_PLAYLIST_KEYS, key)) top('artist_in_playlist', "unknown key 'artist_in_playlist." + key + "'");
      });
      if ('min_tracks' in ai && (!isInt(ai.min_tracks) || ai.min_tracks < 1)) {
        top('artist_in_playlist.min_tracks', "'artist_in_playlist.min_tracks' must be an integer >= 1");
      }
      if ('min_dominance' in ai) {
        var md = ai.min_dominance;
        if (typeof md !== 'number' || !isFinite(md) || md <= 0 || md > 1) {
          top('artist_in_playlist.min_dominance', "'artist_in_playlist.min_dominance' must be a number > 0 and <= 1");
        }
      }
      if ('exclude_playlists' in ai && (!Array.isArray(ai.exclude_playlists) || !ai.exclude_playlists.every(nonemptyStr))) {
        top('artist_in_playlist.exclude_playlists', "'artist_in_playlist.exclude_playlists' must be a list of non-empty strings");
      }
    }

    var rawRules = 'rules' in data ? data.rules : [];
    if (!Array.isArray(rawRules)) {
      top('rules', "'rules' must be a list");
    } else {
      var seen = {};
      rawRules.forEach(function (raw, i) {
        var before = errors.length;
        var name = validateRule(raw, i, errors);
        if (errors.length > before || name === null) return;
        var folded = name.toLowerCase();
        if (Object.prototype.hasOwnProperty.call(seen, folded)) {
          errors.push({ msg: 'rules[' + i + '] (' + pyRepr(name) + '): duplicate rule name', short: 'duplicate rule name', rule: i, field: 'name' });
        }
        seen[folded] = true;
      });
    }
    return { errors: errors };
  }

  root.SpotiValidate = {
    validateConfig: validateConfig,
    MATCH_KEYS: MATCH_KEYS,
    LIST_MATCH_KEYS: LIST_MATCH_KEYS,
    INT_MATCH_KEYS: INT_MATCH_KEYS,
    STR_MATCH_KEYS: STR_MATCH_KEYS,
    BOOL_MATCH_KEYS: BOOL_MATCH_KEYS,
    TRUE_ONLY_MATCH_KEYS: TRUE_ONLY_MATCH_KEYS,
    LOGGING_KEYS: LOGGING_KEYS,
    ARTIST_IN_PLAYLIST_KEYS: ARTIST_IN_PLAYLIST_KEYS,
    AUTO_TARGET: AUTO_TARGET
  };
})(typeof window !== 'undefined' ? window : globalThis);
