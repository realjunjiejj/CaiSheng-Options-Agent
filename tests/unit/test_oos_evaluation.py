"""Unit tests for out-of-sample historical evaluation runner and upgraded forecasting engine."""

import json
import math
from pathlib import Path
import pytest

from volagent.evaluation.oos_runner import calibration_breakdown, chronological_event_splits, run_out_of_sample_evaluation
from volagent.quant.forecast import compute_shrinkage_forecast

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_oos_universe_manifest_exists_and_valid():
    manifest_path = PROJECT_ROOT / "data" / "evaluation" / "oos_universe_manifest.json"
    assert manifest_path.exists(), "OOS manifest must exist"
    with open(manifest_path, "r") as f:
        data = json.load(f)
    events = data["events"]
    assert len(events) >= 30, f"Expected >= 30 events, got {len(events)}"
    for e in events:
        assert "event_id" in e
        assert "symbol" in e
        assert "earnings_date" in e
        assert "front_option_expiry" in e
        assert "source_url" in e


def test_oos_runner_uses_full_graph_and_has_no_daily_option_fallback():
    source = (PROJECT_ROOT / "src" / "volagent" / "evaluation" / "oos_runner.py").read_text()
    assert "workflow = VolAgentWorkflow(config=proxy_cfg)" in source
    assert "result = workflow.run" in source
    assert "OptionBarsRequest" not in source
    assert "agent_eligible_expiration" in source
    assert "oos_locked_predictions.json" in source


def test_chronological_splits_reserve_the_newest_events_for_holdout():
    events = [
        {"event_id": f"EV-{index}", "cutoff_ny": f"2024-01-{index:02d} 15:30:00"}
        for index in range(1, 11)
    ]

    splits = chronological_event_splits(events)

    assert [splits[f"EV-{index}"] for index in range(1, 7)] == ["train"] * 6
    assert [splits[f"EV-{index}"] for index in range(7, 9)] == ["validation"] * 2
    assert [splits[f"EV-{index}"] for index in range(9, 11)] == ["holdout"] * 2


def test_calibration_breakdown_uses_only_locked_forecasts_and_revealed_outcomes():
    rows = [
        {"event_id": "a", "agent_median_forecast": 0.02, "realized_abs_move": 0.01},
        {"event_id": "b", "agent_median_forecast": 0.04, "realized_abs_move": 0.05},
        {"event_id": "c", "agent_median_forecast": 0.10, "realized_abs_move": 0.08},
    ]

    breakdown = calibration_breakdown(rows)

    assert [item["events"] for item in breakdown] == [1, 1, 1]
    assert breakdown[0]["mean_predicted_abs_move"] == 0.02
    assert breakdown[-1]["mean_realized_abs_move"] == 0.08


def test_oos_evaluation_results_contain_required_metrics():
    results_path = PROJECT_ROOT / "data" / "evaluation" / "oos_evaluation_results.json"
    assert results_path.exists(), "Results JSON must exist"
    with open(results_path, "r") as f:
        data = json.load(f)
    
    summary = data["summary"]
    assert summary["evaluated_events_count"] >= 0
    assert summary["excluded_events_count"] >= 0
    assert summary["verdict"] in [
        "No evidence of predictive alpha",
        "Promising but statistically unproven",
        "Evidence of out-of-sample improvement, pending independent validation",
    ]
    
    metrics = summary["metrics"]
    assert "mae" in metrics
    assert "rmse" in metrics
    assert "median_absolute_error" in metrics
    assert "win_rate" in metrics
    assert "bias" in metrics
    assert "calibration" in metrics
    assert "bootstrap_95ci_mae_diff" in metrics
    assert "selective_prediction" in metrics


def test_oos_evaluation_events_have_hashes_and_strictly_valid_fields():
    results_path = PROJECT_ROOT / "data" / "evaluation" / "oos_evaluation_results.json"
    with open(results_path, "r") as f:
        data = json.load(f)
    
    for ev in data["events"]:
        assert len(ev["forecast_hash"]) == 64, "SHA-256 forecast hash must be 64 hex chars"
        assert ev["spot_cutoff"] > 0
        assert ev["realized_abs_move"] >= 0
        assert ev["abs_error_agent"] >= 0
        assert ev["abs_error_b0"] >= 0
        assert ev["abs_error_b1"] >= 0
        assert ev["abs_error_b2"] >= 0


def test_hybrid_vrp_shrinkage_incorporates_implied_move_and_vrp():
    features_low_iv = {"implied_move_pct": 0.03, "atm_iv": 0.35, "magnitude_pressure_score": 0.5}
    features_high_iv = {"implied_move_pct": 0.09, "atm_iv": 0.85, "magnitude_pressure_score": 0.5}
    history = [0.05, 0.05, 0.05, 0.05]

    fc_low, _ = compute_shrinkage_forecast(features_low_iv, history, vrp_discount_ratio=0.85)
    fc_high, _ = compute_shrinkage_forecast(features_high_iv, history, vrp_discount_ratio=0.85)

    assert fc_high.median_abs_move_pct > fc_low.median_abs_move_pct, "Higher implied move must elevate hybrid VRP forecast"


def test_heavy_tailed_interval_ordering_and_tail_ratio():
    features = {"implied_move_pct": 0.06, "atm_iv": 0.50, "magnitude_pressure_score": 0.5}
    history_fat_tails = [0.02, 0.03, 0.06, 0.14, 0.25]
    
    fc, iv_fc = compute_shrinkage_forecast(features, history_fat_tails)
    assert fc.q20_abs_move_pct < fc.median_abs_move_pct < fc.q80_abs_move_pct
    assert fc.q80_abs_move_pct / fc.median_abs_move_pct >= 1.35, "Heavy-tailed stock must have upper quantile expansion >= 1.35x"


def test_log_logistic_exceedance_monotonicity():
    history = [0.04, 0.05, 0.06, 0.05]
    features_cheap_straddle = {"implied_move_pct": 0.02, "atm_iv": 0.25, "magnitude_pressure_score": 0.5}
    features_expensive_straddle = {"implied_move_pct": 0.12, "atm_iv": 0.95, "magnitude_pressure_score": 0.5}

    fc_cheap, _ = compute_shrinkage_forecast(features_cheap_straddle, history)
    fc_exp, _ = compute_shrinkage_forecast(features_expensive_straddle, history)

    assert fc_cheap.probability_exceeds_implied > fc_exp.probability_exceeds_implied
    assert 0.01 <= fc_cheap.probability_exceeds_implied <= 0.99
    assert 0.01 <= fc_exp.probability_exceeds_implied <= 0.99


def test_nonlinear_catalyst_expansion_on_high_magnitude_pressure():
    history = [0.05, 0.05, 0.05, 0.05]
    features_quiet = {"implied_move_pct": 0.05, "atm_iv": 0.50, "magnitude_pressure_score": 0.1}
    features_catalyst = {"implied_move_pct": 0.05, "atm_iv": 0.50, "magnitude_pressure_score": 0.9}

    fc_quiet, _ = compute_shrinkage_forecast(features_quiet, history)
    fc_catalyst, _ = compute_shrinkage_forecast(features_catalyst, history)

    assert fc_catalyst.median_abs_move_pct > fc_quiet.median_abs_move_pct * 1.5, "High catalyst pressure must expand forecast non-linearly"
