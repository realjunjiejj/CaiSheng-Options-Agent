"""Multi-leg strategy synthesis with topological validation and strict sizing."""

from datetime import datetime, timezone
import hashlib
from volagent.clock import year_fraction_to_expiry
from volagent.config import RiskConfig
from volagent.domain.enums import Decision, OptionType
from volagent.domain.market import OptionContractSnapshot
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.errors import ValidationError
from volagent.quant.pricing import bsm_greeks


def build_long_straddle_candidate(
    atm_call: OptionContractSnapshot,
    atm_put: OptionContractSnapshot,
    spot_price: float,
    nav: float,
    risk_config: RiskConfig,
) -> StrategyCandidate:
    """Construct an ATM Long Straddle with conservative entry at Ask and strict risk sizing."""
    if atm_call.strike != atm_put.strike:
        raise ValidationError("Long Straddle requires identical ATM call and put strikes.")
    if atm_call.expiration != atm_put.expiration:
        raise ValidationError("Long Straddle requires identical expirations.")

    t_exp = year_fraction_to_expiry(atm_call.quote_time, atm_call.expiration)
    if t_exp <= 0:
        t_exp = 1.0 / 365.0

    call_entry = atm_call.ask
    put_entry = atm_put.ask
    debit_per_unit = (call_entry + put_entry) * 100.0  # 100 multiplier

    # Target recommended risk budget (0.5% NAV)
    budget = nav * risk_config.recommended_risk_nav_pct
    affordable_qty = int(budget // debit_per_unit) if debit_per_unit > 0 else 0

    # Ensure it stays within hard cap (1.0% NAV) and max_contracts
    hard_max_budget = nav * risk_config.hard_max_risk_nav_pct
    max_allowed = int(hard_max_budget // debit_per_unit) if debit_per_unit > 0 else 0
    
    if affordable_qty == 0 and max_allowed >= 1:
        final_qty = 1
    else:
        final_qty = min(affordable_qty, max_allowed, risk_config.max_contracts)

    # Compute individual Greeks at actual T
    c_greeks = bsm_greeks(spot_price, atm_call.strike, t_exp, atm_call.vendor_implied_vol or 0.60, option_type=OptionType.CALL)
    p_greeks = bsm_greeks(spot_price, atm_put.strike, t_exp, atm_put.vendor_implied_vol or 0.60, option_type=OptionType.PUT)

    legs = [
        OptionLeg(
            contract_symbol=atm_call.symbol,
            option_type="call",
            strike=atm_call.strike,
            expiration=atm_call.expiration,
            side="buy",
            ratio_qty=1,
            position_intent="buy_to_open",
            entry_price_assumption=call_entry,
            delta=c_greeks["delta"],
            gamma=c_greeks["gamma"],
            theta=c_greeks["theta"],
            vega=c_greeks["vega"],
        ),
        OptionLeg(
            contract_symbol=atm_put.symbol,
            option_type="put",
            strike=atm_put.strike,
            expiration=atm_put.expiration,
            side="buy",
            ratio_qty=1,
            position_intent="buy_to_open",
            entry_price_assumption=put_entry,
            delta=p_greeks["delta"],
            gamma=p_greeks["gamma"],
            theta=p_greeks["theta"],
            vega=p_greeks["vega"],
        ),
    ]

    multiplier_scaled = final_qty * 100.0
    net_delta = (c_greeks["delta"] + p_greeks["delta"]) * multiplier_scaled
    net_gamma = (c_greeks["gamma"] + p_greeks["gamma"]) * multiplier_scaled
    net_theta = (c_greeks["theta"] + p_greeks["theta"]) * multiplier_scaled
    net_vega = (c_greeks["vega"] + p_greeks["vega"]) * multiplier_scaled

    max_loss = debit_per_unit * final_qty
    strat_hash = hashlib.sha256(f"STRADDLE:{atm_call.symbol}:{atm_put.symbol}".encode()).hexdigest()[:12]

    return StrategyCandidate(
        strategy_id=f"strat-straddle-{strat_hash}",
        decision=Decision.LONG_STRADDLE,
        legs=legs,
        quantity=final_qty,
        entry_debit_credit=debit_per_unit * final_qty,  # Positive = net debit
        net_delta=net_delta,
        net_gamma=net_gamma,
        net_theta=net_theta,
        net_vega=net_vega,
        max_loss=max_loss,
        max_profit=None,
        liquidity_score=0.90,
    )


def build_short_iron_butterfly_candidate(
    atm_call: OptionContractSnapshot,
    atm_put: OptionContractSnapshot,
    wing_call: OptionContractSnapshot,
    wing_put: OptionContractSnapshot,
    spot_price: float,
    nav: float,
    risk_config: RiskConfig,
) -> StrategyCandidate:
    """Construct a defined-risk Short Iron Butterfly with strict topological wing validation."""
    # Topological Wing Checks
    if not (wing_put.strike < atm_put.strike == atm_call.strike < wing_call.strike):
        raise ValidationError(
            f"Invalid Iron Butterfly strikes topology: LongPut({wing_put.strike}) < "
            f"ShortPut({atm_put.strike}) == ShortCall({atm_call.strike}) < LongCall({wing_call.strike})"
        )

    # Common Expiration Check
    exp = atm_call.expiration
    if not (atm_put.expiration == wing_call.expiration == wing_put.expiration == exp):
        raise ValidationError("All 4 legs of Iron Butterfly must share the identical expiration date.")

    t_exp = year_fraction_to_expiry(atm_call.quote_time, exp)
    if t_exp <= 0:
        t_exp = 1.0 / 365.0

    # Entry Assumptions: Sell shorts at Bid, Buy wings at Ask
    short_c_entry = atm_call.bid
    short_p_entry = atm_put.bid
    long_c_entry = wing_call.ask
    long_p_entry = wing_put.ask

    credit_per_share = (short_c_entry + short_p_entry) - (long_c_entry + long_p_entry)
    if credit_per_share <= 0:
        raise ValidationError(f"Iron Butterfly must produce a positive net credit, got {credit_per_share:.2f}")

    credit_per_unit = credit_per_share * 100.0
    wing_width = min(atm_call.strike - wing_put.strike, wing_call.strike - atm_call.strike)
    max_loss_per_unit = (wing_width * 100.0) - credit_per_unit
    if max_loss_per_unit <= 0:
        max_loss_per_unit = wing_width * 100.0

    budget = nav * risk_config.recommended_risk_nav_pct
    affordable_qty = int(budget // max_loss_per_unit) if max_loss_per_unit > 0 else 0

    hard_max_budget = nav * risk_config.hard_max_risk_nav_pct
    max_allowed = int(hard_max_budget // max_loss_per_unit) if max_loss_per_unit > 0 else 0
    
    if affordable_qty == 0 and max_allowed >= 1:
        final_qty = 1
    else:
        final_qty = min(affordable_qty, max_allowed, risk_config.max_contracts)

    # Calculate Greeks for all 4 legs
    g_sc = bsm_greeks(spot_price, atm_call.strike, t_exp, atm_call.vendor_implied_vol or 0.60, option_type=OptionType.CALL)
    g_sp = bsm_greeks(spot_price, atm_put.strike, t_exp, atm_put.vendor_implied_vol or 0.60, option_type=OptionType.PUT)
    g_lc = bsm_greeks(spot_price, wing_call.strike, t_exp, wing_call.vendor_implied_vol or 0.60, option_type=OptionType.CALL)
    g_lp = bsm_greeks(spot_price, wing_put.strike, t_exp, wing_put.vendor_implied_vol or 0.60, option_type=OptionType.PUT)

    legs = [
        OptionLeg(
            contract_symbol=wing_put.symbol,
            option_type="put",
            strike=wing_put.strike,
            expiration=exp,
            side="buy",
            ratio_qty=1,
            position_intent="buy_to_open",
            entry_price_assumption=long_p_entry,
            delta=g_lp["delta"],
            gamma=g_lp["gamma"],
            theta=g_lp["theta"],
            vega=g_lp["vega"],
        ),
        OptionLeg(
            contract_symbol=atm_put.symbol,
            option_type="put",
            strike=atm_put.strike,
            expiration=exp,
            side="sell",
            ratio_qty=1,
            position_intent="sell_to_open",
            entry_price_assumption=short_p_entry,
            delta=-g_sp["delta"],
            gamma=-g_sp["gamma"],
            theta=-g_sp["theta"],
            vega=-g_sp["vega"],
        ),
        OptionLeg(
            contract_symbol=atm_call.symbol,
            option_type="call",
            strike=atm_call.strike,
            expiration=exp,
            side="sell",
            ratio_qty=1,
            position_intent="sell_to_open",
            entry_price_assumption=short_c_entry,
            delta=-g_sc["delta"],
            gamma=-g_sc["gamma"],
            theta=-g_sc["theta"],
            vega=-g_sc["vega"],
        ),
        OptionLeg(
            contract_symbol=wing_call.symbol,
            option_type="call",
            strike=wing_call.strike,
            expiration=exp,
            side="buy",
            ratio_qty=1,
            position_intent="buy_to_open",
            entry_price_assumption=long_c_entry,
            delta=g_lc["delta"],
            gamma=g_lc["gamma"],
            theta=g_lc["theta"],
            vega=g_lc["vega"],
        ),
    ]

    multiplier_scaled = final_qty * 100.0
    net_delta = (g_lp["delta"] - g_sp["delta"] - g_sc["delta"] + g_lc["delta"]) * multiplier_scaled
    net_gamma = (g_lp["gamma"] - g_sp["gamma"] - g_sc["gamma"] + g_lc["gamma"]) * multiplier_scaled
    net_theta = (g_lp["theta"] - g_sp["theta"] - g_sc["theta"] + g_lc["theta"]) * multiplier_scaled
    net_vega = (g_lp["vega"] - g_sp["vega"] - g_sc["vega"] + g_lc["vega"]) * multiplier_scaled

    strat_hash = hashlib.sha256(f"IBFLY:{atm_call.symbol}:{wing_call.symbol}:{wing_put.symbol}".encode()).hexdigest()[:12]

    return StrategyCandidate(
        strategy_id=f"strat-ibfly-{strat_hash}",
        decision=Decision.SHORT_IRON_BUTTERFLY,
        legs=legs,
        quantity=final_qty,
        entry_debit_credit=-credit_per_unit * final_qty,  # Negative = net credit
        net_delta=net_delta,
        net_gamma=net_gamma,
        net_theta=net_theta,
        net_vega=net_vega,
        max_loss=max_loss_per_unit * final_qty,
        max_profit=credit_per_unit * final_qty,
        liquidity_score=0.85,
    )
