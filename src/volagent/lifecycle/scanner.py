"""Confirmed Event Scanner with Typed Source Contract and Entry Window Cutoff."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from volagent.domain.enums import DataMode, EventTiming, OpportunityKind
from volagent.domain.events import EarningsEvent
from volagent.provenance import Provenance, compute_canonical_hash

DEFAULT_UNIVERSE: list[str] = ["NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "GOOGL", "META"]
ET_TZ = ZoneInfo("America/New_York")


class EventScanner:
    """Scans configured universe for confirmed upcoming AMC earnings events."""

    def __init__(
        self,
        universe: list[str] | None = None,
        entry_window_minutes_before_close: int = 45,
        entry_cutoff_minutes_before_close: int = 5,
        daily_volatility_symbols: list[str] | None = None,
        daily_scan_start_et: str = "10:15",
        daily_scan_end_et: str = "14:30",
        trading_client: Any | None = None,
    ):
        self.universe = [s.upper() for s in (universe or DEFAULT_UNIVERSE)]
        self.entry_window_minutes_before_close = entry_window_minutes_before_close
        self.entry_cutoff_minutes_before_close = entry_cutoff_minutes_before_close
        self.daily_volatility_symbols = [
            symbol.upper() for symbol in (daily_volatility_symbols or ["SPY", "QQQ", "IWM"])
        ]
        self.daily_scan_start_et = time.fromisoformat(daily_scan_start_et)
        self.daily_scan_end_et = time.fromisoformat(daily_scan_end_et)
        self.trading_client = trading_client

    def scan_daily_volatility_opportunities(
        self,
        current_time: datetime | None = None,
    ) -> list[EarningsEvent]:
        """Create one stable, market-data-backed volatility opportunity per liquid ETF and day."""
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_et = now.astimezone(ET_TZ)
        if not self.is_market_open(now):
            return []
        if not (self.daily_scan_start_et <= now_et.time().replace(tzinfo=None) <= self.daily_scan_end_et):
            return []

        if self.trading_client:
            try:
                future_sessions = self._broker_sessions(now_et.date() + timedelta(days=1), now_et.date() + timedelta(days=10))
                if not future_sessions:
                    return []
                next_session_date = self._session_datetime(future_sessions[0], "open").date()
            except Exception:
                return []
        else:
            next_session_date = now_et.date() + timedelta(days=1)
            while next_session_date.weekday() >= 5:
                next_session_date += timedelta(days=1)

        exit_time = datetime.combine(next_session_date, time(15, 15), tzinfo=ET_TZ).astimezone(timezone.utc)
        opportunities: list[EarningsEvent] = []
        for symbol in self.daily_volatility_symbols:
            declaration = {
                "symbol": symbol,
                "session": now_et.date().isoformat(),
                "policy": "daily_liquid_etf_volatility_v1",
                "window": f"{self.daily_scan_start_et.isoformat()}-{self.daily_scan_end_et.isoformat()}",
            }
            provenance = Provenance(
                source_name="Alpaca market session + CaiSheng competition policy",
                source_uri="https://paper-api.alpaca.markets/v2/clock",
                retrieved_at=now,
                observed_at=now,
                effective_at=now,
                content_hash=compute_canonical_hash(declaration),
                data_mode=DataMode.LIVE,
            )
            opportunities.append(EarningsEvent(
                event_id=f"daily-vol-{now_et.date().isoformat()}-{symbol}",
                symbol=symbol,
                event_type="scheduled_volatility",
                opportunity_kind=OpportunityKind.DAILY_VOLATILITY,
                event_time=now,
                timing=EventTiming.DURING_MARKET_HOURS,
                confirmed=True,
                decision_time=now,
                exit_time=exit_time,
                provenance=provenance,
            ))
        return opportunities

    def _broker_sessions(self, start: date, end: date) -> list[Any]:
        """Return authoritative Alpaca sessions when a trading client is available."""
        if not self.trading_client:
            return []
        try:
            from alpaca.trading.requests import GetCalendarRequest
            request = GetCalendarRequest(start=start, end=end)
        except ImportError:
            # Keeps the calendar contract injectable in lightweight tests; a
            # real Alpaca client still receives the official SDK request.
            from types import SimpleNamespace
            request = SimpleNamespace(start=start, end=end)
        sessions = self.trading_client.get_calendar(request)
        return list(sessions or [])

    @staticmethod
    def _session_datetime(session: Any, field: str) -> datetime:
        value = getattr(session, field)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=ET_TZ)
        session_date = getattr(session, "date")
        if isinstance(session_date, str):
            session_date = date.fromisoformat(session_date)
        session_time = value if isinstance(value, time) else time.fromisoformat(str(value))
        return datetime.combine(session_date, session_time, tzinfo=ET_TZ)

    def is_market_open(self, current_time: datetime | None = None) -> bool:
        """Verify regular-hours market session is active (09:30 - 16:00 ET Monday-Friday)."""
        now = current_time or datetime.now(timezone.utc)
        now_et = now.astimezone(ET_TZ)
        if self.trading_client:
            try:
                sessions = self._broker_sessions(now_et.date(), now_et.date())
                if not sessions:
                    return False
                market_open = self._session_datetime(sessions[0], "open").astimezone(ET_TZ)
                market_close = self._session_datetime(sessions[0], "close").astimezone(ET_TZ)
                return market_open <= now_et <= market_close
            except Exception:
                # A live calendar lookup failure is not permission to assume a
                # regular session. Fail closed.
                return False
        if now_et.weekday() >= 5:
            return False
        return time(9, 30) <= now_et.time() <= time(16, 0)

    def is_inside_entry_window(self, event_date: date, current_time: datetime | None = None) -> bool:
        """Verify current time is within permitted entry window (e.g. 15:15 - 15:55 ET on event day)."""
        now = current_time or datetime.now(timezone.utc)
        now_et = now.astimezone(ET_TZ)
        if now_et.date() != event_date:
            return False
        if not self.is_market_open(now):
            return False

        close_minutes = 16 * 60
        if self.trading_client:
            try:
                sessions = self._broker_sessions(event_date, event_date)
                if not sessions:
                    return False
                close_et = self._session_datetime(sessions[0], "close").astimezone(ET_TZ)
                close_minutes = close_et.hour * 60 + close_et.minute
            except Exception:
                return False
        start_minute = close_minutes - self.entry_window_minutes_before_close
        cutoff_minute = close_minutes - self.entry_cutoff_minutes_before_close

        now_minutes = now_et.hour * 60 + now_et.minute
        return start_minute <= now_minutes <= cutoff_minute

    def scan_eligible_events(
        self,
        known_calendar: dict[str, dict[str, Any]],
        current_time: datetime | None = None,
    ) -> list[EarningsEvent]:
        """Scan candidate calendar and return confirmed AMC events inside the entry window."""
        now = current_time or datetime.now(timezone.utc)
        now_et = now.astimezone(ET_TZ)
        eligible_events: list[EarningsEvent] = []

        cal_by_symbol: dict[str, dict[str, Any]] = {}
        if isinstance(known_calendar, dict):
            if "earnings_calendar" in known_calendar and isinstance(known_calendar["earnings_calendar"], list):
                for item in known_calendar["earnings_calendar"]:
                    sym = str(item.get("symbol", "")).upper()
                    if sym:
                        cal_by_symbol[sym] = item
            else:
                cal_by_symbol = {str(k).upper(): v for k, v in known_calendar.items() if isinstance(v, dict)}
        elif isinstance(known_calendar, list):
            for item in known_calendar:
                sym = str(item.get("symbol", "")).upper()
                if sym:
                    cal_by_symbol[sym] = item

        for symbol in self.universe:
            info = cal_by_symbol.get(symbol)
            if not info:
                continue

            event_date = info.get("event_date") or info.get("earnings_date")
            if isinstance(event_date, str):
                event_date = date.fromisoformat(event_date)
            elif not isinstance(event_date, date):
                continue

            # Strict entry window enforcement
            if not self.is_inside_entry_window(event_date, now):
                continue

            timing_str = str(info.get("timing") or info.get("earnings_time") or "amc").lower()
            if timing_str != "amc":
                continue


            confirmed = bool(info.get("confirmed", False))
            if not confirmed:
                continue

            source_url = str(info.get("source_url") or "").strip()
            if not source_url or not (source_url.startswith("http://") or source_url.startswith("https://")):
                continue



            event_id = f"evt-{event_date.isoformat()}-{symbol}"

            prov = Provenance(
                source_name="Official Earnings Calendar",
                source_uri=source_url,
                retrieved_at=now,
                observed_at=now,
                content_hash=compute_canonical_hash({"symbol": symbol, "date": event_date.isoformat(), "timing": "amc"}),
                data_mode=DataMode.LIVE,
            )

            if self.trading_client:
                try:
                    event_sessions = self._broker_sessions(event_date, event_date)
                    next_sessions = self._broker_sessions(
                        event_date + timedelta(days=1), event_date + timedelta(days=10)
                    )
                    if not event_sessions or not next_sessions:
                        continue
                    event_close = self._session_datetime(event_sessions[0], "close")
                    next_session_date = self._session_datetime(next_sessions[0], "open").date()
                except Exception:
                    continue
            else:
                # Deterministic replay fallback; live mode injects the Alpaca
                # client and therefore uses exchange holidays/early closes.
                days_ahead = 3 if event_date.weekday() == 4 else 1
                next_session_date = event_date + timedelta(days=days_ahead)
                event_close = datetime.combine(event_date, time(16, 0), tzinfo=ET_TZ)

            event_dt = event_close.astimezone(timezone.utc)
            exit_dt = datetime.combine(next_session_date, time(9, 35), tzinfo=ET_TZ).astimezone(timezone.utc)

            event = EarningsEvent(
                event_id=event_id,
                symbol=symbol,
                event_date=event_date,
                event_time=event_dt,
                timing=EventTiming.AFTER_MARKET_CLOSE,
                opportunity_kind=OpportunityKind.EARNINGS_EVENT,
                confirmed=True,
                source_url=source_url,
                decision_time=now,
                exit_time=exit_dt,
                provenance=prov,
            )

            eligible_events.append(event)

        return eligible_events
