"""Interactive Rough Volatility, Markovian Lifting & Path Signature Simulator."""

import math
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from volagent.quant.rough_vol import (
    compute_path_signature_2d,
    compute_rough_vol_smile,
    simulate_lifted_heston,
)
from volagent.ui.theme import (
    ALPACA_DARK,
    ALPACA_YELLOW,
    CYAN_ACCENT,
    GREEN_PROFIT,
    PURPLE_VOL,
    RED_LOSS,
    SURFACE_COLOR,
)


def render_rough_vol_simulator_page() -> None:
    st.markdown("## 🌪️ Frontier Quantitative Engine: Rough Volatility & Markovian Lifting")
    st.markdown("""
    **Options Alpha Research Frontier — Non-Markovian Volatility Dynamics & Path Signatures**
    Standard Black-Scholes and Heston diffusion models assume volatility is a Markovian semimartingale ($H=0.5$).
    Empirical high-frequency options studies motivate a **rough-volatility approximation ($H \\approx 0.10$)**,
    producing a severe power-law blowup in short-term implied volatility skew $\\sim T^{H-1/2}$ that standard models fail to fit.
    """)

    st.markdown("---")

    # Interactive Simulator Sidebar / Column Controls
    c_ctrl1, c_ctrl2, c_ctrl3, c_ctrl4 = st.columns(4)

    with c_ctrl1:
        hurst = st.slider(
            "🌊 Hurst Parameter (H)",
            min_value=0.05,
            max_value=0.45,
            value=0.10,
            step=0.01,
            help="H < 0.5 indicates Rough Volatility. H = 0.5 is standard Brownian motion.",
        )
    with c_ctrl2:
        n_factors = st.slider(
            "⚙️ Markovian Lifting Factors (n)",
            min_value=2,
            max_value=12,
            value=8,
            step=1,
            help="Number of exponential OU factors approximating the singular fractional kernel K(t).",
        )
    with c_ctrl3:
        nu_vol_of_vol = st.slider(
            "⚡ Vol of Vol (ν)",
            min_value=0.10,
            max_value=0.80,
            value=0.40,
            step=0.05,
            help="Volatility of variance process.",
        )
    with c_ctrl4:
        time_to_exp = st.slider(
            "⏳ Time to Expiration (T years)",
            min_value=0.01,
            max_value=0.30,
            value=0.05,
            step=0.01,
            help="Option maturity. Short maturities (T < 0.05) exhibit explosive rough skew.",
        )

    col_sub1, col_sub2 = st.columns(2)
    with col_sub1:
        rho_corr = st.slider(
            "📉 Leverage Correlation (ρ)",
            min_value=-0.90,
            max_value=0.00,
            value=-0.70,
            step=0.05,
            help="Correlation between stock price and instantaneous volatility shocks.",
        )
    with col_sub2:
        base_spot = st.number_input("💵 Spot Price ($)", min_value=50.0, max_value=500.0, value=200.0, step=10.0)

    # Compute Rough Volatility Smile and Simulation
    with st.spinner("Computing Lifted Heston Monte Carlo and Inverting Implied Volatility Smile..."):
        smile_data = compute_rough_vol_smile(
            spot=base_spot,
            v0=0.04,  # 20% base IV
            hurst=hurst,
            n_factors=n_factors,
            nu=nu_vol_of_vol,
            rho=rho_corr,
            time_to_expiry=time_to_exp,
            strike_range_pct=0.15,
            n_strikes=17,
            n_paths=3000,
            random_seed=42,
        )

    st.markdown("---")

    # 1. Plotly Chart: Implied Volatility Smile Comparison
    st.markdown("### 📈 1. Implied Volatility Smile & Skew: Rough Volatility vs. Standard Diffusion")

    strikes = smile_data["strikes"]
    rough_ivs = smile_data["rough_ivs"] * 100.0
    std_ivs = smile_data["standard_ivs"] * 100.0
    base_iv_pct = smile_data["atm_iv"] * 100.0

    fig_smile = go.Figure()

    # Rough Volatility Curve
    fig_smile.add_trace(go.Scatter(
        x=strikes,
        y=rough_ivs,
        mode="lines+markers",
        name=f"Rough Volatility (H={hurst:.2f}, n={n_factors})",
        line=dict(color=CYAN_ACCENT, width=3),
        marker=dict(size=6, color=CYAN_ACCENT),
    ))

    # Standard Heston Diffusion Curve (H=0.5)
    fig_smile.add_trace(go.Scatter(
        x=strikes,
        y=std_ivs,
        mode="lines",
        name="Standard Diffusion (H=0.50 Markovian Heston)",
        line=dict(color=PURPLE_VOL, width=2, dash="dash"),
    ))

    # Flat Black-Scholes Base
    fig_smile.add_trace(go.Scatter(
        x=strikes,
        y=[base_iv_pct] * len(strikes),
        mode="lines",
        name="Black-Scholes Flat IV (No Skew)",
        line=dict(color="#8B949E", width=1, dash="dot"),
    ))

    # Strike Vertical Line at ATM
    fig_smile.add_vline(x=base_spot, line_width=1, line_dash="dash", line_color=ALPACA_YELLOW, annotation_text="ATM Strike")

    fig_smile.update_layout(
        title=f"Implied Volatility Smile (T = {time_to_exp:.3f} yrs / {time_to_exp*365:.1f} days, H = {hurst:.2f})",
        xaxis_title="Strike Price ($)",
        yaxis_title="Implied Volatility (%)",
        template="plotly_dark",
        paper_bgcolor=ALPACA_DARK,
        plot_bgcolor=SURFACE_COLOR,
        font=dict(family="JetBrains Mono, monospace", color="#C9D1D9"),
        height=420,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    st.plotly_chart(fig_smile, width="stretch")

    # 2. Sub-charts: Path Simulation & Skew Term Structure
    col_paths, col_skew = st.columns(2)

    with col_paths:
        st.markdown("### 🧬 2. Rough Instantaneous Volatility Trajectories")
        t_grid = smile_data["time_grid"] * 365.0  # In days
        vol_paths = smile_data["vol_paths"] * 100.0

        fig_paths = go.Figure()
        colors = [CYAN_ACCENT, ALPACA_YELLOW, GREEN_PROFIT, PURPLE_VOL, "#FF7B72"]
        for p in range(vol_paths.shape[0]):
            fig_paths.add_trace(go.Scatter(
                x=t_grid,
                y=vol_paths[p],
                mode="lines",
                name=f"Path {p+1}",
                line=dict(color=colors[p % len(colors)], width=1.5),
            ))

        fig_paths.update_layout(
            title=f"Simulated Instantaneous Volatility $V_t^{{1/2}}$ (n={n_factors} Lifted OU Factors)",
            xaxis_title="Time (Days)",
            yaxis_title="Volatility (%)",
            template="plotly_dark",
            paper_bgcolor=ALPACA_DARK,
            plot_bgcolor=SURFACE_COLOR,
            font=dict(family="JetBrains Mono, monospace", color="#C9D1D9"),
            height=360,
            margin=dict(l=30, r=30, t=50, b=30),
            showlegend=False,
        )
        st.plotly_chart(fig_paths, width="stretch")

    with col_skew:
        st.markdown("### 💥 3. At-The-Money Skew Explosion ($T \\to 0$)")
        # Theoretical Skew Term Structure: S(T) ~ T^(H - 0.5)
        maturities = np.linspace(0.005, 0.25, 40)
        rough_skew_curve = (maturities ** (hurst - 0.5)) * 0.15
        std_skew_curve = np.full_like(maturities, 0.15)

        fig_skew = go.Figure()
        fig_skew.add_trace(go.Scatter(
            x=maturities * 365.0,
            y=rough_skew_curve,
            mode="lines",
            name=f"Rough Vol Skew ~ T^({hurst-0.5:.2f})",
            line=dict(color=CYAN_ACCENT, width=3),
        ))
        fig_skew.add_trace(go.Scatter(
            x=maturities * 365.0,
            y=std_skew_curve,
            mode="lines",
            name="Standard Diffusion (Flat Skew ~ O(1))",
            line=dict(color=PURPLE_VOL, width=2, dash="dash"),
        ))

        fig_skew.update_layout(
            title="ATM Implied Volatility Skew $|\\partial \\sigma / \\partial k|$ vs. Maturity",
            xaxis_title="Maturity T (Days)",
            yaxis_title="ATM Skew Magnitude",
            template="plotly_dark",
            paper_bgcolor=ALPACA_DARK,
            plot_bgcolor=SURFACE_COLOR,
            font=dict(family="JetBrains Mono, monospace", color="#C9D1D9"),
            height=360,
            margin=dict(l=30, r=30, t=50, b=30),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_skew, width="stretch")

    st.markdown("---")

    # 3. Path Signatures Decomposition
    st.markdown("### 🔣 4. Rough Path Signature Analysis (Lyons 1998)")
    st.markdown("""
    Path Signatures $\\mathbb{S}(X)$ encode the continuous geometric trajectory of stock prices and instantaneous volatility
    into a coordinate-free tensor series of iterated integrals:
    """)

    sample_time = smile_data["time_grid"]
    sample_spot = smile_data["spot_paths"][0]
    sig_features = compute_path_signature_2d(sample_time, sample_spot, depth=2)

    col_sig1, col_sig2 = st.columns(2)
    with col_sig1:
        st.markdown(r"**Level 1 Increments ($\Delta X$):**")
        st.write({
            "Time Increment (Δt)": f"{sig_features['sig_t']:.4f}",
            "Spot Increment (ΔS)": f"{sig_features['sig_s']:+.4f}",
        })
        st.markdown("**Levy Area (Roughness Measure):**")
        st.metric("Levy Area (Signed Area Enclosed)", f"{sig_features['levy_area']:.6f}")

    with col_sig2:
        st.markdown(r"**Level 2 Iterated Integrals ($\int X^i dX^j$):**")
        sig_table = [
            {"Coordinate": "∫ t dt", "Value": f"{sig_features['sig_tt']:.6f}", "Interpretation": "Time quadratic progression"},
            {"Coordinate": "∫ t dS", "Value": f"{sig_features['sig_ts']:+.6f}", "Interpretation": "Time-weighted spot acceleration"},
            {"Coordinate": "∫ S dt", "Value": f"{sig_features['sig_st']:+.6f}", "Interpretation": "Cumulative spot level over time"},
            {"Coordinate": "∫ S dS", "Value": f"{sig_features['sig_ss']:.6f}", "Interpretation": "Realized spot quadratic variation"},
        ]
        st.dataframe(sig_table, width="stretch")
