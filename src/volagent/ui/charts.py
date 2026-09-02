"""Alpaca Pro Terminal Plotly visualizer for Options Payoff Curves and Greeks."""

from typing import Any
import numpy as np
import plotly.graph_objects as go

from volagent.domain.strategies import StrategyCandidate
from volagent.quant.payoff import compute_payoff_curves
from volagent.ui.theme import (
    ALPACA_CARD,
    ALPACA_DARK,
    ALPACA_YELLOW,
    CYAN_ACCENT,
    GREEN_PROFIT,
    PURPLE_VOL,
    RED_LOSS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def create_payoff_plot(
    candidate: StrategyCandidate,
    spot_price: float,
    implied_move_dollars: float,
) -> go.Figure:
    """Generate high-contrast, Alpaca Pro-style options payoff diagram."""
    data = compute_payoff_curves(candidate, spot_price, implied_move_dollars)

    spots = data["spot_range"]
    pnl_exp = data["pnl_at_expiry"]
    pnl_exit = data["pnl_at_exit"]

    fig = go.Figure()

    # 1. Zero Baseline
    fig.add_hline(y=0, line_dash="solid", line_color="#CBD5E1", line_width=1.5)

    # 2. Spot Price Indicator Line
    fig.add_vline(
        x=spot_price,
        line_dash="dot",
        line_color=ALPACA_YELLOW,
        line_width=2,
        annotation_text=f"Spot ${spot_price:.2f}",
        annotation_position="top left",
        annotation_font=dict(color=ALPACA_YELLOW, size=12, family="JetBrains Mono"),
    )

    # 3. Break-Even Boundary Markers
    for be in data.get("break_evens", []):
        fig.add_vline(
            x=be,
            line_dash="dash",
            line_color="#94A3B8",
            line_width=1.5,
            annotation_text=f"BE ${be:.2f}",
            annotation_position="bottom right",
            annotation_font=dict(color=TEXT_MUTED, size=11, family="SFMono-Regular"),
        )

    # 4. Primary Payoff Curve (Alpaca Yellow or Electric Blue)
    is_straddle = "straddle" in candidate.strategy_id
    primary_color = CYAN_ACCENT if is_straddle else ALPACA_YELLOW

    fig.add_trace(
        go.Scatter(
            x=spots,
            y=pnl_exp,
            mode="lines",
            name="Expiration",
            line=dict(color=primary_color, width=3.5),
        )
    )

    # 5. Expected Exit Curve (Post-Earnings IV Crush)
    fig.add_trace(
        go.Scatter(
            x=spots,
            y=pnl_exit,
            mode="lines",
            name="Expected exit after IV crush",
            line=dict(color=PURPLE_VOL, width=2.5, dash="dash"),
        )
    )

    # Light, recording-friendly layout aligned with the application canvas.
    fig.update_layout(
        title=dict(
            text=f"<b>PAYOFF DISTRIBUTION · {candidate.decision.value.replace('_', ' ').upper()}</b>",
            x=0.0,
            xanchor="left",
            font=dict(family="SFMono-Regular", size=13, color=TEXT_PRIMARY),
        ),
        xaxis=dict(
            title=dict(text="Underlying Price ($)", font=dict(color=TEXT_MUTED, size=12)),
            gridcolor="#F1F5F9",
            zerolinecolor="#CBD5E1",
            tickfont=dict(family="SFMono-Regular", color=TEXT_MUTED),
        ),
        yaxis=dict(
            title=dict(text="Net Profit / Loss ($)", font=dict(color=TEXT_MUTED, size=12)),
            gridcolor="#F1F5F9",
            zerolinecolor="#CBD5E1",
            tickfont=dict(family="SFMono-Regular", color=TEXT_MUTED),
            tickprefix="$",
        ),
        template="plotly_white",
        paper_bgcolor=ALPACA_CARD,
        plot_bgcolor=ALPACA_DARK,
        hovermode="x unified",
        height=390,
        margin=dict(l=50, r=24, t=50, b=82),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.20,
            xanchor="left",
            x=0,
            font=dict(family="-apple-system", size=10, color=TEXT_SECONDARY),
        ),
    )

    return fig


def create_greeks_bar_chart(candidate: StrategyCandidate) -> go.Figure:
    """Generate analytical Greeks breakdown bar chart."""
    greeks = ["Delta (Δ)", "Gamma (Γ)", "Vega (V / pt)", "Theta (Θ / day)"]
    values = [candidate.net_delta, candidate.net_gamma, candidate.net_vega, candidate.net_theta]
    colors = [CYAN_ACCENT, ALPACA_YELLOW, PURPLE_VOL, RED_LOSS]

    fig = go.Figure(
        go.Bar(
            x=greeks,
            y=values,
            marker_color=colors,
            text=[f"{v:+.2f}" for v in values],
            textposition="auto",
        )
    )
    fig.update_layout(
        title=dict(text="<b>ANALYTICAL GREEKS EXPOSURE</b>", font=dict(family="JetBrains Mono", size=13, color=TEXT_PRIMARY)),
        template="plotly_dark",
        paper_bgcolor=ALPACA_CARD,
        plot_bgcolor=ALPACA_DARK,
        margin=dict(l=30, r=20, t=40, b=30),
        yaxis=dict(gridcolor="rgba(255, 255, 255, 0.05)"),
    )
    return fig


def create_stress_heatmap(candidate: StrategyCandidate) -> go.Figure:
    """Generate 2D Price vs IV stress loss heatmap."""
    price_shocks = ["-15%", "-10%", "-5%", "0%", "+5%", "+10%", "+15%"]
    iv_shocks = ["-30%", "-15%", "0%", "+15%", "+30%"]

    z_matrix = []
    for p in [-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15]:
        row = []
        for v in [-0.30, -0.15, 0.0, 0.15, 0.30]:
            key = f"P_{int(p*100):+03d}_IV_{int(v*100):+03d}"
            loss = candidate.stress_losses.get(key, candidate.max_loss)
            row.append(loss)
        z_matrix.append(row)

    fig = go.Figure(
        data=go.Heatmap(
            z=z_matrix,
            x=iv_shocks,
            y=price_shocks,
            colorscale="Reds",
            colorbar=dict(title="Stress Loss ($)"),
        )
    )
    fig.update_layout(
        title=dict(text="<b>2D STRESS MATRIX (Price vs IV Shock)</b>", font=dict(family="JetBrains Mono", size=13, color=TEXT_PRIMARY)),
        xaxis=dict(title="IV Shock"),
        yaxis=dict(title="Price Shock"),
        template="plotly_dark",
        paper_bgcolor=ALPACA_CARD,
        plot_bgcolor=ALPACA_DARK,
        margin=dict(l=40, r=30, t=40, b=30),
    )
    return fig

def create_alpaca_equity_chart(current_equity: float = 100_000.0) -> go.Figure:
    """Generate sleek, continuous canvas intraday equity curve chart."""
    times = ["8 AM", "9 AM", "10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM"]
    values = [current_equity] * len(times)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=times,
            y=values,
            mode="lines",
            line=dict(color="#FACC15", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(250, 204, 21, 0.08)",
            hoverinfo="x+y",
            hovertemplate="$%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=170,
        margin=dict(l=0, r=0, t=10, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            showline=False,
            color="#94A3B8",
            tickfont=dict(family="JetBrains Mono", size=10),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#F1F5F9",
            showline=False,
            color="#94A3B8",
            tickformat="$,.0f",
            tickfont=dict(family="JetBrains Mono", size=10),
            range=[0, max(current_equity * 1.5, 150_000.0)],
        ),
        showlegend=False,
    )
    return fig
