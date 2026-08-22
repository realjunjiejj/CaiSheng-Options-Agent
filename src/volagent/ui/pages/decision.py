"""Decision Page: Full Quantitative Rationale, Payoff, Debate & Paper Execution."""

import streamlit as st

from volagent.domain.enums import Decision, GateStatus
from volagent.execution.alpaca import AlpacaPaperBroker, SimulatedPaperBroker, build_order_plan
from volagent.execution.ledger import ExecutionLedger
from volagent.ui.charts import create_greeks_bar_chart, create_payoff_plot, create_stress_heatmap
from volagent.ui.theme import ACCENT_IV, FAIL_COLOR, LONG_VOL_COLOR, PASS_COLOR, SHORT_VOL_COLOR


def render_decision_page() -> None:
    if "last_run_result" not in st.session_state:
        st.warning("⚠️ No active run found. Please run an analysis from the **Analyze** tab first.")
        return

    result = st.session_state["last_run_result"]
    cand = result.get("approved_candidate") or result.get("audit_proposal")
    forecast = result.get("move_forecast")
    iv_fc = result.get("iv_forecast")
    underlying = result.get("underlying")
    risk_rep = result.get("risk_report")
    final_decision = result.get("final_decision", Decision.NO_TRADE)

    # 1. TOP DECISION HERO CARD
    st.markdown(f"""
    <div class="decision-card">
        <h2 style="margin:0; color: #FFF;">{underlying.symbol if underlying else 'N/A'} — Earnings Volatility Decision</h2>
        <h3 style="margin:5px 0 15px 0; color: {ACCENT_IV};">Decision: {final_decision.value.replace('_', ' ').upper()}</h3>
    </div>
    """, unsafe_allow_html=True)

    if forecast and iv_fc:
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("Market Implied Move", f"{forecast.implied_move_pct*100:.1f}%")
        with m2:
            st.metric("Forecast Median Move", f"{forecast.median_abs_move_pct*100:.1f}%", delta=f"{forecast.edge_pct_spot*100:+.2f}%")
        with m3:
            st.metric("P(Move > Implied)", f"{forecast.probability_exceeds_implied*100:.1f}%")
        with m4:
            st.metric("Expected IV Crush", f"{iv_fc.median_iv_change_points:.1f} pts")
        with m5:
            max_loss_str = f"${cand.max_loss:.2f}" if cand else "$0.00"
            st.metric("Max Capital at Risk", max_loss_str)

    st.markdown("---")

    if cand is not None and final_decision != Decision.NO_TRADE:
        # 2. INTERACTIVE PAYOFF & GREEKS CHARTS
        c_left, c_right = st.columns([3, 2])
        with c_left:
            payoff_fig = create_payoff_plot(cand, underlying.price, forecast.implied_move_pct * underlying.price)
            st.plotly_chart(payoff_fig, width="stretch")

        with c_right:
            greeks_fig = create_greeks_bar_chart(cand)
            st.plotly_chart(greeks_fig, width="stretch")

        # 3. 2D STRESS MATRIX
        stress_fig = create_stress_heatmap(cand)
        st.plotly_chart(stress_fig, width="stretch")

    else:
        # Rejection details
        reasons = result.get("rejection_reasons", [])
        st.error(f"Trade Abstained / Rejected: {'; '.join(reasons) if reasons else 'Risk restraint or lack of edge'}")
