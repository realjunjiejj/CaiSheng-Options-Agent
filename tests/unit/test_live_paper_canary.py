"""Behavioral tests for the live-data paper-trading canary boundary."""

from datetime import date, datetime, timedelta, timezone

import pytest

from volagent.config import load_config
from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter
from volagent.domain.enums import BrokerTarget, DataMode, EventTiming
from volagent.domain.events import EarningsEvent
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.errors import ExecutionError
from volagent.execution.alpaca import build_order_plan
from volagent.execution.ledger import ExecutionLedger
from volagent.evaluation.live_outcomes import evaluate_live_forecast, record_live_forecast
from volagent.graph.builder import VolAgentWorkflow
from volagent.quant.forecast import compute_shrinkage_forecast
from volagent.quant.features import build_quantitative_features
from volagent.quant.expected_move import compute_implied_move
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.provenance import Provenance, compute_canonical_hash
from volagent.quant.strategy_factory import build_long_straddle_candidate


def _provenance(now: datetime) -> Provenance:
    return Provenance(
        source_name="live-canary-test",
        source_uri="test://live-canary",
        retrieved_at=now,
        observed_at=now,
        content_hash=compute_canonical_hash({"now": now.isoformat()}),
        data_mode=DataMode.LIVE,
    )


def _live_inputs() -> tuple[EarningsEvent, UnderlyingSnapshot, list[OptionContractSnapshot]]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    event_time = now + timedelta(days=2)
    provenance = _provenance(now)
    event = EarningsEvent(
        event_id="LIVE-TEST",
        symbol="TEST",
        event_time=event_time,
        timing=EventTiming.AFTER_MARKET_CLOSE,
        confirmed=True,
        decision_time=now,
        exit_time=event_time + timedelta(days=1),
        provenance=provenance,
    )
    underlying = UnderlyingSnapshot(
        symbol="TEST",
        price=100.0,
        bid=99.99,
        ask=100.01,
        quote_time=now - timedelta(seconds=5),
        realized_vol_10d=0.35,
        realized_vol_30d=0.38,
        provenance=provenance,
    )
    expiry = event_time.date() + timedelta(days=2)
    contracts = []
    for symbol, option_type, strike, bid, ask in (
        ("TEST260826C00100000", "call", 100.0, 4.90, 5.00),
        ("TEST260826P00100000", "put", 100.0, 4.80, 4.90),
        ("TEST260826C00110000", "call", 110.0, 1.20, 1.30),
        ("TEST260826P00090000", "put", 90.0, 1.10, 1.20),
    ):
        contracts.append(
            OptionContractSnapshot(
                symbol=symbol,
                underlying_symbol="TEST",
                option_type=option_type,
                strike=strike,
                expiration=expiry,
                bid=bid,
                ask=ask,
                quote_time=now - timedelta(seconds=5),
                volume=500,
                open_interest=1000,
                vendor_implied_vol=0.50,
                vendor_delta=0.50 if option_type == "call" else -0.50,
                vendor_gamma=0.03,
                vendor_theta=-0.10,
                vendor_vega=0.20,
                provenance=provenance,
            )
        )
    return event, underlying, contracts


class _OpenLiveAdapter:
    def __init__(self, underlying: UnderlyingSnapshot, chain: list[OptionContractSnapshot]):
        self.underlying = underlying
        self.chain = chain
        self.last_error = None
        self.requested_window = None

    def get_market_status(self):
        return True, self.underlying.quote_time

    def get_underlying_snapshot(self, symbol: str):
        return self.underlying if symbol == "TEST" else None

    def get_option_chain(self, symbol: str, earliest_expiration: date, latest_expiration: date, spot_price: float):
        assert symbol == "TEST"
        assert earliest_expiration <= latest_expiration
        assert spot_price == 100.0
        self.requested_window = (earliest_expiration, latest_expiration)
        return self.chain

    def get_historical_event_moves(self, symbol: str, event_dates: list[date], before_event_date: date):
        assert symbol == "TEST"
        assert event_dates == []
        return [0.03, 0.04, 0.05, 0.06]


class _ClosedLiveAdapter:
    last_error = "Options market is closed."

    def get_market_status(self):
        return False, None


def test_occ_parser_preserves_real_expiry_strike_and_option_type():
    parsed = AlpacaLiveMarketAdapter.parse_occ_option_symbol("NVDA260821C00125000")
    assert parsed == ("NVDA", date(2026, 8, 21), "call", 125.0)
    assert AlpacaLiveMarketAdapter.parse_occ_option_symbol("not-an-occ-symbol") is None


