"""Dashboard fixtures regenerate byte-for-byte and follow docs/dashboard/DATA.md."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "docs" / "dashboard" / "fixtures"


def _gen():
    spec = importlib.util.spec_from_file_location("make_dashboard_fixtures", ROOT / "scripts" / "make_dashboard_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load(name, base=FIX):
    return json.loads((base / name).read_text(encoding="utf-8"))


def test_fixtures_regenerate_identically(tmp_path):
    names = _gen().generate(tmp_path)
    assert names == sorted(p.name for p in FIX.glob("*.json"))
    for n in names:
        assert (tmp_path / n).read_bytes() == (FIX / n).read_bytes(), n


PLAN_KEYS = {"version", "generated_at", "run_id", "mode", "what_if", "inbox_kind", "config_hash", "liked_total", "default_days_threshold",
             "english_default", "inbox_since", "counts", "rules", "playlists", "songs"}
RULE_KEYS = {"name", "enabled", "target_playlist", "target_position", "threshold_days", "conditions", "unless", "uses_language",
             "weak_signals_possible", "would_match", "wins", "target_status", "status"}
SONG_KEYS = {"title", "artists", "uri", "added_at", "age_days", "decision", "reason", "rule", "target_playlist", "target_status",
             "eligible_on", "target_position", "language", "genres", "artist_routing", "explain"}
RUN_KEYS = {"run_id", "time", "mode", "what_if", "planned_moves", "moved", "too_young", "no_match", "blocked", "target_problems", "errors",
            "warnings", "liked_before", "liked_after", "duration_seconds", "verdict", "rule_counts", "moves_by_playlist", "log"}
LOG_KEYS = {"date", "run_id", "mode", "dry_run", "what_if", "evaluated", "moved", "skipped_no_match", "skipped_too_young",
            "skipped_playlist_missing", "errors", "warnings", "journal", "liked_before", "liked_after", "verdict", "rule_counts",
            "config_hash", "plan_counts", "http_audit", "runtime_seconds"}
MOVED_KEYS = {"track", "artist", "uri", "playlist", "playlist_id", "rule", "matched", "age_days", "threshold_days",
              "already_in_target", "original_added_at", "target_position"}


def test_plan_matches_contract_and_covers_every_case():
    p = load("latest-plan.json")
    assert set(p) == PLAN_KEYS and p["version"] == 1
    assert set(p["counts"]) == {"will_move", "too_young", "no_match", "target_problem", "blocked"}
    assert len(p["songs"]) >= 40 and p["liked_total"] == len(p["songs"])
    assert all(v > 0 for v in p["counts"].values())
    for r in p["rules"]:
        assert set(r) == RULE_KEYS
    assert {r["status"] for r in p["rules"]} == {"ok", "dead", "shadowed", "disabled"}
    assert any(r["weak_signals_possible"] for r in p["rules"])
    assert {"resolved", "missing", "not_writable", "ambiguous"} <= {r["target_status"] for r in p["rules"]}
    assert {"top", "bottom"} <= {s["target_position"] for s in p["songs"] if s["decision"] == "will_move"}
    tiers = {s["language"]["source"] for s in p["songs"]}
    assert {"playlist", "script", "hint", "country_default", None} <= tiers
    assert {s["language"]["withheld"]["reason"] for s in p["songs"] if s["language"]["withheld"]} == {"below_90_percent", "unmeasured"}
    for s in p["songs"]:
        assert set(s) == SONG_KEYS
        assert set(s["language"]) == {"value", "source", "confidence", "used_for_rules", "withheld"}
        assert set(s["explain"]) == {"trace", "decided_by", "age_days"}
    for pl in p["playlists"]:
        assert set(pl) == {"name", "status", "size", "planned_in", "rules"}


def test_runs_and_logs_match_contract():
    runs = load("runs.json")
    assert set(runs) == {"version", "generated_at", "schedule", "runs"} and len(runs["runs"]) >= 6
    assert [r["time"] for r in runs["runs"]] == sorted((r["time"] for r in runs["runs"]), reverse=True)
    assert {"mismatch", "error", "ok", "dry_run"} <= {r["verdict"] for r in runs["runs"]}
    assert sum(r["mode"] == "apply" for r in runs["runs"]) >= 2
    assert any(r["what_if"] for r in runs["runs"])
    for r in runs["runs"]:
        assert set(r) == RUN_KEYS
        log = load(r["log"])
        extra = {"reconcile", "restore_command", "batches"} if r["mode"] == "apply" else set()
        assert set(log) == LOG_KEYS | extra, r["log"]
        assert log["run_id"] == r["run_id"] and log["verdict"] == r["verdict"]
        for m in log["moved"]:
            assert set(m) == MOVED_KEYS
        if r["mode"] == "apply":
            assert set(log["reconcile"]) == {"expected_after", "actual_after", "ok"}
            assert log["journal"] and set(log["journal"][0]) == {"uri", "name", "artists", "original_added_at", "target_playlist_id"}
            assert log["reconcile"]["ok"] == (r["verdict"] == "ok")


def test_counts_only_files_match_contract():
    cov = load("enrichment-coverage.json")
    assert set(cov) >= {"date", "tracks", "unique_primary_artists", "genre_coverage_pct_of_artists", "language_coverage_pct_whole_library",
                        "language_coverage_pct_target_language_tracks", "target_language_tracks", "target_language_tracks_resolved",
                        "language_source_counts", "language_distribution", "genre_source_counts", "musicbrainz"}
    assert set(cov["language_source_counts"]) == {"playlist", "script", "hint", "country_default", "none"}
    sp = load("signal-precision.json")
    assert set(sp) == {"version", "generated_at", "min_precision", "min_samples", "by_signal", "qualified"}
    assert set(sp["by_signal"]) == {"playlist", "script", "hint", "country_default"}
    for langs in sp["by_signal"].values():
        for st in langs.values():
            assert set(st) == {"truth", "predicted", "correct", "precision", "recall"}
    # Master decisions 16 removed the dashboard's Backtest view, so backtest.json/backtest-detail.json are no
    # longer part of the dashboard fixture set (they remain real `python -m src.backtest` outputs, covered by
    # tests/test_backtest.py, just not read by the dashboard any more).
    assert not (FIX / "backtest.json").exists()
    assert not (FIX / "backtest-detail.json").exists()
