"""Deterministic Portfolio Mandate Gate and Autonomous Risk Allocator.

Enforces CAISHENG_WORKPLAN.md Section 4.3 Portfolio Mandate Limits:
1. Fresh broker equity authority (no hardcoded fallback).
2. Max 3 concurrent open strategies.
3. Max 2 new entries per day.
4. Strategy max loss <= 1.0% current equity ($1,000 on $100k).
5. Total reserved risk <= 2.0% current equity ($2,000 on $100k).
6. Same-sector reserved risk <= $1,000.
7. Daily loss <= -$1,500 trips persistent daily loss halt.
8. Drawdown from High-Water Mark > 5.0% trips persistent drawdown halt.
9. Sufficient buying power.
10. Active persistent kill switch / system halt enforcement.
"""

import math
import uuid
from volagent.config import MandateConfig
from volagent.domain.enums import Decision, GateStatus
from volagent.domain.portfolio import PortfolioRiskReport, PortfolioSnapshot
from volagent.domain.risk import RiskCheck
from volagent.domain.strategies import StrategyCandidate
from volagent.execution.ledger import ExecutionLedger

SECTOR_MAP: dict[str, str] = {
    "NVDA": "technology",
    "AAPL": "technology",
    "MSFT": "technology",
    "GOOGL": "technology",
    "META": "technology",
    "TSLA": "consumer_cyclical",
    "AMZN": "consumer_cyclical",
    "SPY": "index",
    "QQQ": "index",
}


def get_symbol_sector(symbol: str) -> str:
    sym = (symbol or "").upper().strip()
    return SECTOR_MAP.get(sym, "technology" if any(k in sym for k in ["NVDA", "AAPL", "MSFT", "GOOG", "META"]) else "general")


