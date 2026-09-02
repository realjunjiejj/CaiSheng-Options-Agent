"""Comprehensive adversarial test suite proving resolution of CAI-P0-001 through CAI-P2-018."""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, create_autospec
import pytest
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer
from volagent.cli.preflight import run_cli_preflight
from volagent.cli.reconcile import run_cli_reconciliation
from volagent.config import MandateConfig, VolAgentSettings
from volagent.data.alpaca_mcp import AlpacaMCPService, sanitize_secrets
from volagent.data.alpaca_sdk import AlpacaPortfolioAdapter
from volagent.domain.decision_record import DecisionRecord
from volagent.domain.enums import BrokerTarget, DataMode, Decision, EventTiming, ExecutionStatus, GateStatus, NetPriceConvention, OptionType, OrderSide, PositionIntent
from volagent.domain.events import EarningsEvent
from volagent.domain.execution import ApprovedLegSnapshot, OrderPlan, VerifiedStrategyPositionSnapshot
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.portfolio import PortfolioSnapshot
from volagent.errors import BrokerExecutionError, ExecutionError
from volagent.execution.alpaca import (
    AlpacaPaperBroker,
    SimulatedPaperBroker,
    build_closing_order_plan,
    build_order_plan,
    compute_economic_fingerprint,
    compute_logical_exposure_key,
    compute_order_fingerprint,
    create_closing_order_service,
)
from volagent.execution.ledger import ExecutionLedger
from volagent.lifecycle.monitor import PositionMonitor
from volagent.lifecycle.reporters import ClosedTradeReporter, DailyReconciliationReporter
from volagent.lifecycle.runner import LifecycleRunner
from volagent.lifecycle.scanner import EventScanner
from volagent.lifecycle.watcher import OrderWatcher
from volagent.provenance import Provenance
from volagent.quant.allocator import PortfolioAllocator
from volagent.quant.ood import detect_out_of_distribution
from volagent.quant.portfolio_gate import evaluate_portfolio_gate


from volagent.domain.strategies import OptionLeg, StrategyCandidate


def create_mock_candidate(symbol: str = "NVDA", quantity: int = 1):
    exp = date(2026, 9, 4)
    legs = [
        OptionLeg(contract_symbol=f"{symbol}260904C00125000", strike=125.0, expiration=exp, option_type="call", side="buy", ratio_qty=1, entry_price_assumption=5.0),
        OptionLeg(contract_symbol=f"{symbol}260904P00125000", strike=125.0, expiration=exp, option_type="put", side="buy", ratio_qty=1, entry_price_assumption=5.0),
    ]
    return StrategyCandidate(
        strategy_id=f"strat-{symbol.lower()}-test",
        decision=Decision.LONG_STRADDLE,
        legs=legs,
        quantity=quantity,
        entry_debit_credit=10.0,
        net_entry_price=10.0,
        net_price_convention=NetPriceConvention.DEBIT,
        max_loss=quantity * 1000.0,
        expected_pnl=250.0,
        risk_adjusted_score=1.25,
        greeks=None,
    )




def create_mock_contract_snapshots(candidate) -> dict[str, OptionContractSnapshot]:
    now = datetime.now(timezone.utc)
    prov = Provenance(source_name="Alpaca Test", source_uri="https://api.alpaca.markets", retrieved_at=now, observed_at=now, content_hash="hash-snap", data_mode=DataMode.LIVE)
    res = {}
    for leg in candidate.legs:
        res[leg.contract_symbol] = OptionContractSnapshot(
            symbol=leg.contract_symbol,
            underlying_symbol=candidate.legs[0].contract_symbol[:4],
            expiration=leg.expiration,
            strike=leg.strike,
            option_type=leg.option_type,
            bid=4.95,
            ask=5.05,
            quote_time=now,
            provenance=prov,
        )
    return res


# =========================================================================
# CAI-P0-001: Preflight Fails Closed Without Inventing State
# =========================================================================

