"""Unit tests for SQLite transactional execution ledger and approval safety."""

from datetime import date, datetime, timezone
from pathlib import Path
import pytest

from volagent.domain.enums import BrokerTarget, Decision, ExecutionStatus
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.errors import ExecutionError
from volagent.execution.alpaca import SimulatedPaperBroker, build_order_plan
from volagent.execution.ledger import ExecutionLedger


def create_mock_candidate() -> StrategyCandidate:
    exp = date(2024, 9, 6)
    legs = [
        OptionLeg(contract_symbol="NVDA240906C00125000", option_type="call", strike=125.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=5.0, delta=0.5, gamma=0.04, theta=-0.1, vega=0.2),
        OptionLeg(contract_symbol="NVDA240906P00125000", option_type="put", strike=125.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=5.0, delta=-0.5, gamma=0.04, theta=-0.1, vega=0.2),
    ]
    return StrategyCandidate(
        strategy_id="strat-1",
        decision=Decision.LONG_STRADDLE,
        legs=legs,
        quantity=1,
        entry_debit_credit=1000.0,
        net_delta=0.0,
        net_gamma=0.08,
        net_theta=-0.2,
        net_vega=0.4,
        max_loss=1000.0,
    )


def test_double_click_dispatches_at_most_once(tmp_path: Path):
    """Verify VP-12: A consumed approval token cannot be submitted a second time."""
    db_file = tmp_path / "test_ledger.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = create_mock_candidate()

    # 1. Preview
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)

    # 2. Approve
    approved = ledger.approve_order(plan.approval_token)
    assert approved is True

    # 3. First Submission -> Succeeds
    broker = SimulatedPaperBroker(ledger=ledger)
    receipt1 = broker.submit_simulated_order(plan)
    assert receipt1.status == ExecutionStatus.SIMULATED
    assert receipt1.broker_target == BrokerTarget.SIMULATED_LOCAL

    # 4. Second Submission (Double Click / Replay) -> Raises ExecutionError
    with pytest.raises(ExecutionError):
        broker.submit_simulated_order(plan)


def test_simulated_receipt_is_never_labeled_alpaca(tmp_path: Path):
    """Verify VP-14 & EX-06: Simulated receipt is strictly labeled SIMULATED_LOCAL."""
    db_file = tmp_path / "test_ledger.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = create_mock_candidate()

    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan.approval_token)

    broker = SimulatedPaperBroker(ledger=ledger)
    receipt = broker.submit_simulated_order(plan)

    assert receipt.broker_target == BrokerTarget.SIMULATED_LOCAL
    assert receipt.status == ExecutionStatus.SIMULATED
    assert receipt.broker_order_id.startswith("sim-")


def test_fingerprint_recomputed_before_simulated_dispatch(tmp_path: Path):
    """P0-08 Fix: Recompute fingerprint from submitted OrderPlan and reject if tampered."""
    db_file = tmp_path / "test_ledger.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = create_mock_candidate()

    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL, ledger=ledger)
    ledger.approve_order(plan.approval_token)

    # Tamper with quantity (change from 1 to 9 while keeping same fingerprint)
    tampered_plan = plan.model_copy(update={"quantity": 9})

    broker = SimulatedPaperBroker(ledger=ledger)
    with pytest.raises(ExecutionError, match="Tampered order plan detected"):
        broker.submit_simulated_order(tampered_plan)


def test_order_plan_preserves_exact_approved_leg_snapshot():
    """P0-09 Fix: Order plan must preserve exact expiration date and contract strikes from candidate."""
    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.SIMULATED_LOCAL)

    assert len(plan.legs) == 2
    assert plan.legs[0].expiration == date(2024, 9, 6)
    assert plan.legs[0].strike == 125.0
    assert plan.legs[0].entry_price_assumption == 5.0
    assert plan.symbol == "NVDA"


def test_alpaca_limit_request_serializes_limit_price():
    """P0-11 Fix: Alpaca LimitOrderRequest retains limit_price and position_intent."""
    from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest
    from alpaca.trading.enums import OrderSide as AlpacaOrderSide, PositionIntent as AlpacaPositionIntent, TimeInForce

    cand = create_mock_candidate()
    plan = build_order_plan(cand, broker_target=BrokerTarget.ALPACA_PAPER)

    legs = [
        OptionLegRequest(
            symbol=l.contract_symbol,
            ratio_qty=l.ratio_qty,
            side=AlpacaOrderSide.BUY,
            position_intent=AlpacaPositionIntent.BUY_TO_OPEN,
        )
        for l in plan.legs
    ]

    req = LimitOrderRequest(
        symbol=plan.symbol,
        qty=plan.quantity,
        side=AlpacaOrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        limit_price=plan.limit_price,
        order_class="mleg",
        legs=legs,
    )

    dump = req.model_dump()
    assert dump["limit_price"] == plan.limit_price
    assert dump["order_class"] == "mleg"
    assert len(dump["legs"]) == 2
    assert dump["legs"][0]["position_intent"] == "buy_to_open"
