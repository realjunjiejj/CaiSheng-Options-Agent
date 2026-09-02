"""Operator-controlled live-data paper-trading canary for CaiSheng."""

from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

from volagent.clock import NY_TZ
from volagent.config import load_config
from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter
from volagent.domain.enums import BrokerTarget, DataMode, Decision, EventTiming, GateStatus
from volagent.domain.events import EarningsEvent
from volagent.execution.alpaca import AlpacaPaperBroker, build_order_plan
from volagent.execution.ledger import ExecutionLedger
from volagent.evaluation.live_outcomes import evaluate_live_forecast, list_live_forecasts, record_live_forecast
from volagent.graph.builder import VolAgentWorkflow
from volagent.provenance import Provenance, compute_canonical_hash


def _build_confirmed_event(symbol: str, event_time: datetime, source_uri: str) -> EarningsEvent:
    """Build an auditable, manually confirmed AMC event for a live canary run."""
    now = datetime.now(timezone.utc)
    payload = {"symbol": symbol, "event_time": event_time.isoformat(), "source_uri": source_uri}
    provenance = Provenance(
        source_name="Operator-confirmed live event",
        source_uri=source_uri,
        retrieved_at=now,
        observed_at=now,
        effective_at=event_time,
        content_hash=compute_canonical_hash(payload),
        data_mode=DataMode.LIVE,
    )
    return EarningsEvent(
        event_id=f"LIVE-{symbol}-{event_time:%Y%m%d%H%M}",
        symbol=symbol,
        fiscal_period=None,
        event_time=event_time,
        timing=EventTiming.AFTER_MARKET_CLOSE,
        confirmed=True,
        decision_time=now,
        exit_time=event_time + timedelta(days=1),
        provenance=provenance,
    )


def _parse_verified_event_dates(raw_dates: str) -> list[date]:
    """Parse user-confirmed prior event dates without coupling the agent to a ticker."""
    if not raw_dates.strip():
        return []
    try:
        return sorted({date.fromisoformat(value.strip()) for value in raw_dates.split(",") if value.strip()})
    except ValueError as exc:
        raise ValueError("Use comma-separated YYYY-MM-DD dates for prior confirmed events.") from exc


def _render_outcome_evaluator(config) -> None:
    """Render post-event scoring for every sealed live forecast, including NO_TRADE."""
    st.markdown("### Post-event forecast score")
    records = list_live_forecasts()
    if not records:
        st.caption("A complete live forecast is sealed before its event and becomes scoreable after its declared exit time.")
        return
    labels = {
        record["event"]["event_id"]: f"{record['event']['symbol']} · {record['event']['event_id']} · {record['recorded_at']}"
        for record in records
    }
    selected_event_id = st.selectbox("Sealed forecast", list(labels), format_func=labels.get)
    selected = next(record for record in records if record["event"]["event_id"] == selected_event_id)
    exit_time = datetime.fromisoformat(selected["event"]["exit_time"]).astimezone(timezone.utc)
    if datetime.now(timezone.utc) < exit_time:
        st.info(f"Outcome scoring unlocks after {exit_time.isoformat()}. The pre-event artifact is already sealed.")
        return
    if st.button("Fetch post-event data and score forecast", width="stretch"):
        event = selected["event"]
        adapter = AlpacaLiveMarketAdapter(
            config.alpaca_api_key,
            config.alpaca_secret_key,
            stock_feed=config.market_data.stock_feed,
            options_feed=config.market_data.options_feed,
        )
        exit_underlying = adapter.get_underlying_snapshot(event["symbol"])
        exit_chain = adapter.get_option_chain(
            event["symbol"],
            datetime.fromisoformat(event["event_time"]).date(),
            datetime.fromisoformat(event["event_time"]).date() + timedelta(days=config.contracts.max_dte_days),
            exit_underlying.price if exit_underlying else None,
        )
        try:
            if not exit_underlying:
                raise ValueError(adapter.last_error or "No valid post-event underlying quote.")
            outcome = evaluate_live_forecast(selected_event_id, exit_underlying, exit_chain)
            st.success("Post-event score recorded with fresh Alpaca data.")
            st.json(outcome)
        except Exception as exc:
            st.error(f"Outcome was not scored: {exc}")