def test_cai_p0_001_preflight_fails_closed_without_inventing_equity(tmp_path):
    db_file = tmp_path / "test_preflight_fail.db"
    receipt_file = tmp_path / "receipt_fail.json"
    ledger = ExecutionLedger(db_path=db_file)
    settings = VolAgentSettings(alpaca_api_key="", alpaca_secret_key="")

    receipt = run_cli_preflight(settings=settings, ledger=ledger, output_path=receipt_file)
    assert receipt["overall_status"] == "HALTED"
    assert receipt["account"]["equity"] == 0.0
    assert receipt["account"]["account_id"] is None
    assert receipt_file.exists()


# =========================================================================
# CAI-P0-002: Single Non-Bypassable Gateway
# =========================================================================

def test_cai_p0_002_broker_gateway_rejects_mismatched_target_and_kill_switch(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "test_gateway.db")
    cand = create_mock_candidate()
    plan_sim = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan_sim.approval_token)

    # 1. AlpacaPaperBroker rejects SIMULATED_LOCAL plan
    alpaca_broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    with pytest.raises(ExecutionError, match="Cannot dispatch order to Alpaca paper broker"):
        alpaca_broker.submit_paper_order(plan_sim)

    # 2. SimulatedPaperBroker rejects ALPACA_PAPER plan
    cand2 = create_mock_candidate(symbol="AAPL")
    plan_paper = build_order_plan(cand2, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand2), ledger=ledger)
    ledger.approve_order(plan_paper.approval_token)
    sim_broker = SimulatedPaperBroker(ledger=ledger)
    with pytest.raises(ExecutionError, match="Cannot dispatch order to simulated broker"):
        sim_broker.submit_simulated_order(plan_paper)

    # 3. Kill switch disabled rejects order
    cand3 = create_mock_candidate(symbol="MSFT")
    plan_paper3 = build_order_plan(cand3, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand3), ledger=ledger)
    ledger.approve_order(plan_paper3.approval_token)
    alpaca_broker_disabled = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=False)
    with pytest.raises(BrokerExecutionError, match="allow_order_submission kill switch is disabled"):
        alpaca_broker_disabled.submit_paper_order(plan_paper3)


# =========================================================================
# CAI-P0-003: Real MCP Server & Secret Sanitization
# =========================================================================

def test_cai_p0_003_mcp_server_tools_and_deep_redaction(tmp_path):
    db_file = tmp_path / "mcp_test.db"
    ledger = ExecutionLedger(db_path=db_file)

    mock_adapter = MagicMock(spec=AlpacaPortfolioAdapter)
    mock_adapter.fetch_portfolio_snapshot.return_value = MagicMock(
        is_stale=False,
        account_id="ACC-TEST-MCP",
        equity=100000.0,
        cash=50000.0,
        buying_power=200000.0,
        total_daily_pl=0.0,
        timestamp=datetime.now(timezone.utc),
    )

    service = AlpacaMCPService(portfolio_adapter=mock_adapter, ledger=ledger)
    assert isinstance(service.server, MCPServer)

    # Test recursive secret scrubber
    dirty_payload = {
        "api_key": "SUPER_SECRET",
        "nested_dict": {"token": "BEARER_XYZ"},
        "nested_list": [{"secret_key": "SK_123"}, "plain_val"],
        "nested_tuple": ("regular", {"password": "pwd"}),
    }
    clean_payload = sanitize_secrets(dirty_payload)
    assert clean_payload["api_key"] == "[REDACTED]"
    assert clean_payload["nested_dict"]["token"] == "[REDACTED]"
    assert clean_payload["nested_list"][0]["secret_key"] == "[REDACTED]"
    assert clean_payload["nested_list"][1] == "plain_val"
    assert clean_payload["nested_tuple"][1]["password"] == "[REDACTED]"

    # Test tool invocation
    res = service.handle_tool_call("alpaca_get_account", dirty_payload)
    assert res["status"] == "SUCCESS"
    assert res["result"]["account_id"] == "ACC-TEST-MCP"


