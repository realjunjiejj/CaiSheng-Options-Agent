# Shared UI Components & Primitives

## 1. `AlpacaHeroCard`
Card container with high-contrast obsidian background, subtle border, and decision badge.

```html
<div class="alpaca-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <div>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 1.9em; font-weight: 800; color: #FFFFFF;">NVDA</span>
            <span style="color: #9DA7B3; margin-left: 10px; font-size: 1.15em; font-weight: 600;">$128.50</span>
        </div>
        <span class="decision-tag tag-long">LONG STRADDLE</span>
    </div>
    <p style="color: #E6EDF3; font-size: 1.02em; line-height: 1.6; margin: 12px 0 16px 0;">
        <strong>Long Volatility Thesis:</strong> Elevated analyst dispersion and post-earnings guidance uncertainty justify long volatility exposure.
    </p>
    <div class="alpaca-code-box">
        <span class="code-comment"># Alpaca Level-3 Multi-Leg Order Intent & Execution Blueprint</span><br>
        <span class="code-keyword">from</span> alpaca.trading.client <span class="code-keyword">import</span> TradingClient<br>
        trade_client = <span class="code-func">TradingClient</span>(API_KEY, SECRET_KEY, paper=<span class="code-keyword">True</span>)<br>
        <span class="code-comment"># Target: LONG_STRADDLE · Quantity: 1 unit(s) · Max Stress Loss: $500.00</span>
    </div>
</div>
```

---

## 2. `MetricGrid` & `MetricBox`
High-contrast financial metric boxes with monospace figures and colored labels.

```html
<div class="metric-grid">
    <div class="metric-box">
        <div class="metric-label">Market Implied Move (Brenner-Subrahmanyam)</div>
        <div class="metric-value" style="color: #FFD000;">±8.4%</div>
    </div>
    <div class="metric-box">
        <div class="metric-label">Forecast Move (Empirical Bayes Shrinkage)</div>
        <div class="metric-value" style="color: #0070F3;">±11.2% <span style="font-size: 0.65em; color: #FFFFFF;">(+2.80%)</span></div>
    </div>
    <div class="metric-box">
        <div class="metric-label">Max Risk (1% NAV Hard Cap)</div>
        <div class="metric-value" style="color: #FF3B30;">$500.00</div>
    </div>
</div>
```

---

## 3. `GreekChips`
Greeks and risk parameter chips.

```html
<span class="greek-chip">Δ Delta: +0.02</span>
<span class="greek-chip">Γ Gamma: 0.14</span>
<span class="greek-chip">V Vega: +$45.20/pt</span>
<span class="greek-chip">Θ Theta: -$12.40/day</span>
```

---

## 4. `PayoffDiagram`
Interactive Plotly options expiration and post-earnings IV crush payoff visualizer.

```python
# src/volagent/ui/charts.py
def create_payoff_plot(candidate, spot_price, implied_move_dollars):
    data = compute_payoff_curves(candidate, spot_price, implied_move_dollars)
    fig = go.Figure()
    fig.add_hline(y=0, line_dash="solid", line_color="rgba(255, 255, 255, 0.2)")
    fig.add_vline(x=spot_price, line_dash="dot", line_color="#FFD000")
    fig.add_trace(go.Scatter(x=data["spot_range"], y=data["pnl_at_expiry"], name="Expiration P&L", line=dict(color="#FFD000", width=3.5)))
    fig.add_trace(go.Scatter(x=data["spot_range"], y=data["pnl_at_exit"], name="Post-Event Expected Exit", line=dict(color="#9333EA", dash="dash")))
    return fig
```
