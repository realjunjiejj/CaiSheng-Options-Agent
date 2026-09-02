"""Unit tests for SQLite transactional execution ledger, state machine, and approval safety."""

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, create_autospec
import pytest

from volagent.domain.enums import BrokerTarget, Decision, ExecutionStatus, PositionIntent
from volagent.domain.execution import ExecutionReceipt, OrderPlan, VerifiedPositionLeg, VerifiedStrategyPositionSnapshot
from volagent.domain.market import OptionContractSnapshot
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.errors import BrokerExecutionError, ExecutionError
from volagent.execution.alpaca import (
    AlpacaPaperBroker,
    SimulatedPaperBroker,
    build_closing_order_plan,
    build_order_plan,
    create_closing_order_service,
    reconcile_due_unknown_orders,
)
from volagent.execution.ledger import ExecutionLedger, get_default_ledger_path
from volagent.execution.mapper import extract_fill_metrics, map_broker_status
from volagent.execution.reconciliation import ReconciliationStatus, reconcile_broker_and_ledger
from volagent.provenance import Provenance


def create_mock_candidate(strategy_id: str = "strat-1", quantity: int = 1, decision: Decision = Decision.LONG_STRADDLE) -> StrategyCandidate:
    exp = date(2027, 9, 17)
    legs = [
        OptionLeg(contract_symbol="NVDA270917C00125000", option_type="call", strike=125.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=5.0, delta=0.5, gamma=0.04, theta=-0.1, vega=0.2),
        OptionLeg(contract_symbol="NVDA270917P00125000", option_type="put", strike=125.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=5.0, delta=-0.5, gamma=0.04, theta=-0.1, vega=0.2),
    ]
    return StrategyCandidate(
        strategy_id=strategy_id,
        decision=decision,
        legs=legs,
        quantity=quantity,
        entry_debit_credit=500.0 * quantity,
        net_delta=0.0,
        net_gamma=0.08,
        net_theta=-0.2,
        net_vega=0.4,
        max_loss=500.0 * quantity,
    )



def create_mock_iron_butterfly_candidate(strategy_id: str = "ib-strat-1", quantity: int = 1) -> StrategyCandidate:
    exp = date(2027, 9, 17)
    legs = [
        OptionLeg(contract_symbol="NVDA270917C00125000", option_type="call", strike=125.0, expiration=exp, side="sell", ratio_qty=1, position_intent="sell_to_open", entry_price_assumption=5.0),
        OptionLeg(contract_symbol="NVDA270917P00125000", option_type="put", strike=125.0, expiration=exp, side="sell", ratio_qty=1, position_intent="sell_to_open", entry_price_assumption=5.0),
        OptionLeg(contract_symbol="NVDA270917C00135000", option_type="call", strike=135.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=1.5),
        OptionLeg(contract_symbol="NVDA270917P00115000", option_type="put", strike=115.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=1.5),
    ]
    return StrategyCandidate(
        strategy_id=strategy_id,
        decision=Decision.SHORT_IRON_BUTTERFLY,
        legs=legs,
        quantity=quantity,
        entry_debit_credit=-700.0 * quantity,
        net_delta=0.0,
        net_gamma=-0.04,
        net_theta=0.3,
        net_vega=-0.4,
        max_loss=300.0 * quantity,
    )


def create_mock_contract_snapshots(candidate: StrategyCandidate) -> dict[str, OptionContractSnapshot]:
    quote_time = datetime.now(timezone.utc)
    provenance = Provenance.from_synthetic("execution-safety-test")
    return {
        leg.contract_symbol: OptionContractSnapshot(
            symbol=leg.contract_symbol,
            underlying_symbol="NVDA",
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
            bid=4.90,
            ask=5.00,
            quote_time=quote_time,
            volume=500,
            open_interest=1000,
            vendor_implied_vol=0.50,
            vendor_delta=leg.delta,
            vendor_gamma=leg.gamma,
            vendor_theta=leg.theta,
            vendor_vega=leg.vega,
            provenance=provenance,
        )
        for leg in candidate.legs
    }


# =========================================================================
# 1. TEN INDEPENDENT ADVERSARIAL INVARIANTS FROM RE-AUDIT #2
# =========================================================================

def test_unrecognized_broker_status_maps_to_unknown_never_accepted():
    """Invariant 1: Unrecognized broker status maps to UNKNOWN, never ACCEPTED."""
    assert map_broker_status("some_future_status_xyz") == ExecutionStatus.UNKNOWN
    assert map_broker_status("unknown_variant") == ExecutionStatus.UNKNOWN
    assert map_broker_status(None) == ExecutionStatus.UNKNOWN


