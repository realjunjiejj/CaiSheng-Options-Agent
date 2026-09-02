import json
import html
import streamlit as st

from volagent.competition import read_competition_status
from volagent.config import VolAgentSettings, load_config
from volagent.data.alpaca_mcp import AlpacaMCPService
from volagent.data.alpaca_sdk import AlpacaPortfolioAdapter
from volagent.execution.broker_risk import build_broker_risk_envelope
from volagent.execution.ledger import ExecutionLedger
from volagent.integrations.alpaca_lockbox import run_alpaca_technology_lockbox
from volagent.operator_control import (
    EMERGENCY_CONFIRMATION,
    OperatorController,
)
from volagent.ui.integration_status import (
    run_mcp_read_verification,
    sanitize_preflight_for_judges,
)


def build_competition_judge_summary(
    settings: VolAgentSettings,
    account_id: str | None,
) -> dict[str, object]:
    """Return the minimal, sanitized competition controls a judge needs."""
    status = read_competition_status(
        path=settings.competition.lease_path,
        settings=settings,
        paper_account_id=account_id,
    )
    return {
        "status": status["status"],
        "submission_authorized": status["submission_authorized"],
        "reason": status["reason"],
        "expires_at": status.get("expires_at"),
        "paper_only": settings.execution.paper_only and settings.alpaca_paper_trade,
        "recommended_loss": settings.mandate.competition_initial_nav
        * settings.risk.recommended_risk_nav_pct,
        "hard_loss": settings.mandate.competition_initial_nav
        * settings.risk.hard_max_risk_nav_pct,
        "max_entries_per_day": settings.mandate.max_new_entries_per_day,
        "max_open_strategies": settings.mandate.max_open_strategies,
        "symbols": list(settings.competition.daily_volatility_symbols),
        "scan_window": f"{settings.competition.scan_start_et}–{settings.competition.scan_end_et} ET",
    }


