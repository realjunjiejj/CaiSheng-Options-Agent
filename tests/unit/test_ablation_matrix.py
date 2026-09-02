"""Adversarial and rigorous unit tests for Component Ablation Matrix & Benchmark Evaluation Engine."""

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

from volagent.data.replay import ReplayDataManager
from volagent.domain.enums import Decision, GateStatus
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.evaluation.accounting_oracle import compute_realized_trade_pnl
from volagent.evaluation.evaluator import evaluate_benchmarks
from volagent.execution.ledger import ExecutionLedger
from volagent.graph.builder import VolAgentWorkflow


def test_evaluator_uses_entry_option_quotes_not_spot_percentages():
    """Verify that evaluator computes P&L directly from contract bid/ask quotes and not spot percentages."""
    res = evaluate_benchmarks()
    table = res["ablation_table"]
    nvda_rows = [r for r in table if "NVDA" in r["Scenario"]]
    assert len(nvda_rows) > 0
    full_row = next(r for r in nvda_rows if "CaiSheng" in r["Model"])
    assert "Debit" in full_row["Entry"] or "$" in full_row["Entry"]
    # P&L is dynamic and exact from contract quotes
    assert full_row["Net P&L"] != "$0.00"


def test_evaluator_uses_exit_quotes_for_same_contract_symbols():
    """Verify evaluator maps exit quotes by contract symbol."""
    mgr = ReplayDataManager()
    nvda = mgr.load_scenario("SCENARIO-NVDA-2024Q2-AMC")
    exit_quotes = nvda["sealed_outcomes"]["exit_option_quotes"]
    assert "NVDA240830C00125500" in exit_quotes
    assert "NVDA240830P00125500" in exit_quotes
    assert exit_quotes["NVDA240830C00125500"]["bid"] > 0.0 or exit_quotes["NVDA240830C00125500"]["ask"] > 0.0


def test_long_enters_at_ask_and_exits_at_bid():
    """Verify shared accounting oracle: long structures enter at ask and exit at bid."""
    call_leg = OptionLeg(
        contract_symbol="TESTC100",
        option_type="call",
        strike=100.0,
        expiration=datetime(2024, 8, 30, tzinfo=timezone.utc).date(),
        side="buy",
        ratio_qty=1,
        entry_price_assumption=5.50,
    )
    cand = StrategyCandidate(
        strategy_id="cand-test-long",
        decision=Decision.LONG_STRADDLE,
        underlying_symbol="TEST",
        legs=[call_leg],
        net_delta=0.5,
        net_vega=0.1,
        net_theta=-0.05,
        max_loss=550.0,
        entry_debit_credit=550.0,
        quantity=1,
    )
    exit_quotes = {"TESTC100": {"bid": 8.00, "ask": 8.50}}
    res = compute_realized_trade_pnl(cand, exit_quotes, fee_per_contract=0.0, slippage_per_contract=0.0)
    # Entry: paid ask 5.50 * 100 = 550.00. Exit: received bid 8.00 * 100 = 800.00. Net PnL = +250.00
    assert res.net_pnl == 250.00
    assert res.is_valid is True


def test_short_enters_at_bid_and_exits_at_ask():
    """Verify shared accounting oracle: short structures enter at bid and exit at ask."""
    call_leg = OptionLeg(
        contract_symbol="TESTC100",
        option_type="call",
        strike=100.0,
        expiration=datetime(2024, 8, 30, tzinfo=timezone.utc).date(),
        side="sell",
        ratio_qty=1,
        entry_price_assumption=5.00,
    )
    cand = StrategyCandidate(
        strategy_id="cand-test-short",
        decision=Decision.SHORT_IRON_BUTTERFLY,
        underlying_symbol="TEST",
        legs=[call_leg],
        net_delta=-0.5,
        net_vega=-0.1,
        net_theta=0.05,
        max_loss=500.0,
        entry_debit_credit=-500.0,
        quantity=1,
    )
    exit_quotes = {"TESTC100": {"bid": 1.00, "ask": 1.50}}
    res = compute_realized_trade_pnl(cand, exit_quotes, fee_per_contract=0.0, slippage_per_contract=0.0)
    # Entry: received bid 5.00 * 100 = 500.00 credit. Exit: paid ask 1.50 * 100 = 150.00 to close. Net PnL = +350.00
    assert res.net_pnl == 350.00
    assert res.is_valid is True


