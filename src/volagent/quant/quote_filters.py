"""Quote filtering pipeline for options contracts."""

from datetime import datetime
from typing import Any
from volagent.config import ContractFiltersConfig
from volagent.domain.market import OptionContractSnapshot


def filter_option_chain(
    chain: list[OptionContractSnapshot],
    target_symbol: str,
    target_expiration: Any,
    as_of_time: datetime,
    config: ContractFiltersConfig,
) -> tuple[list[OptionContractSnapshot], dict[str, Any]]:
    """Filter raw option chain quotes using strict quality, freshness, and no-arbitrage rules."""
    passed = []
    rejection_counts = {
        "wrong_symbol": 0,
        "wrong_expiration": 0,
        "future_timestamp": 0,
        "stale_quote": 0,
        "crossed_quote": 0,
        "zero_bid": 0,
        "wide_spread": 0,
        "low_volume": 0,
        "low_open_interest": 0,
    }

    for contract in chain:
        if contract.underlying_symbol != target_symbol:
            rejection_counts["wrong_symbol"] += 1
            continue

        if contract.expiration != target_expiration:
            rejection_counts["wrong_expiration"] += 1
            continue

        # Independent market-data endpoints can differ by milliseconds. Permit
        # only bounded clock skew; later data remains unavailable to a decision.
        future_skew = (contract.quote_time - as_of_time).total_seconds()
        if future_skew > config.clock_skew_tolerance_seconds:
            rejection_counts["future_timestamp"] += 1
            continue

        # Freshness check: quote age <= max_quote_age_seconds
        age_seconds = max(0.0, (as_of_time - contract.quote_time).total_seconds())
        if age_seconds > config.max_quote_age_seconds:
            rejection_counts["stale_quote"] += 1
            continue

        # Crossed or zero quotes
        if contract.bid > contract.ask or contract.bid < 0:
            rejection_counts["crossed_quote"] += 1
            continue

        if contract.bid <= 0.01:
            rejection_counts["zero_bid"] += 1
            continue

        # Relative spread filter: (ask - bid) / mid <= max_relative_spread_pct
        mid = (contract.bid + contract.ask) / 2.0
        rel_spread = (contract.ask - contract.bid) / mid
        if rel_spread > config.max_relative_spread_pct:
            rejection_counts["wide_spread"] += 1
            continue

        # Liquidity filter
        if contract.volume < config.min_volume:
            rejection_counts["low_volume"] += 1
            continue

        if contract.open_interest < config.min_open_interest:
            rejection_counts["low_open_interest"] += 1
            continue

        passed.append(contract)

    audit_summary = {
        "raw_quotes_count": len(chain),
        "passed_quotes_count": len(passed),
        "rejection_counts": rejection_counts,
    }

    return passed, audit_summary