def _render_operator_controls(
    controller: OperatorController,
    *,
    paper_account_id: str | None,
) -> None:
    """Render the private, fail-closed session control surface."""
    operator = controller.status(paper_account_id=paper_account_id)
    lease = operator["lease"]
    heartbeat = operator["heartbeat"]
    armed = bool(lease["submission_authorized"])
    halted = bool(operator["system_halted"])

    if halted:
        state_label = "EMERGENCY HALT — MONITORING ACTIVE"
        state_color = "#DC2626"
    elif armed:
        state_label = "ARMED — AUTONOMOUS ENTRIES AUTHORIZED"
        state_color = "#059669"
    elif lease["status"] == "BLOCKED":
        state_label = "BLOCKED — MONITORING ACTIVE"
        state_color = "#DC2626"
    else:
        state_label = "DISARMED — MONITORING ACTIVE"
        state_color = "#D97706"
    heartbeat_color = "#059669" if heartbeat["monitor_active"] else "#DC2626"
    heartbeat_time = html.escape(str(heartbeat.get("generated_at") or "NO RECEIPT"))
    expiry = html.escape(str(lease.get("expires_at") or "NONE")) if armed else "NONE"
    host_label = "PRIVATE HOST VERIFIED" if operator["host_safe"] else "MUTATIONS BLOCKED"
    host_color = "#0284C7" if operator["host_safe"] else "#DC2626"

    st.markdown(
        f"""<div class="sd-card-dark" style="margin: 0 0 14px 0; border: 1px solid #E2E8F0; border-left: 4px solid {state_color};">
<div style="display:flex; justify-content:space-between; align-items:center; gap:18px; flex-wrap:wrap; margin-bottom:14px;">
<div>
<div style="font-family:'JetBrains Mono',monospace; color:{state_color}; font-size:0.82em; font-weight:800; letter-spacing:0.04em;">● {state_label}</div>
<div style="font-family:'JetBrains Mono',monospace; color:#64748B; font-size:0.72em; margin-top:5px;">HEARTBEAT: <span style="color:{heartbeat_color}; font-weight:700;">{heartbeat_time}</span></div>
</div>
<div style="display:flex; gap:22px; flex-wrap:wrap; font-family:'JetBrains Mono',monospace; font-size:0.75em;">
<div><span style="color:#64748B;">SESSION LEASE</span><br><strong style="color:#0F172A;">{expiry}</strong></div>
<div><span style="color:#64748B;">EXECUTION HOST</span><br><strong style="color:{host_color};">{host_label}</strong></div>
</div>
</div>
<div style="color:#64748B; font-size:0.78em; border-top:1px solid #F1F5F9; padding-top:10px;">
Stop blocks new entries while position monitoring and risk-reducing exits continue. Emergency Halt cancels governed pending entry orders and blocks entries; it does not silently flatten positions.
</div>
</div>""",
        unsafe_allow_html=True,
    )

    c_start, c_scan, c_stop, c_halt = st.columns(4)
    with c_start:
        if st.button(
            "Start Autonomous Session",
            type="primary",
            width="stretch",
            disabled=not operator["can_start"],
        ):
            try:
                with st.spinner("Verifying Alpaca, monitor heartbeat, and risk halt…"):
                    receipt = controller.start_session()
                st.session_state["operator_last_receipt"] = receipt
                st.success("Autonomous paper session armed. No order was submitted by arming.")
                st.rerun()
            except Exception as exc:
                st.error(f"Start blocked: {exc}")
    with c_scan:
        if st.button(
            "Run Live Scan Now",
            width="stretch",
            disabled=not operator["can_scan"],
        ):
            try:
                with st.spinner("Running one live Alpaca scan through the guarded lifecycle…"):
                    receipt = controller.run_live_scan(
                        paper_account_id=paper_account_id
                    )
                st.session_state["operator_last_receipt"] = receipt
                st.success("Live scan completed through the canonical execution gateway.")
            except Exception as exc:
                st.error(f"Live scan blocked or failed: {exc}")
    with c_stop:
        if st.button(
            "Stop New Entries",
            width="stretch",
            disabled=not operator["can_stop"],
        ):
            try:
                receipt = controller.stop_new_entries()
                st.session_state["operator_last_receipt"] = receipt
                st.success("New entries stopped. Existing positions remain monitored.")
                st.rerun()
            except Exception as exc:
                st.error(f"Stop failed closed: {exc}")
    with c_halt:
        if st.button(
            "Emergency Halt",
            width="stretch",
            disabled=halted or not operator["host_safe"],
        ):
            st.session_state["confirm_operator_emergency_halt"] = True

    if st.session_state.get("confirm_operator_emergency_halt"):
        st.error(
            "Emergency Halt permanently blocks new entries and requests cancellation "
            "of governed working entry orders. It does not flatten open positions."
        )
        confirmation = st.text_input(
            f"Type {EMERGENCY_CONFIRMATION} to confirm",
            key="operator_emergency_confirmation",
        )
        confirm_col, cancel_col = st.columns([1, 1])
        with confirm_col:
            if st.button(
                "Confirm Emergency Halt",
                type="primary",
                width="stretch",
                disabled=confirmation != EMERGENCY_CONFIRMATION,
            ):
                try:
                    receipt = controller.emergency_halt(confirmation=confirmation)
                    st.session_state["operator_last_receipt"] = receipt
                    st.session_state["confirm_operator_emergency_halt"] = False
                    st.success("Emergency Halt recorded. Monitoring remains active.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Emergency Halt failed closed: {exc}")
        with cancel_col:
            if st.button("Cancel Emergency Halt", width="stretch"):
                st.session_state["confirm_operator_emergency_halt"] = False
                st.rerun()

    receipts = controller.list_action_receipts(limit=5)
    latest = st.session_state.get("operator_last_receipt") or (receipts[0] if receipts else None)
    latest_label = (
        f"{latest['action']} · {latest['outcome']} · {latest['action_id']}"
        if latest
        else "No operator action recorded"
    )
    with st.expander(f"Operator Audit Receipt · {latest_label}", expanded=False):
        if receipts:
            st.json(receipts)
        else:
            st.info("Start, stop, scan, and emergency actions will create signed receipts here.")


