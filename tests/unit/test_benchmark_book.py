from datetime import date, datetime, timedelta, timezone
import json

import pytest

from volagent.domain.enums import Decision
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.evaluation.benchmark_book import (
    POLICY_IDS,
    BenchmarkExitSnapshot,
    BenchmarkOptionQuote,
    aggregate_benchmark_receipts,
    lock_benchmark_intent,
    settle_due_benchmark_intents,
    settle_benchmark_intent,
)
from volagent.execution.ledger import ExecutionLedger
from volagent.errors import ExecutionError, ValidationError
from volagent.lifecycle.runner import LifecycleRunner
from volagent.provenance import Provenance
from volagent.ui.pages.scoreboard import benchmark_tape_html


NOW = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
EXIT = NOW + timedelta(hours=4)
EXPIRY = date(2026, 9, 4)


def _option(symbol: str, option_type: str, strike: float, bid: float, ask: float) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        symbol=symbol,
        underlying_symbol="SPY",
        option_type=option_type,
        strike=strike,
        expiration=EXPIRY,
        bid=bid,
        ask=ask,
        quote_time=NOW,
        provenance=Provenance.from_synthetic("benchmark-test"),
    )


def _candidate(decision: Decision, legs: list[OptionLeg], max_loss: float) -> StrategyCandidate:
    return StrategyCandidate(
        strategy_id=f"candidate-{decision.value}",
        decision=decision,
        legs=legs,
        quantity=1,
        entry_debit_credit=0.0,
        max_loss=max_loss,
    )


@pytest.fixture
def market_inputs():
    call = _option("SPY260904C00100000", "call", 100.0, 1.90, 2.10)
    put = _option("SPY260904P00100000", "put", 100.0, 1.90, 2.10)
    call_wing = _option("SPY260904C00105000", "call", 105.0, 0.40, 0.50)
    put_wing = _option("SPY260904P00095000", "put", 95.0, 0.40, 0.50)
    straddle = _candidate(
        Decision.LONG_STRADDLE,
        [
            OptionLeg(contract_symbol=call.symbol, option_type="call", strike=100.0, expiration=EXPIRY, side="buy", entry_price_assumption=2.10),
            OptionLeg(contract_symbol=put.symbol, option_type="put", strike=100.0, expiration=EXPIRY, side="buy", entry_price_assumption=2.10),
        ],
        420.0,
    )
    butterfly = _candidate(
        Decision.SHORT_IRON_BUTTERFLY,
        [
            OptionLeg(contract_symbol=put_wing.symbol, option_type="put", strike=95.0, expiration=EXPIRY, side="buy", entry_price_assumption=0.50),
            OptionLeg(contract_symbol=put.symbol, option_type="put", strike=100.0, expiration=EXPIRY, side="sell", entry_price_assumption=1.90),
            OptionLeg(contract_symbol=call.symbol, option_type="call", strike=100.0, expiration=EXPIRY, side="sell", entry_price_assumption=1.90),
            OptionLeg(contract_symbol=call_wing.symbol, option_type="call", strike=105.0, expiration=EXPIRY, side="buy", entry_price_assumption=0.50),
        ],
        220.0,
    )
    underlying = UnderlyingSnapshot(
        symbol="SPY",
        price=100.0,
        bid=99.90,
        ask=100.10,
        quote_time=NOW,
        provenance=Provenance.from_synthetic("benchmark-underlying"),
    )
    return underlying, [call, put, call_wing, put_wing], straddle, butterfly


def _locked(market_inputs, approved: Decision = Decision.LONG_STRADDLE):
    underlying, chain, straddle, butterfly = market_inputs
    approved_candidate = straddle if approved == Decision.LONG_STRADDLE else butterfly
    return lock_benchmark_intent(
        opportunity_id="daily-vol-SPY-20260831",
        decision_id="decision-001",
        decision_time=NOW,
        exit_time=EXIT,
        underlying=underlying,
        option_chain=chain,
        candidates=[straddle, butterfly],
        approved_candidate=approved_candidate,
        final_decision=approved,
        starting_nav=100_000.0,
        risk_budget=500.0,
        fee_per_contract=0.65,
        slippage_per_contract=0.02,
    )


