"""Audit Page: Provenance, Configuration, Decision Receipt & Cryptographic Verification."""

import json
import streamlit as st

from volagent.config import load_config
from volagent.provenance import to_canonical_json


def render_audit_page() -> None:
    st.markdown("## 🔍 System Audit & Provenance Inspector")
    st.markdown("Inspect cryptographic data provenance, configuration invariants, model versions, and raw decision receipts.")

    config = load_config()

    # 1. Active Configuration Thresholds
    st.markdown("### ⚙️ Deterministic Risk & Execution Thresholds")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Application Config**")
        st.json({
            "name": config.application.name,
            "timezone": config.application.timezone,
            "seed": config.application.random_seed,
            "max_runtime_sec": config.application.max_graph_runtime_seconds,
        })
    with c2:
        st.markdown("**Risk Invariants**")
        st.json({
            "hard_max_risk_nav_pct": f"{config.risk.hard_max_risk_nav_pct*100:.1f}%",
            "recommended_risk_nav_pct": f"{config.risk.recommended_risk_nav_pct*100:.1f}%",
            "max_abs_dollar_delta_nav_pct": f"{config.risk.max_abs_dollar_delta_nav_pct*100:.1f}%",
            "max_contracts": config.risk.max_contracts,
            "require_defined_risk": config.risk.require_defined_risk_for_short_vol,
        })
    with c3:
        st.markdown("**Execution Rules**")
        st.json({
            "paper_only": config.execution.paper_only,
            "require_human_approval": config.execution.require_human_approval,
            "order_type": config.execution.order_type,
            "slippage_per_contract": f"${config.execution.slippage_per_contract:.2f}",
            "fee_per_contract": f"${config.execution.fee_per_contract:.2f}",
        })

    st.markdown("---")

    # 2. Raw Decision Receipt JSON
    st.markdown("### 📄 Immutable Decision Receipt (`decision_receipt.json`)")
    if "last_run_result" in st.session_state:
        res = st.session_state["last_run_result"]
        cand = res.get("approved_candidate") or res.get("audit_proposal")
        receipt_data = {
            "schema_version": "1.0",
            "run_id": res.get("run_id"),
            "symbol": res["underlying"].symbol if res.get("underlying") else "UNKNOWN",
            "event": res["event"].model_dump(mode="json") if res.get("event") else None,
            "underlying": res["underlying"].model_dump(mode="json") if res.get("underlying") else None,
            "move_forecast": res["move_forecast"].model_dump(mode="json") if res.get("move_forecast") else None,
            "iv_forecast": res["iv_forecast"].model_dump(mode="json") if res.get("iv_forecast") else None,
            "long_vol_thesis": res["long_vol_thesis"].model_dump(mode="json") if res.get("long_vol_thesis") else None,
            "short_vol_thesis": res["short_vol_thesis"].model_dump(mode="json") if res.get("short_vol_thesis") else None,
            "critic_report": res["critic_report"].model_dump(mode="json") if res.get("critic_report") else None,
            "decision": cand.decision.value if cand else "no_trade",
            "selected_strategy": cand.model_dump(mode="json") if cand else None,
            "risk_report": res["risk_report"].model_dump(mode="json") if res.get("risk_report") else None,
            "rejection_reasons": res.get("rejection_reasons", []),
            "trace_events": res.get("trace_events", []),
        }

        receipt_str = json.dumps(receipt_data, indent=2, default=str)
        st.download_button(
            label="💾 Download Decision Receipt JSON",
            data=receipt_str,
            file_name=f"decision_receipt_{res.get('run_id')}.json",
            mime="application/json",
        )
        st.code(receipt_str, language="json")
    else:
        st.info("ℹ️ No active run to display receipt for. Run an analysis in the Analyze tab.")

    st.markdown("---")

    # 3. Attribution and Academic Citations
    st.markdown("### 📚 Research Foundations & Attribution")
    st.markdown("""
    * **TradingAgents Multi-Agent Dialectic Architecture:** Inspired by [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (Xiao et al., 2024), adapted for non-directional volatility and options distributions.
    * **Variance Risk Premium (VRP) Harvesting:** Bollerslev, Tauchen, Zhou (2009); Carr & Wu (2009).
    * **Post-Earnings Announcement IV Dynamics & Expected Move:** Patel et al. (2020).
    * **Deep Hedging & Greek Neutrality:** Buehler, Gonon, Teichmann, Wood (2019).
    """)