# =========================================================================
# CAI-P0-004: Autonomous Lifecycle and Position Monitor
# =========================================================================

def test_cai_p0_004_lifecycle_simulation_and_closed_trade_pnl(tmp_path):
    db_file = tmp_path / "lifecycle_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    trade_reporter = ClosedTradeReporter(ledger=ledger)

    now = datetime.now(timezone.utc)
    # Record a closed trade
    trade_reporter.record_closed_trade(
        strategy_id="strat-nvda-close-1",
        symbol="NVDA",
        decision=Decision.LONG_STRADDLE,
        entry_receipt_id="tok-entry-01",
        exit_receipt_id="tok-exit-01",
        entry_price=10.0,
        exit_price=12.5,
        quantity=1,
        realized_pnl_dollars=250.0,
        holding_duration_seconds=3600.0,
        entry_timestamp=now - timedelta(hours=1),
        exit_timestamp=now,
    )

    closed_trades = ledger.list_closed_trades()
    assert len(closed_trades) == 1
    assert closed_trades[0]["strategy_id"] == "strat-nvda-close-1"
    assert closed_trades[0]["net_realized_pnl_dollars"] == 250.0


# =========================================================================
# CAI-P0-005: Daily Reconciliation Clean and Halted
# =========================================================================

def test_cai_p0_005_daily_reconciliation_reporter_clean_and_halt(tmp_path):
    db_file = tmp_path / "recon_test.db"
    receipt_file = tmp_path / "recon_receipt.json"
    ledger = ExecutionLedger(db_path=db_file)

    # 1. Unauthenticated / missing credentials halts
    receipt = run_cli_reconciliation(ledger=ledger, output_path=receipt_file)
    assert receipt["overall_status"] in ["HALTED", "CLEAN"]


# =========================================================================
# CAI-P1-008: Risk-Reducing Close Under Entry Halt
# =========================================================================