def test_lock_is_deterministic_complete_and_uses_executable_quotes(market_inputs):
    first = _locked(market_inputs)
    second = _locked(market_inputs)

    assert first.intent_id == second.intent_id
    assert first.receipt_hash == second.receipt_hash == first.compute_hash()
    assert tuple(v.policy_id for v in first.variants) == POLICY_IDS
    assert first.evidence_tier == "shadow_counterfactual"
    assert first.outcome_known is False

    long_vol = first.variant("B2_ALWAYS_LONG_STRADDLE")
    assert [leg.contract_symbol for leg in long_vol.legs] == [
        "SPY260904C00100000",
        "SPY260904P00100000",
    ]
    assert [leg.entry_price for leg in long_vol.legs] == [2.10, 2.10]

    short_vol = first.variant("B3_ALWAYS_SHORT_DEFINED_RISK_VOL")
    assert [leg.entry_price for leg in short_vol.legs] == [0.50, 1.90, 1.90, 0.50]
    assert first.variant("B4_IMPLIED_MOVE_ONLY").decision == "no_trade"
    assert first.variant("B5_CAISHENG_NO_RESIDUAL").decision == "no_trade"


def test_ledger_keeps_locked_intent_and_outcome_immutable(tmp_path, market_inputs):
    ledger = ExecutionLedger(tmp_path / "ledger.db")
    intent = _locked(market_inputs)
    ledger.record_benchmark_intent(intent)
    ledger.record_benchmark_intent(intent)
    assert len(ledger.list_benchmark_intents()) == 1

    changed = intent.model_copy(update={"risk_budget": 499.0})
    with pytest.raises(ExecutionError, match="immutable benchmark intent"):
        ledger.record_benchmark_intent(changed)


def test_due_settlement_fetches_same_live_snapshot_and_is_idempotent(tmp_path, market_inputs):
    ledger = ExecutionLedger(tmp_path / "ledger.db")
    intent = _locked(market_inputs)
    ledger.record_benchmark_intent(intent)
    underlying, chain, _, _ = market_inputs

    class FakeMarket:
        def get_underlying_snapshot(self, symbol):
            assert symbol == "SPY"
            return underlying.model_copy(
                update={"price": 103.0, "bid": 102.90, "ask": 103.10, "quote_time": EXIT}
            )

        def get_option_chain(self, symbol, earliest_expiration, latest_expiration, spot_price):
            assert symbol == "SPY"
            assert earliest_expiration == latest_expiration == EXPIRY
            assert spot_price is None
            exit_quotes = {
                "SPY260904C00100000": (3.00, 3.20),
                "SPY260904P00100000": (1.00, 1.20),
                "SPY260904C00105000": (0.80, 0.90),
                "SPY260904P00095000": (0.10, 0.20),
            }
            return [
                quote.model_copy(
                    update={"bid": exit_quotes[quote.symbol][0], "ask": exit_quotes[quote.symbol][1], "quote_time": EXIT}
                )
                for quote in chain
            ]

    first = settle_due_benchmark_intents(ledger=ledger, market_adapter=FakeMarket(), now=EXIT)
    second = settle_due_benchmark_intents(ledger=ledger, market_adapter=FakeMarket(), now=EXIT)

    assert first == {"due": 1, "settled": 1, "pending": 0, "errors": []}
    assert second == {"due": 0, "settled": 0, "pending": 0, "errors": []}
    assert len(ledger.list_benchmark_outcomes()) == 1


