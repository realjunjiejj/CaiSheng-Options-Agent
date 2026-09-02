"""Point-in-time historical volatility replay built from Alpaca bars.

This module deliberately does *not* represent historical bars as executable
option quotes.  Alpaca's historical bars can support an honest forecast
replay, but they do not provide the timestamped historical bid/ask, Greeks,
IV, or open interest needed for an execution backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
from statistics import stdev
from typing import Any, Iterable

from volagent.clock import year_fraction_to_expiry
from volagent.domain.enums import DataMode
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.provenance import Provenance, compute_canonical_hash
from volagent.quant.implied_vol import invert_implied_volatility
from volagent.quant.pricing import bsm_greeks


HISTORICAL_BAR_PROXY_LABEL = "Historical bar proxy — non-executable"


@dataclass(frozen=True)
class HistoricalBarSnapshot:
    """Market inputs observable at a declared historical decision boundary."""

    underlying: UnderlyingSnapshot
    option_chain: list[OptionContractSnapshot]
    cutoff_time: datetime
    limitations: tuple[str, ...]


def _as_utc(value: datetime) -> datetime:
    """Normalize an Alpaca timestamp, rejecting no data by returning UTC only."""
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def last_bar_at_or_before(bars: Iterable[object], cutoff_time: datetime) -> object | None:
    """Select the newest bar at or before the decision boundary; never after it."""
    cutoff = _as_utc(cutoff_time)
    eligible = [bar for bar in bars if _as_utc(bar.timestamp) <= cutoff]
    return max(eligible, key=lambda bar: _as_utc(bar.timestamp), default=None)


def annualized_realized_volatility(bars: Iterable[object], cutoff_time: datetime, window: int) -> float | None:
    """Compute RV using only *completed* sessions before the decision date."""
    decision_date = _as_utc(cutoff_time).date()
    closes = [
        float(bar.close)
        for bar in sorted(bars, key=lambda item: _as_utc(item.timestamp))
        if _as_utc(bar.timestamp).date() < decision_date
        and getattr(bar, "close", None) is not None
        and float(bar.close) > 0.0
    ]
    returns = [math.log(current / previous) for previous, current in zip(closes, closes[1:])]
    sample = returns[-window:]
    if len(sample) < window or len(sample) < 2:
        return None
    return math.sqrt(252.0) * stdev(sample)


def proxy_contract_from_bar(
    *,
    symbol: str,
    underlying_symbol: str,
    option_type: str,
    strike: float,
    expiration: date,
    bar: object,
    spot: float,
    cutoff_time: datetime,
) -> OptionContractSnapshot | None:
    """Construct a derived option observation from one pre-cutoff close bar.

    The equal bid/ask is intentionally a *bar-price proxy*, never a claim that
    a zero-spread historical quote existed.  Missing OI and volume history is
    represented as zero and bypassed only in the replay-specific configuration.
    """
    bar_time = _as_utc(bar.timestamp)
    cutoff = _as_utc(cutoff_time)
    price = float(getattr(bar, "close", 0.0) or 0.0)
    time_to_expiry = year_fraction_to_expiry(cutoff, expiration)
    if bar_time > cutoff or price <= 0.0 or not math.isfinite(price) or time_to_expiry <= 0.0:
        return None
    implied_vol = invert_implied_volatility(
        price=price,
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        option_type=option_type,
    )
    if implied_vol is None or not math.isfinite(implied_vol):
        return None
    greeks = bsm_greeks(spot, strike, time_to_expiry, implied_vol, option_type=option_type)
    payload = {
        "symbol": symbol,
        "bar_time": bar_time.isoformat(),
        "bar_close": price,
        "decision_time": cutoff.isoformat(),
    }
    provenance = Provenance(
        source_name=HISTORICAL_BAR_PROXY_LABEL,
        source_uri=f"alpaca://historical/options/bars/{symbol}",
        retrieved_at=datetime.now(timezone.utc),
        observed_at=bar_time,
        effective_at=cutoff,
        content_hash=compute_canonical_hash(payload),
        data_mode=DataMode.REPLAY_REAL,
    )
    return OptionContractSnapshot(
        symbol=symbol,
        underlying_symbol=underlying_symbol,
        option_type=option_type,  # type: ignore[arg-type]
        strike=strike,
        expiration=expiration,
        bid=price,
        ask=price,
        last=price,
        quote_time=bar_time,
        volume=0,
        open_interest=0,
        vendor_implied_vol=implied_vol,
        vendor_delta=greeks["delta"],
        vendor_gamma=greeks["gamma"],
        vendor_theta=greeks["theta"],
        vendor_vega=greeks["vega"],
        provenance=provenance,
    )


def score_bar_proxy_forecast(
    result: dict[str, Any], exit_spot: float, exit_option_closes: dict[str, float]) -> dict[str, Any]:
    """Score a locked historical forecast without asserting executable P&L."""
    underlying = result.get("underlying")
    forecast = result.get("move_forecast")
    feature_set = result.get("feature_set", {})
    if underlying is None or forecast is None or exit_spot <= 0.0:
        raise ValueError("A complete locked forecast and a positive post-event spot are required.")
    realized_abs_move = abs(exit_spot / underlying.price - 1.0)
    atm_symbols = [
        contract.symbol
        for contract in (feature_set.get("atm_call"), feature_set.get("atm_put"))
        if contract is not None
    ]
    if len(atm_symbols) != 2 or any(price <= 0.0 for price in (exit_option_closes.get(symbol, 0.0) for symbol in atm_symbols)):
        proxy_pnl = None
    else:
        entry = sum((feature_set[key].last or feature_set[key].bid) for key in ("atm_call", "atm_put"))
        exit_value = sum(exit_option_closes[symbol] for symbol in atm_symbols)
        proxy_pnl = {
            "value": (exit_value - entry) * 100.0,
            "label": "bar-close premium change only — not executable P&L",
        }
    return {
        "label": HISTORICAL_BAR_PROXY_LABEL,
        "entry_spot": underlying.price,
        "exit_spot": exit_spot,
        "realized_abs_move_pct": realized_abs_move,
        "forecast_median_abs_error_pct": abs(realized_abs_move - forecast.median_abs_move_pct),
        "implied_move_abs_error_pct": abs(realized_abs_move - forecast.implied_move_pct),
        "within_q20_q80_interval": forecast.q20_abs_move_pct <= realized_abs_move <= forecast.q80_abs_move_pct,
        "bar_close_premium_change": proxy_pnl,
    }


class AlpacaHistoricalBarReplayAdapter:
    """Read-only Alpaca adapter for a generic, pre-event bar replay."""

    def __init__(self, api_key: str | None, secret_key: str | None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.last_error: str | None = None

    def _require_credentials(self) -> None:
        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca credentials are required for historical bar replay.")

    def _stock_bars(self, symbol: str, start: datetime, end: datetime, timeframe: object) -> list[object]:
        from alpaca.data.enums import DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest

        response = StockHistoricalDataClient(self.api_key, self.secret_key).get_stock_bars(
            StockBarsRequest(symbol_or_symbols=symbol, start=start, end=end, timeframe=timeframe, feed=DataFeed.IEX)
        )
        return list(response.data.get(symbol, []))

    def _option_bars(self, symbols: list[str], start: datetime, end: datetime) -> dict[str, list[object]]:
        from alpaca.data.historical import OptionHistoricalDataClient
        from alpaca.data.requests import OptionBarsRequest
        from alpaca.data.timeframe import TimeFrame

        response = OptionHistoricalDataClient(self.api_key, self.secret_key).get_option_bars(
            OptionBarsRequest(symbol_or_symbols=symbols, start=start, end=end, timeframe=TimeFrame.Minute)
        )
        return {symbol: list(bars) for symbol, bars in response.data.items()}

    def build_snapshot(self, symbol: str, cutoff_time: datetime, expiration: date) -> HistoricalBarSnapshot:
        """Return only observations at or before cutoff; no event outcome is read."""
        self._require_credentials()
        from alpaca.data.timeframe import TimeFrame
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import AssetStatus
        from alpaca.trading.requests import GetOptionContractsRequest

        symbol = symbol.strip().upper()
        cutoff = _as_utc(cutoff_time)
        if not symbol.isalpha() or len(symbol) > 6:
            raise ValueError("Enter a valid US ticker symbol.")
        if expiration <= cutoff.date():
            raise ValueError("Option expiration must be after the historical decision time.")

        stock_minute_bars = self._stock_bars(symbol, cutoff - timedelta(minutes=30), cutoff, TimeFrame.Minute)
        spot_bar = last_bar_at_or_before(stock_minute_bars, cutoff)
        if spot_bar is None or float(getattr(spot_bar, "close", 0.0) or 0.0) <= 0.0:
            raise ValueError("No positive underlying minute bar exists at or before the selected cutoff.")
        daily_bars = self._stock_bars(symbol, cutoff - timedelta(days=70), cutoff, TimeFrame.Day)
        spot = float(spot_bar.close)
        prior_daily = [bar for bar in daily_bars if _as_utc(bar.timestamp).date() < cutoff.date()]
        previous_close = float(prior_daily[-1].close) if prior_daily else None
        underlying_provenance = Provenance(
            source_name=HISTORICAL_BAR_PROXY_LABEL,
            source_uri=f"alpaca://historical/stocks/bars/{symbol}",
            retrieved_at=datetime.now(timezone.utc),
            observed_at=_as_utc(spot_bar.timestamp),
            effective_at=cutoff,
            content_hash=compute_canonical_hash({"symbol": symbol, "bar_time": _as_utc(spot_bar.timestamp).isoformat(), "close": spot}),
            data_mode=DataMode.REPLAY_REAL,
        )
        underlying = UnderlyingSnapshot(
            symbol=symbol,
            price=spot,
            bid=spot,
            ask=spot,
            quote_time=_as_utc(spot_bar.timestamp),
            previous_close=previous_close,
            realized_vol_10d=annualized_realized_volatility(daily_bars, cutoff, 10),
            realized_vol_30d=annualized_realized_volatility(daily_bars, cutoff, 30),
            provenance=underlying_provenance,
        )

        contracts_response = TradingClient(self.api_key, self.secret_key, paper=True).get_option_contracts(
            GetOptionContractsRequest(
                underlying_symbols=[symbol],
                expiration_date_gte=expiration,
                expiration_date_lte=expiration,
                status=AssetStatus.INACTIVE,
                limit=1000,
            )
        )
        metadata: list[tuple[str, str, float]] = []
        for contract in contracts_response.option_contracts or []:
            parsed = self._parse_contract(contract.symbol)
            if parsed and parsed[0] == symbol and parsed[1] == expiration:
                _, _, option_type, strike = parsed
                metadata.append((contract.symbol, option_type, strike))
        if not metadata:
            raise ValueError("Alpaca returned no expired contracts for this ticker and expiry.")

        # Bound the request to a small symmetric strike band, then require real
        # bars for both sides. Contract metadata itself is not used as historical
        # liquidity evidence.
        by_strike: dict[float, dict[str, str]] = {}
        for contract_symbol, option_type, strike in metadata:
            by_strike.setdefault(strike, {})[option_type] = contract_symbol
        paired_strikes = [
            (strike, sides["call"], sides["put"])
            for strike, sides in by_strike.items()
            if "call" in sides and "put" in sides
        ]
        paired_strikes.sort(key=lambda row: abs(row[0] - spot))
        selected_pairs = paired_strikes[:9]
        if not selected_pairs:
            raise ValueError("No common call/put strike pairs exist for the selected expiry.")
        requested_symbols = [contract_symbol for _, call, put in selected_pairs for contract_symbol in (call, put)]
        bars_by_symbol = self._option_bars(requested_symbols, cutoff - timedelta(minutes=30), cutoff)
        chain: list[OptionContractSnapshot] = []
        for strike, call_symbol, put_symbol in selected_pairs:
            for contract_symbol, option_type in ((call_symbol, "call"), (put_symbol, "put")):
                bar = last_bar_at_or_before(bars_by_symbol.get(contract_symbol, []), cutoff)
                if bar:
                    proxy = proxy_contract_from_bar(
                        symbol=contract_symbol,
                        underlying_symbol=symbol,
                        option_type=option_type,
                        strike=strike,
                        expiration=expiration,
                        bar=bar,
                        spot=spot,
                        cutoff_time=cutoff,
                    )
                    if proxy:
                        chain.append(proxy)
        pair_counts: dict[float, int] = {}
        for contract in chain:
            pair_counts[contract.strike] = pair_counts.get(contract.strike, 0) + 1
        chain = [contract for contract in chain if pair_counts[contract.strike] == 2]
        if len(chain) < 2:
            raise ValueError("No common call/put pair had valid pre-cutoff historical bars.")
        return HistoricalBarSnapshot(
            underlying=underlying,
            option_chain=chain,
            cutoff_time=cutoff,
            limitations=(
                "Historical options bid/ask snapshots are unavailable; bar closes are a pricing proxy.",
                "Historical options IV and Greeks are derived with Black-Scholes inversion, not vendor snapshots.",
                "Historical open interest is unavailable as-of; liquidity OI/volume gates are not evaluated.",
                "No result from this screen is an executable fill, backtested trading return, or alpha claim.",
            ),
        )

    def exit_prices(self, symbol: str, contract_symbols: list[str], exit_time: datetime) -> tuple[float, dict[str, float]]:
        """Fetch only outcome bars up to an explicit post-event exit boundary."""
        self._require_credentials()
        from alpaca.data.timeframe import TimeFrame

        exit_cutoff = _as_utc(exit_time)
        stock_bars = self._stock_bars(symbol.upper(), exit_cutoff - timedelta(minutes=30), exit_cutoff, TimeFrame.Minute)
        spot_bar = last_bar_at_or_before(stock_bars, exit_cutoff)
        if spot_bar is None:
            raise ValueError("No post-event underlying minute bar exists at the selected exit time.")
        option_bars = self._option_bars(contract_symbols, exit_cutoff - timedelta(minutes=30), exit_cutoff)
        closes: dict[str, float] = {}
        for contract_symbol, bars in option_bars.items():
            bar = last_bar_at_or_before(bars, exit_cutoff)
            if bar and float(getattr(bar, "close", 0.0) or 0.0) > 0.0:
                closes[contract_symbol] = float(bar.close)
        return float(spot_bar.close), closes

    @staticmethod
    def _parse_contract(symbol: str) -> tuple[str, date, str, float] | None:
        # Keep this module read-only and reuse the audited OCC parser.
        from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter

        return AlpacaLiveMarketAdapter.parse_occ_option_symbol(symbol)