def test_all_baselines_share_fee_slippage_and_multiplier():
    """Verify fee and slippage are applied identically across all baselines."""
    call_leg = OptionLeg(
        contract_symbol="TESTC100",
        option_type="call",
        strike=100.0,
        expiration=datetime(2024, 8, 30, tzinfo=timezone.utc).date(),
        side="buy",
        ratio_qty=1,
        entry_price_assumption=5.00,
    )
    cand = StrategyCandidate(
        strategy_id="cand-test-fee",
        decision=Decision.LONG_STRADDLE,
        underlying_symbol="TEST",
        legs=[call_leg],
        net_delta=0.5,
        net_vega=0.1,
        net_theta=-0.05,
        max_loss=500.0,
        entry_debit_credit=500.0,
        quantity=1,
    )
    exit_quotes = {"TESTC100": {"bid": 5.00, "ask": 5.00}}
    # Zero move: price unchanged 5.00 -> 5.00. Friction: 0.65 fee * 2 = 1.30, 0.02 slippage * 2 * 100 = 4.00. Total friction = -5.30
    res = compute_realized_trade_pnl(cand, exit_quotes, fee_per_contract=0.65, slippage_per_contract=0.02, multiplier=100)
    assert res.net_pnl == -5.30
    assert res.total_friction == 5.30


@pytest.mark.parametrize(
    "exit_quote, expected_fragment",
    [
        ({"bid": 6.0, "ask": 5.0}, "crossed or negative"),
        ({"bid": float("nan"), "ask": 5.0}, "non-finite"),
    ],
)
def test_accounting_oracle_rejects_invalid_exit_markets(exit_quote, expected_fragment):
    leg = OptionLeg(
        contract_symbol="TESTC100",
        option_type="call",
        strike=100.0,
        expiration=datetime(2024, 8, 30, tzinfo=timezone.utc).date(),
        side="buy",
        ratio_qty=1,
        entry_price_assumption=5.0,
    )
    candidate = StrategyCandidate(
        strategy_id="invalid-exit",
        decision=Decision.LONG_STRADDLE,
        legs=[leg],
        net_delta=0.0,
        net_vega=0.0,
        net_theta=0.0,
        max_loss=500.0,
        entry_debit_credit=500.0,
        quantity=1,
    )
    result = compute_realized_trade_pnl(candidate, {"TESTC100": exit_quote})
    assert result.is_valid is False
    assert result.net_pnl is None
    assert expected_fragment in result.validity_note


def test_accounting_oracle_rejects_wrong_exit_timestamp():
    leg = OptionLeg(
        contract_symbol="TESTC100",
        option_type="call",
        strike=100.0,
        expiration=datetime(2024, 8, 30, tzinfo=timezone.utc).date(),
        side="buy",
        ratio_qty=1,
        entry_price_assumption=5.0,
    )
    candidate = StrategyCandidate(
        strategy_id="wrong-time",
        decision=Decision.LONG_STRADDLE,
        legs=[leg],
        max_loss=500.0,
        entry_debit_credit=500.0,
        quantity=1,
    )
    expected = datetime(2024, 8, 29, 14, 0, tzinfo=timezone.utc)
    result = compute_realized_trade_pnl(
        candidate,
        {"TESTC100": {"bid": 5.0, "ask": 5.2, "quote_time": "2024-08-29T15:00:00Z"}},
        expected_exit_time=expected,
    )
    assert result.is_valid is False
    assert "timestamp mismatch" in result.validity_note