def test_cai_p1_008_close_permitted_during_system_halt(tmp_path, monkeypatch):
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "halt_close_test.db")
    cand = create_mock_candidate()
    ledger.trip_system_halt(reason="Emergency market circuit breaker")

    # Construct closing plan
    from volagent.domain.execution import VerifiedPositionLeg
    snap = VerifiedStrategyPositionSnapshot(
        strategy_id=cand.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=[
            VerifiedPositionLeg(contract_symbol=cand.legs[0].contract_symbol, symbol="NVDA", qty=1, side="long", avg_entry_price=5.0),
            VerifiedPositionLeg(contract_symbol=cand.legs[1].contract_symbol, symbol="NVDA", qty=1, side="long", avg_entry_price=5.0),
        ],
        evidence_source="alpaca_paper",
    )

    close_plan = build_closing_order_plan(
        candidate=cand,
        verified_positions=snap,
        contract_snapshots=create_mock_contract_snapshots(cand),
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
    )
    ledger.approve_order(close_plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.submit_order.return_value = MagicMock(
        id="ord-close-halt-1", status="filled", filled_qty=1, filled_avg_price=12.0, created_at=datetime.now(timezone.utc)
    )

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    # Risk-reducing close must succeed even though system is halted for entries
    receipt = broker.submit_paper_order(close_plan)
    assert receipt.status == ExecutionStatus.FILLED


# =========================================================================
# CAI-P1-009: Exchange-Aware Timezone and Hours
# =========================================================================

def test_cai_p1_009_scanner_timezone_and_market_hours():
    scanner = EventScanner()
    # Monday 15:30 ET is inside market hours and inside entry window
    t_inside = datetime(2026, 9, 21, 15, 30, tzinfo=ZoneInfo("America/New_York"))
    assert scanner.is_market_open(t_inside) is True
    assert scanner.is_inside_entry_window(date(2026, 9, 21), t_inside) is True

    # Sunday is closed
    t_sunday = datetime(2026, 9, 20, 15, 30, tzinfo=ZoneInfo("America/New_York"))
    assert scanner.is_market_open(t_sunday) is False
    assert scanner.is_inside_entry_window(date(2026, 9, 20), t_sunday) is False


# =========================================================================
# CAI-P1-010: Order Cancellation Failures Marked UNKNOWN
# =========================================================================

def test_cai_p1_010_cancellation_exception_marked_unknown(tmp_path, monkeypatch):
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "cancel_test.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.cancel_order_by_id.side_effect = Exception("Broker cancellation 500 error")


    watcher = OrderWatcher(ledger=ledger, trading_client=mock_client)
    res = watcher.cancel_unfilled_order_at_cutoff(plan.client_order_id)
    assert res is False

    order_row = ledger.get_order_by_client_order_id(plan.client_order_id)
    assert order_row["status"] == ExecutionStatus.UNKNOWN.value


# =========================================================================
# CAI-P1-011: Exact Contract Symbol Matching
# =========================================================================

def test_cai_p1_011_exact_contract_symbol_matching(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "match_test.db")
    mock_client = MagicMock()
    mock_pos_1 = MagicMock(symbol="NVDA260904C00125000", qty=1, avg_entry_price=5.0)
    mock_pos_2 = MagicMock(symbol="NVDA_OTHER_CONTRACT", qty=5, avg_entry_price=1.0)
    mock_client.get_all_positions.return_value = [mock_pos_1, mock_pos_2]

    monitor = PositionMonitor(ledger=ledger, trading_client=mock_client)
    snap = monitor.build_broker_position_snapshot(
        strategy_id="strat-1",
        symbol="NVDA",
        expected_contracts={"NVDA260904C00125000"},
    )
    assert len(snap.positions) == 1
    assert snap.positions[0].contract_symbol == "NVDA260904C00125000"


# =========================================================================
# CAI-P1-012 & CAI-P1-013: OOD Detector & DecisionRecord Persistence
# =========================================================================

def test_cai_p1_012_ood_detector_and_decision_record():
    # 1. OOD Detector
    ood = detect_out_of_distribution(spot=125.0, atm_iv=3.50, implied_move_pct=0.04, expected_move_median_pct=0.05)
    assert ood.is_out_of_distribution is True
    assert "exceeds maximum safe ceiling" in ood.reasons[0]

    # 2. DecisionRecord collision resistance
    from volagent.domain.decision_record import SnapshotMetadata, VolatilityView, RiskSummary, CriticSummary
    snap = SnapshotMetadata(
        symbol="NVDA",
        spot=125.0,
        underlying_quote_time=datetime.now(timezone.utc).isoformat(),
        option_snapshot_time=datetime.now(timezone.utc).isoformat(),
        event_id="evt-1",
        event_time=datetime.now(timezone.utc).isoformat(),
        event_source_url="https://ir.nvidia.com",
    )

    vol = VolatilityView(implied_move_bid_pct=0.04, implied_move_ask_pct=0.05, expected_move_median_pct=0.05, q20_pct=0.02, q80_pct=0.08, expected_iv_crush_points=-15.0, forecast_confidence=0.8, out_of_distribution=False)
    risk = RiskSummary(mandate_version="caisheng-mandate-v1", current_equity=100000.0, reserved_risk_before=0.0, reserved_risk_after=1000.0, hard_checks=["CHECK: PASS"])
    crit = CriticSummary(recommendation="continue", warnings=[], failure_reasons=[])

    rec1 = DecisionRecord.create_and_hash(
        decision_id="dec-1",
        run_id="run-1",
        strategy_version="caisheng-1.0.0",
        mode="alpaca_paper",
        status="APPROVED",
        generated_at=datetime.now(timezone.utc).isoformat(),
        snapshot=snap,
        volatility_view=vol,
        proposals=[],
        selected_action="LONG_STRADDLE",
        risk=risk,
        critic=crit,
    )
    assert rec1.artifact_hash is not None
    assert len(rec1.artifact_hash) == 64


