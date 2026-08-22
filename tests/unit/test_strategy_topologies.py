"""Unit tests for strategy topology invariants and quantity sizing."""

from datetime import date, datetime, timezone
import pytest
from volagent.config import RiskConfig
from volagent.domain.enums import DataMode
from volagent.domain.market import OptionContractSnapshot
from volagent.errors import ValidationError
from volagent.provenance import Provenance
from volagent.quant.strategy_factory import (
    build_long_straddle_candidate,
    build_short_iron_butterfly_candidate,
)


def create_mock_contract(symbol: str, opt_type: str, strike: float, bid: float, ask: float) -> OptionContractSnapshot:
    dt = datetime(2024, 8, 28, 19, 45, 0, tzinfo=timezone.utc)
    prov = Provenance(source_name="t", source_uri="t", retrieved_at=dt, observed_at=dt, content_hash="h", data_mode=DataMode.REPLAY_SYNTHETIC)
    return OptionContractSnapshot(
        symbol=symbol,
        underlying_symbol="TSLA",
        option_type=opt_type,
        strike=strike,
        expiration=date(2024, 11, 1),
        bid=bid,
        ask=ask,
        quote_time=dt,
        volume=1000,
        open_interest=5000,
        provenance=prov,
    )


def test_malformed_or_mismatched_iron_butterfly_rejected():
    """Verify that inverted wings or mismatched short strikes raise ValidationError."""
    atm_call = create_mock_contract("TSLA241101C00215000", "call", 215.0, 11.20, 11.50)
    atm_put = create_mock_contract("TSLA241101P00215000", "put", 215.0, 10.40, 10.70)
    wing_call = create_mock_contract("TSLA241101C00230000", "call", 230.0, 4.20, 4.50)
    
    # Inverted wing put (strike > atm_put)
    bad_wing_put = create_mock_contract("TSLA241101P00220000", "put", 220.0, 220.0, 225.0)

    risk_cfg = RiskConfig()
    with pytest.raises(ValidationError):
        build_short_iron_butterfly_candidate(atm_call, atm_put, wing_call, bad_wing_put, 215.0, 100_000.0, risk_cfg)


def test_zero_affordable_quantity_forces_no_trade():
    """Verify that when NAV or budget is insufficient to cover 1 contract, quantity is sized to 0."""
    atm_call = create_mock_contract("TSLA241101C00215000", "call", 215.0, 11.20, 11.50)
    atm_put = create_mock_contract("TSLA241101P00215000", "put", 215.0, 10.40, 10.70)
    risk_cfg = RiskConfig()

    # NAV is only $100 -> Budget is $0.50 (cannot afford $2220 straddle debit)
    cand = build_long_straddle_candidate(atm_call, atm_put, 215.0, 100.0, risk_cfg)
    assert cand.quantity == 0