def test_scenario_description_does_not_control_decision(tmp_path: Path):
    """P0-A02 Fix: Renaming scenario description does not alter the underlying model decision."""
    sc_file = Path("data/replay/scenarios/scenario_nvda_2024q2.json")
    sc_dict = json.loads(sc_file.read_text())

    (tmp_path / "sc1.json").write_text(json.dumps(sc_dict))

    sc_dict_mutated = copy.deepcopy(sc_dict)
    sc_dict_mutated["name"] = "Misleading Short Vol Description"
    (tmp_path / "sc2.json").write_text(json.dumps(sc_dict_mutated))

    manifest = {
        "scenarios": [
            {"scenario_id": "SC-1", "symbol": "NVDA", "description": "Synthetic Long", "file": "sc1.json"},
            {"scenario_id": "SC-2", "symbol": "NVDA", "description": "Misleading Short Vol Description", "file": "sc2.json"},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    res = evaluate_benchmarks(data_dir=tmp_path)
    dec1 = res["rows"][0]["volagent"]["decision"]
    dec2 = res["rows"][1]["volagent"]["decision"]
    assert dec1 == dec2


def test_ticker_name_does_not_control_decision(tmp_path: Path):
    """P0-A02 Fix: Renaming ticker symbol does not alter the underlying decision."""
    sc_file = Path("data/replay/scenarios/scenario_nvda_2024q2.json")
    sc_dict = json.loads(sc_file.read_text())

    sc_dict_mutated = copy.deepcopy(sc_dict)
    sc_dict_mutated["symbol"] = "RANDOMXYZ"
    sc_dict_mutated["decision_inputs"]["underlying"]["symbol"] = "RANDOMXYZ"
    sc_dict_mutated["decision_inputs"]["event"]["symbol"] = "RANDOMXYZ"
    for c in sc_dict_mutated["decision_inputs"]["option_chain"]:
        c["underlying_symbol"] = "RANDOMXYZ"

    (tmp_path / "sc_rand.json").write_text(json.dumps(sc_dict_mutated))
    manifest = {
        "scenarios": [
            {"scenario_id": "SC-RAND", "symbol": "RANDOMXYZ", "description": "Arbitrary Ticker", "file": "sc_rand.json"}
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    (tmp_path / "sc_original.json").write_text(json.dumps(sc_dict))
    manifest["scenarios"].insert(0, {
        "scenario_id": "SC-ORIGINAL",
        "symbol": "NVDA",
        "description": "Original Ticker",
        "file": "sc_original.json",
    })
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    res = evaluate_benchmarks(data_dir=tmp_path)
    assert len(res["rows"]) == 2
    assert res["rows"][0]["volagent"]["decision"] == res["rows"][1]["volagent"]["decision"]


def test_controlled_variants_are_declared_from_one_graph_protocol():
    """Full, B3, and B4 must differ only through explicit component controls."""
    res = evaluate_benchmarks()
    controls = {row["Model"]: row for row in res["variant_controls"]}
    assert controls["CaiSheng (Full)"]["Final Governor"] == "ON"
    assert controls["B3: FINAL_GOVERNOR_OFF"]["Final Governor"] == "OFF"
    assert controls["B4: QUANT_ONLY"]["Agent Debate"] == "OFF"
    assert controls["B4: QUANT_ONLY"]["Final Governor"] == "ON"


def test_replay_evaluation_is_isolated_from_live_system_halt(tmp_path, monkeypatch):
    live_ledger = ExecutionLedger(tmp_path / "live-halted.db")
    live_ledger.trip_system_halt("Live-account safety halt")
    monkeypatch.setenv("VOLAGENT_LEDGER_DB_PATH", str(live_ledger.db_path))

    result = evaluate_benchmarks()
    full = next(
        row for row in result["summary"]
        if row["Model Benchmark"] == "CaiSheng (Full)"
    )

    assert full["Valid Trades"] == "4/6"
    assert full["Executable Net P&L"] == "$+2044.00"
    assert full["Risk Breaches"] == "0"


def test_b3_reuses_identical_upstream_graph_state_and_candidate():
    scenario = ReplayDataManager().load_scenario("SCENARIO-GATE-UNCONFIRMED")
    workflow = VolAgentWorkflow()
    inputs = {
        "scenario_id": scenario["scenario_id"],
        "underlying": scenario["underlying"],
        "event": scenario["event"],
        "option_chain": scenario["option_chain"],
        "evidence": scenario["evidence"],
        "historical_moves": scenario["historical_moves"],
        "enable_agent_debate": True,
    }
    full = workflow.run({**inputs, "enable_risk_governor": True})
    b3 = workflow.run({**inputs, "enable_risk_governor": False})

    assert full["move_forecast"] == b3["move_forecast"]
    assert full["event_assessment"] == b3["event_assessment"]
    full_candidate = full["audit_proposal"]
    b3_candidate = b3["approved_candidate"]
    assert full_candidate is not None and b3_candidate is not None
    assert [leg.contract_symbol for leg in full_candidate.legs] == [
        leg.contract_symbol for leg in b3_candidate.legs
    ]
    assert full["risk_report"].overall_status == GateStatus.FAIL
    assert b3["risk_report"].overall_status == GateStatus.FAIL
    assert b3["governor_bypassed"] is True


def test_b4_disables_debate_but_retains_deterministic_safety():
    scenario = ReplayDataManager().load_scenario("SCENARIO-NVDA-2024Q2-AMC")
    result = VolAgentWorkflow().run({
        "scenario_id": scenario["scenario_id"],
        "underlying": scenario["underlying"],
        "event": scenario["event"],
        "option_chain": scenario["option_chain"],
        "evidence": scenario["evidence"],
        "historical_moves": scenario["historical_moves"],
        "enable_agent_debate": False,
        "enable_risk_governor": True,
    })
    assert "event_assessment" not in result
    assert "long_vol_thesis" not in result
    assert "short_vol_thesis" not in result
    assert result["critic_report"].status == GateStatus.PASS
    assert result["approved_candidate"] is not None


def test_ungated_variant_disables_only_final_risk_governor():
    """The dedicated challenge must isolate the final event-confirmation governor."""
    res = evaluate_benchmarks()
    table = res["ablation_table"]
    full = next(r for r in table if r["Scenario"].startswith("GATE ") and r["Model"] == "CaiSheng (Full)")
    b3 = next(r for r in table if r["Scenario"].startswith("GATE ") and r["Model"] == "B3: FINAL_GOVERNOR_OFF")
    assert full["Decision"] == "no_trade"
    assert b3["Decision"] != "no_trade"
    assert b3["Risk Breach"] == "Yes (event_timing)"
    assert b3["Execution Validity"] == "COUNTERFACTUAL (Policy Bypassed)"


def test_ungated_variant_does_not_invent_candidate(tmp_path: Path):
    """P0-A03 Fix: B3 remains NO_TRADE if no candidate exists upstream."""
    sc_empty = {
        "scenario_id": "SC-EMPTY",
        "symbol": "TEST",
        "decision_inputs": {
            "underlying": {"symbol": "TEST", "price": 100.0, "bid": 99.9, "ask": 100.1, "quote_time": "2024-08-28T19:45:00Z", "previous_close": 99.0, "realized_vol_10d": 0.3, "realized_vol_30d": 0.3},
            "event": {"event_id": "E1", "symbol": "TEST", "fiscal_period": "Q1", "event_time": "2024-08-28T20:00:00Z", "timing": "amc", "confirmed": True, "decision_time": "2024-08-28T19:45:00Z", "exit_time": "2024-08-29T14:00:00Z"},
            "option_chain": [],
        },
        "sealed_outcomes": {"exit_spot": 100.0}
    }
    (tmp_path / "sc_empty.json").write_text(json.dumps(sc_empty))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [{"scenario_id": "SC-EMPTY", "symbol": "TEST", "file": "sc_empty.json"}]
    }))
    res = evaluate_benchmarks(data_dir=tmp_path)
    assert res["rows"] == [] or res["rows"][0]["b3"]["pnl"] in ("$0.00", "0.0", "$0.0")


def test_quant_only_variant_disables_agent_contribution():
    """Verify B4 is a functioning quant-only graph, not a missing-critic flat line."""
    res = evaluate_benchmarks()
    table = res["ablation_table"]
    b4_rows = [r for r in table if "B4" in r["Model"]]
    assert len(b4_rows) == res["total_scenarios"]
    assert any(row["Decision"] != "no_trade" for row in b4_rows)
    assert all("critic_approval" not in row["Abstention Reason"] for row in b4_rows)
    aapl_b4 = next(r for r in b4_rows if "AAPL" in r["Scenario"])
    assert aapl_b4["Decision"] == "no_trade"


def test_b4_can_differ_from_full_when_event_assessment_changes_forecast():
    """The context challenge isolates the structured agent-assessment contribution."""
    res = evaluate_benchmarks()
    table = res["ablation_table"]
    full = next(r for r in table if r["Scenario"].startswith("CTX ") and r["Model"] == "CaiSheng (Full)")
    b4 = next(r for r in table if r["Scenario"].startswith("CTX ") and r["Model"] == "B4: QUANT_ONLY")
    assert full["Decision"] == "long_straddle"
    assert b4["Decision"] == "no_trade"


def test_no_arbitrary_stale_penalty_exists():
    """P0-A04 Fix: No fabricated -5% spot penalty is applied to stale data."""
    res = evaluate_benchmarks()
    table = res["ablation_table"]
    aapl_b1 = next(r for r in table if "AAPL" in r["Scenario"] and "B1" in r["Model"])
    assert aapl_b1["Net P&L"] == "$0.00"
    assert aapl_b1["Abstention Reason"] == "missing_shared_candidate"


def test_invalid_counterfactual_pnl_is_na_and_excluded_from_totals():
    """Invalid attempt denominators remain explicit and dynamic."""
    res = evaluate_benchmarks()
    summary = res["summary"]
    b1_sum = next(s for s in summary if "B1" in s["Model Benchmark"])
    assert any("Invalid Attempts" in k for k in b1_sum.keys())
    assert b1_sum["Invalid Attempts"].endswith(f"/{res['total_scenarios']}")


def test_summary_denominators_are_dynamic(tmp_path: Path):
    """P1-A02 Fix: Summary denominators derive dynamically from scenario count."""
    sc_file = Path("data/replay/scenarios/scenario_nvda_2024q2.json")
    (tmp_path / "sc1.json").write_text(sc_file.read_text())
    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [{"scenario_id": "SC-1", "symbol": "NVDA", "file": "sc1.json"}]
    }))
    res = evaluate_benchmarks(data_dir=tmp_path)
    assert res["summary"][0]["Valid Trades"].endswith("/1")


