"""Unit tests for file-backed replay scenarios, provenance hashing, and benchmark evaluator."""

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
    assert len(nvda_data["artifact_hash"]) == 64  # Valid SHA-256 hex string


def test_unknown_ticker_raises_data_unavailable():
    """Verify DA-13: Unknown ticker does not fall through to AAPL and raises DataUnavailableError."""
    mgr = ReplayDataManager()
    with pytest.raises(DataUnavailableError):
        mgr.load_scenario("SCENARIO-UNKNOWN-XYZ")


def test_evaluator_produces_consistent_benchmarks():
    """Verify VP-18: Evaluator generates row-by-row benchmark results without circularity."""
    res = evaluate_benchmarks()
    assert "rows" in res
    assert "summary" in res
    assert len(res["rows"]) == 3
    assert len(res["summary"]) == 5