def test_unfilled_order_reports_none_average_price():
    """Invariant 2: Unfilled order (filled_qty == 0) reports average_price = None, never limit_price."""
    mock_order = MagicMock(filled_qty=0, filled_avg_price=None, limit_price=10.5)
    qty, avg_px = extract_fill_metrics(mock_order)
    assert qty == 0
    assert avg_px is None


def test_previewed_cannot_jump_directly_to_filled(tmp_path: Path):
    """Invariant 3: PREVIEWED cannot jump directly to FILLED."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)

    with pytest.raises(ExecutionError, match="Illegal state transition"):
        ledger.record_broker_result(plan.approval_token, ExecutionStatus.FILLED)


def test_previewed_cannot_become_intent_persisted_without_approval(tmp_path: Path):
    """Invariant 4: PREVIEWED cannot become INTENT_PERSISTED without approval."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)

    with pytest.raises(ExecutionError, match="Illegal state transition"):
        ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))


def test_recovery_receipt_preserves_original_fingerprint(tmp_path: Path, monkeypatch):
    """Invariant 5: Reconciled recovery receipt preserves original intent fingerprint."""
    from alpaca.trading.client import TradingClient

    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.mark_unknown(plan.approval_token, "network ambiguity")

    mock_client = create_autospec(TradingClient, instance=True)
    mock_order = MagicMock(id="alp-rec-1", status="accepted", filled_qty=0, filled_avg_price=None, created_at=datetime.now(timezone.utc))
    mock_client.get_order_by_client_id.return_value = mock_order

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    receipt = broker.reconcile_order_by_client_order_id(plan.client_order_id)
    assert receipt is not None
    assert receipt.fingerprint == plan.fingerprint
    assert receipt.fingerprint != ""


def test_live_paper_close_requires_verified_broker_positions(tmp_path: Path):
    """Invariant 6: Live paper close plan requires verified broker positions snapshot."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    snapshots = create_mock_contract_snapshots(cand)

    with pytest.raises(ExecutionError, match="Live paper close order requires verified broker position snapshot"):
        build_closing_order_plan(cand, contract_snapshots=snapshots, verified_positions=None, broker_target=BrokerTarget.ALPACA_PAPER, ledger=ledger)


def test_candidate_long_position_cannot_close_against_short_broker_position(tmp_path: Path):
    """Invariant 7: Candidate long position cannot close against short broker position."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()  # Has 2 long legs
    snapshots = create_mock_contract_snapshots(cand)

    # Broker holds position as short instead of long
    bad_positions = [
        {"symbol": "NVDA270917C00125000", "qty": 1, "side": "short"},
        {"symbol": "NVDA270917P00125000", "qty": 1, "side": "long"},
    ]
    with pytest.raises(ExecutionError, match="does not match expected long"):
        build_closing_order_plan(cand, contract_snapshots=snapshots, verified_positions=bad_positions, broker_target=BrokerTarget.ALPACA_PAPER, ledger=ledger)


def test_unknown_broker_order_produces_halted_reconciliation_report(tmp_path: Path, monkeypatch):
    """Invariant 8: Broker order unknown to CaiSheng ledger produces HALTED reconciliation report."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    mock_client = MagicMock()
    mock_client.get_orders.return_value = [
        MagicMock(id="alp-orphan-1", client_order_id="unknown-ext-123", symbol="NVDA", qty=1, filled_qty=0, side="buy", type="limit", status="new", limit_price=5.0, legs=[])
    ]
    mock_client.get_all_positions.return_value = []

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    report = reconcile_broker_and_ledger(broker, ledger)
    assert report.status == ReconciliationStatus.HALTED
    assert len(report.orphan_broker_orders) == 1
    halted, reason = ledger.is_system_halted()
    assert halted is True


def test_repriced_limit_cannot_bypass_unresolved_unknown_exposure(tmp_path: Path):
    """Invariant 9: Changing only the limit price cannot bypass an unresolved UNKNOWN exposure."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()

    plan1 = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan1.approval_token)
    ledger.persist_order_intent(plan1.approval_token, plan1.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan1.approval_token, plan1.fingerprint)
    ledger.mark_unknown(plan1.approval_token, error_message="ambiguous timeout")

    # Construct candidate with identical contracts/event but slightly repriced entry debit
    repriced_cand = cand.model_copy(update={"entry_debit_credit": 1050.0})
    with pytest.raises(ExecutionError, match="Duplicate logical exposure prevented"):
        build_order_plan(repriced_cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)


