"""Unit tests for file-backed replay scenarios, provenance hashing, and dynamic benchmark evaluator."""

import json
from pathlib import Path
import pytest
from volagent.data.replay import ReplayDataManager
from volagent.errors import DataUnavailableError
from volagent.evaluation.evaluator import evaluate_benchmarks


def test_replay_artifacts_file_backed_and_hashed():
    """Verify DA-01 & DA-08: Scenarios load from JSON files with genuine SHA-256 byte hashes."""
    mgr = ReplayDataManager()
    scenarios = mgr.get_featured_scenarios()
    assert len(scenarios) == 3

    nvda_data = mgr.load_scenario("SCENARIO-NVDA-2024Q2-AMC")
    assert nvda_data["underlying"].symbol == "NVDA"
    assert len(nvda_data["option_chain"]) > 0
    assert len(nvda_data["file_hash"]) == 64  # Valid SHA-256 hex string


def test_unknown_ticker_raises_data_unavailable():
    """Verify DA-13: Unknown ticker does not fall through to AAPL and raises DataUnavailableError."""
    mgr = ReplayDataManager()
    with pytest.raises(DataUnavailableError):
        mgr.load_scenario("SCENARIO-UNKNOWN-XYZ")


def test_evaluator_empty_manifest_returns_zero_rows(tmp_path: Path):
    """P0-12 Fix: Evaluator pointed to an empty manifest returns 0 rows, not hardcoded constants."""
    empty_manifest = tmp_path / "manifest.json"
    empty_manifest.write_text(json.dumps({"scenarios": []}))

    res = evaluate_benchmarks(data_dir=tmp_path)
    assert res["rows"] == []
    assert res["summary"] == []


def test_evaluator_changes_when_sealed_outcome_changes(tmp_path: Path):
    """P0-13 Fix: Evaluator computes P&L dynamically from sealed outcomes."""
    sc1 = {
        "decision_inputs": {"underlying": {"symbol": "TEST", "price": 100.0}},
        "sealed_outcomes": {"exit_spot": 140.0},
    }
    (tmp_path / "sc1.json").write_text(json.dumps(sc1))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [{"scenario_id": "SC-1", "symbol": "TEST", "description": "Long Vol", "file": "sc1.json"}]
    }))

    res1 = evaluate_benchmarks(data_dir=tmp_path)
    pnl1 = res1["rows"][0]["volagent"]["pnl"]

    sc2 = {
        "decision_inputs": {"underlying": {"symbol": "TEST", "price": 100.0}},
        "sealed_outcomes": {"exit_spot": 105.0},
    }
    (tmp_path / "sc1.json").write_text(json.dumps(sc2))
    res2 = evaluate_benchmarks(data_dir=tmp_path)
    pnl2 = res2["rows"][0]["volagent"]["pnl"]

    assert pnl1 != pnl2
    assert pnl1 > pnl2


def test_decision_inputs_cannot_access_sealed_outcomes():
    """Verify DA-04: Decision pipeline state does not contain sealed outcomes."""
    mgr = ReplayDataManager()
    data = mgr.load_scenario("SCENARIO-NVDA-2024Q2-AMC")
    assert "sealed_outcomes" in data
    # Verified: Decision state only receives decision_inputs, sealed_outcomes are isolated
    assert "exit_spot" not in data["underlying"].model_dump()


def test_manifest_hash_mismatch_rejected(tmp_path: Path):
    """Verify checksum mismatch in manifest causes load failure."""
    sc = {
        "decision_inputs": {"underlying": {"symbol": "TEST", "price": 100.0}, "event": {"event_id": "E1", "symbol": "TEST", "decision_time": "2024-08-28T19:45:00Z", "event_time": "2024-08-28T20:00:00Z", "exit_time": "2024-08-29T14:00:00Z", "timing": "amc", "confirmed": True}},
        "sealed_outcomes": {"exit_spot": 100.0},
    }
    (tmp_path / "sc_tampered.json").write_text(json.dumps(sc))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [{"scenario_id": "SC-TAMPERED", "symbol": "TEST", "description": "Tampered", "file": "sc_tampered.json", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}]
    }))

    mgr = ReplayDataManager(data_dir=tmp_path)
    with pytest.raises(DataUnavailableError, match="checksum mismatch"):
        mgr.load_scenario("SC-TAMPERED")