def test_live_graph_uses_injected_live_snapshot_not_replay_data():
    event, underlying, chain = _live_inputs()
    config = load_config()
    adapter = _OpenLiveAdapter(underlying, chain)
    result = VolAgentWorkflow(config=config).run(
        {
            "symbol": "TEST",
            "event": event,
            "mode": DataMode.LIVE,
            "nav": 100_000.0,
            "paper_canary": True,
            "live_market_adapter": adapter,
        }
    )

    assert result["underlying"].provenance.data_mode == DataMode.LIVE
    assert adapter.requested_window == (
        event.event_time.date() + timedelta(days=config.contracts.min_dte_days),
        event.event_time.date() + timedelta(days=config.contracts.max_dte_days),
    )
    assert {contract.symbol for contract in result["option_chain"]}.issubset({contract.symbol for contract in chain})
    assert any("Fetched live Alpaca snapshot" in trace["summary"] for trace in result["trace_events"])


def test_live_graph_fails_closed_when_market_is_closed():
    event, _, _ = _live_inputs()
    result = VolAgentWorkflow(config=load_config()).run(
        {"symbol": "TEST", "event": event, "mode": DataMode.LIVE, "live_market_adapter": _ClosedLiveAdapter()}
    )

    assert any("market is closed" in reason.lower() for reason in result["rejection_reasons"])
    assert result["approved_candidate"] is None


def test_missing_ticker_fails_closed_instead_of_defaulting_to_nvda():
    event, _, _ = _live_inputs()
    result = VolAgentWorkflow(config=load_config()).run({"event": event, "mode": DataMode.LIVE})
    assert any("ticker symbol is required" in reason.lower() for reason in result["rejection_reasons"])


def test_live_paper_plan_requires_real_immutable_contract_quotes():
    _, underlying, chain = _live_inputs()
    candidate = build_long_straddle_candidate(chain[0], chain[1], underlying.price, 100_000.0, load_config().risk)
    ledger = ExecutionLedger()

    with pytest.raises(ExecutionError, match="immutable quote snapshot"):
        build_order_plan(candidate, broker_target=BrokerTarget.ALPACA_PAPER, ledger=ledger)

    plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ExecutionLedger(),
        contract_snapshots={contract.symbol: contract for contract in chain},
    )
    assert [leg.bid for leg in plan.legs] == [4.90, 4.80]
    assert [leg.ask for leg in plan.legs] == [5.00, 4.90]


def test_missing_history_is_explicitly_ood_not_synthetic():
    event, underlying, chain = _live_inputs()
    metrics = compute_implied_move(chain[0], chain[1], underlying.price)
    features = build_quantitative_features(underlying, metrics, 0.9, event, historical_event_moves=[])
    forecast, _ = compute_shrinkage_forecast(features, historical_ticker_moves=[])
    assert features["has_historical_event_moves"] is False
    assert features["historical_move_median"] is None
    assert forecast.out_of_distribution is True


def test_live_outcome_is_scored_only_after_sealed_exit(monkeypatch, tmp_path):
    import volagent.evaluation.live_outcomes as live_outcomes

    monkeypatch.setattr(live_outcomes, "LIVE_EVALUATION_DIR", tmp_path)
    event, underlying, chain = _live_inputs()
    event = event.model_copy(update={"event_time": datetime.now(timezone.utc) - timedelta(days=2), "exit_time": datetime.now(timezone.utc) - timedelta(days=1)})
    candidate = build_long_straddle_candidate(chain[0], chain[1], underlying.price, 100_000.0, load_config().risk)
    result = {
        "event": event,
        "underlying": underlying,
        "move_forecast": MoveForecast(median_abs_move_pct=0.05, q20_abs_move_pct=0.03, q80_abs_move_pct=0.08, probability_exceeds_implied=0.5, implied_move_pct=0.06, edge_pct_spot=-0.01),
        "iv_forecast": IVCrushForecast(median_iv_change_points=-20.0, q20_iv_change_points=-30.0, q80_iv_change_points=-10.0),
        "feature_set": {"atm_call": chain[0], "atm_put": chain[1]},
        "approved_candidate": candidate,
        "final_decision": candidate.decision,
        "risk_report": None,
    }
    record_live_forecast(result, load_config().execution)
    exit_time = datetime.now(timezone.utc)
    exit_underlying = underlying.model_copy(update={"price": 106.0, "quote_time": exit_time})
    exit_chain = [contract.model_copy(update={"quote_time": exit_time, "vendor_implied_vol": 0.30}) for contract in chain]
    outcome = evaluate_live_forecast(event.event_id, exit_underlying, exit_chain, evaluated_at=exit_time)
    assert outcome["realized_abs_move_pct"] == pytest.approx(0.06)
    assert outcome["within_q20_q80_interval"] is True
    assert outcome["paper_trade"]["is_valid"] is True