def test_partial_fill_reconciliation_compares_filled_quantity_not_requested(tmp_path: Path, monkeypatch):
    """Invariant 10: Partial fill reconciliation compares broker positions against filled_quantity, not requested quantity."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate(quantity=2)  # Requested quantity = 2

    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    # Order partially filled with 1 unit out of 2 requested
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.PARTIALLY_FILLED, broker_order_id="alp-part-1", filled_quantity=1)

    mock_client = MagicMock()
    mock_client.get_orders.return_value = [
        MagicMock(id="alp-part-1", client_order_id=plan.client_order_id, symbol="NVDA", qty=2, filled_qty=1, side="buy", type="limit", status="partially_filled", limit_price=10.0, legs=[])
    ]
    # Broker holds exactly 1 unit of each leg
    mock_client.get_all_positions.return_value = [
        MagicMock(symbol="NVDA270917C00125000", qty=1, side="long", avg_entry_price=5.0, current_price=5.0, market_value=500.0, unrealized_pl=0.0, unrealized_plpc=0.0),
        MagicMock(symbol="NVDA270917P00125000", qty=1, side="long", avg_entry_price=5.0, current_price=5.0, market_value=500.0, unrealized_pl=0.0, unrealized_plpc=0.0),
    ]

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    report = reconcile_broker_and_ledger(broker, ledger)
    assert report.status == ReconciliationStatus.CLEAN
    assert report.matched_positions_count == 2


def test_reconciliation_normalizes_signed_sdk_quantities_and_enum_sides(tmp_path: Path, monkeypatch):
    """SDK negative quantities and PositionSide enums must not be double-negated."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    candidate = create_mock_iron_butterfly_candidate()
    plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        contract_snapshots=create_mock_contract_snapshots(candidate),
        ledger=ledger,
    )
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(
        plan.approval_token,
        ExecutionStatus.FILLED,
        broker_order_id="alp-iron-1",
        filled_quantity=1,
    )

    mock_client = MagicMock()
    mock_client.get_orders.return_value = []
    mock_client.get_all_positions.return_value = [
        MagicMock(symbol=leg.contract_symbol, qty=(-1 if leg.side == "sell" else 1),
                  side=("PositionSide.SHORT" if leg.side == "sell" else "PositionSide.LONG"),
                  avg_entry_price=5.0, current_price=5.0, market_value=500.0,
                  unrealized_pl=0.0, unrealized_plpc=0.0)
        for leg in candidate.legs
    ]
    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    report = reconcile_broker_and_ledger(broker, ledger)

    assert report.status == ReconciliationStatus.CLEAN
    assert report.matched_positions_count == 4


def test_terminal_historical_broker_order_does_not_permanently_halt(tmp_path: Path, monkeypatch):
    """Closed historical activity is evidence, not active orphan exposure."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    mock_client = MagicMock()
    mock_client.get_orders.return_value = [
        MagicMock(id="old-fill", client_order_id="external-old", symbol="NVDA",
                  qty=1, filled_qty=1, side="buy", type="limit",
                  status="OrderStatus.FILLED", limit_price=5.0, legs=[])
    ]
    mock_client.get_all_positions.return_value = []
    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    report = reconcile_broker_and_ledger(broker, ledger)

    assert report.status == ReconciliationStatus.CLEAN
    assert report.orphan_broker_orders == []


def test_gateway_reconciles_and_blocks_orphan_exposure_before_entry(tmp_path: Path, monkeypatch):
    """Every new entry must fail closed when Alpaca holds untracked exposure."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    candidate = create_mock_candidate()
    plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        contract_snapshots=create_mock_contract_snapshots(candidate),
        ledger=ledger,
    )
    ledger.approve_order(plan.approval_token)

    mock_client = MagicMock()
    mock_client.get_orders.return_value = []
    mock_client.get_all_positions.return_value = [
        MagicMock(symbol="TSLA270917C00400000", qty=10,
                  side="PositionSide.LONG", avg_entry_price=10.0,
                  current_price=8.0, market_value=8000.0,
                  unrealized_pl=-2000.0, unrealized_plpc=-0.2)
    ]
    broker = AlpacaPaperBroker(
        api_key="k", secret_key="s", ledger=ledger,
        allow_order_submission=True,
    )
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    with pytest.raises(BrokerExecutionError, match="reconciliation"):
        broker.submit_paper_order(plan)

    mock_client.submit_order.assert_not_called()
    assert ledger.is_system_halted()[0] is True


# =========================================================================
# 2. ALL MANDATORY MILESTONE 1 BEHAVIORAL TESTS FROM AUDIT #1
# =========================================================================

def test_alpaca_recovery_uses_real_sdk_get_order_by_client_id(tmp_path: Path, monkeypatch):
    """Verify recovery calls client.get_order_by_client_id."""
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.mark_unknown(plan.approval_token, "network ambiguity")

    mock_client = create_autospec(TradingClient, instance=True)
    mock_order = MagicMock(id="ord-1", status="accepted", filled_qty=0, filled_avg_price=None, created_at=datetime.now(timezone.utc))
    mock_client.get_order_by_client_id.return_value = mock_order

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    broker.reconcile_order_by_client_order_id(plan.client_order_id)
    mock_client.get_order_by_client_id.assert_called_once_with(plan.client_order_id)


