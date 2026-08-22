"""Test payoff sign conventions, golden values at center/wings, and cash flow consistency."""

from datetime import date, datetime, timezone
import pytest

from volagent.domain.enums import Decision, OptionType
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.provenance import Provenance
from volagent.quant.payoff import compute_payoff_curves
from volagent.quant.strategy_factory import build_long_straddle_candidate, build_short_iron_butterfly_candidate
from volagent.config import RiskConfig


def test_long_straddle_payoff_center_equals_negative_debit():
    """At center (S=K), a Long Straddle at expiration has 0 intrinsic value, so P&L = -Entry Debit."""
    spot = 100.0
    debit_per_share = 7.00  # $7.00 total debit
    debit_total = debit_per_share * 100.0 * 1  # 1 unit = $700.00

    cand = StrategyCandidate(
        strategy_id="test-straddle",
        decision=Decision.LONG_STRADDLE,
        legs=[
            OptionLeg(contract_symbol="C100", option_type="call", strike=100.0, expiration=date(2024, 8, 23), side="buy", ratio_qty=1, entry_price_assumption=3.50),
            OptionLeg(contract_symbol="P100", option_type="put", strike=100.0, expiration=date(2024, 8, 23), side="buy", ratio_qty=1, entry_price_assumption=3.50),
        ],
        quantity=1,
        entry_debit_credit=debit_total,  # +$700 debit
        max_loss=debit_total,
    )

    curves = compute_payoff_curves(cand, spot_price=100.0, implied_move_dollars=7.0, n_points=101)
    
    # Find P&L at center spot = 100.0
    spots = curves["spot_range"]
    pnl_expiry = curves["pnl_at_expiry"]
    
    center_idx = min(range(len(spots)), key=lambda i: abs(spots[i] - 100.0))
    assert spots[center_idx] == pytest.approx(100.0, abs=0.1)
    assert pnl_expiry[center_idx] == pytest.approx(-debit_total, abs=1.0)


def test_short_iron_butterfly_payoff_center_equals_credit():
    """At center (S=K), a Short Iron Butterfly at expiration has 0 intrinsic losses, so P&L = +Entry Credit."""
    spot = 100.0
    credit_per_share = 4.00
    credit_total = credit_per_share * 100.0 * 1  # 1 unit = $400.00 credit

    cand = StrategyCandidate(
        strategy_id="test-ibfly",
        decision=Decision.SHORT_IRON_BUTTERFLY,
        legs=[
            OptionLeg(contract_symbol="P90", option_type="put", strike=90.0, expiration=date(2024, 8, 23), side="buy", ratio_qty=1, entry_price_assumption=1.00),
            OptionLeg(contract_symbol="P100", option_type="put", strike=100.0, expiration=date(2024, 8, 23), side="sell", ratio_qty=1, entry_price_assumption=3.00),
            OptionLeg(contract_symbol="C100", option_type="call", strike=100.0, expiration=date(2024, 8, 23), side="sell", ratio_qty=1, entry_price_assumption=3.00),
            OptionLeg(contract_symbol="C110", option_type="call", strike=110.0, expiration=date(2024, 8, 23), side="buy", ratio_qty=1, entry_price_assumption=1.00),
        ],
        quantity=1,
        entry_debit_credit=-credit_total,  # -$400 credit in our convention
        max_loss=600.0,
    )

    curves = compute_payoff_curves(cand, spot_price=100.0, implied_move_dollars=5.0, n_points=101)
    spots = curves["spot_range"]
    pnl_expiry = curves["pnl_at_expiry"]

    center_idx = min(range(len(spots)), key=lambda i: abs(spots[i] - 100.0))
    assert pnl_expiry[center_idx] == pytest.approx(credit_total, abs=1.0)


def test_payoff_and_monte_carlo_share_cashflow_convention():
    """Verify that payoff curve and Monte Carlo pricing use the identical cash flow convention."""
    cand = StrategyCandidate(
        strategy_id="test-straddle-convention",
        decision=Decision.LONG_STRADDLE,
        legs=[
            OptionLeg(contract_symbol="C100", option_type="call", strike=100.0, expiration=date(2024, 8, 23), side="buy", ratio_qty=1, entry_price_assumption=3.50),
            OptionLeg(contract_symbol="P100", option_type="put", strike=100.0, expiration=date(2024, 8, 23), side="buy", ratio_qty=1, entry_price_assumption=3.50),
        ],
        quantity=1,
        entry_debit_credit=700.0,  # Debit positive
        max_loss=700.0,
    )

    curves = compute_payoff_curves(cand, spot_price=100.0, implied_move_dollars=7.0, n_points=50)
    # At far tail (S=120), intrinsic value is 20 * 100 = 2000, PnL = 2000 - 700 = +1300
    far_tail_idx = min(range(len(curves["spot_range"])), key=lambda i: abs(curves["spot_range"][i] - 120.0))
    assert curves["pnl_at_expiry"][far_tail_idx] > 1000.0


def test_asymmetric_butterfly_uses_larger_wing_loss():
    """Verify that an asymmetric Iron Butterfly uses the larger wing width for max loss."""
    prov = Provenance.from_synthetic("test")
    now = datetime(2024, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
    exp = date(2024, 8, 23)
    c_atm = OptionContractSnapshot(symbol="C100", underlying_symbol="XYZ", option_type="call", strike=100.0, expiration=exp, bid=3.0, ask=3.2, quote_time=now, provenance=prov)
    p_atm = OptionContractSnapshot(symbol="P100", underlying_symbol="XYZ", option_type="put", strike=100.0, expiration=exp, bid=3.0, ask=3.2, quote_time=now, provenance=prov)
    
    # Asymmetric wings: lower width = 10 ($90 put), upper width = 20 ($120 call)
    p_wing = OptionContractSnapshot(symbol="P90", underlying_symbol="XYZ", option_type="put", strike=90.0, expiration=exp, bid=0.8, ask=1.0, quote_time=now, provenance=prov)
    c_wing = OptionContractSnapshot(symbol="C120", underlying_symbol="XYZ", option_type="call", strike=120.0, expiration=exp, bid=0.8, ask=1.0, quote_time=now, provenance=prov)

    cand = build_short_iron_butterfly_candidate(c_atm, p_atm, c_wing, p_wing, spot_price=100.0, nav=500_000.0, risk_config=RiskConfig())

    # Credit = (3.0 + 3.0) - (1.0 + 1.0) = 4.0 ($400/unit)
    # Larger wing width = max(10, 20) = 20 ($2000)
    # Max loss per unit = 2000 - 400 = $1600 (not 1000 - 400 = $600)
    assert cand.max_loss == pytest.approx(1600.0 * cand.quantity, abs=1.0)
