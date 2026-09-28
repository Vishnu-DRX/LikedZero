// Single source of truth for the Configure schema-reference drawer. Mirrors src/config.py / validate.js.
// Do not hand-duplicate this table anywhere else — the drawer, and any future help text, should read from here.
(function (root) {
  'use strict';

  var SCHEMA = [
    { key: 'default_days_threshold', type: 'integer >= 0', def: '14', note: 'Whole days a song waits in Liked Songs before any rule can match it.' },
    { key: 'fallback_playlist', type: 'string or null', def: 'null', note: 'Playlist for unmatched songs. null leaves them in Liked Songs.' },
    { key: 'inbox_since', type: 'date (YYYY-MM-DD) or null', def: 'null', note: 'Songs liked before this date are never evaluated, no matter how a run is started. Required before an unattended (scheduled) run is allowed.' },
    { key: 'language_playlists', type: 'map<string,string>', def: '{}', note: 'Playlist name -> language (canonical English name, ISO code or native name accepted as input).' },
    { key: 'enrichment.musicbrainz', type: 'boolean', def: 'true', note: 'Look up genre/language on MusicBrainz (free, 1 req/s).' },
    { key: 'enrichment.english_default', type: 'boolean', def: 'false', note: 'Weak guess: assume English for Latin-script songs by US/GB/AU/CA/IE/NZ artists.' },
    { key: 'logging.include_track_names', type: 'boolean', def: 'false', note: 'Off = committed public logs show counts/links only, not song titles.' },
    { key: 'artist_in_playlist.min_tracks', type: 'integer >= 1', def: '3', note: 'The artist needs at least this many existing tracks in one playlist, or the signal is too weak.' },
    { key: 'artist_in_playlist.min_dominance', type: 'number, 0 < n <= 1', def: '0.9', note: 'That top playlist must hold at least this share of the artist’s tracked-playlist tracks.' },
    { key: 'artist_in_playlist.exclude_playlists', type: 'list<string>', def: '[]', note: 'Never a candidate target. Vault_drx is always excluded too, whether or not it is listed here.' },
    { key: 'rules[].name', type: 'non-empty string', def: 'required', note: 'Unique (case-insensitive) across all rules.' },
    { key: 'rules[].enabled', type: 'boolean', def: 'true', note: 'Disabled rules are skipped entirely.' },
    { key: 'rules[].match', type: 'non-empty map', def: 'required', note: 'All conditions inside one rule must match (AND).' },
    { key: 'rules[].match.artist_in', type: 'list<string>', def: '-', note: 'Matches any credited artist, case-insensitive.' },
    { key: 'rules[].match.genre_contains', type: 'list<string>', def: '-', note: 'Substring match against the artist’s genres.' },
    { key: 'rules[].match.language_in', type: 'list<string>', def: '-', note: 'Canonical language names; ISO codes/native names normalised on input.' },
    { key: 'rules[].match.release_year_before', type: 'integer 1-9999', def: '-', note: 'Album release year strictly before this value.' },
    { key: 'rules[].match.release_year_after', type: 'integer 1-9999', def: '-', note: 'Album release year strictly after this value.' },
    { key: 'rules[].match.explicit', type: 'boolean', def: '-', note: 'true = explicit only, false = clean only.' },
    { key: 'rules[].match.track_name_contains', type: 'non-empty string', def: '-', note: 'Case-insensitive substring of the track title.' },
    { key: 'rules[].match.album_name_contains', type: 'non-empty string', def: '-', note: 'Case-insensitive substring of the album title.' },
    { key: 'rules[].match.artist_in_playlist', type: 'true (only)', def: '-', note: 'Gate for auto-routing (design/proposals/artist_in_playlist.md). Requires target_playlist: auto.' },
    { key: 'rules[].match.any', type: 'true (only)', def: '-', note: 'Matches unconditionally — the real catch-all. Put this rule last; everything above it is tried first.' },
    { key: 'rules[].match.artist_country_in', type: 'list<string> (2-letter ISO codes)', def: '-', note: 'The primary artist’s MusicBrainz/ISRC country, e.g. [IN, US]. Same weak-signal caveat as country defaults — informational, not a strong signal.' },
    { key: 'rules[].match.any_of', type: 'list<map> (>= 1 group)', def: '-', note: '"OR" within one rule: matches if ANY group’s conditions all pass, then AND-combined with the rest of match. A group cannot contain artist_in_playlist or nest another any_of.' },
    { key: 'rules[].unless', type: 'non-empty map', def: '-', note: 'Exceptions: same match-key vocabulary as match, AND-combined. If match passes AND unless also fully passes, the rule is blocked (treated as no match — evaluation continues to the next rule). Cannot contain artist_in_playlist.' },
    { key: 'rules[].target_playlist', type: 'non-empty string, or "auto"', def: 'required', note: 'Name of an existing playlist you own or collaborate on. "auto" is only valid with match.artist_in_playlist and is resolved per song.' },
    { key: 'rules[].days_threshold', type: 'integer >= 0', def: 'default_days_threshold', note: 'Per-rule override of the global threshold.' },
    { key: 'rules[].create_missing_playlists', type: 'boolean', def: 'false', note: 'If true, SpotiSort creates the target playlist when it does not exist.' },
    { key: 'rules[].target_position', type: '"top" | "bottom"', def: 'bottom', note: 'top inserts new songs at index 0; existing order is kept.' }
  ];

  root.SpotiSchema = { SCHEMA: SCHEMA };
})(typeof window !== 'undefined' ? window : globalThis);
