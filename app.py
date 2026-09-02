"""CaiSheng: autonomous options alpha on Alpaca."""

import html
import os
from pathlib import Path
import tempfile
import uuid

import streamlit as st

from volagent.config import load_config
from volagent.domain.enums import Decision
from volagent.execution.ledger import ExecutionLedger
from volagent.graph.builder import VolAgentWorkflow
from volagent.ui.charts import create_payoff_plot
from volagent.ui.integration_status import judge_workspaces
from volagent.ui.pages.cockpit import render_cockpit_page
from volagent.ui.pages.overview import render_overview_page
from volagent.ui.pages.scoreboard import render_scoreboard_page
from volagent.ui.theme import CUSTOM_CSS


# Configure Streamlit page
st.set_page_config(
    page_title="Alpaca / CaiSheng — Autonomous Options Alpha",
    page_icon="🦙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Inject the shared judge-facing theme.
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def main() -> None:
    public_judge_mode = os.environ.get("CAISHENG_PUBLIC_JUDGE_MODE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    workspaces = judge_workspaces(public_read_only=public_judge_mode)

    # Compact product header: capability labels only, never runtime-state claims.
    st.markdown(
        """<div class="cs-judge-header">
<div class="cs-header-left">
    <div>
        <div class="cs-eyebrow">
            <span>ALPACA · OPTIONS ALPHA</span>
            <span class="cs-version">v1.0</span>
        </div>
        <div class="cs-title">CaiSheng</div>
        <div class="cs-subtitle">Autonomous options decisions. Deterministic risk. Verifiable Alpaca execution.</div>
    </div>
</div>
<div class="cs-status-pills">
    <span class="cs-proof-pill">$100K PAPER MANDATE</span>
    <span class="cs-proof-pill">ALPACA API · MCP · CLI</span>
    <span class="cs-proof-pill cs-proof-pill-accent">LANGGRAPH</span>
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

    if workspace == "Overview":
        render_overview_page()
        return

    if workspace == "Operations":
        render_cockpit_page()
        return

    if workspace == "Results":
        render_scoreboard_page()
        return

    with st.container():
        st.markdown(
            """<div class="cs-context-row">
<span class="cs-context-badge">CONTROLLED REPLAY</span>
<span class="cs-context-boundary">NOT COMPETITION P&amp;L</span>
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
        # Three judge-ready outcomes: long vol, short vol, and disciplined abstention.
        with st.container(key="scenario_selector"):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("NVDA · Long volatility", width="stretch"):
                    st.session_state["scenario_id"] = "SCENARIO-NVDA-2024Q2-AMC"
                    st.session_state["active_symbol"] = "NVDA"
                    st.session_state.pop("approved_token", None)
                    st.session_state.pop("latest_receipt", None)
            with col_b:
                if st.button("TSLA · Short volatility", width="stretch"):
                    st.session_state["scenario_id"] = "SCENARIO-TSLA-2024Q3-AMC"
                    st.session_state["active_symbol"] = "TSLA"
                    st.session_state.pop("approved_token", None)
                    st.session_state.pop("latest_receipt", None)
            with col_c:
                if st.button("AAPL · Abstain", width="stretch"):
                    st.session_state["scenario_id"] = "SCENARIO-AAPL-2024Q4-STALE"
                    st.session_state["active_symbol"] = "AAPL"
                    st.session_state.pop("approved_token", None)
                    st.session_state.pop("latest_receipt", None)

        symbol = st.session_state.get("active_symbol", "NVDA")
        scenario_id = st.session_state.get("scenario_id", "SCENARIO-NVDA-2024Q2-AMC")

        # Run LangGraph Engine
        config = load_config().model_copy(
            update={"volagent_replay_scenario_id": scenario_id},
            deep=True,
        )
        workflow = VolAgentWorkflow(config=config)
        result = workflow.run({"symbol": symbol, "ledger": replay_ledger})

        final_decision = result["final_decision"]
        cand = result.get("approved_candidate")
        forecast = result.get("move_forecast")
        risk_rep = result.get("risk_report")
        underlying = result.get("underlying")
        long_thesis = result.get("long_vol_thesis")
        short_thesis = result.get("short_vol_thesis")
        critic_report = result.get("critic_report")
        spot_val = underlying.price if underlying else 100.0

        def excerpt(value: str, limit: int = 190) -> str:
            cleaned = " ".join(value.split())
            suffix = "…" if len(cleaned) > limit else ""
            return html.escape(cleaned[:limit].rstrip()) + suffix

        tag_class = (
            "badge-long"
            if final_decision == Decision.LONG_STRADDLE
            else (
                "badge-short"
                if final_decision == Decision.SHORT_IRON_BUTTERFLY
                else "badge-abstain"
            )
        )
        if final_decision == Decision.LONG_STRADDLE and long_thesis:
            thesis_label = "LONG VOLATILITY SELECTED"
            hero_thesis = excerpt(long_thesis.thesis, 230)
        elif final_decision == Decision.SHORT_IRON_BUTTERFLY and short_thesis:
            thesis_label = "SHORT VOLATILITY SELECTED"
            hero_thesis = excerpt(short_thesis.thesis, 230)
        else:
            thesis_label = "CAPITAL PRESERVED"
            hero_thesis = "The model-risk critic or deterministic gate found insufficient evidence to risk capital."

        max_loss_val = f"${cand.max_loss:.2f}" if cand else "$0.00"
        edge_val = (forecast.edge_pct_spot * 100.0) if forecast else 0.0
        edge_display = f"{edge_val:+.2f}%"
        implied_move_display = f"±{forecast.implied_move_pct * 100:.1f}%" if forecast else "—"
        forecast_move_display = f"±{forecast.median_abs_move_pct * 100:.1f}%" if forecast else "—"

        # The first viewport answers opportunity, decision, edge, and risk.
        desk_header_html = f"""<section class="cs-decision-hero">
<div class="cs-decision-topline">
<div class="cs-instrument">
<div class="cs-symbol">{html.escape(symbol)}</div>
<div><div class="cs-spot">${spot_val:.2f}</div><div class="cs-scenario-id">{html.escape(scenario_id)}</div></div>
</div>
<span class="pill-badge {tag_class}">{final_decision.value.replace('_', ' ')}</span>
</div>
<div class="cs-thesis"><span>{thesis_label}</span>{hero_thesis}</div>
<div class="cs-metric-strip">
<div class="cs-metric">
<div class="cs-metric-label">MARKET IMPLIED MOVE</div>
<div class="cs-metric-value cs-metric-amber">{implied_move_display}</div>
</div>
<div class="cs-metric">
<div class="cs-metric-label">CAISHENG FORECAST</div>
<div class="cs-metric-value cs-metric-blue">{forecast_move_display}<small>{edge_display} edge</small></div>
</div>
<div class="cs-metric">
<div class="cs-metric-label">MAXIMUM DEFINED RISK</div>
<div class="cs-metric-value cs-metric-red">{max_loss_val}</div>
</div>
</div>
</section>"""
        st.markdown(desk_header_html, unsafe_allow_html=True)
        decision_record = result.get("decision_record")
        runtime = getattr(decision_record, "agent_runtime", None)
        snapshot = getattr(decision_record, "snapshot", None)
        risk_checks = list(risk_rep.checks) if risk_rep else []
        warned_checks = sum(check.status.value.upper() == "WARN" for check in risk_checks)
        risk_proof = f"{len(risk_checks)} CHECKS · {risk_rep.overall_status.value.upper()}" if risk_rep else "RISK GATE · UNAVAILABLE"
        if warned_checks:
            risk_proof += f" · {warned_checks} WARN"
        st.markdown(
            f"""<div class="cs-runtime-proof">
<span>{html.escape(getattr(runtime, 'mode', 'unverified').replace('_', ' ').upper())}</span>
<span>STOCK · {html.escape(getattr(snapshot, 'stock_feed', 'unknown').upper())}</span>
<span>OPTIONS · {html.escape(getattr(snapshot, 'options_feed', 'unknown').upper())}</span>
<span>{risk_proof}</span>
</div>""",
            unsafe_allow_html=True,
        )

        # Keep the debate and deterministic proof visible in one scan path.
        col_left, col_right = st.columns([1, 1])

        with col_left:
            # Dialectic Debate Split Cards
            l_conf = long_thesis.confidence if long_thesis else 0.5
            l_stmt = long_thesis.thesis if long_thesis else "No Long Thesis Generated."
            s_conf = short_thesis.confidence if short_thesis else 0.5
            s_stmt = short_thesis.thesis if short_thesis else "No Short Thesis Generated."

            critic_status = critic_report.status.value.upper() if critic_report else "UNAVAILABLE"
            critic_action = (
                critic_report.recommendation.replace("_", " ").upper()
                if critic_report
                else "NO VERDICT"
            )
            critic_notes = (
                list(critic_report.failure_reasons) + list(critic_report.warnings)
                if critic_report
                else []
            )
            critic_detail = excerpt(
                critic_notes[0] if critic_notes else "No leakage, stale-data, or unsupported-claim veto.",
                150,
            )
            critic_class = "cs-critic-pass" if critic_status == "PASS" else "cs-critic-fail"

            debate_html = f"""<section class="cs-agent-section">
<div class="cs-section-heading"><span>MULTI-AGENT DEBATE</span><small>Direction-neutral volatility reasoning</small></div>
<div class="cs-agent-grid">
<article class="cs-agent-card cs-agent-long">
<div class="cs-agent-label"><span class="cs-agent-dot"></span>LONG VOL ADVOCATE <b>{l_conf*100:.0f}%</b></div>
<p>{excerpt(l_stmt)}</p>
<div class="cs-agent-metrics"><span>FORECAST {forecast_move_display}</span><span>EDGE {edge_display}</span></div>
</article>
<article class="cs-agent-card cs-agent-short">
<div class="cs-agent-label"><span class="cs-agent-dot"></span>SHORT VOL ADVOCATE <b>{s_conf*100:.0f}%</b></div>
<p>{excerpt(s_stmt)}</p>
<div class="cs-agent-metrics"><span>IMPLIED {implied_move_display}</span><span>IV CRUSH CASE</span></div>
</article>
</div>
<div class="cs-critic-strip {critic_class}"><span>MODEL-RISK CRITIC · {critic_status}</span><strong>{critic_action}</strong><small>{critic_detail}</small></div>
</section>"""

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
                structure_badge = "AUTONOMOUS SIZING"
            else:
                legs_table_rows = """<tr><td colspan="6" style="padding: 16px; text-align: center; color: #94A3B8; font-size: 0.85em;">No active contract legs (Strategy Abstained)</td></tr>"""
                structure_header = "Level-3 MLEG Structure"
                structure_badge = "NO ORDER CREATED"

            legs_card_html = f"""<div class="sd-card-dark" style="padding: 20px; margin-bottom: 16px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #E2E8F0;">
<span style="font-family: 'JetBrains Mono', monospace; font-size: 0.82em; font-weight: 800; color: #475569; text-transform: uppercase;">{structure_header}</span>
<span style="background: #FEF3C7; color: #D97706; border: 1px solid #FDE68A; font-family: 'JetBrains Mono', monospace; font-size: 0.74em; font-weight: 800; padding: 4px 10px; border-radius: 9999px;">{structure_badge}</span>
</div>
<div class="cs-contract-table-wrap"><table style="width: 100%; min-width: 640px; border-collapse: collapse; text-align: left;">
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
</table></div>
</div>"""
            st.markdown(debate_html, unsafe_allow_html=True)
            st.markdown(legs_card_html, unsafe_allow_html=True)

            with st.expander("Alpaca Level 3 MLEG payload", expanded=False):
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
                st.markdown("""<div class="cs-empty-payoff">
<strong>NO PAYOFF CREATED</strong>
<span>NO_TRADE · zero capital committed</span>
</div>""", unsafe_allow_html=True)

            # Selected checks from the actual deterministic risk report.
            gate_status = risk_rep.overall_status.value.upper() if risk_rep else "UNAVAILABLE"
            gate_color = "#059669" if gate_status == "PASS" else "#DC2626"
            checks_by_name = {
                check.name: check for check in (risk_rep.checks if risk_rep else [])
            }
            preferred_check_names = (
                "hard_max_loss",
                "model_confidence",
                "quote_quality",
                "critic_approval",
                "data_consistency",
                "event_timing",
                "paper_only_endpoint",
            )
            selected_check_names = [
                name for name in preferred_check_names if name in checks_by_name
            ][:4]
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
<span>Deterministic Risk Gate · {len(risk_checks)} checks</span><span style="color:{gate_color};">{gate_status}</span>
</div>
<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">{gate_rows}</div>
</div>"""
            st.markdown(gate_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
