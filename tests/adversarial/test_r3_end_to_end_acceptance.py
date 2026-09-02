"""Adversarial R3 End-to-End Acceptance Test Suite.

Reproduces and permanently locks all 8 independent failures identified in the
CaiSheng Post-Remediation Adversarial Re-audit.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from volagent.config import MandateConfig, VolAgentSettings
from volagent.domain.enums import (
    BrokerTarget,
    Decision,
    ExecutionStatus,
    GateStatus,
    NetPriceConvention,
    OptionType,
    OrderSide,
    PositionIntent,
)
from volagent.domain.execution import (
    ApprovedLegSnapshot,
    OrderPlan,
    VerifiedPositionLeg,
    VerifiedStrategyPositionSnapshot,
)
from volagent.domain.portfolio import PortfolioSnapshot
from volagent.domain.state import VolAgentState
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.errors import BrokerExecutionError, ExecutionError
from volagent.execution.alpaca import (
    AlpacaPaperBroker,
    SimulatedPaperBroker,
    build_closing_order_plan,
    build_order_plan,
    compute_order_fingerprint,
    create_closing_order_service,
)
from volagent.execution.ledger import ExecutionLedger
from volagent.execution.reconciliation import ReconciliationStatus
from volagent.graph.builder import VolAgentWorkflow
from volagent.lifecycle.monitor import PositionMonitor
from volagent.lifecycle.runner import LifecycleRunner
from volagent.lifecycle.scanner import EventScanner
from volagent.data.alpaca_mcp import AlpacaMCPService


@pytest.fixture
def temp_ledger(tmp_path):
    """Provide an isolated temporary SQLite execution ledger."""
    db_path = str(tmp_path / "test_r3_ledger.db")
    return ExecutionLedger(db_path=db_path)


def _make_sample_order_plan(
    symbol: str = "NVDA",
    qty: int = 1,
    broker_target: BrokerTarget = BrokerTarget.ALPACA_PAPER,
    ledger: ExecutionLedger | None = None,
) -> OrderPlan:
    now = datetime.now(timezone.utc)
    legs = [
        ApprovedLegSnapshot(
            contract_symbol=f"{symbol}260918C00120000",
            underlying_symbol=symbol,
            option_type=OptionType.CALL,
            strike=120.0,
            expiration=date(2026, 9, 18),
            side=OrderSide.BUY,
            ratio_qty=1,
            position_intent=PositionIntent.BUY_TO_OPEN,
            bid=5.00,
            ask=5.20,
            multiplier=100,
            vendor_implied_vol=0.55,
            vendor_delta=0.50,
            quote_time=now,
            entry_price_assumption=5.10,
        ),
        ApprovedLegSnapshot(
            contract_symbol=f"{symbol}260918P00120000",
            underlying_symbol=symbol,
            option_type=OptionType.PUT,
            strike=120.0,
            expiration=date(2026, 9, 18),
            side=OrderSide.BUY,
            ratio_qty=1,
            position_intent=PositionIntent.BUY_TO_OPEN,
            bid=5.00,
            ask=5.20,
            multiplier=100,
            vendor_implied_vol=0.55,
            vendor_delta=-0.50,
            quote_time=now,
            entry_price_assumption=5.10,
        ),
    ]
    cand = StrategyCandidate(
        strategy_id="strat-test-r3",
        decision=Decision.LONG_STRADDLE,
        legs=[
            OptionLeg(
                contract_symbol=f"{symbol}260918C00120000",
                option_type="call",
                strike=120.0,
                expiration=date(2026, 9, 18),
                side="buy",
                position_intent="buy_to_open",
                ratio_qty=1,
                entry_price_assumption=5.10,
            ),
            OptionLeg(
                contract_symbol=f"{symbol}260918P00120000",
                option_type="put",
                strike=120.0,
                expiration=date(2026, 9, 18),
                side="buy",
                position_intent="buy_to_open",
                ratio_qty=1,
                entry_price_assumption=5.10,
            ),
        ],
        quantity=qty,
        entry_debit_credit=10.20,
        max_loss=1020.0,
        max_profit=None,
        break_evens=[109.80, 130.20],
        expected_pnl=150.0,
        risk_adjusted_score=1.5,
    )
    from volagent.domain.market import OptionContractSnapshot
    from volagent.provenance import Provenance
    from volagent.domain.enums import DataMode

    snaps = {
        leg.contract_symbol: OptionContractSnapshot(
            symbol=leg.contract_symbol,
            underlying_symbol=symbol,
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
            bid=5.00,
            ask=5.20,
            quote_time=now,
            multiplier=100,
            provenance=Provenance(
                source_name="Alpaca Paper Market Data",
                source_uri=f"https://paper-api.alpaca.markets/v2/options/contracts/{leg.contract_symbol}",
                retrieved_at=now,
                observed_at=now,
                content_hash="hash-sample-snap",
                data_mode=DataMode.LIVE,
            ),
        )
        for leg in cand.legs
    }
    plan = build_order_plan(cand, broker_target=broker_target, ledger=ledger, contract_snapshots=snaps if broker_target == BrokerTarget.ALPACA_PAPER else None)
    return plan


# ============================================================================
# Acceptance Test 1: Autonomous runner must invoke real LangGraph and generate decisions
# ============================================================================

def test_autonomous_runner_must_invoke_real_graph(temp_ledger):
    """CAI-R3-P0-001: Autonomous runner executes scan -> graph -> decision without swallowing errors."""
    runner = LifecycleRunner(ledger=temp_ledger)
    
    # Wednesday 15:30 ET (20:30 UTC for EDT / 19:30 UTC)
    # Market close is 16:00 ET (20:00 UTC during EDT)
    # Scanner checks 15:15 to 15:55 ET for AMC events
    now_amc = datetime(2026, 9, 16, 19, 30, tzinfo=timezone.utc)
    calendar_data = {
        "earnings_calendar": [
            {
                "symbol": "NVDA",
                "company_name": "NVIDIA Corporation",
                "earnings_date": "2026-09-16",
                "earnings_time": "AMC",
                "confirmed": True,
                "expected_move_pct": 0.085,
                "implied_move_pct": 0.072,
                "straddle_bid": 7.00,
                "straddle_ask": 7.40,
                "spot_price": 120.0,
                "source_url": "https://investor.nvidia.com/events/2026",
            }
        ]
    }

    
    res = runner.run_cycle(calendar=calendar_data, current_time=now_amc)
    assert res["events_found"] == 1
    assert res["decisions_generated"] >= 1, "Lifecycle runner must generate at least 1 graph decision for eligible event"
    assert res["reconciliation_status"] == "CLEAN"


# ============================================================================
# Acceptance Test 2: Replay DecisionRecord uses replay_synthetic provenance
# ============================================================================

def test_replay_decision_mode_is_truthful(temp_ledger):
    """CAI-R3-P0-006: DecisionRecord generated during replay must state mode='replay_synthetic'."""
    workflow = VolAgentWorkflow()
    now_utc = datetime(2026, 9, 16, 15, 30, tzinfo=timezone.utc)
    initial_inputs = {
        "symbol": "NVDA",
        "now": now_utc,
        "run_id": "run-replay-test-01",
        "ledger": temp_ledger,
    }
    result = workflow.run(initial_inputs)
    
    records = temp_ledger.list_decision_records()
    assert len(records) >= 1, "Decision record must be persisted to ledger"
    
    # Read persisted record
    dec_row = records[0]
    payload = json.loads(dec_row["raw_payload"])
    assert payload["mode"] == "replay_synthetic", f"Expected mode 'replay_synthetic', got '{payload.get('mode')}'"


# ============================================================================
# Acceptance Test 3: Every graph decision is persisted in SQLite
# ============================================================================

def test_every_graph_decision_is_persisted(temp_ledger):
    """CAI-R3-P0-005: DecisionRecords must persist reliably to SQLite without schema attribute errors."""
    workflow = VolAgentWorkflow()
    now_utc = datetime(2026, 9, 16, 15, 30, tzinfo=timezone.utc)
    initial_inputs = {
        "symbol": "TSLA",
        "mode": "live_read_only",
        "now": now_utc,
        "run_id": "run-persist-test-01",
        "ledger": temp_ledger,
    }
    result = workflow.run(initial_inputs)
    
    records = temp_ledger.list_decision_records()
    assert len(records) >= 1, "Graph execution must persist DecisionRecord in SQLite"
    assert records[0]["symbol"] == "TSLA"
    assert records[0]["status"] in ("APPROVED", "NO_TRADE")


# ============================================================================
# Acceptance Test 4: MCP Discovery includes alpaca_get_option_chain
# ============================================================================

def test_mcp_discovery_includes_option_chain():
    """CAI-R3-P0-004: FastMCP server tool discovery must register and expose alpaca_get_option_chain."""
    service = AlpacaMCPService()
    
    # FastMCP server inspect
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        tools = loop.run_until_complete(service.server.list_tools())
        tool_names = [t.name for t in tools]
        assert "alpaca_get_option_chain" in tool_names, f"alpaca_get_option_chain missing from tools: {tool_names}"
    finally:
        loop.close()


# ============================================================================
# Acceptance Test 5: MCP write tool schema validation and canonical order routing
# ============================================================================

def test_mcp_write_tool_schema_and_execution(temp_ledger):
    """CAI-R3-P0-004: MCP multileg order tool must use canonical OrderPlan schema and valid expiry."""
    service = AlpacaMCPService(ledger=temp_ledger)
    
    call_res = service.handle_tool_call(
        "alpaca_submit_multileg_order",
        {
            "symbol": "NVDA",
            "quantity": 1,
            "limit_price": 10.20,
            "decision": "LONG_STRADDLE",
            "legs": [
                {
                    "contract_symbol": "NVDA260918C00120000",
                    "side": "buy",
                    "position_intent": "buy_to_open",
                    "ratio_qty": 1,
                    "strike": 120.0,
                    "option_type": "call",
                },
                {
                    "contract_symbol": "NVDA260918P00120000",
                    "side": "buy",
                    "position_intent": "buy_to_open",
                    "ratio_qty": 1,
                    "strike": 120.0,
                    "option_type": "put",
                },
            ],
        },
    )
    
    # A schema-valid request must never leak an internal exception. Raw order
    # construction is expected to be rejected until it references a canonical,
    # independently approved OrderPlan.
    assert call_res["status"] in ("SUCCESS", "REJECTED")
    err_msg = call_res.get("result", {}).get("error", "")
    assert "ValidationError" not in err_msg
    assert "FrozenInstanceError" not in err_msg


# ============================================================================
# Acceptance Test 6: Broker gateway rejects entry at max open strategies
# ============================================================================

def test_gateway_enforces_open_strategy_limit(temp_ledger, monkeypatch):
    """CAI-R3-P0-002: submit_paper_order must recheck portfolio limits and reject at 3 open strategies."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    broker = AlpacaPaperBroker(
        api_key="test_key",
        secret_key="test_secret",
        paper=True,
        ledger=temp_ledger,
        allow_order_submission=True,
    )
    mock_client = MagicMock()
    # Mock portfolio with 3 open strategies (capacity breach)
    mock_client.get_account.return_value = MagicMock(
        id="test-acc-id",
        equity="100000.00",
        cash="100000.00",
        buying_power="400000.00",
        status="ACTIVE",
    )
    # Return 3 existing positions
    mock_client.get_all_positions.return_value = [
        MagicMock(symbol="AAPL260918C00200000", qty="1", avg_entry_price="5.0"),
        MagicMock(symbol="MSFT260918C00400000", qty="1", avg_entry_price="8.0"),
        MagicMock(symbol="GOOG260918C00180000", qty="1", avg_entry_price="6.0"),
    ]
    broker._trading_client = mock_client
    
    plan = _make_sample_order_plan(symbol="NVDA", qty=1, ledger=temp_ledger)
    
    # Pre-register approval in ledger
    temp_ledger.record_approval(plan.approval_token, approver="test_admin")
    
    # Setting open_strategies_count = 3 in portfolio adapter
    clean_reconciliation = MagicMock(
        status=ReconciliationStatus.CLEAN,
        mismatches=[],
        reconciliation_id="rec-isolated-portfolio-gate",
    )
    with (
        patch(
            "volagent.execution.reconciliation.reconcile_broker_and_ledger",
            return_value=clean_reconciliation,
        ),
        patch("volagent.data.alpaca_sdk.AlpacaPortfolioAdapter.fetch_portfolio_snapshot") as mock_snap,
    ):
        mock_snap.return_value = PortfolioSnapshot(
            equity=100000.0,
            cash=100000.0,
            buying_power=400000.0,
            open_strategies_count=3,  # Max limit is 3
            new_entries_today_count=0,
            # Isolate the concurrency boundary.  This must fail because there
            # are already three open strategies, not because another risk cap
            # happened to fail first.
            reserved_risk_dollars=0.0,
            daily_realized_pl=0.0,
            high_water_equity=100000.0,
            timestamp=datetime.now(timezone.utc),
            account_id="test-acc-id",
        )

        with pytest.raises(BrokerExecutionError) as exc_info:
            broker.submit_paper_order(plan)
        
        assert "Portfolio Mandate Gate" in str(exc_info.value) or "open_strategies" in str(exc_info.value)