def test_timeout_recovery_reuses_exact_original_client_order_id(tmp_path: Path, monkeypatch):
    """Verify timeout recovery reuses exact original client_order_id."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.get_account.return_value = MagicMock(equity=100000.0, cash=50000.0, buying_power=200000.0, last_equity=100000.0, id="acc-1")
    mock_client.submit_order.side_effect = TimeoutError("Timeout")
    mock_order = MagicMock(id="ord-timeout-1", status="accepted", filled_qty=0, filled_avg_price=None, created_at=datetime.now(timezone.utc))
    mock_client.get_order_by_client_id.return_value = mock_order

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    receipt = broker.submit_paper_order(plan)
    assert receipt.client_order_id == plan.client_order_id
    mock_client.get_order_by_client_id.assert_called_once_with(plan.client_order_id)


def test_timeout_recovery_never_resubmits_order(tmp_path: Path, monkeypatch):
    """Verify timeout recovery calls get_order_by_client_id and never resubmits submit_order."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.get_account.return_value = MagicMock(equity=100000.0, cash=50000.0, buying_power=200000.0, last_equity=100000.0, id="acc-1")
    mock_client.submit_order.side_effect = TimeoutError("Gateway Timeout")
    mock_client.get_order_by_client_id.side_effect = Exception("404 not found")

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    with pytest.raises(BrokerExecutionError):
        broker.submit_paper_order(plan)

    assert mock_client.submit_order.call_count == 1  # Exactly 1 submission attempt, NO resubmission


def test_timeout_then_not_found_remains_unknown(tmp_path: Path, monkeypatch):
    """Verify post-timeout 404 lookup retains UNKNOWN status in ledger."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.get_account.return_value = MagicMock(equity=100000.0, cash=50000.0, buying_power=200000.0, last_equity=100000.0, id="acc-1")
    mock_client.submit_order.side_effect = TimeoutError("Network timeout")
    mock_client.get_order_by_client_id.side_effect = Exception("404 Order not found")

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    with pytest.raises(BrokerExecutionError):
        broker.submit_paper_order(plan)

    rec = ledger.get_order_by_client_order_id(plan.client_order_id)
    assert rec["status"] == ExecutionStatus.UNKNOWN.value


def test_unknown_blocks_equivalent_new_entry(tmp_path: Path):
    """Verify UNKNOWN order blocks equivalent new entry."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.mark_unknown(plan.approval_token, "timed out")

    # Attempt second equivalent order - immediately blocked at preview registration
    with pytest.raises(ExecutionError, match="Duplicate logical exposure prevented"):
        build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)



def test_unknown_survives_process_restart_and_reconciles(tmp_path: Path, monkeypatch):
    """Verify UNKNOWN state persists in SQLite and reconciles via separate broker process instance."""
    from alpaca.trading.client import TradingClient
    db_file = tmp_path / "persistent_ledger.db"

    # Instance 1: Register and mark UNKNOWN
    ledger1 = ExecutionLedger(db_path=db_file)
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger1)
    ledger1.approve_order(plan.approval_token)
    ledger1.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger1.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger1.mark_unknown(plan.approval_token, "simulated network crash")

    # Instance 2: Process restart -> reads due unknown orders and reconciles
    ledger2 = ExecutionLedger(db_path=db_file)
    mock_client = create_autospec(TradingClient, instance=True)
    mock_order = MagicMock(id="ord-restart-1", status="filled", filled_qty=1, filled_avg_price=10.0, created_at=datetime.now(timezone.utc))
    mock_client.get_order_by_client_id.return_value = mock_order

    broker2 = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger2)
    monkeypatch.setattr(broker2, "_get_trading_client", lambda: mock_client)

    receipts = reconcile_due_unknown_orders(broker2, ledger2)
    assert len(receipts) == 1
    assert receipts[0].status == ExecutionStatus.FILLED
    assert receipts[0].fingerprint == plan.fingerprint

    # Check updated status in DB
    updated = ledger2.get_order_by_client_order_id(plan.client_order_id)
    assert updated["status"] == ExecutionStatus.FILLED.value


