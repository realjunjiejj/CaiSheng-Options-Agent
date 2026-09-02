"""Academic Foundations & Quantitative Literature Page for CaiSheng."""

import streamlit as st
from volagent.research.bibliography import RESEARCH_BIBLIOGRAPHY, AcademicPaper
from volagent.ui.theme import ACCENT_IV, LONG_VOL_COLOR, PASS_COLOR, SHORT_VOL_COLOR, SURFACE_COLOR


def render_research_page() -> None:
    st.markdown("## 📚 Academic Foundations & Quantitative Literature")
    st.markdown("""
    **Options Alpha: Volatility & Event Trading Agents — Mathematical & Theoretical Grounding**
    Every quantitative pricing model, shrinkage forecast, tail risk measure, and multi-agent dialectic consensus
    mechanism in CaiSheng is derived directly from peer-reviewed financial economics and computer science literature.
    """)

    # Top summary metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Papers Backing Engine", str(len(RESEARCH_BIBLIOGRAPHY)))
    with c2:
        st.metric("Quantitative Subsystems", "6 Subsystems")
    with c3:
        st.metric("Risk Measure", "Rockafellar-Uryasev CVaR")
    with c4:
        st.metric("Multi-Agent Debate", "Du et al. (MIT/DeepMind)")

    st.markdown("---")

    # Category Filter
    categories = [
        "All Categories",
        "Volatility Dynamics & VRP",
        "Empirical Bayes Shrinkage",
        "Analytical Option Pricing",
        "Coherent Risk & CVaR",
        "Multi-Agent AI Debate",
        "Defined-Risk Derivatives",
    ]
    selected_cat = st.selectbox("🎯 Filter by Research Discipline", categories)

    cat_map = {
        "Volatility Dynamics & VRP": "volatility_dynamics",
        "Empirical Bayes Shrinkage": "empirical_bayes_shrinkage",
        "Analytical Option Pricing": "analytical_pricing",
        "Coherent Risk & CVaR": "coherent_risk_cvar",
        "Multi-Agent AI Debate": "multi_agent_ai",
        "Defined-Risk Derivatives": "defined_risk_derivatives",
    }

    filtered_papers = RESEARCH_BIBLIOGRAPHY
    if selected_cat != "All Categories":
        target = cat_map.get(selected_cat)
        filtered_papers = [p for p in RESEARCH_BIBLIOGRAPHY if p.category == target]

    st.markdown("### 📑 Peer-Reviewed Literature Registry")

    for p in filtered_papers:
        with st.expander(f"📖 [{p.paper_id}] {p.title} ({p.year}) — {p.authors}", expanded=True):
            st.markdown(f"**Publication:** *{p.journal}* | [DOI / Link]({p.doi_or_url})")
            st.markdown(f"**Core Theoretical Concept:** {p.core_concept}")

            st.markdown("**Mathematical Formulation:**")
            st.latex(p.latex_formula)

            c_left, c_right = st.columns(2)
            with c_left:
                st.markdown(f"**CaiSheng Subsystem:** `{p.volagent_subsystem}`")
            with c_right:
                st.markdown(f"**Options Alpha Edge:** {p.relevance_to_track_2}")

    st.markdown("---")

    # Interactive LaTeX Mathematical Sandbox
    st.markdown("### 📐 Key Mathematical Proofs in CaiSheng (Options Alpha)")


    tab1, tab2, tab3, tab4 = st.tabs([
        "1. Brenner-Subrahmanyam IV Inversion",
        "2. James-Stein Shrinkage Forecast",
        "3. Rockafellar-Uryasev Tail ES95",
        "4. Exact Signed Payoff Identity",
    ])

    with tab1:
        st.markdown("#### Analytical Fast Option Inversion (Brenner & Subrahmanyam 1988)")
        st.markdown("For short-dated ATM straddles ($S = K, r \\approx 0$):")
        st.latex(r"C_{\text{ATM}} = P_{\text{ATM}} \approx \frac{S_0 \sigma \sqrt{T}}{\sqrt{2\pi}} \approx 0.40 \cdot S_0 \cdot \sigma \cdot \sqrt{T}")
        st.latex(r"\sigma \approx \frac{\text{Straddle}_{\text{ATM}}}{0.80 \cdot S_0 \cdot \sqrt{T}}, \quad M_{\text{implied}} = \frac{\text{Straddle}_{\text{ATM}}}{S_0}")
        st.info("💡 Enables real-time inverted ATM implied move and base IV calibration without slow numerical root-finders.")

    with tab2:
        st.markdown("#### Hierarchical Empirical Bayes Move Forecast (James-Stein 1961)")
        st.markdown("Prevents overfitting to sparse sample size ($N < 10$) in quarterly earnings:")
        st.latex(r"\hat{m}_{\text{shrunk}} = w_t \cdot m_{\text{ticker}} + w_s \cdot m_{\text{sector}} + w_g \cdot m_{\text{global}}")
        st.latex(r"q_{50} = \hat{m}_{\text{shrunk}} \cdot (0.70 + 0.65 \cdot \text{magnitude\_pressure})")
        st.info("💡 Pulls noisy individual ticker jump estimates toward broader sector and macro jump distributions.")

    with tab3:
        st.markdown("#### Coherent Risk Optimization via Expected Shortfall (Rockafellar & Uryasev 2000)")
        st.markdown("Sub-additive coherent tail risk measure capturing asymmetric option tail risk:")
        st.latex(r"\text{Loss} = \max(-\text{PnL}, 0), \quad \text{VaR}_{95} = \text{Quantile}(\text{Loss}, 0.95)")
        st.latex(r"\text{ES}_{95} = \mathbb{E}[\text{Loss} \mid \text{Loss} \ge \text{VaR}_{95}], \quad \text{Score} = \mathbb{E}[\text{PnL}] - \lambda \cdot \text{ES}_{95}")
        st.info("💡 Penalizes extreme tail blowout scenarios rather than naive symmetric standard deviation.")

    with tab4:
        st.markdown("#### Exact Universal Signed Payoff Identity")
        st.markdown("Universal accounting identity for option strategy cash flows:")
        st.latex(r"\text{PnL}(S) = \text{Position Value}(S) - \text{Entry Cash Flow} - \text{Transaction Friction}")
        st.latex(r"\text{Long Straddle}(K) = 0 - \text{Debit} = -\text{Debit}, \quad \text{Short Iron Butterfly}(K) = 0 - (-\text{Credit}) = +\text{Credit}")
        st.info("💡 Guarantees mathematical sign consistency across analytical curves, Monte Carlo simulation, and execution ledger.")