# ============================================================================
# Acceptance Test 7: Triggered simulated close completes and persists realized P&L
# ============================================================================

def test_triggered_simulated_close_completes(temp_ledger):
    """CAI-R3-P0-003: Monitor triggers exit, builds closing plan, executes and persists realized P&L."""
    monitor = PositionMonitor(ledger=temp_ledger)

    plan = _make_sample_order_plan(symbol="NVDA", qty=1, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=temp_ledger)
    temp_ledger.approve_order(plan.approval_token, actor="acceptance_test")
    temp_ledger.persist_order_intent(
        plan.approval_token, full_order_plan=plan.model_dump(mode="json")
    )
    temp_ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    temp_ledger.record_broker_result(
        plan.approval_token,
        ExecutionStatus.SIMULATED,
        broker_order_id="sim-entry-triggered-close",
        filled_quantity=1,
        average_price=10.20,
    )
    # Create position snapshot with matching contracts
    verified_snapshot = VerifiedStrategyPositionSnapshot(
        strategy_id=plan.approval_token,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=[
            VerifiedPositionLeg(
                contract_symbol="NVDA260918C00120000",
                symbol="NVDA",
                qty=1,
                side="long",
                avg_entry_price=5.10,
            ),
            VerifiedPositionLeg(
                contract_symbol="NVDA260918P00120000",
                symbol="NVDA",
                qty=1,
                side="long",
                avg_entry_price=5.10,
            ),
        ],
        evidence_source="simulated",
    )
    
    strategy_row = {
        "strategy_id": plan.approval_token,
        "client_order_id": plan.client_order_id,
        "approval_token": plan.approval_token,
        "symbol": "NVDA",
        "quantity": 1,
        "limit_price": 10.20,
        "strategy_decision": "LONG_STRADDLE",
        "full_order_plan": json.dumps(plan.model_dump(mode="json")),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Force an exit trigger (e.g. mark price = 16.00 for 56% profit)
    report = monitor.monitor_and_close_strategy(
        strategy_row=strategy_row,
        verified_snapshot=verified_snapshot,
        current_mark_price=16.00,
    )
    
    assert report.status == "CLOSED", f"Expected CLOSED status, got {report.status}"
    closed_trades = temp_ledger.list_closed_trades()
    assert len(closed_trades) >= 1, "Closed trade record must be persisted to SQLite"
    assert closed_trades[0]["symbol"] == "NVDA"
    pnl = closed_trades[0].get("net_realized_pnl_dollars", closed_trades[0].get("gross_realized_pnl_dollars", 0.0))
    assert pnl > 0, "Realized P&L must be positive on profit exit"



# ============================================================================
# Acceptance Test 8: Missing event-source evidence is rejected, not fabricated
# ============================================================================

def test_scanner_rejects_missing_source_instead_of_fabricating_one():
    """CAI-R3-P1-009: EventScanner must reject events lacking verified source_url rather than fabricating IR portal."""
    scanner = EventScanner()
    now_amc = datetime(2026, 9, 16, 19, 30, tzinfo=timezone.utc)
    calendar_without_source = {
        "earnings_calendar": [
            {
                "symbol": "AMD",
                "company_name": "Advanced Micro Devices",
                "earnings_date": "2026-09-16",
                "earnings_time": "AMC",
                "confirmed": True,
                "expected_move_pct": 0.075,
                "implied_move_pct": 0.065,
                "spot_price": 150.0,
                # Missing source_url
            }
        ]
    }
    eligible = scanner.scan_eligible_events(calendar_without_source, current_time=now_amc)
    assert len(eligible) == 0, "Events without valid source_url must be rejected, not fabricated with fake URL"
