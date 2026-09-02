"""Tests for the non-executable, point-in-time historical bar replay."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from volagent.config import load_config
from volagent.domain.enums import DataMode, EventTiming
from volagent.domain.events import EarningsEvent
from volagent.domain.market import UnderlyingSnapshot
from volagent.evaluation.historical_bar_replay import (
    HISTORICAL_BAR_PROXY_LABEL,
    last_bar_at_or_before,
    proxy_contract_from_bar,
    score_bar_proxy_forecast,
)
from volagent.graph.builder import VolAgentWorkflow
from volagent.provenance import Provenance, compute_canonical_hash
from volagent.ui.pages.live_canary import _build_confirmed_event


def _bar(timestamp: datetime, close: float) -> object:
    return SimpleNamespace(timestamp=timestamp, close=close)


def _provenance(now: datetime) -> Provenance:
    return Provenance(
        source_name="historical-test", source_uri="test://historical", retrieved_at=now, observed_at=now,
        content_hash=compute_canonical_hash({"now": now.isoformat()}), data_mode=DataMode.REPLAY_REAL,
    )


def test_bar_selection_cannot_use_a_post_cutoff_bar():
    cutoff = datetime(2026, 5, 20, 19, 50, tzinfo=timezone.utc)
    prior, future = _bar(cutoff - timedelta(minutes=1), 4.0), _bar(cutoff + timedelta(seconds=1), 9.0)
    assert last_bar_at_or_before([prior, future], cutoff) is prior


def test_proxy_contract_is_derived_from_pre_cutoff_bar_and_not_vendor_quote():
    cutoff = datetime(2026, 5, 20, 19, 50, tzinfo=timezone.utc)
    contract = proxy_contract_from_bar(
        symbol="TEST260522C00100000", underlying_symbol="TEST", option_type="call", strike=100.0,
        expiration=date(2026, 5, 22), bar=_bar(cutoff, 4.0), spot=100.0, cutoff_time=cutoff,
    )
    assert contract is not None
    assert contract.bid == contract.ask == contract.last == 4.0
    assert contract.volume == contract.open_interest == 0
    assert contract.vendor_implied_vol is not None and contract.vendor_gamma is not None
    assert contract.provenance.data_mode == DataMode.REPLAY_REAL
    assert contract.provenance.source_name == HISTORICAL_BAR_PROXY_LABEL
    assert proxy_contract_from_bar(
        symbol="TEST260522C00100000", underlying_symbol="TEST", option_type="call", strike=100.0,
        expiration=date(2026, 5, 22), bar=_bar(cutoff + timedelta(seconds=1), 4.0), spot=100.0, cutoff_time=cutoff,
    ) is None


def test_historical_replay_uses_event_decision_boundary_for_freshness():
    cutoff = datetime(2026, 5, 20, 19, 50, tzinfo=timezone.utc)
    event = EarningsEvent(
        event_id="HIST-TEST", symbol="TEST", event_time=cutoff + timedelta(minutes=15),
        timing=EventTiming.AFTER_MARKET_CLOSE, confirmed=True, decision_time=cutoff, exit_time=cutoff + timedelta(days=1),
        provenance=_provenance(cutoff),
    )
    underlying = UnderlyingSnapshot(
        symbol="TEST", price=100.0, bid=100.0, ask=100.0, quote_time=cutoff,
        realized_vol_10d=0.25, realized_vol_30d=0.30, provenance=_provenance(cutoff),
    )
    chain = [
        proxy_contract_from_bar(
            symbol=symbol, underlying_symbol="TEST", option_type=option_type, strike=strike,
            expiration=date(2026, 5, 22), bar=_bar(cutoff, price), spot=100.0, cutoff_time=cutoff,
        )
        for symbol, option_type, strike, price in (
            ("TEST260522C00100000", "call", 100.0, 4.0), ("TEST260522P00100000", "put", 100.0, 4.0),
            ("TEST260522C00110000", "call", 110.0, 1.0), ("TEST260522P00090000", "put", 90.0, 1.0),
        )
    ]
    config = load_config().model_copy(deep=True)
    config.contracts = config.contracts.model_copy(update={"min_volume": 0, "min_open_interest": 0})
    result = VolAgentWorkflow(config=config).run({
        "symbol": "TEST", "event": event, "underlying": underlying, "option_chain": chain,
        "historical_moves": [0.03, 0.04, 0.05, 0.06], "mode": DataMode.REPLAY_REAL, "nav": 100_000.0,
    })
    assert result["critic_report"].stale_data_detected is False
    assert result["underlying"].provenance.data_mode == DataMode.REPLAY_REAL


def test_outcome_score_is_forecast_evaluation_not_executable_pnl():
    cutoff = datetime(2026, 5, 20, 19, 50, tzinfo=timezone.utc)
    call = proxy_contract_from_bar(symbol="TEST260522C00100000", underlying_symbol="TEST", option_type="call", strike=100.0, expiration=date(2026, 5, 22), bar=_bar(cutoff, 4.0), spot=100.0, cutoff_time=cutoff)
    put = proxy_contract_from_bar(symbol="TEST260522P00100000", underlying_symbol="TEST", option_type="put", strike=100.0, expiration=date(2026, 5, 22), bar=_bar(cutoff, 4.0), spot=100.0, cutoff_time=cutoff)
    result = {
        "underlying": UnderlyingSnapshot(symbol="TEST", price=100.0, quote_time=cutoff, provenance=_provenance(cutoff)),
        "move_forecast": SimpleNamespace(median_abs_move_pct=0.06, implied_move_pct=0.08, q20_abs_move_pct=0.03, q80_abs_move_pct=0.10),
        "feature_set": {"atm_call": call, "atm_put": put},
    }
    outcome = score_bar_proxy_forecast(result, 107.0, {call.symbol: 6.0, put.symbol: 3.0})
    assert outcome["realized_abs_move_pct"] == pytest.approx(0.07)
    assert outcome["within_q20_q80_interval"] is True
    assert outcome["bar_close_premium_change"]["label"] == "bar-close premium change only — not executable P&L"
    assert "paper_trade" not in outcome


def test_live_event_builder_returns_an_event_after_date_parser_was_added():
    event_time = datetime(2026, 8, 28, 20, 5, tzinfo=timezone.utc)
    event = _build_confirmed_event("TEST", event_time, "https://example.com/event")
    assert event.symbol == "TEST" and event.event_time == event_time
