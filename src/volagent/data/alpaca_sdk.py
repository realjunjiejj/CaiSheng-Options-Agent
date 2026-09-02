"""Live Alpaca market-data adapter with fail-closed option-chain normalization."""

from datetime import date, datetime, timedelta, timezone
import json
import math
import re
from statistics import stdev
from typing import Any


from volagent.config import PROJECT_ROOT
from volagent.domain.enums import DataMode
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.portfolio import PortfolioSnapshot
from volagent.provenance import Provenance, compute_canonical_hash


class AlpacaPortfolioAdapter:
    """Connects to Alpaca Trading API to read live account equity, cash, buying power, and positions."""

    def __init__(self, api_key: str | None = None, secret_key: str | None = None, paper: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.last_error: str | None = None
        self._trading_client = None

    def _get_client(self):
        if self._trading_client is None:
            if not self.api_key or not self.secret_key:
                raise ValueError("Missing Alpaca API credentials.")
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
        return self._trading_client

    def fetch_portfolio_snapshot(
        self,
        ledger: Any | None = None,
        mandate_config: Any | None = None,
        high_water_equity: float | None = None,
    ) -> PortfolioSnapshot:
        """Fetch fresh point-in-time portfolio snapshot from Alpaca Trading API. Fails closed on missing/error."""
        now = datetime.now(timezone.utc)
        if not self.api_key or not self.secret_key:
            self.last_error = "Missing Alpaca API credentials."
            return PortfolioSnapshot(
                equity=0.0,
                cash=0.0,
                buying_power=0.0,
                initial_nav=100000.0,
                high_water_equity=100000.0,
                timestamp=now,
                is_stale=True,
                account_id=None,
            )

        try:
            client = self._get_client()
            account = client.get_account()
            equity = float(account.equity) if account.equity is not None else 0.0
            cash = float(account.cash) if account.cash is not None else 0.0
            buying_power = float(account.buying_power) if account.buying_power is not None else 0.0
            last_equity = float(account.last_equity) if getattr(account, "last_equity", None) is not None else equity
            daily_unrealized = equity - last_equity
            acct_id = str(getattr(account, "id", getattr(account, "account_number", "")))

            open_strats = 0
            entries_today = 0
            reserved_risk = 0.0
            sector_risk: dict[str, float] = {}

            init_nav = 100000.0
            stored_hwm = init_nav
            if ledger is not None:
                open_strats = ledger.get_open_strategies_count()
                entries_today = ledger.get_new_entries_today_count()
                reserved_risk, sector_risk = ledger.get_portfolio_reserved_risk()
                meta = ledger.get_or_init_competition_metadata(starting_nav=100000.0, paper_account_id=acct_id)
                init_nav = float(meta.get("starting_nav", 100000.0))
                latest_snap = ledger.get_latest_portfolio_snapshot()
                if latest_snap:
                    stored_hwm = float(latest_snap.get("high_water_equity", init_nav))
                daily_realized = ledger.get_daily_realized_pnl()
            else:
                daily_realized = 0.0

            hwm = max(init_nav, equity, high_water_equity or stored_hwm)

            snap = PortfolioSnapshot(
                equity=equity,
                cash=cash,
                buying_power=buying_power,
                initial_nav=init_nav,
                high_water_equity=hwm,
                daily_realized_pl=daily_realized,
                daily_unrealized_pl=daily_unrealized,
                open_strategies_count=open_strats,
                new_entries_today_count=entries_today,
                reserved_risk_dollars=reserved_risk,
                sector_reserved_risk=sector_risk,
                timestamp=now,
                is_stale=False,
                account_id=acct_id,
            )
            if ledger is not None:
                try:
                    ledger.record_portfolio_snapshot(snap)
                except Exception:
                    pass
            return snap

        except Exception as exc:
            self.last_error = f"Failed to fetch Alpaca account snapshot: {type(exc).__name__}: {exc}"
            return PortfolioSnapshot(
                equity=0.0,
                cash=0.0,
                buying_power=0.0,
                initial_nav=100000.0,
                high_water_equity=100000.0,
                timestamp=now,
                is_stale=True,
                account_id=None,
            )

    def list_positions(self) -> list[Any]:
        """Fetch active broker positions."""
        client = self._get_client()
        return client.get_all_positions()

    def list_orders(self, status: str = "open", limit: int = 50) -> list[Any]:
        """Fetch broker orders filtered by status."""
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        client = self._get_client()
        order_status = QueryOrderStatus.OPEN if status == "open" else (QueryOrderStatus.CLOSED if status == "closed" else QueryOrderStatus.ALL)
        req = GetOrdersRequest(status=order_status, limit=limit)
        return client.get_orders(req)

    def get_market_clock(self) -> dict[str, Any]:
        """Fetch market clock state."""
        client = self._get_client()
        clock = client.get_clock()
        return {
            "is_open": clock.is_open,
            "next_open": clock.next_open.isoformat() if clock.next_open else None,
            "next_close": clock.next_close.isoformat() if clock.next_close else None,
            "timestamp": clock.timestamp.isoformat() if clock.timestamp else None,
        }



class AlpacaLiveMarketAdapter:

    """Connects to Alpaca Market Data API for live stock and options chain ingestion."""

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        *,
        stock_feed: str = "iex",
        options_feed: str = "indicative",
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.stock_feed = stock_feed
        self.options_feed = options_feed
        self.last_error: str | None = None

    @staticmethod
    def _daily_bars(
        symbol: str,
        start: datetime,
        end: datetime,
        api_key: str,
        secret_key: str,
        stock_feed: str = "iex",
    ) -> list[object]:
        """Fetch raw (unadjusted) daily bars for deterministic live features."""
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        response = StockHistoricalDataClient(api_key, secret_key).get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                feed=DataFeed(stock_feed),
            )
        )
        return list(response.data.get(symbol, []))

    def _realized_volatilities(self, symbol: str) -> tuple[float | None, float | None]:
        """Compute annualized 10/30-session realized volatility from real bars."""
        if not self.api_key or not self.secret_key:
            return None, None
        try:
            now = datetime.now(timezone.utc)
            bars = self._daily_bars(
                symbol,
                now - timedelta(days=60),
                now,
                self.api_key,
                self.secret_key,
                self.stock_feed,
            )
            closes = [float(bar.close) for bar in bars if getattr(bar, "close", None) and float(bar.close) > 0.0]
            if len(closes) < 11:
                return None, None
            returns = [math.log(current / previous) for previous, current in zip(closes, closes[1:])]

            def annualized(window: int) -> float | None:
                sample = returns[-window:]
                if len(sample) < window or len(sample) < 2:
                    return None
                return math.sqrt(252.0) * stdev(sample)

            return annualized(10), annualized(30)
        except Exception:
            # Quote validity is independent from the optional volatility feature.
            return None, None

    def get_historical_event_moves(
        self,
        symbol: str,
        event_dates: list[date],
        before_event_date: date,
    ) -> list[float]:
        """Calculate real prior-event reactions from caller-supplied verified dates.

        Alpaca supplies prices, not an authoritative earnings calendar.  The
        operator or an upstream calendar provider must therefore supply dates
        for the current ticker; no ticker-specific calendar is embedded here.
        Missing dates return no history and keep the forecast OOD.
        """
        if not self.api_key or not self.secret_key:
            return []

        moves: list[float] = []
        cache_rows: list[dict[str, object]] = []
        for event_date in sorted(set(event_dates)):
            if event_date >= before_event_date:
                continue
            try:
                start = datetime.combine(event_date, datetime.min.time(), tzinfo=timezone.utc)
                bars = self._daily_bars(
                    symbol.upper(),
                    start,
                    start + timedelta(days=7),
                    self.api_key,
                    self.secret_key,
                    self.stock_feed,
                )
                closes = [(bar.timestamp.date(), float(bar.close)) for bar in bars if getattr(bar, "close", None) and float(bar.close) > 0.0]
                event_close = next((close for bar_date, close in closes if bar_date == event_date), None)
                next_close = next((close for bar_date, close in closes if bar_date > event_date), None)
                if event_close is None or next_close is None:
                    continue
                move = abs(next_close / event_close - 1.0)
                if math.isfinite(move):
                    moves.append(move)
                    cache_rows.append({
                        "event_date": event_date.isoformat(),
                        "absolute_close_to_close_move": move,
                    })
            except Exception:
                continue

        if cache_rows:
            cache_dir = PROJECT_ROOT / "data" / "live_evaluations"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / f"{symbol.upper()}_earnings_history.json"
            cache_file.write_text(json.dumps({"symbol": symbol.upper(), "retrieved_at": datetime.now(timezone.utc).isoformat(), "observations": cache_rows}, indent=2))
        return moves

    @staticmethod
    def parse_occ_option_symbol(symbol: str) -> tuple[str, date, str, float] | None:
        """Parse an OCC option symbol without inventing its strike or expiry."""
        match = re.fullmatch(r"([A-Z]{1,6})(\d{6})([CP])(\d{8})", symbol.strip().upper())
        if not match:
            return None
        root, expiry_raw, option_type, strike_raw = match.groups()
        try:
            expiry = datetime.strptime(expiry_raw, "%y%m%d").date()
            strike = int(strike_raw) / 1000.0
        except ValueError:
            return None
        return root, expiry, "call" if option_type == "C" else "put", strike

    def get_market_status(self) -> tuple[bool, datetime | None]:
        """Return the paper market clock; failures are closed-market failures."""
        if not self.api_key or not self.secret_key:
            self.last_error = "Alpaca credentials are missing."
            return False, None
        try:
            from alpaca.trading.client import TradingClient

            clock = TradingClient(self.api_key, self.secret_key, paper=True).get_clock()
            self.last_error = None
            return bool(clock.is_open), clock.timestamp.astimezone(timezone.utc)
        except Exception as exc:
            self.last_error = f"Unable to read Alpaca market clock: {type(exc).__name__}"
            return False, None

    def get_paper_account_equity(self) -> float | None:
        """Read paper equity for risk sizing; never infer NAV from a fixture."""
        if not self.api_key or not self.secret_key:
            self.last_error = "Alpaca credentials are missing."
            return None
        try:
            from alpaca.trading.client import TradingClient

            equity = float(TradingClient(self.api_key, self.secret_key, paper=True).get_account().equity)
            if not math.isfinite(equity) or equity <= 0:
                self.last_error = "Paper account equity is non-positive or invalid."
                return None
            self.last_error = None
            return equity
        except Exception as exc:
            self.last_error = f"Unable to read Alpaca paper equity: {type(exc).__name__}"
            return None

    def get_underlying_snapshot(self, symbol: str) -> UnderlyingSnapshot | None:
        """Fetch real-time stock quote from Alpaca."""
        if not self.api_key or not self.secret_key:
            return None

        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.enums import DataFeed
            from alpaca.data.requests import StockLatestQuoteRequest

            client = StockHistoricalDataClient(self.api_key, self.secret_key)
            req = StockLatestQuoteRequest(
                symbol_or_symbols=symbol,
                feed=DataFeed(self.stock_feed),
            )
            res = client.get_stock_latest_quote(req)
            quote = res.get(symbol)

            if quote and all(math.isfinite(float(value)) for value in (quote.bid_price, quote.ask_price)):
                now = datetime.now(timezone.utc)
                mid = (quote.bid_price + quote.ask_price) / 2.0
                if quote.bid_price <= 0 or quote.ask_price < quote.bid_price:
                    self.last_error = "Underlying quote is non-positive or crossed."
                    return None
                prov = Provenance(
                    source_name=f"Alpaca Live Market Data ({self.stock_feed})",
                    source_uri=f"alpaca://stocks/{symbol}/quote",
                    retrieved_at=now,
                    observed_at=quote.timestamp.astimezone(timezone.utc),
                    content_hash=compute_canonical_hash({"symbol": symbol, "price": mid}),
                    data_mode=DataMode.LIVE,
                )
                rv10, rv30 = self._realized_volatilities(symbol)
                return UnderlyingSnapshot(
                    symbol=symbol,
                    price=float(mid),
                    bid=float(quote.bid_price),
                    ask=float(quote.ask_price),
                    quote_time=quote.timestamp.astimezone(timezone.utc),
                    previous_close=float(mid),
                    realized_vol_10d=rv10,
                    realized_vol_30d=rv30,
                    data_feed=self.stock_feed,
                    provenance=prov,
                )
        except Exception as exc:
            self.last_error = f"Unable to fetch live underlying quote: {type(exc).__name__}"
            return None
        return None

    def _option_volumes(self, client: object, symbols: list[str]) -> dict[str, int]:
        """Fetch recent contract volumes in bounded batches; absent volume fails closed."""
        from alpaca.data.requests import OptionBarsRequest
        from alpaca.data.timeframe import TimeFrame

        volumes: dict[str, int] = {}
        start = datetime.now(timezone.utc) - timedelta(days=7)
        for offset in range(0, len(symbols), 100):
            batch = symbols[offset:offset + 100]
            bars = client.get_option_bars(OptionBarsRequest(symbol_or_symbols=batch, start=start, timeframe=TimeFrame.Day))
            for contract_symbol, contract_bars in bars.data.items():
                if contract_bars:
                    volume = getattr(contract_bars[-1], "volume", None)
                    if volume is not None:
                        volumes[contract_symbol] = int(volume)
        return volumes

    def get_option_chain(
        self,
        symbol: str,
        earliest_expiration: date | None = None,
        latest_expiration: date | None = None,
        spot_price: float | None = None,
    ) -> list[OptionContractSnapshot]:
        """Fetch real contract metadata, quotes, Greeks, open interest, and volume."""
        if not self.api_key or not self.secret_key:
            self.last_error = "Alpaca credentials are missing."
            return []

        try:
            from alpaca.data.historical import OptionHistoricalDataClient
            from alpaca.data.enums import OptionsFeed
            from alpaca.data.requests import OptionChainRequest
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import GetOptionContractsRequest

            option_client = OptionHistoricalDataClient(self.api_key, self.secret_key)
            contract_client = TradingClient(self.api_key, self.secret_key, paper=True)
            strike_floor = str(round(max(0.01, spot_price * 0.85), 2)) if spot_price else None
            strike_ceiling = str(round(spot_price * 1.15, 2)) if spot_price else None
            request = GetOptionContractsRequest(
                underlying_symbols=[symbol.upper()],
                expiration_date_gte=earliest_expiration,
                expiration_date_lte=latest_expiration,
                strike_price_gte=strike_floor,
                strike_price_lte=strike_ceiling,
                limit=1000,
            )
            contract_response = contract_client.get_option_contracts(request)
            metadata = {
                contract.symbol: contract
                for contract in (contract_response.option_contracts or [])
                if contract.tradable
            }
            if not metadata:
                self.last_error = "No active, tradable Alpaca option contracts matched the canary window."
                return []

            chain_res = option_client.get_option_chain(
                OptionChainRequest(
                    underlying_symbol=symbol.upper(),
                    feed=OptionsFeed(self.options_feed),
                    expiration_date_gte=earliest_expiration,
                    expiration_date_lte=latest_expiration,
                    strike_price_gte=float(strike_floor) if strike_floor else None,
                    strike_price_lte=float(strike_ceiling) if strike_ceiling else None,
                )
            )
            volumes = self._option_volumes(option_client, list(metadata))

            contracts = []
            now = datetime.now(timezone.utc)

            for sym, snap in chain_res.items():
                contract = metadata.get(sym)
                parsed = self.parse_occ_option_symbol(sym)
                if contract and parsed and snap.latest_quote:
                    q = snap.latest_quote
                    mid = (q.bid_price + q.ask_price) / 2.0
                    try:
                        open_interest = int(contract.open_interest) if contract.open_interest is not None else None
                    except (TypeError, ValueError):
                        open_interest = None
                    volume = volumes.get(sym)
                    if (
                        not math.isfinite(float(q.bid_price))
                        or not math.isfinite(float(q.ask_price))
                        or q.bid_price <= 0
                        or q.ask_price < q.bid_price
                        or mid <= 0
                        or open_interest is None
                        or volume is None
                        or snap.implied_volatility is None
                        or snap.greeks is None
                        or any(
                            value is None or not math.isfinite(float(value))
                            for value in (snap.greeks.delta, snap.greeks.gamma, snap.greeks.theta, snap.greeks.vega)
                        )
                    ):
                        continue

                    _, expiry, option_type, strike = parsed
                    prov = Provenance(
                        source_name=f"Alpaca Live Options Chain ({self.options_feed})",
                        source_uri=f"alpaca://options/{sym}",
                        retrieved_at=now,
                        observed_at=q.timestamp.astimezone(timezone.utc),
                        content_hash=compute_canonical_hash({"symbol": sym, "bid": q.bid_price, "ask": q.ask_price}),
                        data_mode=DataMode.LIVE,
                    )
                    contracts.append(
                        OptionContractSnapshot(
                            symbol=sym,
                            underlying_symbol=contract.underlying_symbol,
                            option_type=option_type,
                            strike=strike,
                            expiration=expiry,
                            bid=float(q.bid_price),
                            ask=float(q.ask_price),
                            quote_time=q.timestamp.astimezone(timezone.utc),
                            volume=volume,
                            open_interest=open_interest,
                            vendor_implied_vol=snap.implied_volatility,
                            vendor_delta=snap.greeks.delta if snap.greeks else None,
                            vendor_gamma=snap.greeks.gamma if snap.greeks else None,
                            vendor_theta=snap.greeks.theta if snap.greeks else None,
                            vendor_vega=snap.greeks.vega if snap.greeks else None,
                            data_feed=self.options_feed,
                            provenance=prov,
                        )
                    )
            self.last_error = None if contracts else "No live option quotes passed metadata and liquidity availability checks."
            return contracts
        except Exception as exc:
            self.last_error = f"Unable to fetch live option chain: {type(exc).__name__}"
            return []