def test_settlement_uses_one_exit_snapshot_and_literal_round_trip_accounting(market_inputs):
    intent = _locked(market_inputs)
    exit_snapshot = BenchmarkExitSnapshot.create_and_hash(
        observed_at=EXIT,
        underlying_bid=102.90,
        underlying_ask=103.10,
        underlying_quote_time=EXIT,
        option_quotes=[
            BenchmarkOptionQuote(contract_symbol="SPY260904C00100000", bid=3.00, ask=3.20, quote_time=EXIT),
            BenchmarkOptionQuote(contract_symbol="SPY260904P00100000", bid=1.00, ask=1.20, quote_time=EXIT),
            BenchmarkOptionQuote(contract_symbol="SPY260904C00105000", bid=0.80, ask=0.90, quote_time=EXIT),
            BenchmarkOptionQuote(contract_symbol="SPY260904P00095000", bid=0.10, ask=0.20, quote_time=EXIT),
        ],
    )
    result = settle_benchmark_intent(intent, exit_snapshot)

    # Long straddle: (3.00 - 2.10 + 1.00 - 2.10) * 100 = -20 gross.
    # Two contracts, two sides of the round trip, $0.67 per contract-side = $2.68.
    long_vol = result.outcome("B2_ALWAYS_LONG_STRADDLE")
    assert long_vol.gross_pnl == pytest.approx(-20.0)
    assert long_vol.costs == pytest.approx(2.68)
    assert long_vol.net_pnl == pytest.approx(-22.68)

    # Full selected the same exact straddle, so it must have identical economics.
    assert result.outcome("FULL_CAISHENG").net_pnl == pytest.approx(long_vol.net_pnl)

    # Short butterfly gross: +30 +70 -130 -40 = -70; 8 contract-sides cost $5.36.
    short_vol = result.outcome("B3_ALWAYS_SHORT_DEFINED_RISK_VOL")
    assert short_vol.gross_pnl == pytest.approx(-70.0)
    assert short_vol.costs == pytest.approx(5.36)
    assert short_vol.net_pnl == pytest.approx(-75.36)

    # Capital-matched underlying uses floor(500 / 100.10) = 4 shares and ask-to-bid.
    assert result.outcome("B1_BUY_AND_HOLD_UNDERLYING").net_pnl == pytest.approx((102.90 - 100.10) * 4)
    assert result.competition_pnl_eligible is False


def test_settlement_rejects_lookahead_and_invalid_quotes(market_inputs):
    intent = _locked(market_inputs)
    too_early = BenchmarkExitSnapshot.create_and_hash(
        observed_at=EXIT - timedelta(seconds=1),
        underlying_bid=100.0,
        underlying_ask=100.1,
        underlying_quote_time=EXIT - timedelta(seconds=1),
        option_quotes=[],
    )
    with pytest.raises(ValidationError, match="before locked exit time"):
        settle_benchmark_intent(intent, too_early)

    with pytest.raises(ValidationError, match="crossed"):
        BenchmarkOptionQuote(contract_symbol="BAD", bid=2.0, ask=1.0, quote_time=EXIT)

    pre_exit = BenchmarkExitSnapshot.create_and_hash(
        observed_at=EXIT + timedelta(minutes=1),
        underlying_bid=100.0,
        underlying_ask=100.1,
        underlying_quote_time=EXIT - timedelta(seconds=1),
        option_quotes=[],
    )
    with pytest.raises(ValidationError, match="predates locked exit time"):
        settle_benchmark_intent(intent, pre_exit)


def test_live_lock_rejects_stale_entry_evidence(market_inputs):
    underlying, chain, straddle, butterfly = market_inputs
    with pytest.raises(ValidationError, match="stale underlying entry quote"):
        lock_benchmark_intent(
            opportunity_id="stale-opportunity",
            decision_id="stale-decision",
            decision_time=NOW + timedelta(minutes=11),
            exit_time=EXIT,
            underlying=underlying,
            option_chain=chain,
            candidates=[straddle, butterfly],
            approved_candidate=straddle,
            final_decision=Decision.LONG_STRADDLE,
            starting_nav=100_000.0,
            risk_budget=500.0,
            fee_per_contract=0.65,
            slippage_per_contract=0.02,
            data_mode="live",
        )