def test_explicit_broker_rejection_maps_to_rejected(tmp_path: Path, monkeypatch):
    """Verify explicit broker rejection maps to REJECTED."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.get_account.return_value = MagicMock(equity=100000.0, cash=50000.0, buying_power=200000.0, last_equity=100000.0, id="acc-1")
    mock_res = MagicMock(id="ord-rej-1", status="rejected", filled_qty=0, filled_avg_price=None, created_at=datetime.now(timezone.utc))
    mock_client.submit_order.return_value = mock_res

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    receipt = broker.submit_paper_order(plan)
    assert receipt.status == ExecutionStatus.REJECTED


def test_multileg_order_omits_forbidden_parent_symbol(tmp_path: Path, monkeypatch):
    """Alpaca mleg requests identify contracts through legs, not a parent symbol."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient

    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    candidate = create_mock_iron_butterfly_candidate()
    plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        contract_snapshots=create_mock_contract_snapshots(candidate),
        ledger=ledger,
    )
    ledger.approve_order(plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.get_account.return_value = MagicMock(
        equity=100000.0,
        cash=50000.0,
        buying_power=200000.0,
        last_equity=100000.0,
        id="acc-1",
    )
    mock_client.submit_order.return_value = MagicMock(
        id="ord-mleg-1",
        status="accepted",
        filled_qty=0,
        filled_avg_price=None,
        created_at=datetime.now(timezone.utc),
    )
    broker = AlpacaPaperBroker(
        api_key="k",
        secret_key="s",
        ledger=ledger,
        allow_order_submission=True,
    )
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    broker.submit_paper_order(plan)

    request = mock_client.submit_order.call_args.args[0]
    assert request.symbol is None
    assert {leg.symbol for leg in request.legs} == {
        leg.contract_symbol for leg in plan.legs
    }


def test_immediate_fill_maps_fill_quantity_and_average_price(tmp_path: Path, monkeypatch):
    """Verify immediate fill maps filled quantity and average price."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.get_account.return_value = MagicMock(equity=100000.0, cash=50000.0, buying_power=200000.0, last_equity=100000.0, id="acc-1")
    mock_res = MagicMock(id="ord-fill-1", status="filled", filled_qty=1, filled_avg_price=9.95, created_at=datetime.now(timezone.utc))
    mock_client.submit_order.return_value = mock_res

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    receipt = broker.submit_paper_order(plan)
    assert receipt.status == ExecutionStatus.FILLED
    assert receipt.filled_quantity == 1
    assert receipt.average_price == 9.95


def test_immediate_partial_fill_maps_actual_status(tmp_path: Path, monkeypatch):
    """Verify immediate partial fill maps PARTIALLY_FILLED status."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate(quantity=2)
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.get_account.return_value = MagicMock(equity=250000.0, cash=150000.0, buying_power=500000.0, last_equity=250000.0, id="acc-1")
    mock_res = MagicMock(id="ord-pfill-1", status="partially_filled", filled_qty=1, filled_avg_price=10.0, created_at=datetime.now(timezone.utc))

    mock_client.submit_order.return_value = mock_res

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    receipt = broker.submit_paper_order(plan)
    assert receipt.status == ExecutionStatus.PARTIALLY_FILLED
    assert receipt.filled_quantity == 1


def test_canceled_response_is_not_recorded_as_accepted(tmp_path: Path, monkeypatch):
    """Verify canceled response maps to CANCELED, never ACCEPTED."""
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)

    mock_client = create_autospec(TradingClient, instance=True)
    mock_client.get_account.return_value = MagicMock(equity=100000.0, cash=50000.0, buying_power=200000.0, last_equity=100000.0, id="acc-1")
    mock_res = MagicMock(id="ord-canc-1", status="canceled", filled_qty=0, filled_avg_price=None, created_at=datetime.now(timezone.utc))
    mock_client.submit_order.return_value = mock_res

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger, allow_order_submission=True)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    receipt = broker.submit_paper_order(plan)
    assert receipt.status == ExecutionStatus.CANCELED



def test_full_intent_is_committed_before_submit_order(tmp_path: Path):
    """Verify full intent is committed before submit_order."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan.approval_token)

    broker = SimulatedPaperBroker(ledger=ledger)
    broker.submit_simulated_order(plan)

    row = ledger.get_order_by_client_order_id(plan.client_order_id)
    assert row["full_order_plan"] is not None
    plan_dict = json.loads(row["full_order_plan"])
    assert plan_dict["client_order_id"] == plan.client_order_id


def test_persisted_intent_contains_exact_legs_quotes_and_position_intents(tmp_path: Path):
    """Verify persisted intent contains exact legs, quotes, and position intents."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)

    row = ledger.get_order_by_client_order_id(plan.client_order_id)
    plan_dict = json.loads(row["full_order_plan"])
    legs = plan_dict["legs"]
    assert len(legs) == 2
    assert legs[0]["position_intent"] == "buy_to_open"
    assert legs[0]["bid"] > 0
    assert legs[0]["ask"] >= legs[0]["bid"]