def test_staleness_uses_quote_age_not_filename(tmp_path: Path):
    """P1-A03 Fix: Staleness is determined by quote timestamp age vs decision time, not filename string."""
    sc_file = Path("data/replay/scenarios/scenario_nvda_2024q2.json")
    sc_dict = json.loads(sc_file.read_text())

    # Make quote timestamps 2 hours old
    sc_dict["decision_inputs"]["underlying"]["quote_time"] = "2024-08-28T17:45:00Z"
    for c in sc_dict["decision_inputs"]["option_chain"]:
        c["quote_time"] = "2024-08-28T17:45:00Z"

    (tmp_path / "fresh_name_no_stale_word.json").write_text(json.dumps(sc_dict))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [{"scenario_id": "SC-FRESH-NAME", "symbol": "NVDA", "description": "Clean Fresh Name", "file": "fresh_name_no_stale_word.json"}]
    }))

    res = evaluate_benchmarks(data_dir=tmp_path)
    assert res["rows"][0]["volagent"]["decision"] == "no_trade"


def test_mutating_entry_quote_changes_pnl(tmp_path: Path):
    """P1-A04 Fix: Modifying entry option quotes modifies realized P&L."""
    sc_file = Path("data/replay/scenarios/scenario_nvda_2024q2.json")
    sc_dict = json.loads(sc_file.read_text())

    (tmp_path / "sc_base.json").write_text(json.dumps(sc_dict))

    sc_dict_high = copy.deepcopy(sc_dict)
    for c in sc_dict_high["decision_inputs"]["option_chain"]:
        c["ask"] += 5.00
    (tmp_path / "sc_high.json").write_text(json.dumps(sc_dict_high))

    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [
            {"scenario_id": "SC-BASE", "symbol": "NVDA", "file": "sc_base.json"},
            {"scenario_id": "SC-HIGH", "symbol": "NVDA", "file": "sc_high.json"},
        ]
    }))

    res = evaluate_benchmarks(data_dir=tmp_path)
    pnl_base = res["rows"][0]["b1"]["pnl"]
    pnl_high = res["rows"][1]["b1"]["pnl"]
    assert pnl_base != pnl_high