def evaluate_portfolio_gate(
    candidate: StrategyCandidate | None,
    decision: Decision,
    portfolio: PortfolioSnapshot,
    mandate_config: MandateConfig,
    underlying_symbol: str = "NVDA",
    is_paper_endpoint: bool = True,
    ledger: ExecutionLedger | None = None,
    is_close_order: bool = False,
    candidate_risk_already_reserved: bool = False,
) -> PortfolioRiskReport:
    """Evaluate candidate proposal against portfolio mandate and broker account state."""
    checks: list[RiskCheck] = []
    rejection_reasons: list[str] = []

    def add_hard_check(name: str, passed: bool, observed: str, limit: str, explanation: str) -> None:
        status = GateStatus.PASS if passed else GateStatus.FAIL
        if not passed:
            rejection_reasons.append(f"{name}: {explanation}")
        checks.append(RiskCheck(name=name, status=status, observed=observed, limit=limit, explanation=explanation))

    sector = get_symbol_sector(underlying_symbol)

    # 1. Positive and Finite Equity
    equity_valid = portfolio.equity > 0 and math.isfinite(portfolio.equity)
    add_hard_check("positive_equity", equity_valid, f"${portfolio.equity:.2f}", "> $0.00", "Portfolio account equity must be strictly positive and finite.")

    # 2. Fresh Account Snapshot (Fail-closed on stale state)
    add_hard_check("fresh_account_snapshot", not portfolio.is_stale, f"Stale={portfolio.is_stale}", "Fresh", "Account and portfolio state must be fresh from broker.")

    # 3. Paper Endpoint Assertion
    add_hard_check("paper_only_endpoint", is_paper_endpoint, f"Paper={is_paper_endpoint}", "True", "Trading must target Alpaca paper endpoint.")

    # 4. System Halt / Kill Switch Check
    is_halted = False
    halt_reason = ""
    if ledger is not None:
        is_halted, halt_reason = ledger.is_system_halted()

    # If this is a risk-reducing close, allow it even under halt; entry orders are blocked!
    if is_close_order:
        add_hard_check("halt_state", True, "Risk-reducing close order permitted", "Permitted", "Closing positions is permitted during halt.")
    else:
        add_hard_check("halt_state", not is_halted, f"Halted={is_halted} ({halt_reason})", "Not Halted", "System must not be in a persistent halt state for new entries.")

    # 5. Daily Loss Threshold Check (Realized + Unrealized Loss <= -$1,500 trips halt)
    daily_loss_limit = -abs(mandate_config.daily_loss_halt_dollars)
    daily_loss_breached = portfolio.total_daily_pl <= daily_loss_limit
    if daily_loss_breached and ledger is not None and not is_halted and not is_close_order:
        ledger.trip_system_halt(f"Daily loss limit breached: total daily P&L ${portfolio.total_daily_pl:.2f} <= limit ${daily_loss_limit:.2f}")

    add_hard_check(
        "daily_loss_limit",
        (not daily_loss_breached) if not is_close_order else True,
        f"${portfolio.total_daily_pl:.2f}",
        f"> ${daily_loss_limit:.2f}",
        f"Daily loss must not exceed ${mandate_config.daily_loss_halt_dollars:.2f} halt limit."
    )

    # 6. Competition Drawdown Check (Drawdown > 5.0% trips persistent halt)
    drawdown_breached = portfolio.drawdown_from_hwm_pct > mandate_config.drawdown_halt_pct
    if drawdown_breached and ledger is not None and not is_halted and not is_close_order:
        ledger.trip_system_halt(f"Competition drawdown limit breached: {portfolio.drawdown_from_hwm_pct*100:.2f}% > limit {mandate_config.drawdown_halt_pct*100:.1f}%")

    add_hard_check(
        "drawdown_limit",
        (not drawdown_breached) if not is_close_order else True,
        f"{portfolio.drawdown_from_hwm_pct*100:.2f}%",
        f"<= {mandate_config.drawdown_halt_pct*100:.1f}%",
        "Drawdown from High-Water Mark must not exceed 5.00% halt threshold."
    )


    # If NO_TRADE or closing order, return report
    if decision == Decision.NO_TRADE or is_close_order:
        status = GateStatus.PASS if not rejection_reasons else GateStatus.FAIL
        return PortfolioRiskReport(
            overall_status=status,
            checks=checks,
            approved_quantity=getattr(candidate, "quantity", 0) if (candidate and status == GateStatus.PASS) else 0,
            rejection_reasons=rejection_reasons,
            mandate_version=mandate_config.mandate_version,
            current_equity=portfolio.equity,
            reserved_risk_before=portfolio.reserved_risk_dollars,
            reserved_risk_after=portfolio.reserved_risk_dollars,
            risk_reservation_ref=None,
        )

    cand_qty = getattr(candidate, "quantity", 0) if candidate else 0
    cand_max_loss = getattr(candidate, "max_loss", getattr(candidate, "max_loss_dollars", 0.0)) if candidate else 0.0
    cand_cost = getattr(candidate, "entry_debit_credit", getattr(candidate, "estimated_cost_dollars", 0.0)) if candidate else 0.0

    # 7. Open Strategies Capacity (Max 3 open strategies)
    # A PREVIEWED/APPROVED order is an intent, not an existing open strategy.
    # The broker snapshot is authoritative for filled exposure, so a new entry
    # must always consume one additional strategy slot at this boundary.
    open_cap_passed = portfolio.open_strategies_count < mandate_config.max_open_strategies
    add_hard_check(
        "max_open_strategies",
        open_cap_passed,
        f"{portfolio.open_strategies_count} open",
        f"< {mandate_config.max_open_strategies}",
        f"Portfolio concurrency limited to {mandate_config.max_open_strategies} open strategies."
    )

    # 8. Daily Entry Rate Limit (Max 2 new entries per day)
    # The gateway registers the candidate before its final broker-side recheck,
    # so its pending intent may already be present in this count.  Callers must
    # state that explicitly; mere presence of a preview is not inferred.
    daily_entry_passed = (
        portfolio.new_entries_today_count <= mandate_config.max_new_entries_per_day
        if candidate_risk_already_reserved
        else portfolio.new_entries_today_count < mandate_config.max_new_entries_per_day
    )
    add_hard_check(
        "max_daily_entries",
        daily_entry_passed,
        f"{portfolio.new_entries_today_count} entries today",
        (f"<= {mandate_config.max_new_entries_per_day} (candidate already reserved)"
         if candidate_risk_already_reserved else f"< {mandate_config.max_new_entries_per_day}"),
        f"Maximum {mandate_config.max_new_entries_per_day} new strategy entries per market day."
    )

    # 9. Absolute Strategy Maximum Loss Cap (1.0% current equity / $1,000 on $100k)
    strat_max_loss_limit = portfolio.equity * mandate_config.absolute_max_loss_nav_pct
    strat_loss_passed = cand_max_loss <= (strat_max_loss_limit + 1e-4)
    add_hard_check(
        "strategy_max_loss_cap",
        strat_loss_passed,
        f"${cand_max_loss:.2f}",
        f"<= ${strat_max_loss_limit:.2f} ({mandate_config.absolute_max_loss_nav_pct*100:.1f}% equity)",
        "Strategy maximum loss must not exceed 1.00% of current account equity."
    )

    # 10. Total Reserved Risk Across Portfolio (Max 2.0% current equity / $2,000 on $100k)
    new_total_reserved_risk = (
        portfolio.reserved_risk_dollars
        if candidate_risk_already_reserved
        else portfolio.reserved_risk_dollars + cand_max_loss
    )
    total_risk_limit = portfolio.equity * mandate_config.max_total_reserved_risk_nav_pct
    total_risk_passed = new_total_reserved_risk <= (total_risk_limit + 1e-4)
    add_hard_check(
        "total_reserved_risk_cap",
        total_risk_passed,
        f"${new_total_reserved_risk:.2f}",
        f"<= ${total_risk_limit:.2f} ({mandate_config.max_total_reserved_risk_nav_pct*100:.1f}% equity)",
        "Total portfolio reserved risk across all open strategies must not exceed 2.00% of current equity."
    )

    # 11. Same-Sector Reserved Risk Cap (Max $1,000)
    current_sector_risk = portfolio.sector_reserved_risk.get(sector, 0.0)
    new_sector_risk = (
        current_sector_risk
        if candidate_risk_already_reserved
        else current_sector_risk + cand_max_loss
    )
    sector_risk_passed = new_sector_risk <= (mandate_config.max_same_sector_reserved_risk + 1e-4)
    add_hard_check(
        "sector_risk_cap",
        sector_risk_passed,
        f"Sector {sector}: ${new_sector_risk:.2f}",
        f"<= ${mandate_config.max_same_sector_reserved_risk:.2f}",
        f"Reserved risk in sector {sector} must not exceed ${mandate_config.max_same_sector_reserved_risk:.2f}."
    )


    # 12. Buying Power Availability
    est_cost = max(0.0, cand_cost)
    bp_passed = est_cost <= (portfolio.buying_power + 1e-4)
    add_hard_check(
        "sufficient_buying_power",
        bp_passed,
        f"Cost=${est_cost:.2f}, BP=${portfolio.buying_power:.2f}",
        f"Cost <= BP (${portfolio.buying_power:.2f})",
        "Required entry cost must not exceed available broker buying power."
    )

    overall_status = GateStatus.PASS if not rejection_reasons else GateStatus.FAIL
    approved_quantity = cand_qty if overall_status == GateStatus.PASS else 0
    reservation_ref = f"rsk-{uuid.uuid4().hex[:8]}" if overall_status == GateStatus.PASS else None


    return PortfolioRiskReport(
        overall_status=overall_status,
        checks=checks,
        approved_quantity=approved_quantity,
        rejection_reasons=rejection_reasons,
        mandate_version=mandate_config.mandate_version,
        current_equity=portfolio.equity,
        reserved_risk_before=portfolio.reserved_risk_dollars,
        reserved_risk_after=new_total_reserved_risk if overall_status == GateStatus.PASS else portfolio.reserved_risk_dollars,
        risk_reservation_ref=reservation_ref,
    )
