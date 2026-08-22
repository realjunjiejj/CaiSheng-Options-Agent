r"""Executable implied move calculations and bounds.

Academic Reference:
- Brenner, M., & Subrahmanyam, M. G. (1988). "A Simple Formula to Compute the Implied Standard Deviation."
  Financial Analysts Journal, 44(5), 80-83.
  $$\text{Straddle}_{\text{ATM}} \approx 0.80 \cdot S_0 \cdot \sigma \cdot \sqrt{T}, \quad M_{\text{implied}} = \frac{\text{Straddle}}{S_0}$$
"""

from pydantic import BaseModel, ConfigDict, Field
from volagent.domain.market import OptionContractSnapshot
from volagent.errors import ValidationError


class ImpliedMoveMetrics(BaseModel):
    """ATM straddle-implied move bounds across executable ask/mid/bid prices."""
    model_config = ConfigDict(extra="ignore")

    atm_strike: float = Field(gt=0)
    implied_move_ask_dollars: float = Field(gt=0)
    implied_move_mid_dollars: float = Field(gt=0)
    implied_move_bid_dollars: float = Field(gt=0)
    implied_move_ask_pct: float = Field(gt=0)
    implied_move_mid_pct: float = Field(gt=0)
    implied_move_bid_pct: float = Field(gt=0)
    call_mid_iv: float = Field(gt=0)
    put_mid_iv: float = Field(gt=0)
    straddle_iv_avg: float = Field(gt=0)

    @property
    def atm_iv(self) -> float:
        return self.straddle_iv_avg

    @property
    def implied_move_long_entry_pct(self) -> float:
        return self.implied_move_ask_pct

    @property
    def implied_move_short_entry_pct(self) -> float:
        return self.implied_move_bid_pct


def compute_implied_move(
    atm_call: OptionContractSnapshot,
    atm_put: OptionContractSnapshot,
    spot_price: float,
) -> ImpliedMoveMetrics:
    """Calculate exact executable ATM Straddle Implied Move metrics with strict pair validation."""
    if atm_call.underlying_symbol != atm_put.underlying_symbol:
        raise ValidationError(f"Mismatched underlyings: {atm_call.underlying_symbol} vs {atm_put.underlying_symbol}")
    if atm_call.strike != atm_put.strike:
        raise ValidationError(f"Mismatched strikes for ATM straddle pair: {atm_call.strike} vs {atm_put.strike}")
    if atm_call.expiration != atm_put.expiration:
        raise ValidationError(f"Mismatched expirations: {atm_call.expiration} vs {atm_put.expiration}")
    if spot_price <= 0:
        raise ValidationError(f"Spot price must be positive, got {spot_price}")

    # Ask Bound (Debit to enter Long Straddle)
    straddle_ask = atm_call.ask + atm_put.ask
    # Mid Bound
    straddle_mid = ((atm_call.bid + atm_call.ask) / 2.0) + ((atm_put.bid + atm_put.ask) / 2.0)
    # Bid Bound (Credit received for selling Short Straddle)
    straddle_bid = atm_call.bid + atm_put.bid

    call_iv = atm_call.vendor_implied_vol or 0.60
    put_iv = atm_put.vendor_implied_vol or 0.60
    straddle_iv = (call_iv + put_iv) / 2.0

    return ImpliedMoveMetrics(
        atm_strike=atm_call.strike,
        implied_move_ask_dollars=round(straddle_ask, 4),
        implied_move_mid_dollars=round(straddle_mid, 4),
        implied_move_bid_dollars=round(straddle_bid, 4),
        implied_move_ask_pct=round(straddle_ask / spot_price, 4),
        implied_move_mid_pct=round(straddle_mid / spot_price, 4),
        implied_move_bid_pct=round(straddle_bid / spot_price, 4),
        call_mid_iv=round(call_iv, 4),
        put_mid_iv=round(put_iv, 4),
        straddle_iv_avg=round(straddle_iv, 4),
    )