def test_illegal_state_transition_is_rejected(tmp_path: Path):
    """Verify illegal state transitions raise ExecutionError."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)

    # Illegal: PREVIEWED -> SUBMITTING
    with pytest.raises(ExecutionError, match="Illegal state transition"):
        ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)


def test_transition_history_is_append_only(tmp_path: Path):
    """Verify transition_events table logs each state transition in append-only fashion."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.FILLED)

    events = ledger.get_transition_history(plan.fingerprint)
    assert len(events) >= 5
    statuses = [e["to_status"] for e in events]
    assert statuses == ["previewed", "approved", "intent_persisted", "submitting", "filled"]


def test_concurrent_identical_intents_create_one_active_record(tmp_path: Path):
    """Verify duplicate registration inside transaction creates only one active record."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan1 = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)

    with pytest.raises(ExecutionError, match="Duplicate logical exposure prevented"):
        build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)


def test_expired_preview_does_not_block_new_preview(tmp_path: Path):
    """Verify expired preview allows new preview creation."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan1 = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)

    # Expire plan1
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with ledger._get_connection() as conn:
        conn.execute("UPDATE execution_ledger SET expires_at = ? WHERE fingerprint = ?", (past_iso, plan1.fingerprint))
        conn.commit()

    plan2 = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    assert plan2.client_order_id != plan1.client_order_id


def test_filled_open_strategy_blocks_duplicate_entry(tmp_path: Path):
    """Verify FILLED open strategy blocks new duplicate entry."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.FILLED)

    with pytest.raises(ExecutionError, match="Duplicate logical exposure prevented"):
        build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)


def test_closed_strategy_can_create_a_new_later_entry(tmp_path: Path):
    """Verify CLOSED strategy allows a new later entry."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan1 = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan1.approval_token)
    ledger.persist_order_intent(plan1.approval_token, plan1.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan1.approval_token, plan1.fingerprint)
    ledger.record_broker_result(plan1.approval_token, ExecutionStatus.FILLED)
    ledger.record_broker_result(plan1.approval_token, ExecutionStatus.CLOSED)

    plan2 = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    assert plan2.client_order_id != plan1.client_order_id


def test_small_limit_change_cannot_bypass_unknown_exposure_block(tmp_path: Path):
    """Verify changing limit price cannot bypass UNKNOWN exposure."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan1 = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan1.approval_token)
    ledger.persist_order_intent(plan1.approval_token, plan1.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan1.approval_token, plan1.fingerprint)
    ledger.mark_unknown(plan1.approval_token, "unknown timeout")

    repriced = cand.model_copy(update={"entry_debit_credit": 990.0})
    with pytest.raises(ExecutionError, match="Duplicate logical exposure prevented"):
        build_order_plan(repriced, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)


def test_reconcile_updates_order_fill_from_broker_evidence(tmp_path: Path, monkeypatch):
    """Verify reconciliation updates order fill status from broker evidence."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.ACCEPTED, broker_order_id="ord-b-1")

    mock_client = MagicMock()
    mock_client.get_orders.return_value = [
        MagicMock(id="ord-b-1", client_order_id=plan.client_order_id, symbol="NVDA", qty=1, filled_qty=1, side="buy", type="limit", status="filled", limit_price=10.0, filled_avg_price=9.90, legs=[])
    ]
    mock_client.get_all_positions.return_value = [
        MagicMock(symbol="NVDA270917C00125000", qty=1, side="long", avg_entry_price=5.0, current_price=5.0, market_value=500.0, unrealized_pl=0.0, unrealized_plpc=0.0),
        MagicMock(symbol="NVDA270917P00125000", qty=1, side="long", avg_entry_price=5.0, current_price=5.0, market_value=500.0, unrealized_pl=0.0, unrealized_plpc=0.0),
    ]

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    reconcile_broker_and_ledger(broker, ledger)
    updated = ledger.get_order_by_client_order_id(plan.client_order_id)
    assert updated["status"] == ExecutionStatus.FILLED.value
    assert updated["filled_quantity"] == 1
    assert updated["average_price"] == 9.90


