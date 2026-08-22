"""Analyze Page: Scenario Selection and Live Multi-Agent Execution."""

import time
import streamlit as st

from volagent.config import load_config
from volagent.data.replay import ReplayDataManager
from volagent.domain.enums import DataMode
from volagent.graph.builder import VolAgentWorkflow


def render_analyze_page() -> None:
    st.markdown("## 🔍 Market & Event Scenario Analysis")
    st.markdown("Select a real earnings event or a synthetic stress scenario to launch the **VolAgent Alpha** multi-agent pipeline.")

    replay_mgr = ReplayDataManager()
    scenarios = replay_mgr.get_featured_scenarios()

    col1, col2 = st.columns([2, 1])

    with col1:
        scenario_options = {s["name"]: s for s in scenarios}
        selected_name = st.selectbox("Select Scenario:", list(scenario_options.keys()))
        selected_scenario = scenario_options[selected_name]

    with col2:
        mode_badge = (
            '<span class="badge-replay">REPLAY — REAL</span>'
            if selected_scenario["mode"] == DataMode.REPLAY_REAL
            else '<span class="badge-synthetic">SYNTHETIC FAILURE</span>'
        )
        st.markdown(f"**Data Mode:** {mode_badge}", unsafe_allow_html=True)
        st.markdown(f"**Target Ticker:** `{selected_scenario['symbol']}`")
        st.markdown(f"**Event Time:** `{selected_scenario['event_time']}`")

    st.markdown("---")

    # Risk & Capital Settings
    c1, c2, c3 = st.columns(3)
    with c1:
        nav = st.number_input("Portfolio NAV ($)", value=100_000.0, step=10_000.0)
    with c2:
        risk_pct = st.selectbox("Risk Budget (% NAV)", [0.005, 0.01], format_func=lambda x: f"{x*100:.1f}% (Hard Cap: 1.0%)")
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("🚀 Run VolAgent Multi-Agent Analysis", type="primary", use_container_width=True)

    if run_btn:
        config = load_config()
        config.volagent_replay_scenario_id = selected_scenario["scenario_id"]

        progress_container = st.container()
        with progress_container:
            st.info("⚙️ Initializing LangGraph Multi-Agent Pipeline...")
            p_bar = st.progress(10)
            time.sleep(0.2)

            st.write("📊 **Node 1/4:** Fetching Snapshot & Running Parallel Analysis (`EventMagnitudeAgent` ∥ `VolatilityQuantEngine`)...")
            p_bar.progress(35)
            time.sleep(0.2)

            st.write("⚔️ **Node 2/4:** Synthesizing Dialectical Volatility Debate (`LongVolAdvocate` ∥ `ShortVolAdvocate`)...")
            p_bar.progress(60)
            time.sleep(0.2)

            st.write("🛡️ **Node 3/4:** Independent Audit (`ModelRiskCritic` & `TrackComplianceGuard`)...")
            p_bar.progress(80)
            time.sleep(0.2)

            st.write("📐 **Node 4/4:** Monte Carlo Strategy Repricing & 20-Point Deterministic Risk Gate...")
            workflow = VolAgentWorkflow(config=config)
            result = workflow.run({"symbol": selected_scenario["symbol"]})
            p_bar.progress(100)

            st.session_state["last_run_result"] = result
            st.session_state["selected_scenario"] = selected_scenario
            st.success("✅ Analysis Complete! Switch to the **Decision** tab to view results.")