def test_mutating_exit_quote_changes_pnl(tmp_path: Path):
    """P1-A04 Fix: Modifying exit quotes modifies realized P&L."""
    sc_file = Path("data/replay/scenarios/scenario_nvda_2024q2.json")
    sc_dict = json.loads(sc_file.read_text())

    (tmp_path / "sc_base.json").write_text(json.dumps(sc_dict))

    sc_dict_exit = copy.deepcopy(sc_dict)
    for sym, q in sc_dict_exit["sealed_outcomes"]["exit_option_quotes"].items():
        q["bid"] += 10.00
    (tmp_path / "sc_exit.json").write_text(json.dumps(sc_dict_exit))

    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [
            {"scenario_id": "SC-BASE", "symbol": "NVDA", "file": "sc_base.json"},
            {"scenario_id": "SC-EXIT", "symbol": "NVDA", "file": "sc_exit.json"},
        ]
    }))

    res = evaluate_benchmarks(data_dir=tmp_path)
    row_base = res["rows"][0]["b1"]["pnl"]
    row_exit = res["rows"][1]["b1"]["pnl"]
    assert row_base != row_exit


def test_mutating_description_does_not_change_pnl(tmp_path: Path):
    """Verify description text has 0 impact on calculated P&L."""
    sc_file = Path("data/replay/scenarios/scenario_nvda_2024q2.json")
    sc_dict = json.loads(sc_file.read_text())

    (tmp_path / "sc_desc1.json").write_text(json.dumps(sc_dict))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [
            {"scenario_id": "SC-1", "symbol": "NVDA", "description": "Alpha Strategy Test", "file": "sc_desc1.json"},
            {"scenario_id": "SC-2", "symbol": "NVDA", "description": "Omega Strategy Test", "file": "sc_desc1.json"},
        ]
    }))

    res = evaluate_benchmarks(data_dir=tmp_path)
    pnl1 = res["rows"][0]["b1"]["pnl"]
    pnl2 = res["rows"][1]["b1"]["pnl"]
    assert pnl1 == pnl2