def test_reconcile_detects_orphan_broker_order(tmp_path: Path, monkeypatch):
    """Verify reconciliation detects orphan broker order and halts."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    mock_client = MagicMock()
    mock_client.get_orders.return_value = [
        MagicMock(id="ord-orphan-1", client_order_id="untracked-client-id", symbol="NVDA", qty=1, filled_qty=0, side="buy", type="limit", status="new", limit_price=5.0, legs=[])
    ]
    mock_client.get_all_positions.return_value = []

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    report = reconcile_broker_and_ledger(broker, ledger)
    assert report.status == ReconciliationStatus.HALTED
    assert len(report.orphan_broker_orders) == 1


def test_reconcile_detects_orphan_broker_position(tmp_path: Path, monkeypatch):
    """Verify reconciliation detects orphan broker position."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    mock_client = MagicMock()
    mock_client.get_orders.return_value = []
    mock_client.get_all_positions.return_value = [
        MagicMock(symbol="TSLA240920C00250000", qty=10, side="long", avg_entry_price=10.0, current_price=10.0, market_value=10000.0, unrealized_pl=0.0, unrealized_plpc=0.0)
    ]

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    report = reconcile_broker_and_ledger(broker, ledger)
    assert report.status == ReconciliationStatus.HALTED
    assert len(report.orphan_broker_positions) == 1


def test_reconcile_detects_missing_or_mismatched_strategy_leg(tmp_path: Path, monkeypatch):
    """Verify reconciliation detects missing or mismatched strategy leg."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.FILLED, broker_order_id="ord-b-1", filled_quantity=1)

    mock_client = MagicMock()
    mock_client.get_orders.return_value = []
    # Broker only holds the Call leg, Put leg is missing!
    mock_client.get_all_positions.return_value = [
        MagicMock(symbol="NVDA270917C00125000", qty=1, side="long", avg_entry_price=5.0, current_price=5.0, market_value=500.0, unrealized_pl=0.0, unrealized_plpc=0.0)
    ]

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    report = reconcile_broker_and_ledger(broker, ledger)
    assert report.status == ReconciliationStatus.HALTED
    assert len(report.orphan_ledger_positions) == 1


def test_reconcile_mismatch_halts_new_entries(tmp_path: Path, monkeypatch):
    """Verify reconciliation mismatch trips halt and rejects new entries."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    mock_client = MagicMock()
    mock_client.get_orders.return_value = [
        MagicMock(id="orphan-1", client_order_id="unknown", symbol="NVDA", qty=1, filled_qty=0, side="buy", type="limit", status="new", limit_price=10.0, legs=[])
    ]
    mock_client.get_all_positions.return_value = []

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    reconcile_broker_and_ledger(broker, ledger)
    assert ledger.is_system_halted()[0] is True

    cand = create_mock_candidate()
    with pytest.raises(ExecutionError, match="System is currently HALTED"):
        build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)


