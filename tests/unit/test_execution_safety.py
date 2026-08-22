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
