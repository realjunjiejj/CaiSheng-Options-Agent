"""Decision Page: Full Quantitative Rationale, Payoff, Debate & Paper Execution."""

import streamlit as st

from volagent.agents.explainer import generate_decision_explanation
from volagent.domain.enums import Decision, GateStatus
from volagent.execution.alpaca import AlpacaPaperBroker, build_order_plan
from volagent.ui.charts import create_greeks_bar_chart, create_payoff_plot, create_stress_heatmap
from volagent.ui.theme import ACCENT_IV, FAIL_COLOR, LONG_VOL_COLOR, PASS_COLOR, SHORT_VOL_COLOR


def render_decision_page() -> None:
    if "last_run_result" not in st.session_state:
        st.warning("⚠️ No active run found. Please run an analysis from the **Analyze** tab first.")
        return

    result = st.session_state["last_run_result"]
    cand = result.get("selected_candidate")
    forecast = result["move_forecast"]
    iv_fc = result["iv_forecast"]
    underlying = result["underlying"]
    risk_rep = result["risk_report"]
    decision = cand.decision if cand else Decision.NO_TRADE

    explanation = generate_decision_explanation(underlying.symbol, decision, forecast, cand, risk_rep)

    # 1. TOP DECISION HERO CARD
    st.markdown(f"""
    <div class="decision-card">
        <h2 style="margin:0; color: #FFF;">{underlying.symbol} — Earnings Volatility Decision</h2>
        <h3 style="margin:5px 0 15px 0; color: {ACCENT_IV};">Decision: {decision.value.replace('_', ' ').upper()}</h3>
        <p style="color: #9AA7B8; font-size: 1.1em; margin-bottom: 0;">{explanation['why_decision_won']}</p>
    </div>
    """, unsafe_allow_html=True)

    # Key Metrics Banner
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

    if cand is not None and decision != Decision.NO_TRADE:
        # 2. INTERACTIVE PAYOFF & GREEKS CHARTS
        c_left, c_right = st.columns([3, 2])
        with c_left:
            payoff_fig = create_payoff_plot(cand, underlying.price, forecast.implied_move_pct * underlying.price)
            st.plotly_chart(payoff_fig, use_container_width=True)

        with c_right:
            greeks_fig = create_greeks_bar_chart(cand)
            st.plotly_chart(greeks_fig, use_container_width=True)

        # 3. 2D STRESS TEST HEATMAP
        if cand.stress_losses:
            st.markdown("### 🌡️ 2D Stress Loss Heatmap")
            stress_fig = create_stress_heatmap(cand.stress_losses)
            st.plotly_chart(stress_fig, use_container_width=True)

        # 4. STRATEGY LEGS TABLE
        st.markdown("### 📋 Multi-Leg Contract Structure")
        legs_data = []
        for leg in cand.legs:
            legs_data.append({
                "Contract Symbol": leg.contract_symbol,
                "Type": leg.option_type.upper(),
                "Strike": f"${leg.strike:.2f}",
                "Side": leg.side.upper(),
                "Action": leg.position_intent.replace("_", " ").title(),
                "Ratio": leg.ratio_qty,
                "Delta (Δ)": f"{leg.delta:.3f}",
                "Vega (V)": f"${leg.vega:.2f}/pt",
                "Entry Price": f"${leg.entry_price_assumption:.2f}",
            })
        st.dataframe(legs_data, use_container_width=True)

    else:
        st.error("🛑 **TRADE ABSTAINED (NO_TRADE)**")
        st.markdown(f"**Reasons:** {explanation['rejection_reasons']}")

    st.markdown("---")

    # 5. DIALECTICAL AGENT DEBATE
    st.markdown("### ⚔️ Multi-Agent Dialectical Debate")
    d1, d2, d3 = st.columns(3)

    with d1:
        st.markdown(f"""
        <div style="background-color: #151A23; padding: 15px; border-radius: 8px; border-top: 4px solid {LONG_VOL_COLOR};">
            <h4 style="color: {LONG_VOL_COLOR}; margin-top:0;">📈 Long-Vol Advocate</h4>
            <p><strong>Confidence:</strong> {result['long_vol_thesis'].confidence*100:.1f}%</p>
            <p>{result['long_vol_thesis'].thesis}</p>
            <p style="font-size:0.9em; color:#9AA7B8;"><em>{result['long_vol_thesis'].numeric_argument}</em></p>
        </div>
        """, unsafe_allow_html=True)

    with d2:
        st.markdown(f"""
        <div style="background-color: #151A23; padding: 15px; border-radius: 8px; border-top: 4px solid {SHORT_VOL_COLOR};">
            <h4 style="color: {SHORT_VOL_COLOR}; margin-top:0;">📉 Short-Vol Advocate</h4>
            <p><strong>Confidence:</strong> {result['short_vol_thesis'].confidence*100:.1f}%</p>
            <p>{result['short_vol_thesis'].thesis}</p>
            <p style="font-size:0.9em; color:#9AA7B8;"><em>{result['short_vol_thesis'].numeric_argument}</em></p>
        </div>
        """, unsafe_allow_html=True)

    with d3:
        critic = result["critic_report"]
        critic_color = PASS_COLOR if critic.status == GateStatus.PASS else FAIL_COLOR
        st.markdown(f"""
        <div style="background-color: #151A23; padding: 15px; border-radius: 8px; border-top: 4px solid {critic_color};">
            <h4 style="color: {critic_color}; margin-top:0;">🛡️ Model-Risk Critic</h4>
            <p><strong>Status:</strong> {critic.status.value.upper()}</p>
            <p><strong>Recommendation:</strong> {critic.recommendation.upper()}</p>
            <p style="font-size:0.9em; color:#9AA7B8;">Stale Data: {critic.stale_data_detected} | Temporal Leakage: {critic.temporal_leakage_detected}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # 6. DETERMINISTIC RISK GATE CHECKLIST
    st.markdown("### 🛡️ 20-Point Quantitative Risk Gate Checklist")
    with st.expander("View Full Risk Gate Audit", expanded=(decision != Decision.NO_TRADE)):
        for check in risk_rep.checks:
            icon = "✅" if check.status == GateStatus.PASS else "❌"
            st.markdown(f"{icon} **{check.name}**: Observed `{check.observed}` | Limit `{check.limit}` — *{check.explanation}*")

    st.markdown("---")

    # 7. ALPACA PAPER TRADING EXECUTION CARD
    st.markdown("### ⚡ Alpaca Paper Trading Execution")
    if cand and decision != Decision.NO_TRADE and risk_rep.overall_status == GateStatus.PASS:
        plan = build_order_plan(cand)

        col_p1, col_p2 = st.columns([2, 1])
        with col_p1:
            st.markdown(f"**Order Fingerprint:** `{plan.fingerprint}`")
            st.markdown(f"**Order Type:** `Limit Multi-Leg (MLEG)` | Quantity: `{plan.quantity}` unit(s)")
            st.markdown(f"**Target Broker:** `Alpaca Paper Trading Endpoint`")

        with col_p2:
            confirm_box = st.checkbox("I confirm this is an Alpaca paper trade only.")
            if st.button("🚀 Approve & Submit Paper Order to Alpaca", type="primary", disabled=not confirm_box):
                broker = AlpacaPaperBroker()
                receipt = broker.submit_paper_order(plan)
                st.balloons()
                st.success(f"🎉 Paper Order Submitted Successfully! Order ID: `{receipt.order_id}` | Status: `{receipt.status.upper()}`")
    else:
        st.info("ℹ️ Order submission is disabled because risk invariants rejected the trade or no trade was recommended.")