def render_live_canary_page() -> None:
    """Render a live-only evaluation path that fails closed before any paper order."""
    st.markdown("## Live Paper Canary")
    st.caption("Fresh Alpaca market data only · one-unit maximum · no replay contracts · manual event confirmation required")

    config = load_config()
    if not config.alpaca_api_key or not config.alpaca_secret_key:
        st.error("Alpaca paper credentials are missing from .env. Live canary is unavailable.")
        return

    if config.execution.allow_order_submission:
        st.warning("Paper-order submission is enabled. A final order still requires an approved plan and an explicit checkbox below.")
    else:
        st.info("Paper-order submission is disabled by the kill switch. You can run the full live analysis safely, but cannot submit an order.")

    now_ny = datetime.now(NY_TZ)
    input_col, event_col = st.columns([1, 2])
    with input_col:
        symbol = st.text_input("Underlying", placeholder="e.g. AAPL", max_chars=6).strip().upper()
    with event_col:
        source_uri = st.text_input("Confirmed-event source URL", placeholder="https://investor.example.com/earnings")

    historical_dates = st.text_input(
        "Prior confirmed AMC event dates (optional)",
        placeholder="YYYY-MM-DD, YYYY-MM-DD, YYYY-MM-DD",
        help="Provide verified prior event dates for this ticker. Without them, the agent remains out-of-distribution and will not trade.",
    )

    date_col, time_col, confirm_col = st.columns([1, 1, 1])
    with date_col:
        event_date = st.date_input("Event date (New York)", value=now_ny.date() + timedelta(days=7))
    with time_col:
        event_clock = st.time_input("Event time (New York)", value=time(16, 5))
    with confirm_col:
        st.markdown("<br>", unsafe_allow_html=True)
        confirmed = st.checkbox("I verified this is a confirmed AMC event")

    run_canary = st.button("Run live canary — no order", type="primary", width="stretch")
    if run_canary:
        event_time = datetime.combine(event_date, event_clock, tzinfo=NY_TZ).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        try:
            historical_event_dates = _parse_verified_event_dates(historical_dates)
        except ValueError as exc:
            st.error(str(exc))
            return
        if not symbol.isalpha() or not source_uri.startswith(("https://", "http://")) or not confirmed:
            st.error("Enter a ticker, an HTTPS/HTTP event source, and confirm the AMC event before running.")
            return
        if event_time <= now:
            st.error("The live canary requires an event timestamp in the future.")
            return

        adapter = AlpacaLiveMarketAdapter(
            config.alpaca_api_key,
            config.alpaca_secret_key,
            stock_feed=config.market_data.stock_feed,
            options_feed=config.market_data.options_feed,
        )
        equity = adapter.get_paper_account_equity()
        if equity is None:
            st.error(adapter.last_error or "Could not read paper-account equity.")
            return

        event = _build_confirmed_event(symbol, event_time, source_uri)
        result = VolAgentWorkflow(config=config).run(
            {
                "symbol": symbol,
                "event": event,
                "evidence": [],
                "mode": DataMode.LIVE,
                "nav": equity,
                "paper_canary": True,
                "live_market_adapter": adapter,
                "historical_event_dates": historical_event_dates,
            }
        )
        st.session_state["live_canary_result"] = result
        try:
            record_live_forecast(result, config.execution)
        except ValueError:
            # Incomplete fail-closed runs have no forecast to score later.
            pass
        st.session_state.pop("live_canary_plan", None)
        st.session_state.pop("live_canary_approved", None)

    result = st.session_state.get("live_canary_result")
    if not result:
        return

    decision = result.get("final_decision", Decision.NO_TRADE)
    risk_report = result.get("risk_report")
    underlying = result.get("underlying")
    candidate = result.get("approved_candidate")
    decision_record = result.get("decision_record")
    runtime = getattr(decision_record, "agent_runtime", None)
    snapshot = getattr(decision_record, "snapshot", None)

    status_col, data_col, agent_col, risk_col = st.columns(4)
    with status_col:
        st.metric("Decision", decision.value.replace("_", " ").upper())
    with data_col:
        feed_label = getattr(snapshot, "options_feed", "unknown").upper()
        st.metric("Alpaca options feed", feed_label if underlying else "REJECTED")
    with agent_col:
        st.metric(
            "Agent runtime",
            getattr(runtime, "mode", "unverified").replace("_", " ").upper(),
        )
    with risk_col:
        risk_status = risk_report.overall_status.value.upper() if risk_report else "FAIL"
        st.metric("Risk governor", risk_status)

    if not candidate or not risk_report or risk_report.overall_status != GateStatus.PASS:
        st.error("No paper order is eligible. The live canary failed closed.")
        for reason in result.get("rejection_reasons", []):
            st.write(f"- {reason}")
        with st.expander("Live trace"):
            st.json(result.get("trace_events", []))
        _render_outcome_evaluator(config)
        return

    if candidate.quantity != 1:
        st.error("Canary safety invariant failed: candidate quantity is not exactly one. No order can be created.")
        return

    if "live_canary_ledger" not in st.session_state:
        st.session_state["live_canary_ledger"] = ExecutionLedger()
    ledger = st.session_state["live_canary_ledger"]
    if "live_canary_plan" not in st.session_state:
        snapshots = {contract.symbol: contract for contract in result.get("option_chain", [])}
        try:
            st.session_state["live_canary_plan"] = build_order_plan(
                candidate,
                broker_target=BrokerTarget.ALPACA_PAPER,
                ledger=ledger,
                contract_snapshots=snapshots,
            )
        except Exception as exc:
            st.error(f"Could not build an immutable live order plan: {exc}")
            return

    plan = st.session_state["live_canary_plan"]
    st.success(f"Eligible one-unit canary plan: {plan.decision.replace('_', ' ').upper()} · limit ${plan.limit_price:.2f}")
    st.caption(f"Contracts: {', '.join(leg.contract_symbol for leg in plan.legs)}")

    reviewed = st.checkbox("I reviewed the live contracts, limit price, maximum loss, and the one-unit paper-only scope.")
    approve_col, submit_col = st.columns(2)
    with approve_col:
        if st.button("Approve immutable plan", disabled=not reviewed, width="stretch"):
            ledger.approve_order(plan.approval_token)
            st.session_state["live_canary_approved"] = plan.approval_token
            st.success("Immutable plan approved. Quotes must remain fresh at submission.")
    with submit_col:
        approved = st.session_state.get("live_canary_approved") == plan.approval_token
        if st.button(
            "Submit one-unit paper order",
            disabled=not (approved and reviewed and config.execution.allow_order_submission),
            width="stretch",
        ):
            try:
                receipt = AlpacaPaperBroker(config.alpaca_api_key, config.alpaca_secret_key, ledger).submit_paper_order(plan)
                st.success(f"Paper order accepted: {receipt.broker_order_id}")
                st.json(receipt.model_dump(mode="json"))
            except Exception as exc:
                st.error(f"Paper order was not submitted: {exc}")

    with st.expander("Live trace and risk receipt"):
        st.json({"trace": result.get("trace_events", []), "risk": risk_report.model_dump(mode="json")})

    _render_outcome_evaluator(config)