def render_cockpit_page() -> None:
    """Render the authoritative CaiSheng Capital Command Screen."""
    ledger = ExecutionLedger()
    config = load_config()
    competition_config = load_config("config/competition.yaml")
    adapter = AlpacaPortfolioAdapter(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_secret_key,
        paper=config.alpaca_paper_trade,
    )

    # 1. Fetch Metadata and Snapshot
    meta = ledger.get_or_init_competition_metadata(
        starting_nav=competition_config.mandate.competition_initial_nav
    )
    snap = adapter.fetch_portfolio_snapshot(ledger=ledger)
    is_halted, _halt_reason = ledger.is_system_halted()

    start_nav = meta.get("starting_nav", 100_000.0)
    eq = snap.equity
    snapshot_verified = bool(not snap.is_stale and snap.account_id and eq > 0)
    total_pnl = eq - start_nav if snapshot_verified else None
    broker_positions = []
    positions_error = None
    if snapshot_verified:
        try:
            broker_positions = adapter.list_positions()
        except Exception as exc:
            positions_error = f"{type(exc).__name__}: {exc}"

    governed_contracts: set[str] = set()
    for order in ledger.list_open_positions():
        try:
            plan_payload = json.loads(order.get("full_order_plan") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        governed_contracts.update(
            str(leg.get("contract_symbol"))
            for leg in plan_payload.get("legs", [])
            if leg.get("contract_symbol")
        )
    risk_envelope = build_broker_risk_envelope(
        positions=broker_positions,
        governed_contract_symbols=governed_contracts,
        snapshot_verified=snapshot_verified and positions_error is None,
        starting_nav=float(start_nav),
        current_equity=float(eq) if snapshot_verified else None,
        system_halted=is_halted,
        drawdown_halt_pct=competition_config.mandate.drawdown_halt_pct,
        max_contracts=competition_config.risk.max_contracts,
    )
    governed_realized_pnl = sum(
        float(trade.get("net_realized_pnl_dollars") or 0.0)
        for trade in ledger.list_closed_trades()
    )
    reserved_risk, _ = ledger.get_portfolio_reserved_risk()
    max_risk_cap = (
        eq * competition_config.mandate.max_total_reserved_risk_nav_pct
        if snapshot_verified
        else None
    )
    remaining_cap = (
        max(0.0, max_risk_cap - reserved_risk)
        if max_risk_cap is not None
        else None
    )

    if is_halted:
        halt_badge_class = "badge-abstain"
        halt_text = "HALTED"
        connection_text = "System halt is active; inspect ledger receipt"
    elif not snapshot_verified:
        halt_badge_class = "badge-abstain"
        halt_text = "AWAITING PREFLIGHT"
        connection_text = "No verified Alpaca paper account snapshot"
    else:
        halt_badge_class = "badge-long"
        halt_text = "CLEAN / OPERATIONAL"
        connection_text = "Alpaca paper account verified"

    equity_display = f"${eq:,.2f}" if snapshot_verified else "AWAITING"
    pnl_display = f"{total_pnl:+,.2f} Net P&L" if total_pnl is not None else "Run preflight to verify"
    pnl_color = "#059669" if total_pnl is not None and total_pnl >= 0 else "#DC2626"
    remaining_display = (
        f"${remaining_cap:,.2f} Capacity Left"
        if remaining_cap is not None
        else "Awaiting verified NAV"
    )

    # 2. Broker-derived operational state. No fallback account figures are rendered.
    cockpit_html = f"""<div class="sd-card-dark" style="margin-bottom: 24px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
<div>
<div style="font-size: 1.4em; font-weight: 800; color: #0F172A; letter-spacing: -0.02em;">Operations</div>
<div style="color: #64748B; font-size: 0.88em; margin-top: 4px;">Broker state, autonomy controls and deterministic risk limits.</div>
</div>
<span class="pill-badge {halt_badge_class}">{halt_text}</span>
</div>
<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px;">
<div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 18px;">
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72em; font-weight: 700; text-transform: uppercase; color: #64748B; margin-bottom: 4px;">Initial Mandate NAV</div>
<div style="font-family: 'JetBrains Mono', monospace; font-size: 1.5em; font-weight: 800; color: #D97706;">${start_nav:,.2f}</div>
<div style="font-size: 0.75em; color: #64748B; margin-top: 4px;">Fixed Competition Baseline</div>
</div>
<div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 18px;">
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72em; font-weight: 700; text-transform: uppercase; color: #64748B; margin-bottom: 4px;">Current Equity</div>
<div style="font-family: 'JetBrains Mono', monospace; font-size: 1.5em; font-weight: 800; color: #0F172A;">{equity_display}</div>
<div style="font-size: 0.75em; color: {pnl_color}; font-weight: 600; margin-top: 4px;">{pnl_display}</div>
</div>
<div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 18px;">
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72em; font-weight: 700; text-transform: uppercase; color: #64748B; margin-bottom: 4px;">Reserved Risk / 0.5% Cap</div>
<div style="font-family: 'JetBrains Mono', monospace; font-size: 1.5em; font-weight: 800; color: #0284C7;">${reserved_risk:,.2f}</div>
<div style="font-size: 0.75em; color: #64748B; margin-top: 4px;">{remaining_display}</div>
</div>
<div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 18px;">
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72em; font-weight: 700; text-transform: uppercase; color: #64748B; margin-bottom: 4px;">Circuit Breaker Status</div>
<div style="font-family: 'JetBrains Mono', monospace; font-size: 1.3em; font-weight: 800; color: {'#DC2626' if is_halted else '#059669'};">{halt_text}</div>
<div style="font-size: 0.75em; color: #64748B; margin-top: 4px;">{connection_text}</div>
</div>
</div>
</div>"""
    st.markdown(cockpit_html, unsafe_allow_html=True)

    competition = build_competition_judge_summary(
        competition_config,
        snap.account_id if snapshot_verified else None,
    )
    auth_status = str(competition["status"])
    auth_color = "#059669" if auth_status == "ARMED" else "#DC2626"
    auth_label = "AUTONOMY ARMED" if auth_status == "ARMED" else f"AUTONOMY {auth_status}"
    symbols = " · ".join(str(symbol) for symbol in competition["symbols"])
    expiry = html.escape(str(competition["expires_at"] or "ARM VIA CLI BEFORE THE SESSION"))
    reason = html.escape(str(competition["reason"]))
    competition_html = f"""<div style="border: 1px solid #E2E8F0; background: #FFFFFF; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); padding: 16px 20px; margin: -8px 0 20px 0;">
<div style="display:flex; justify-content:space-between; gap:16px; align-items:center; flex-wrap:wrap;">
<div>
<div style="font-family:'JetBrains Mono',monospace; color:{auth_color}; font-weight:800; font-size:0.82em;">{auth_label} · PAPER ONLY</div>
<div style="color:#64748B; font-size:0.78em; margin-top:3px;">{reason} · Expires {expiry}</div>
</div>
<div style="display:flex; gap:22px; flex-wrap:wrap; font-family:'JetBrains Mono',monospace;">
<div><span style="color:#64748B;font-size:0.67em;">RISK / TRADE</span><br><strong style="color:#D97706;">${competition['recommended_loss']:.0f} target · ${competition['hard_loss']:.0f} hard</strong></div>
<div><span style="color:#64748B;font-size:0.67em;">FREQUENCY</span><br><strong style="color:#0F172A;">≤ {competition['max_entries_per_day']} entry/day · {competition['max_open_strategies']} open</strong></div>
<div><span style="color:#64748B;font-size:0.67em;">DAILY VOL UNIVERSE</span><br><strong style="color:#0F172A;">{symbols} · {competition['scan_window']}</strong></div>
</div>
</div>
</div>"""
    st.markdown(competition_html, unsafe_allow_html=True)

    operator_controller = OperatorController(
        settings=competition_config,
        ledger=ledger,
        portfolio_adapter=adapter,
    )
    _render_operator_controls(
        operator_controller,
        paper_account_id=snap.account_id if snapshot_verified else None,
    )

    # 3. Alpaca integration checks and operational receipts
    st.markdown("""<div style="font-size: 1.2em; font-weight: 800; color: #0F172A; margin: 24px 0 12px 0;">
Alpaca integration checks
</div>""", unsafe_allow_html=True)

    st.caption(
        "CaiSheng-generated verification—not an Alpaca product. Checks the CLI, "
        "MCP Server V2 and paper-only order boundary."
    )
    if st.button("Run Alpaca integration checks", type="primary", width="stretch"):
        with st.spinner("Running official CLI diagnostics and MCP V2 discovery…"):
            st.session_state["alpaca_lockbox_receipt"] = run_alpaca_technology_lockbox(
                config
            )

    lockbox = st.session_state.get("alpaca_lockbox_receipt")
    if lockbox:
        components = lockbox.get("components") or {}
        lock_cols = st.columns(4)
        labels = (
            ("Official CLI", components.get("official_cli", {}).get("status")),
            ("Official MCP V2", components.get("official_mcp_v2", {}).get("status")),
            ("Official Skills", components.get("official_skills", {}).get("status")),
            ("Order Boundary", "LOCKED" if lockbox.get("paper_only") else "FAIL"),
        )
        for column, (label, status) in zip(lock_cols, labels, strict=True):
            column.metric(label, status or "FAIL")
        if lockbox.get("overall_status") == "PASS":
            st.success(
                "Official Alpaca CLI, MCP V2, and skills verified; sponsor interfaces "
                "remain read-only and paper-only."
            )
        else:
            st.error("Alpaca integration checks failed closed. Inspect the receipt.")
        with st.expander("Inspect sanitized verification receipt", expanded=False):
            st.json(lockbox)

    st.markdown("""<div style="font-size: 1.05em; font-weight: 800; color: #0F172A; margin: 20px 0 10px 0;">
Execution diagnostics
</div>""", unsafe_allow_html=True)

    c_pref, c_rec, c_mcp, c_audit = st.columns(4)
    with c_pref:
        if st.button("Run CaiSheng Preflight", width="stretch"):
            from volagent.cli.preflight import run_cli_preflight
            pref = run_cli_preflight(ledger=ledger, portfolio_adapter=adapter)
            st.json(sanitize_preflight_for_judges(pref))
    with c_rec:
        if st.button("Reconcile Alpaca", width="stretch"):
            from volagent.cli.reconcile import run_cli_reconciliation
            rec = run_cli_reconciliation(ledger=ledger)
            st.json(rec)
    with c_mcp:
        if st.button("Verify Guarded MCP", width="stretch"):
            service = AlpacaMCPService(
                portfolio_adapter=adapter,
                ledger=ledger,
                settings=config,
            )
            proof = run_mcp_read_verification(service)
            if proof["overall_status"] == "PASS":
                st.success("MCP account and market-clock tools verified.")
            else:
                st.error("MCP read verification failed closed.")
            st.json(proof)
    with c_audit:
        if st.button("View Gateway Audit", width="stretch"):
            mcp_events = ledger.list_mcp_audit_events()
            st.write(f"Total MCP Invocations: {len(mcp_events)}")
            safe_events = [
                {
                    "event_id": event.get("event_id"),
                    "tool_name": event.get("tool_name"),
                    "decision_id": event.get("decision_id"),
                    "result_status": event.get("result_status"),
                    "called_at": event.get("called_at"),
                }
                for event in mcp_events
            ]
            st.json(safe_events)

    mode_color = {
        "NORMAL": "#059669",
        "LIQUIDATE_ONLY": "#DC2626",
        "UNVERIFIED": "#D97706",
    }[risk_envelope.mode]
    account_pnl_display = (
        f"${risk_envelope.full_account_net_pnl:+,.2f}"
        if risk_envelope.full_account_net_pnl is not None
        else "UNVERIFIED"
    )
    provenance_display = (
        f"{risk_envelope.governed_position_legs}/{risk_envelope.broker_position_legs} governed"
    )
    underlyings_display = " · ".join(risk_envelope.underlying_symbols) or "NONE"
    st.markdown(f"""<div style="font-size: 1.15em; font-weight: 800; color: #0F172A; margin: 24px 0 10px 0;">
Broker risk envelope
</div>
<div style="border:1px solid #E2E8F0; border-left:4px solid {mode_color}; background:#FFFFFF; border-radius:12px; box-shadow:0 1px 3px rgba(0,0,0,0.04); padding:18px 22px;">
<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(165px,1fr)); gap:14px; font-family:'JetBrains Mono',monospace;">
<div><span style="color:#64748B;font-size:.70em;">ENTRY MODE</span><br><strong style="font-size:1.15em;color:{mode_color};">{risk_envelope.mode}</strong></div>
<div><span style="color:#64748B;font-size:.70em;">FULL ALPACA ACCOUNT P&amp;L</span><br><strong style="font-size:1.15em;color:#0F172A;">{account_pnl_display}</strong></div>
<div><span style="color:#64748B;font-size:.70em;">GOVERNED CLOSED-TRADE P&amp;L</span><br><strong style="font-size:1.15em;color:#0F172A;">${governed_realized_pnl:+,.2f}</strong></div>
<div><span style="color:#64748B;font-size:.70em;">EXPOSURE PROVENANCE</span><br><strong style="font-size:1.15em;color:#0F172A;">{provenance_display}</strong></div>
<div><span style="color:#64748B;font-size:.70em;">GROSS MARKED EXPOSURE</span><br><strong style="font-size:1.15em;color:#0F172A;">${risk_envelope.gross_marked_exposure:,.2f}</strong></div>
</div>
<div style="margin-top:12px;color:#64748B;font-size:.80em;border-top:1px solid #F1F5F9;padding-top:8px;">Underlyings: {html.escape(underlyings_display)} · Broker legs: {risk_envelope.broker_position_legs} · Maximum quantity: {risk_envelope.max_abs_contract_quantity} · Unrealized P&amp;L: ${risk_envelope.unrealized_pnl:+,.2f}</div>
</div>""", unsafe_allow_html=True)
    if risk_envelope.orphan_position_legs:
        st.error(
            f"{risk_envelope.orphan_position_legs} broker position legs have no canonical "
            "CaiSheng order intent or decision receipt. No agent rationale is claimed for "
            "them. Autonomous entries are blocked; risk-reducing exits remain permitted."
        )
    elif risk_envelope.mode == "NORMAL":
        st.success("Every open broker leg is tied to the canonical gateway and ledger.")
    elif risk_envelope.mode == "LIQUIDATE_ONLY":
        st.warning(
            "System halt is active. New entries are blocked; position monitoring "
            "and risk-reducing exits remain enabled."
        )
    else:
        st.warning("Broker state is not verified. CaiSheng refuses new entries.")
    if risk_envelope.violations or positions_error:
        with st.expander("Inspect Risk Envelope violations", expanded=False):
            st.json(
                {
                    "violations": risk_envelope.violations,
                    "broker_positions_error": positions_error,
                    "untracked_contract_symbols": risk_envelope.orphan_contract_symbols,
                }
            )

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)


    # 4. Two Columns: Decision Timeline & Closed Trade Accounting
    c_dec, c_trades = st.columns(2)

    with c_dec:
        st.markdown("""<div style="font-size: 1.1em; font-weight: 800; color: #0F172A; margin-bottom: 10px;">
Decision records · caisheng.decision.v1
</div>""", unsafe_allow_html=True)
        decisions = ledger.list_decision_records()
        if not decisions:
            st.info("No decision records generated yet. Run a candidate scan from the Pro Desk.")
        else:
            for d in decisions[:5]:
                try:
                    decision_payload = json.loads(d.get("raw_payload") or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    decision_payload = {}
                decision_mode = str(decision_payload.get("mode") or "unknown").upper()
                with st.expander(
                    f"{d.get('decision_id')} · {d.get('symbol')} "
                    f"[{d.get('selected_action')}] · {decision_mode}",
                    expanded=False,
                ):
                    st.write(f"**Generated At:** {d.get('generated_at')}")
                    st.write(f"**SHA-256 Hash:** `{d.get('artifact_hash')}`")
                    st.write(f"**Status:** `{d.get('status')}` | **Quantity:** `{d.get('quantity')}`")
                    if decision_payload:
                        st.json(decision_payload)

    with c_trades:
        st.markdown("""<div style="font-size: 1.1em; font-weight: 800; color: #0F172A; margin-bottom: 10px;">
Closed trades
</div>""", unsafe_allow_html=True)
        closed = ledger.list_closed_trades()
        if not closed:
            st.info("No closed trades recorded yet.")
        else:
            for t in closed[:5]:
                pnl = t.get("net_realized_pnl_dollars", 0.0)
                pnl_color = "green" if pnl >= 0 else "red"
                with st.expander(f"{t.get('trade_id')} · {t.get('symbol')} [{t.get('decision')}]: :{pnl_color}[${pnl:+,.2f}]"):
                    st.write(f"**Outcome:** `{t.get('outcome_label')}` | **Return on Risk:** `{t.get('realized_return_pct')*100:.1f}%`")
                    st.write(f"**Holding Duration:** `{t.get('holding_hours'):.1f} hours`")
                    st.write(f"**Fees & Slippage:** `${t.get('fees_and_slippage'):.2f}`")
                    st.write(f"**Post-Event Move:** `{t.get('actual_post_event_move')*100:.1f}%` vs Expected `{t.get('pre_event_expected_move')*100:.1f}%`")

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    # 5. Shadow-Book Counterfactual Comparison
    st.markdown("""<div style="font-size: 1.1em; font-weight: 800; color: #0F172A; margin-bottom: 10px;">
Benchmark outcomes
</div>""", unsafe_allow_html=True)
    shadow_records = ledger.list_shadow_book_records()
    if not shadow_records:
        st.info("No shadow book evaluations recorded yet.")
    else:
        st.dataframe(shadow_records, width="stretch")
