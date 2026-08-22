"""VolAgent Alpha: Alpaca Pro High-Contrast Volatility Trading Desk."""

import json
import html
import streamlit as st

from volagent.config import load_config
from volagent.domain.enums import BrokerTarget, Decision, GateStatus
from volagent.evaluation.evaluator import evaluate_benchmarks
from volagent.execution.alpaca import AlpacaPaperBroker, SimulatedPaperBroker, build_order_plan
from volagent.execution.ledger import ExecutionLedger
from volagent.graph.builder import VolAgentWorkflow
from volagent.ui.charts import create_payoff_plot
from volagent.ui.pages.research import render_research_page
from volagent.ui.pages.rough_vol_simulator import render_rough_vol_simulator_page
from volagent.ui.pages.scoreboard import render_scoreboard_page
from volagent.ui.theme import (
    ALPACA_CARD,
    ALPACA_DARK,
    ALPACA_YELLOW,
    CUSTOM_CSS,
    CYAN_ACCENT,
    GREEN_PROFIT,
    PURPLE_VOL,
    RED_LOSS,
)

# Configure Streamlit page
st.set_page_config(
    page_title="VolAgent Alpha — Alpaca Options Desk",
    page_icon="🦙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Inject custom Alpaca CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def main() -> None:
    # 1. ALPACA BRANDED PRO TERMINAL HEADER
    st.markdown(f"""
    <div class="alpaca-header">
        <div class="alpaca-logo">
            <span>🦙 VolAgent Alpha</span>
            <span class="alpaca-badge">PAPER TRADING PROTOTYPE</span>
        </div>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85em; color: #8B949E;">
            TRACK 02: VOLATILITY & EVENT DESK · NEURO-SYMBOLIC MULTI-AGENT ARCHITECTURE
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Top-Level Main Tabs
    tab_desk, tab_benchmarks, tab_research, tab_rough_vol = st.tabs([
        "⚡ Pro Trading Desk",
        "📊 Replay Benchmarks",
        "📚 Academic Foundations",
        "🌪️ Rough Volatility Simulator",
    ])

    with tab_desk:
        # 2. TICKER CONTROLS & ARCHETYPE SELECTOR
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
        result = workflow.run({"symbol": symbol})

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
        tag_class = "tag-long" if final_decision == Decision.LONG_STRADDLE else ("tag-short" if final_decision == Decision.SHORT_IRON_BUTTERFLY else "tag-abstain")
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

        st.markdown(f"""
        <div class="hero-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div>
                    <span class="ticker-symbol">{html.escape(symbol)}</span>
                    <span style="color: #8B949E; margin-left: 8px; font-size: 1.1em;">${spot_val:.2f}</span>
                </div>
                <span class="{tag_class}">{final_decision.value.replace('_', ' ')}</span>
            </div>
            <p style="color: #E6EDF3; font-size: 1.05em; line-height: 1.5; margin: 14px 0 0 0;">
                {hero_thesis}
            </p>
            <div class="metric-grid">
                <div class="metric-box">
                    <div class="metric-label">Market Implied Move (Brenner-Subrahmanyam)</div>
                    <div class="metric-value" style="color: {ALPACA_YELLOW};">±{forecast.implied_move_pct*100:.1f}%</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">Forecast Move (Empirical Bayes Shrinkage)</div>
                    <div class="metric-value" style="color: {CYAN_ACCENT};">±{forecast.median_abs_move_pct*100:.1f}% <span style="font-size: 0.7em; color: #FFF;">({edge_display})</span></div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">Max Risk (1% NAV Hard Cap)</div>
                    <div class="metric-value" style="color: {RED_LOSS if cand else '#8B949E'};">{max_loss_val}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 4. PAYOFF DIAGRAM & DETAILS
        if cand and final_decision != Decision.NO_TRADE:
            col_payoff, col_details = st.columns([3, 2])
            with col_payoff:
                payoff_fig = create_payoff_plot(cand, spot_val, forecast.implied_move_pct * spot_val)
                st.plotly_chart(payoff_fig, width="stretch")

            with col_details:
                st.markdown(f"""
                <div class="info-card">
                    <div class="info-title">📐 Strategy Structure & Greeks</div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85em; color: #C9D1D9; margin-bottom: 8px;">
                        Quantity: {cand.quantity} unit(s) · Entry: ${abs(cand.entry_debit_credit):.2f} ({'Debit' if cand.entry_debit_credit > 0 else 'Credit'})<br>
                        Break-Evens: {cand.break_evens if cand.break_evens else 'N/A'}<br>
                        Expected Shortfall (ES95): ${cand.expected_shortfall_95:.2f} (Rockafellar-Uryasev CVaR)
                    </div>
                    <div style="margin-bottom: 6px;">
                        <span class="greek-chip">Δ Delta: {cand.net_delta:+.1f}</span>
                        <span class="greek-chip">Γ Gamma: {cand.net_gamma:.2f}</span>
                        <span class="greek-chip">V Vega: ${cand.net_vega:+.1f}/pt</span>
                        <span class="greek-chip">Θ Theta: ${cand.net_theta:.1f}/day</span>
                    </div>
                    <div style="font-size: 0.8em; color: #8B949E;">
                        Legs: {len(cand.legs)} immutable contracts · Defined Risk Topology
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Order Execution Flow
                ledger = ExecutionLedger()
                plan_cache_key = f"order_plan_{scenario_id}_{cand.strategy_id}"
                if plan_cache_key not in st.session_state:
                    target = BrokerTarget.ALPACA_PAPER if (config.alpaca_api_key and config.execution.allow_order_submission) else BrokerTarget.SIMULATED_LOCAL
                    st.session_state[plan_cache_key] = build_order_plan(cand, broker_target=target, ledger=ledger)

                plan = st.session_state[plan_cache_key]

                st.markdown(f"""
                <div class="info-card" style="margin-top: 10px;">
                    <div class="info-title">📋 Order Approval & Submission Control</div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.82em; color: #8B949E;">
                        Client Order ID: {plan.client_order_id}<br>
                        Target Broker: {plan.broker_target.value.upper()}<br>
                        Fingerprint: {plan.fingerprint[:16]}...<br>
                        Token: {plan.approval_token[:16]}...
                    </div>
                </div>
                """, unsafe_allow_html=True)

                c_approve, c_submit = st.columns(2)
                with c_approve:
                    if st.button("1️⃣ Approve Plan Token", width="stretch"):
                        ledger.approve_order(plan.approval_token)
                        st.session_state["approved_token"] = plan.approval_token
                        st.success("✓ Plan Approved in Transactional Ledger")

                with c_submit:
                    has_approval = st.session_state.get("approved_token") == plan.approval_token
                    btn_label = f"2️⃣ Execute ({cand.quantity} Unit)"
                    if st.button(btn_label, width="stretch", disabled=not has_approval):
                        if plan.broker_target == BrokerTarget.ALPACA_PAPER:
                            broker = AlpacaPaperBroker(api_key=config.alpaca_api_key, secret_key=config.alpaca_secret_key, ledger=ledger)
                            receipt = broker.submit_paper_order(plan)
                            st.session_state["latest_receipt"] = receipt
                        else:
                            sim_broker = SimulatedPaperBroker(ledger=ledger)
                            receipt = sim_broker.submit_simulated_order(plan)
                            st.session_state["latest_receipt"] = receipt
                        st.session_state.pop("approved_token", None)

                if "latest_receipt" in st.session_state:
                    r = st.session_state["latest_receipt"]
                    st.success(f"✓ Order Executed: {r.broker_target.value} · Broker ID: {r.broker_order_id} · Status: {r.status.value.upper()}")

        else:
            # NO_TRADE VIEW
            reasons_list = result.get("rejection_reasons", [])
            st.markdown(f"""
            <div class="info-card" style="border-left: 4px solid {RED_LOSS};">
                <div class="info-title" style="color: {RED_LOSS};">🛑 TRADE ABSTAINED (NO_TRADE)</div>
                <p style="color: #E6EDF3; font-size: 0.95em;">The system safely abstained from trading to preserve capital:</p>
                <ul style="color: #8B949E; font-size: 0.9em;">
                    {''.join(f'<li>{html.escape(r)}</li>' for r in reasons_list)}
                </ul>
            </div>
            """, unsafe_allow_html=True)

        # 5. MULTI-AGENT DIALECTIC THEATER & EVIDENCE SECTION
        st.markdown("### 🎭 Multi-Agent Dialectic Theater & Citations (Du et al. 2023)")
        col_long, col_short, col_critic = st.columns(3)
        
        with col_long:
            l_conf = long_thesis.confidence if long_thesis else 0.5
            l_stmt = long_thesis.thesis if long_thesis else "No Long Thesis Generated."
            st.markdown(f"""
            <div class="info-card">
                <div class="info-title" style="color: {CYAN_ACCENT};">📈 Long Vol Specialist ({l_conf*100:.0f}% Conf)</div>
                <p style="color: #C9D1D9; font-size: 0.85em; line-height: 1.5;">{html.escape(l_stmt)}</p>
                <div style="font-size: 0.75em; color: #8B949E;">Citations: {long_thesis.supporting_evidence_ids if long_thesis else []}</div>
            </div>
            """, unsafe_allow_html=True)

        with col_short:
            s_conf = short_thesis.confidence if short_thesis else 0.5
            s_stmt = short_thesis.thesis if short_thesis else "No Short Thesis Generated."
            st.markdown(f"""
            <div class="info-card">
                <div class="info-title" style="color: {PURPLE_VOL};">📉 Short Vol Specialist ({s_conf*100:.0f}% Conf)</div>
                <p style="color: #C9D1D9; font-size: 0.85em; line-height: 1.5;">{html.escape(s_stmt)}</p>
                <div style="font-size: 0.75em; color: #8B949E;">Citations: {short_thesis.supporting_evidence_ids if short_thesis else []}</div>
            </div>
            """, unsafe_allow_html=True)

        with col_critic:
            c_status = critic_report.status.value.upper() if critic_report else "PASS"
            c_rec = critic_report.recommendation.upper() if critic_report else "CONTINUE"
            st.markdown(f"""
            <div class="info-card">
                <div class="info-title" style="color: {CYAN_ACCENT};">🛡️ Model-Risk Critic ({c_status})</div>
                <p style="color: #C9D1D9; font-size: 0.85em; line-height: 1.5;">
                    Recommendation: <strong>{c_rec}</strong><br>
                    • Stale Quote: {'Detected' if critic_report and critic_report.stale_data_detected else 'Clean'}<br>
                    • Temporal Leakage: {'Detected' if critic_report and critic_report.temporal_leakage_detected else 'None'}<br>
                    • Directional Scan: {'Clean (Track 2 Non-Directional)' if critic_report and not critic_report.directional_leakage_detected else 'Violation'}
                </p>
            </div>
            """, unsafe_allow_html=True)

        # 6. COLLAPSIBLE DEEP AUDIT DRAWER (For Judges)
        with st.expander("🔬 Deep Mathematical Audit, Risk Matrix & Decision Receipt", expanded=False):
            if risk_rep and risk_rep.checks:
                st.markdown("**20-Point Quantitative Risk Gate Invariant Matrix (Artzner 1999)**")
                risk_table = [
                    {"Check Name": c.name, "Status": c.status.value.upper(), "Observed": c.observed, "Limit / Rule": c.limit, "Description": c.explanation}
                    for c in risk_rep.checks
                ]
                st.dataframe(risk_table, width="stretch")

            st.markdown("**Evaluator Benchmark Results (Sealed Outcomes)**")
            benchmarks = evaluate_benchmarks()
            st.dataframe(benchmarks["summary"], width="stretch")

            st.markdown("**Canonical Decision Receipt JSON**")
            receipt_data = {
                "run_id": result.get("run_id"),
                "symbol": symbol,
                "final_decision": final_decision.value,
                "abstention_reason": result.get("abstention_reason", "none"),
                "implied_move_pct": forecast.implied_move_pct if forecast else None,
                "forecast_median_pct": forecast.median_abs_move_pct if forecast else None,
                "risk_status": risk_rep.overall_status.value if risk_rep else "FAIL",
                "approved_quantity": risk_rep.approved_quantity if risk_rep else 0,
                "provenance_hash": result.get("artifact_hashes", {}).get("scenario_file", ""),
                "rejection_reasons": result.get("rejection_reasons", []),
            }
            receipt_json = json.dumps(receipt_data, indent=2)
            st.download_button(
                label="💾 Download Decision Receipt JSON",
                data=receipt_json,
                file_name=f"decision_receipt_{symbol}.json",
                mime="application/json",
            )
            st.code(receipt_json, language="json")

    with tab_benchmarks:
        render_scoreboard_page()

    with tab_research:
        render_research_page()

    with tab_rough_vol:
        render_rough_vol_simulator_page()


if __name__ == "__main__":
    main()
