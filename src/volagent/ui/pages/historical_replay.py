"""Judge-facing, non-executable historical bar replay screen."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

from volagent.clock import NY_TZ
from volagent.config import load_config
from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter
from volagent.domain.enums import DataMode, EventTiming
from volagent.domain.events import EarningsEvent
from volagent.evaluation.historical_bar_replay import (
    HISTORICAL_BAR_PROXY_LABEL,
    AlpacaHistoricalBarReplayAdapter,
    score_bar_proxy_forecast,
)
from volagent.graph.builder import VolAgentWorkflow
from volagent.provenance import Provenance, compute_canonical_hash


def _parse_event_dates(raw_dates: str) -> list[date]:
    if not raw_dates.strip():
        return []
    try:
        return sorted({date.fromisoformat(value.strip()) for value in raw_dates.split(",") if value.strip()})
    except ValueError as exc:
        raise ValueError("Use comma-separated YYYY-MM-DD dates for prior confirmed events.") from exc


def _historical_event(symbol: str, event_time: datetime, cutoff_time: datetime, source_uri: str, exit_time: datetime) -> EarningsEvent:
    provenance = Provenance(
        source_name="Operator-confirmed historical event",
        source_uri=source_uri,
        retrieved_at=datetime.now(timezone.utc),
        observed_at=cutoff_time,
        effective_at=event_time,
        content_hash=compute_canonical_hash(
            {"symbol": symbol, "event_time": event_time.isoformat(), "cutoff_time": cutoff_time.isoformat(), "source_uri": source_uri}
        ),
        data_mode=DataMode.REPLAY_REAL,
    )
    return EarningsEvent(
        event_id=f"HIST-{symbol}-{event_time:%Y%m%d%H%M}",
        symbol=symbol,
        event_time=event_time,
        timing=EventTiming.AFTER_MARKET_CLOSE,
        confirmed=True,
        decision_time=cutoff_time,
        exit_time=exit_time,
        provenance=provenance,
    )


def _render_locked_forecast(record: dict) -> None:
    result = record["result"]
    forecast = result.get("move_forecast")
    underlying = result.get("underlying")
    critic = result.get("critic_report")
    if not forecast or not underlying:
        st.error("The historical snapshot did not produce a complete forecast. It remains a failed, non-executable run.")
        for reason in result.get("rejection_reasons", []):
            st.write(f"- {reason}")
        return
    st.markdown("### Locked pre-event forecast")
    st.caption(f"Digest: `{record['prediction_digest'][:16]}…` · The outcome has not been fetched by this replay run.")
    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Pre-event spot", f"${underlying.price:.2f}")
    metric_b.metric("Market implied move", f"±{forecast.implied_move_pct * 100:.2f}%")
    metric_c.metric("Agent median move", f"±{forecast.median_abs_move_pct * 100:.2f}%")
    metric_d.metric("80% forecast interval", f"{forecast.q20_abs_move_pct * 100:.2f}% – {forecast.q80_abs_move_pct * 100:.2f}%")
    if critic:
        st.caption(f"Model-risk critic: **{critic.status.value.upper()}** · OOD: **{'yes' if forecast.out_of_distribution else 'no'}**")
    st.caption("This screen evaluates the volatility forecast. It never creates an order plan or sends an Alpaca order.")


def _render_outcome(outcome: dict) -> None:
    st.markdown("### Revealed outcome")
    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Realized absolute move", f"±{outcome['realized_abs_move_pct'] * 100:.2f}%")
    metric_b.metric("Agent median error", f"{outcome['forecast_median_abs_error_pct'] * 100:.2f} pp")
    metric_c.metric("Implied-move error", f"{outcome['implied_move_abs_error_pct'] * 100:.2f} pp")
    metric_d.metric("Within agent 80% interval", "YES" if outcome["within_q20_q80_interval"] else "NO")
    premium_change = outcome.get("bar_close_premium_change")
    if premium_change:
        st.warning(f"{premium_change['label']}: ${premium_change['value']:,.2f}")
    else:
        st.info("No paired post-event option bars were available; forecast accuracy was scored without a premium-change proxy.")


def render_historical_replay_page() -> None:
    """Render a generic, two-stage historical forecast and outcome evaluation."""
    st.markdown("## Historical Bar-Proxy Replay")
    st.caption("Forecast with data available before a past event, then reveal the outcome separately. No order submission, no executable-fill claim.")
    st.warning(
        "Method limit: Alpaca historical option bars do not include the historical bid/ask, IV, Greeks, or as-of open interest needed for an execution backtest. "
        "This is a volatility-forecast evaluation only."
    )
    config = load_config()
    if not config.alpaca_api_key or not config.alpaca_secret_key:
        st.error("Alpaca credentials are required to load historical bars.")
        return

    now_ny = datetime.now(NY_TZ)
    controls_a, controls_b, controls_c = st.columns(3)
    with controls_a:
        symbol = st.text_input("Underlying", key="historical_symbol", placeholder="e.g. AAPL", max_chars=6).strip().upper()
        expiry = st.date_input("Option expiration", key="historical_expiry", value=now_ny.date() - timedelta(days=30))
    with controls_b:
        event_date = st.date_input("Past AMC event date", key="historical_event_date", value=now_ny.date() - timedelta(days=90))
        cutoff_clock = st.time_input("Decision cutoff (New York)", key="historical_cutoff_time", value=time(15, 50))
    with controls_c:
        event_clock = st.time_input("Confirmed event time (New York)", key="historical_event_time", value=time(16, 5))
        exit_date = st.date_input("Outcome exit date", key="historical_exit_date", value=now_ny.date() - timedelta(days=89))

    event_source = st.text_input("Historical event source URL", key="historical_source", placeholder="https://investor.example.com/earnings")
    historical_dates = st.text_input(
        "Prior confirmed AMC event dates (optional)",
        key="historical_prior_dates",
        placeholder="YYYY-MM-DD, YYYY-MM-DD, YYYY-MM-DD",
        help="Dates must be before the selected event. Without verified history, the forecast remains explicitly out-of-distribution.",
    )
    analysis_nav = st.number_input("Analytic NAV (risk sizing only; no order)", min_value=1_000.0, value=100_000.0, step=1_000.0)

    if st.button("Lock pre-event forecast", type="primary", width="stretch"):
        try:
            prior_dates = _parse_event_dates(historical_dates)
            cutoff_time = datetime.combine(event_date, cutoff_clock, tzinfo=NY_TZ).astimezone(timezone.utc)
            event_time = datetime.combine(event_date, event_clock, tzinfo=NY_TZ).astimezone(timezone.utc)
            exit_time = datetime.combine(exit_date, time(16, 0), tzinfo=NY_TZ).astimezone(timezone.utc)
            if not symbol.isalpha() or not event_source.startswith(("https://", "http://")):
                raise ValueError("Enter a ticker and a HTTP(S) event source URL.")
            if not cutoff_time < event_time < exit_time:
                raise ValueError("The decision cutoff must precede the event, and the exit must follow the event.")
            if expiry <= event_date:
                raise ValueError("Option expiration must be after the event date.")
            if any(item >= event_date for item in prior_dates):
                raise ValueError("Every prior event date must precede the selected event.")

            adapter = AlpacaHistoricalBarReplayAdapter(config.alpaca_api_key, config.alpaca_secret_key)
            snapshot = adapter.build_snapshot(symbol, cutoff_time, expiry)
            history_reader = AlpacaLiveMarketAdapter(
                config.alpaca_api_key,
                config.alpaca_secret_key,
                stock_feed=config.market_data.stock_feed,
                options_feed=config.market_data.options_feed,
            )
            event = _historical_event(symbol, event_time, cutoff_time, event_source, exit_time)
            proxy_config = config.model_copy(deep=True)
            # These observations have no as-of OI/volume. Setting zero here
            # acknowledges absence; it does not synthesize liquidity evidence.
            proxy_config.contracts = proxy_config.contracts.model_copy(update={"min_volume": 0, "min_open_interest": 0})
            result = VolAgentWorkflow(config=proxy_config).run(
                {
                    "symbol": symbol,
                    "event": event,
                    "underlying": snapshot.underlying,
                    "option_chain": snapshot.option_chain,
                    "historical_moves": history_reader.get_historical_event_moves(symbol, prior_dates, event_date),
                    "evidence": [],
                    "mode": DataMode.REPLAY_REAL,
                    "nav": float(analysis_nav),
                }
            )
            digest = compute_canonical_hash(
                {
                    "event": event.model_dump(mode="json"),
                    "underlying": snapshot.underlying.model_dump(mode="json"),
                    "chain": [contract.model_dump(mode="json") for contract in snapshot.option_chain],
                    "forecast": result.get("move_forecast").model_dump(mode="json") if result.get("move_forecast") else None,
                }
            )
            st.session_state["historical_bar_replay"] = {
                "result": result,
                "adapter": adapter,
                "exit_time": exit_time,
                "limitations": snapshot.limitations,
                "prediction_digest": digest,
            }
            st.session_state.pop("historical_bar_outcome", None)
        except Exception as exc:
            st.error(f"Historical replay was not locked: {exc}")
            return

    record = st.session_state.get("historical_bar_replay")
    if not record:
        return
    st.info(HISTORICAL_BAR_PROXY_LABEL)
    _render_locked_forecast(record)
    with st.expander("Data provenance and limitations"):
        for limitation in record["limitations"]:
            st.write(f"- {limitation}")
        st.json(record["result"].get("trace_events", []))

    if st.button("Reveal post-event outcome and score locked forecast", width="stretch"):
        try:
            result = record["result"]
            symbols = [
                contract.symbol
                for contract in (result.get("feature_set", {}).get("atm_call"), result.get("feature_set", {}).get("atm_put"))
                if contract is not None
            ]
            exit_spot, exit_prices = record["adapter"].exit_prices(result["underlying"].symbol, symbols, record["exit_time"])
            st.session_state["historical_bar_outcome"] = score_bar_proxy_forecast(result, exit_spot, exit_prices)
        except Exception as exc:
            st.error(f"Outcome could not be revealed: {exc}")
    if outcome := st.session_state.get("historical_bar_outcome"):
        _render_outcome(outcome)
