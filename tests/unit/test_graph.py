"""Integration tests for the LangGraph StateGraph multi-agent pipeline."""

from volagent.config import load_config
from volagent.domain.enums import AbstentionReason, Decision, GateStatus
from volagent.graph.builder import VolAgentWorkflow


def test_nvda_long_vol_graph_execution():
    """Verify NVDA synthetic scenario: Long Volatility thesis -> Long Straddle."""
    config = load_config()
    config.volagent_replay_scenario_id = "SCENARIO-NVDA-2024Q2-AMC"

    workflow = VolAgentWorkflow(config=config)
    result = workflow.run({"symbol": "NVDA"})

    assert result["run_id"].startswith("run-")
    assert result["final_decision"] == Decision.LONG_STRADDLE
    assert result["approved_candidate"] is not None
    assert result["approved_candidate"].decision == Decision.LONG_STRADDLE
    assert result["risk_report"].overall_status == GateStatus.PASS
    assert result["risk_report"].approved_quantity >= 1
    assert result["abstention_reason"] == AbstentionReason.NONE


def test_tsla_short_vol_graph_execution():
    """Verify TSLA synthetic scenario: Overpriced IV -> Short Iron Butterfly."""
    config = load_config()
    config.volagent_replay_scenario_id = "SCENARIO-TSLA-2024Q3-AMC"

    workflow = VolAgentWorkflow(config=config)
    result = workflow.run({"symbol": "TSLA"})

    assert result["run_id"].startswith("run-")
    assert result["final_decision"] == Decision.SHORT_IRON_BUTTERFLY
    assert result["approved_candidate"] is not None
    assert result["approved_candidate"].decision == Decision.SHORT_IRON_BUTTERFLY
    assert result["risk_report"].overall_status == GateStatus.PASS
    assert result["risk_report"].approved_quantity >= 1


def test_aapl_stale_rejection_graph_execution():
    """Verify AAPL synthetic scenario: Stale quote safety invariant enforces NO_TRADE."""
    config = load_config()
    config.volagent_replay_scenario_id = "SCENARIO-AAPL-2024Q4-STALE"

    workflow = VolAgentWorkflow(config=config)
    result = workflow.run({"symbol": "AAPL"})

    assert result["final_decision"] == Decision.NO_TRADE
    assert result["approved_candidate"] is None  # Approved candidate is strictly cleared!
    assert result["critic_report"].status == GateStatus.FAIL
    assert len(result["rejection_reasons"]) > 0