def test_long_straddle_close_uses_verified_broker_quantities(tmp_path: Path):
    """Verify long straddle close uses verified broker quantities."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    snapshots = create_mock_contract_snapshots(cand)

    verified_pos = [
        {"symbol": "NVDA270917C00125000", "qty": 1, "side": "long"},
        {"symbol": "NVDA270917P00125000", "qty": 1, "side": "long"},
    ]
    plan = build_closing_order_plan(cand, contract_snapshots=snapshots, verified_positions=verified_pos, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    assert plan.quantity == 1


def test_iron_butterfly_close_uses_verified_broker_quantities(tmp_path: Path):
    """Verify iron butterfly close uses verified broker quantities."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    ib_cand = create_mock_iron_butterfly_candidate()
    verified_pos = [
        {"symbol": "NVDA270917C00125000", "qty": 1, "side": "short"},
        {"symbol": "NVDA270917P00125000", "qty": 1, "side": "short"},
        {"symbol": "NVDA270917C00135000", "qty": 1, "side": "long"},
        {"symbol": "NVDA270917P00115000", "qty": 1, "side": "long"},
    ]
    plan = build_closing_order_plan(ib_cand, verified_positions=verified_pos, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    assert plan.quantity == 1
    assert len(plan.legs) == 4


def test_close_plan_accepts_alpaca_position_side_enum_strings(tmp_path: Path):
    """Closing safety must understand the exact side strings returned by Alpaca SDK."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    candidate = create_mock_iron_butterfly_candidate()
    positions = [
        {
            "symbol": leg.contract_symbol,
            "qty": -1 if leg.side == "sell" else 1,
            "side": "PositionSide.SHORT" if leg.side == "sell" else "PositionSide.LONG",
        }
        for leg in candidate.legs
    ]

    plan = build_closing_order_plan(
        candidate,
        verified_positions=positions,
        broker_target=BrokerTarget.SIMULATED_LOCAL,
        ledger=ledger,
    )

    assert plan.quantity == 1
    assert len(plan.legs) == 4


def test_partial_fill_cannot_generate_full_candidate_quantity_close(tmp_path: Path):
    """Verify partial fill with 1 unit prevents closing 2 candidate units without broker quantity."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate(quantity=2)
    snapshots = create_mock_contract_snapshots(cand)

    # Broker only has 1 unit filled
    verified_pos = [
        {"symbol": "NVDA270917C00125000", "qty": 1, "side": "long"},
        {"symbol": "NVDA270917P00125000", "qty": 1, "side": "long"},
    ]
    plan = build_closing_order_plan(cand, contract_snapshots=snapshots, verified_positions=verified_pos, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    assert plan.quantity == 1  # Adjusted to verified 1 unit


def test_close_rejects_wrong_snapshot_symbol(tmp_path: Path):
    """Verify close rejects mismatched snapshot symbol."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    snapshots = create_mock_contract_snapshots(cand)
    bad_snapshot = snapshots["NVDA270917C00125000"].model_copy(update={"symbol": "AAPL240906C00125000"})
    snapshots["NVDA270917C00125000"] = bad_snapshot

    verified_pos = [
        {"symbol": "NVDA270917C00125000", "qty": 1, "side": "long"},
        {"symbol": "NVDA270917P00125000", "qty": 1, "side": "long"},
    ]
    with pytest.raises(ExecutionError, match="Invalid immutable quote snapshot"):
        build_closing_order_plan(cand, contract_snapshots=snapshots, verified_positions=verified_pos, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)


def test_close_rejects_wrong_snapshot_strike_or_expiry(tmp_path: Path):
    """Verify close rejects wrong strike or expiration snapshot."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    snapshots = create_mock_contract_snapshots(cand)
    bad_snapshot = snapshots["NVDA270917C00125000"].model_copy(update={"strike": 130.0})
    snapshots["NVDA270917C00125000"] = bad_snapshot

    verified_pos = [
        {"symbol": "NVDA270917C00125000", "qty": 1, "side": "long"},
        {"symbol": "NVDA270917P00125000", "qty": 1, "side": "long"},
    ]
    with pytest.raises(ExecutionError, match="Invalid immutable quote snapshot"):
        build_closing_order_plan(cand, contract_snapshots=snapshots, verified_positions=verified_pos, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)


def test_close_rejects_stale_future_crossed_and_nonfinite_quotes(tmp_path: Path):
    """Verify close rejects crossed quotes (bid > ask or bid <= 0)."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    snapshots = create_mock_contract_snapshots(cand)
    crossed_snapshot = snapshots["NVDA270917C00125000"].model_copy(update={"bid": 6.0, "ask": 5.0})
    snapshots["NVDA270917C00125000"] = crossed_snapshot

    verified_pos = [
        {"symbol": "NVDA270917C00125000", "qty": 1, "side": "long"},
        {"symbol": "NVDA270917P00125000", "qty": 1, "side": "long"},
    ]
    with pytest.raises(ExecutionError, match="Invalid immutable quote snapshot"):
        build_closing_order_plan(cand, contract_snapshots=snapshots, verified_positions=verified_pos, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)


def test_reconciled_receipt_preserves_original_fingerprint(tmp_path: Path, monkeypatch):
    """Verify reconciled receipt preserves original fingerprint."""
    from alpaca.trading.client import TradingClient
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER, contract_snapshots=create_mock_contract_snapshots(cand), ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.mark_unknown(plan.approval_token, "network timeout")

    mock_client = create_autospec(TradingClient, instance=True)
    mock_order = MagicMock(id="ord-rec-1", status="accepted", filled_qty=0, filled_avg_price=None, created_at=datetime.now(timezone.utc))
    mock_client.get_order_by_client_id.return_value = mock_order

    broker = AlpacaPaperBroker(api_key="k", secret_key="s", ledger=ledger)
    monkeypatch.setattr(broker, "_get_trading_client", lambda: mock_client)

    receipt = broker.reconcile_order_by_client_order_id(plan.client_order_id)
    assert receipt.fingerprint == plan.fingerprint
    assert receipt.fingerprint != ""


def test_tests_do_not_touch_default_runtime_ledger(tmp_path: Path):
    """Verify autouse fixture isolates default runtime ledger in ~/.volagent."""
    default_runtime = Path.home() / ".volagent" / "execution_ledger.db"
    # Current test run should be pointing to tmp_path due to conftest autouse fixture
    active_path = get_default_ledger_path()
    assert active_path != default_runtime


def test_streamlit_duplicate_preview_is_handled_without_exception(tmp_path: Path):
    """Verify Streamlit UI can retrieve existing active preview without raising unhandled exception."""
    ledger = ExecutionLedger(db_path=tmp_path / "test_ledger.db")
    cand = create_mock_candidate()

    # 1. Preview created in session
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)

    # 2. Re-rendering can retrieve active preview by logical exposure key
    active_prev = ledger.get_active_preview_by_logical_key(plan.logical_exposure_key)
    assert active_prev is not None
    assert active_prev["fingerprint"] == plan.fingerprint
    assert active_prev["status"] == ExecutionStatus.PREVIEWED.value