def test_empty_manifest_returns_empty_ablation_and_summary(tmp_path: Path):
    """Verify empty manifest returns clean empty datasets."""
    (tmp_path / "manifest.json").write_text(json.dumps({"scenarios": []}))
    res = evaluate_benchmarks(data_dir=tmp_path)
    assert res["rows"] == []
    assert res["ablation_table"] == []
    assert res["summary"] == []


def test_evaluation_does_not_leak_sealed_outcomes_into_decision():
    """Verify that decision pipeline cannot see sealed outcomes."""
    mgr = ReplayDataManager()
    scenario = mgr.load_scenario("SCENARIO-NVDA-2024Q2-AMC")
    underlying = scenario["underlying"]
    assert "exit_spot" not in underlying.model_dump()


def test_late_evidence_timestamp_is_preserved_and_vetoed(tmp_path: Path):
    scenario = json.loads(Path("data/replay/scenarios/scenario_nvda_2024q2.json").read_text())
    scenario["decision_inputs"]["evidence"][0]["observed_at"] = "2024-08-28T19:59:00Z"
    (tmp_path / "late.json").write_text(json.dumps(scenario))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [{"scenario_id": "LATE", "symbol": "NVDA", "file": "late.json"}]
    }))

    loaded = ReplayDataManager(tmp_path).load_scenario("LATE")
    assert loaded["evidence"][0].observed_at == datetime(2024, 8, 28, 19, 59, tzinfo=timezone.utc)
    result = evaluate_benchmarks(tmp_path)
    assert result["rows"][0]["volagent"]["decision"] == "no_trade"
    assert result["rows"][0]["volagent"]["status"] == "VALID (Risk Veto)"


def test_broken_scenarios_are_reported_and_excluded_from_denominator(tmp_path: Path):
    source = Path("data/replay/scenarios/scenario_nvda_2024q2.json")
    (tmp_path / "valid.json").write_text(source.read_text())
    (tmp_path / "manifest.json").write_text(json.dumps({
        "scenarios": [
            {"scenario_id": "VALID", "symbol": "NVDA", "file": "valid.json"},
            {"scenario_id": "BROKEN", "symbol": "BAD", "file": "missing.json"},
        ]
    }))

    result = evaluate_benchmarks(tmp_path)
    assert result["declared_scenarios"] == 2
    assert result["total_scenarios"] == 1
    assert len(result["evaluation_errors"]) == 1
    assert result["summary"][0]["Valid Trades"].endswith("/1")


def test_runtime_ledger_uses_configurable_writable_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """P1-A05 Fix: Ledger DB path is configurable and accepts custom writable paths."""
    custom_db = tmp_path / "custom_test_ledger.db"
    ledger = ExecutionLedger(db_path=custom_db)
    assert custom_db.exists()

    env_db = tmp_path / "env_test_ledger.db"
    monkeypatch.setenv("VOLAGENT_LEDGER_DB_PATH", str(env_db))
    ledger_env = ExecutionLedger()
    assert ledger_env.db_path == env_db



def test_scoreboard_data_structures_render_valid_components():
    """Verify Scoreboard evaluation data structures contain valid types and non-empty schemas."""
    res = evaluate_benchmarks()
    assert isinstance(res["rows"], list)
    assert isinstance(res["ablation_table"], list)
    assert isinstance(res["summary"], list)
    assert len(res["ablation_table"]) > 0
    assert len(res["summary"]) > 0
