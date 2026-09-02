"""CaiSheng: Alpaca Pro High-Contrast Volatility Trading Desk."""

import json
import html
import os
from pathlib import Path
import tempfile
import uuid

import streamlit as st

from volagent.config import load_config
from volagent.domain.enums import BrokerTarget, Decision
from volagent.domain.execution import OrderPlan
from volagent.errors import ExecutionError
from volagent.execution.alpaca import SimulatedPaperBroker, build_order_plan
from volagent.execution.ledger import ExecutionLedger
from volagent.graph.builder import VolAgentWorkflow
from volagent.ui.charts import create_payoff_plot
from volagent.ui.integration_status import judge_workspaces
from volagent.ui.pages.cockpit import render_cockpit_page
from volagent.ui.pages.live_canary import render_live_canary_page
from volagent.ui.pages.scoreboard import render_scoreboard_page
from volagent.ui.theme import CUSTOM_CSS


# Configure Streamlit page
st.set_page_config(
    page_title="Alpaca / CaiSheng — Autonomous Options Alpha",
    page_icon="🦙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Inject Superdesign Full-Bleed Theme
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def main() -> None:
    public_judge_mode = os.environ.get("CAISHENG_PUBLIC_JUDGE_MODE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    workspaces = judge_workspaces(public_read_only=public_judge_mode)

    # Institutional Alpaca Partner Header (Zero Consumer Fluff)
    st.markdown(
        """<div class="cs-judge-header">
<div class="cs-header-left">
    <div class="cs-llama-badge">🦙</div>
    <div>
        <div class="cs-eyebrow">
            <span>ALPACA OPTIONS ALPHA · TRACK 02</span>
            <span style="background:#F1F5F9; color:#475569; padding:2px 8px; border-radius:9999px; border:1px solid #E2E8F0; font-size:0.68rem;">caisheng-1.0.0</span>
        </div>
        <div class="cs-title">CaiSheng Options Alpha Desk</div>
        <div class="cs-subtitle">Autonomous opportunity selection, defined-risk execution, and auditable broker evidence.</div>
    </div>
</div>
<div class="cs-status-pills">
    <span class="cs-pill-armed">● $100,000 MANDATE · PAPER ARMED</span>
    <span class="cs-pill-mcp">● FAST-MCP V2 LIVE</span>
</div>
</div>""",
        unsafe_allow_html=True,
    )

    workspace = st.radio(
        "Judge workspace",
        workspaces,
        horizontal=True,
        label_visibility="collapsed",
        format_func=lambda name: f"{workspaces.index(name) + 1:02d}  {name}",
    )

    if public_judge_mode:
        st.markdown(
            """<div class="cs-replay-notice">
<strong>PUBLIC JUDGE DEMO · READ ONLY</strong> · No Alpaca credentials or order controls are present in this service.
Competition account P&amp;L is verified separately by the submitted Alpaca paper account ID.
</div>""",
            unsafe_allow_html=True,
        )

    if workspace == "Command":
        render_cockpit_page()
        return

    if workspace == "Paper Trade":
        render_live_canary_page()
        return

    if workspace == "Evidence":
        render_scoreboard_page()
        return

    with st.container():
        st.markdown(
            """<div class="cs-replay-notice">
<strong>SEALED REPLAY</strong> · Historical scenarios demonstrate decision logic and risk gates.
Execution on this page is local simulation only; use Paper Trade for fresh Alpaca data and paper orders.
</div>""",
            unsafe_allow_html=True,
        )
        if "replay_ledger_path" not in st.session_state:
            st.session_state["replay_ledger_path"] = str(
                Path(tempfile.gettempdir())
                / f"caisheng-replay-ui-{uuid.uuid4().hex}.db"
            )
        replay_ledger = ExecutionLedger(
            db_path=st.session_state["replay_ledger_path"]
        )
        # 3. TICKER CONTROLS & ARCHETYPE SELECTOR
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("NVDA · Long Volatility Archetype", width="stretch"):
                st.session_state["scenario_id"] = "SCENARIO-NVDA-2024Q2-AMC"
                st.session_state["active_symbol"] = "NVDA"
                st.session_state.pop("approved_token", None)
                st.session_state.pop("latest_receipt", None)
        with col_b:
            if st.button("TSLA · Short Volatility Archetype", width="stretch"):
                st.session_state["scenario_id"] = "SCENARIO-TSLA-2024Q3-AMC"
                st.session_state["active_symbol"] = "TSLA"
                st.session_state.pop("approved_token", None)
                st.session_state.pop("latest_receipt", None)
        with col_c:
            if st.button("AAPL · Risk Restraint Archetype", width="stretch"):
                st.session_state["scenario_id"] = "SCENARIO-AAPL-2024Q4-STALE"
                st.session_state["active_symbol"] = "AAPL"
                st.session_state.pop("approved_token", None)
                st.session_state.pop("latest_receipt", None)

        symbol = st.session_state.get("active_symbol", "NVDA")
        scenario_id = st.session_state.get("scenario_id", f"SCENARIO-{symbol}")

        # Run LangGraph Engine
        config = load_config()
        config.volagent_replay_scenario_id = scenario_id
        workflow = VolAgentWorkflow(config=config)
        result = workflow.run({"symbol": symbol, "ledger": replay_ledger})

        final_decision = result["final_decision"]
        cand = result.get("approved_candidate")
        audit_proposal = result.get("audit_proposal")
        forecast = result.get("move_forecast")
        risk_rep = result.get("risk_report")
        underlying = result.get("underlying")
        long_thesis = result.get("long_vol_thesis")
        short_thesis = result.get("short_vol_thesis")
        critic_report = result.get("critic_report")
        evidence = result.get("evidence", [])

        spot_val = underlying.price if underlying else 100.0

        # Hero Banner
        tag_class = "badge-long" if final_decision == Decision.LONG_STRADDLE else ("badge-short" if final_decision == Decision.SHORT_IRON_BUTTERFLY else "badge-abstain")
        hero_thesis = ""
        if final_decision == Decision.LONG_STRADDLE and long_thesis:
            hero_thesis = f"<strong>Long Volatility Thesis:</strong> {html.escape(long_thesis.thesis)}"
        elif final_decision == Decision.SHORT_IRON_BUTTERFLY and short_thesis:
            hero_thesis = f"<strong>Short Volatility Thesis:</strong> {html.escape(short_thesis.thesis)}"
        else:
            hero_thesis = "<strong>Risk Preservation Mode:</strong> The Model-Risk Critic or Quantitative Risk Gate vetoed execution to preserve capital."

        max_loss_val = f"${cand.max_loss:.2f}" if cand else "$0.00"
        edge_val = (forecast.edge_pct_spot * 100.0) if forecast else 0.0
        edge_display = f"{edge_val:+.2f}%"

        # 4. PRO TRADING DESK MAIN CONSOLE (Emil Kowalski Studio Light Card)
        desk_header_html = f"""<div class="sd-card-dark">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
<div style="display: flex; align-items: center; gap: 16px;">
<div style="width: 48px; height: 48px; border-radius: 10px; background: #FEF3C7; border: 1px solid #FDE68A; color: #D97706; font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 1.2em; display: inline-flex; align-items: center; justify-content: center;">{html.escape(symbol)}</div>
<div>
<div style="font-family: 'JetBrains Mono', monospace; font-size: 1.85em; font-weight: 800; color: #0F172A;">${spot_val:.2f}</div>
<div style="font-size: 0.82em; color: #64748B;">Sealed historical replay · {html.escape(scenario_id)}</div>
</div>
</div>
<span class="pill-badge {tag_class}">{final_decision.value.replace('_', ' ')}</span>
</div>
<p style="color: #334155; font-size: 0.95em; line-height: 1.6; margin: 12px 0 18px 0;">
{hero_thesis}
</p>
<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; padding-top: 16px; border-top: 1px solid #E2E8F0;">
<div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 18px;">
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72em; text-transform: uppercase; color: #64748B; margin-bottom: 4px;">Executable ATM Straddle-Implied Move</div>
<div style="font-family: 'JetBrains Mono', monospace; font-size: 1.45em; font-weight: 800; color: #D97706;">±{forecast.implied_move_pct*100:.1f}%</div>
</div>
<div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 18px;">
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72em; text-transform: uppercase; color: #64748B; margin-bottom: 4px;">Forecast Move (Empirical Bayes)</div>
<div style="font-family: 'JetBrains Mono', monospace; font-size: 1.45em; font-weight: 800; color: #0284C7;">±{forecast.median_abs_move_pct*100:.1f}% <span style="font-size: 0.6em; color: #64748B;">({edge_display})</span></div>
</div>
<div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 18px;">
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72em; text-transform: uppercase; color: #64748B; margin-bottom: 4px;">Candidate Max Defined Risk</div>
<div style="font-family: 'JetBrains Mono', monospace; font-size: 1.45em; font-weight: 800; color: #DC2626;">{max_loss_val}</div>
</div>
</div>
</div>"""
        st.markdown(desk_header_html, unsafe_allow_html=True)
        decision_record = result.get("decision_record")
        runtime = getattr(decision_record, "agent_runtime", None)
        snapshot = getattr(decision_record, "snapshot", None)
        st.caption(
            "Runtime proof: "
            f"{getattr(runtime, 'mode', 'unverified').replace('_', ' ').upper()} · "
            f"Stock feed: {getattr(snapshot, 'stock_feed', 'unknown').upper()} · "
            f"Options feed: {getattr(snapshot, 'options_feed', 'unknown').upper()} · "
            "pricing, sizing, risk, and execution remain deterministic"
        )

        # 5. SUPERDESIGN 2-COLUMN SPLIT: LEFT (Debate & Code) / RIGHT (Payoff & Risk Gate)
        col_left, col_right = st.columns([1, 1])

        with col_left:
            # Dialectic Debate Split Cards
            l_conf = long_thesis.confidence if long_thesis else 0.5
            l_stmt = long_thesis.thesis if long_thesis else "No Long Thesis Generated."
            s_conf = short_thesis.confidence if short_thesis else 0.5
            s_stmt = short_thesis.thesis if short_thesis else "No Short Thesis Generated."

            delta_str = f"{cand.net_delta:+.2f}" if cand else "+0.00"
            vega_str = f"{cand.net_vega:+.1f}" if cand else "+0.0"
            theta_str = f"{cand.net_theta:.1f}" if cand else "-0.0"

            debate_html = f"""<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
<div style="background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 12px; padding: 18px; margin-bottom: 0;">
<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
<span style="font-size: 1.1em;">📈</span>
<span style="font-weight: 800; font-size: 0.82em; color: #166534; text-transform: uppercase; letter-spacing: 0.05em;">Advocate: Long Vol ({l_conf*100:.0f}%)</span>
</div>
<p style="font-size: 0.85em; color: #334155; line-height: 1.5; margin-bottom: 14px;">"{html.escape(l_stmt[:180])}..."</p>
<div style="display: flex; gap: 8px;">
<span style="background: #FFFFFF; border: 1px solid #CBD5E1; font-family: 'JetBrains Mono', monospace; font-size: 0.76em; padding: 4px 10px; border-radius: 9999px; color: #475569;">Δ {delta_str}</span>
<span style="background: #FFFFFF; border: 1px solid #CBD5E1; font-family: 'JetBrains Mono', monospace; font-size: 0.76em; padding: 4px 10px; border-radius: 9999px; color: #475569;">V ${vega_str}/pt</span>
</div>
</div>
<div style="background: #FEF2F2; border: 1px solid #FECACA; border-radius: 12px; padding: 18px; margin-bottom: 0;">
<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
<span style="font-size: 1.1em;">📉</span>
<span style="font-weight: 800; font-size: 0.82em; color: #991B1B; text-transform: uppercase; letter-spacing: 0.05em;">Critic: IV Crush ({s_conf*100:.0f}%)</span>
</div>
<p style="font-size: 0.85em; color: #334155; line-height: 1.5; margin-bottom: 14px;">"{html.escape(s_stmt[:180])}..."</p>
<div style="display: flex; gap: 8px;">
<span style="background: #FFFFFF; border: 1px solid #CBD5E1; font-family: 'JetBrains Mono', monospace; font-size: 0.76em; padding: 4px 10px; border-radius: 9999px; color: #475569;">Θ ${theta_str}/d</span>
<span style="background: #FEE2E2; border: 1px solid #FCA5A5; font-family: 'JetBrains Mono', monospace; font-size: 0.76em; padding: 4px 10px; border-radius: 9999px; color: #B91C1C;">Vol Risk: HIGH</span>
</div>
</div>
</div>"""

            # Live Multi-Leg Contract Structure

            legs_table_rows = ""
            if cand and cand.legs:
                for leg in cand.legs:
                    side_color = "#059669" if leg.side == "buy" else "#DC2626"
                    type_color = "#0284C7" if leg.option_type == "call" else "#7C3AED"
                    legs_table_rows += f"""<tr style="border-bottom: 1px solid #F1F5F9; font-family: 'JetBrains Mono', monospace; font-size: 0.82em;">
<td style="padding: 8px 6px; font-weight: 700; color: #0F172A;">{leg.contract_symbol}</td>
<td style="padding: 8px 6px; color: {side_color}; font-weight: 800;">{leg.side.upper()}</td>
<td style="padding: 8px 6px; color: #0F172A;">${leg.strike:.2f} <span style="color: {type_color}; font-weight: 800;">{leg.option_type.upper()}</span></td>
<td style="padding: 8px 6px; color: #64748B;">{leg.expiration.isoformat()}</td>
<td style="padding: 8px 6px; text-align: right; color: #D97706; font-weight: 800;">${leg.entry_price_assumption:.2f}</td>
<td style="padding: 8px 6px; text-align: right; color: #64748B;">Δ {leg.delta:+.2f}</td>
</tr>"""
                debit_label = "Net Debit" if cand.entry_debit_credit >= 0 else "Net Credit"
                structure_header = f"Level-3 MLEG Structure ({len(cand.legs)} Legs) · {debit_label}: ${abs(cand.entry_debit_credit):.2f}"
            else:
                legs_table_rows = """<tr><td colspan="6" style="padding: 16px; text-align: center; color: #94A3B8; font-size: 0.85em;">No active contract legs (Strategy Abstained)</td></tr>"""
                structure_header = "Level-3 MLEG Structure"

            legs_card_html = f"""<div class="sd-card-dark" style="padding: 20px; margin-bottom: 16px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #E2E8F0;">
<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.82em; font-weight: 800; color: #475569; text-transform: uppercase;">{structure_header}</span>
<span style="background: #FEF3C7; color: #D97706; border: 1px solid #FDE68A; font-family: 'JetBrains Mono', monospace; font-size: 0.74em; font-weight: 800; padding: 4px 10px; border-radius: 9999px;">AUTONOMOUS SIZING</span>
</div>
<table style="width: 100%; border-collapse: collapse; text-align: left;">
<thead>
<tr style="border-bottom: 1px solid #CBD5E1; font-family: 'JetBrains Mono', monospace; font-size: 0.72em; text-transform: uppercase; color: #64748B;">
<th style="padding: 6px;">Contract Symbol</th>
<th style="padding: 6px;">Side</th>
<th style="padding: 6px;">Strike/Type</th>
<th style="padding: 6px;">Expiry</th>
<th style="padding: 6px; text-align: right;">Price</th>
<th style="padding: 6px; text-align: right;">Delta</th>
</tr>
</thead>
<tbody>
{legs_table_rows}
</tbody>
</table>
</div>"""
            st.markdown(debate_html, unsafe_allow_html=True)
            st.markdown(legs_card_html, unsafe_allow_html=True)

            with st.expander("🔍 Alpaca Level-3 MLEG API Payload (JSON)", expanded=False):
                if cand:
                    st.json({
                        "order_class": "mleg",
                        "symbol": symbol,
                        "strategy_id": cand.strategy_id,
                        "decision": cand.decision.value,
                        "quantity": cand.quantity,
                        "entry_debit_credit": cand.entry_debit_credit,
                        "max_loss": cand.max_loss,
                        "legs": [leg.model_dump() for leg in cand.legs]
                    })
                else:
                    st.info("No active multi-leg order plan in memory.")


        with col_right:
            # Payoff Curve
            if cand and final_decision != Decision.NO_TRADE:
                payoff_fig = create_payoff_plot(cand, spot_val, forecast.implied_move_pct * spot_val)
                st.plotly_chart(payoff_fig, width="stretch")
            else:
                st.markdown(f"""<div class="sd-card-dark" style="padding: 28px; text-align: center; border: 1px solid #FECACA; background: #FEF2F2;">
<div style="font-size: 2em; margin-bottom: 8px;">🛑</div>
<div style="font-size: 1.15em; font-weight: 800; color: #DC2626; margin-bottom: 6px;">TRADE ABSTAINED (NO_TRADE)</div>
<div style="font-size: 0.88em; color: #64748B;">Model-Risk Critic vetoed entry to protect portfolio capital.</div>
</div>""", unsafe_allow_html=True)

            # Selected checks from the actual deterministic risk report.
            gate_status = risk_rep.overall_status.value.upper() if risk_rep else "UNAVAILABLE"
            gate_color = "#059669" if gate_status == "PASS" else "#DC2626"
            selected_check_names = (
                "hard_max_loss",
                "model_confidence",
                "quote_quality",
                "critic_approval",
            )
            checks_by_name = {
                check.name: check for check in (risk_rep.checks if risk_rep else [])
            }
            gate_rows = ""
            for check_name in selected_check_names:
                check = checks_by_name.get(check_name)
                check_status = check.status.value.upper() if check else "UNAVAILABLE"
                passed = check_status == "PASS"
                status_color = "#059669" if passed else "#DC2626"
                marker = "✓" if passed else "×"
                observed = html.escape(check.observed if check else "No result")
                label = html.escape(check_name.replace("_", " ").title())
                gate_rows += f"""<div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;">
<span style="font-size: 0.82em; color: #0F172A; font-weight: 600;">{label}<br><small style="color:#64748B;">{observed}</small></span>
<span style="color: {status_color}; font-size: 0.88em; font-weight: 800;">{marker} {check_status}</span>
</div>"""

            gate_html = f"""<div class="sd-card-dark" style="padding: 20px; margin-bottom: 16px;">
<div style="display:flex; justify-content:space-between; gap:12px; font-family: 'JetBrains Mono', monospace; font-size: 0.82em; font-weight: 800; color: #475569; text-transform: uppercase; margin-bottom: 14px;">
<span>Deterministic Quantitative Risk Gate</span><span style="color:{gate_color};">{gate_status}</span>
</div>
<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">{gate_rows}</div>
</div>"""
            st.markdown(gate_html, unsafe_allow_html=True)

            # Order Execution Controls
            if cand and final_decision != Decision.NO_TRADE:
                ledger = replay_ledger
                plan_cache_key = f"order_plan_{scenario_id}_{cand.strategy_id}"
                if plan_cache_key not in st.session_state:
                    target = BrokerTarget.SIMULATED_LOCAL
                    try:
                        st.session_state[plan_cache_key] = build_order_plan(cand, broker_target=target, ledger=ledger)
                    except ExecutionError as e:
                        from volagent.execution.alpaca import compute_logical_exposure_key
                        log_key = compute_logical_exposure_key(
                            event_id="evt-default",
                            symbol=cand.symbol if hasattr(cand, "symbol") else "UNKNOWN",
                            decision=cand.decision.value if hasattr(cand.decision, "value") else str(cand.decision),
                            legs=cand.legs,
                            purpose="entry",
                            strategy_id=cand.strategy_id,
                        )
                        active_prev = ledger.get_active_preview_by_logical_key(log_key)
                        if active_prev and active_prev.get("full_order_plan"):
                            st.session_state[plan_cache_key] = OrderPlan.model_validate_json(active_prev["full_order_plan"])
                        else:
                            st.warning(f"Active order state note: {str(e)}")
                            st.session_state[plan_cache_key] = None

                plan = st.session_state.get(plan_cache_key)
                if plan is not None:
                    c_approve, c_submit = st.columns(2)
                    with c_approve:
                        if st.button("1️⃣ Approve Plan Token", width="stretch"):
                            ledger.approve_order(plan.approval_token)
                            st.session_state["approved_token"] = plan.approval_token
                            st.success("✓ Plan Approved in Transactional Ledger")

                    with c_submit:
                        has_approval = st.session_state.get("approved_token") == plan.approval_token
                        btn_label = f"2️⃣ Execute in Local Simulator ({cand.quantity} Unit)"
                        if st.button(btn_label, width="stretch", disabled=not has_approval):
                            sim_broker = SimulatedPaperBroker(ledger=ledger)
                            receipt = sim_broker.submit_simulated_order(plan)
                            st.session_state["latest_receipt"] = receipt
                            st.session_state.pop("approved_token", None)

                if "latest_receipt" in st.session_state:
                    r = st.session_state["latest_receipt"]
                    st.success(f"✓ Simulation Receipt: {r.broker_target.value} · Receipt ID: {r.broker_order_id} · Status: {r.status.value.upper()}")


if __name__ == "__main__":
    main()