def test_aggregate_reports_paired_incremental_pnl_without_competition_claim(market_inputs):
    first = settle_benchmark_intent(
        _locked(market_inputs),
        BenchmarkExitSnapshot.create_and_hash(
            observed_at=EXIT,
            underlying_bid=102.90,
            underlying_ask=103.10,
            underlying_quote_time=EXIT,
            option_quotes=[
                BenchmarkOptionQuote(contract_symbol="SPY260904C00100000", bid=3.00, ask=3.20, quote_time=EXIT),
                BenchmarkOptionQuote(contract_symbol="SPY260904P00100000", bid=1.00, ask=1.20, quote_time=EXIT),
                BenchmarkOptionQuote(contract_symbol="SPY260904C00105000", bid=0.80, ask=0.90, quote_time=EXIT),
                BenchmarkOptionQuote(contract_symbol="SPY260904P00095000", bid=0.10, ask=0.20, quote_time=EXIT),
            ],
        ),
    )
    aggregate = aggregate_benchmark_receipts([first])

    assert aggregate["evidence_tier"] == "shadow_counterfactual"
    assert aggregate["competition_pnl_eligible"] is False
    assert aggregate["opportunities"] == 1
    full = next(row for row in aggregate["policies"] if row["policy_id"] == "FULL_CAISHENG")
    no_trade = next(row for row in aggregate["policies"] if row["policy_id"] == "B0_NO_TRADE")
    assert full["net_pnl"] == pytest.approx(-22.68)
    assert full["incremental_pnl_vs_full"] == 0.0
    assert no_trade["incremental_pnl_vs_full"] == pytest.approx(22.68)


def test_autonomous_lifecycle_locks_shadow_policies_before_any_order(tmp_path):
    ledger = ExecutionLedger(tmp_path / "lifecycle-ledger.db")
    runner = LifecycleRunner(
        ledger=ledger,
        lock_path=str(tmp_path / "lifecycle.lock"),
    )
    result = runner.run_cycle(
        calendar={
            "NVDA": {
                "event_date": "2026-09-02",
                "timing": "amc",
                "confirmed": True,
                "source_url": "https://example.test/earnings-event",
            }
        },
        current_time=datetime(2026, 9, 2, 19, 30, tzinfo=timezone.utc),
    )

    assert result["decisions_generated"] == 1
    assert result["benchmark_intents_locked"] == 1
    assert result["benchmark_intent_failures"] == 0
    assert result["entries_submitted"] == 0
    locked = ledger.list_benchmark_intents()
    assert len(locked) == 1
    assert json.loads(locked[0]["raw_payload"])["competition_pnl_eligible"] is False


def test_judge_benchmark_tape_is_compact_and_never_calls_shadow_pnl_competition_pnl(market_inputs):
    empty = benchmark_tape_html(
        {
            "opportunities": 0,
            "policies": [],
            "evidence_tier": "shadow_counterfactual",
            "competition_pnl_eligible": False,
        },
        locked_count=2,
    )
    assert "AWAITING SETTLEMENT" in empty
    assert "2 locked" in empty

    receipt = settle_benchmark_intent(
        _locked(market_inputs),
        BenchmarkExitSnapshot.create_and_hash(
            observed_at=EXIT,
            underlying_bid=102.90,
            underlying_ask=103.10,
            underlying_quote_time=EXIT,
            option_quotes=[
                BenchmarkOptionQuote(contract_symbol="SPY260904C00100000", bid=3.00, ask=3.20, quote_time=EXIT),
                BenchmarkOptionQuote(contract_symbol="SPY260904P00100000", bid=1.00, ask=1.20, quote_time=EXIT),
                BenchmarkOptionQuote(contract_symbol="SPY260904C00105000", bid=0.80, ask=0.90, quote_time=EXIT),
                BenchmarkOptionQuote(contract_symbol="SPY260904P00095000", bid=0.10, ask=0.20, quote_time=EXIT),
            ],
        ),
    )
    markup = benchmark_tape_html(aggregate_benchmark_receipts([receipt]), locked_count=1)
    assert "FULL CAISHENG" in markup
    assert "BEST ALTERNATIVE" in markup
    assert "SHADOW · NOT COMPETITION P&amp;L" in markup
    assert "B1_BUY_AND_HOLD_UNDERLYING" in markup
