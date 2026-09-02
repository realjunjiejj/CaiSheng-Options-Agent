"""Concise, credential-free judge overview for CaiSheng."""

import html

import streamlit as st

from volagent.config import load_config


def judge_overview_html(
    *,
    starting_nav: float,
    hard_risk_dollars: float,
    max_entries_per_day: int,
    symbols: list[str],
) -> str:
    """Return the one-screen product and judging narrative."""
    universe = " · ".join(html.escape(symbol) for symbol in symbols)
    return f"""<main class="cs-overview">
<section class="cs-overview-hero">
<div class="cs-overview-kicker">VOLATILITY-FIRST OPTIONS ALPHA</div>
<h1>Trade movement only when the edge survives debate.</h1>
<p>CaiSheng compares executable implied movement with a calibrated forecast, lets opposing agents argue the volatility case, then gives deterministic code the final word on risk and execution.</p>
<div class="cs-overview-stats" aria-label="CaiSheng operating mandate">
<div><strong>4</strong><span>specialist roles</span></div>
<div><strong>20</strong><span>risk checks</span></div>
<div><strong>${hard_risk_dollars:,.0f}</strong><span>hard risk / trade</span></div>
<div><strong>{max_entries_per_day}</strong><span>new entry / day</span></div>
</div>
</section>

<section class="cs-overview-section">
<div class="cs-overview-heading"><span>DECISION PATH</span><small>One auditable chain from market data to broker receipt</small></div>
<div class="cs-flow" aria-label="CaiSheng decision flow">
<div><b>01</b><strong>Observe</strong><span>Alpaca stocks + options</span></div>
<div><b>02</b><strong>Estimate</strong><span>Implied move + residual</span></div>
<div><b>03</b><strong>Debate</strong><span>Long vs short volatility</span></div>
<div><b>04</b><strong>Challenge</strong><span>Model-risk critic</span></div>
<div><b>05</b><strong>Govern</strong><span>20 deterministic checks</span></div>
<div><b>06</b><strong>Execute</strong><span>Alpaca MLEG limit order</span></div>
</div>
</section>

<section class="cs-overview-section">
<div class="cs-overview-heading"><span>ALPACA IMPLEMENTATION</span><small>Native components with one non-bypassable order boundary</small></div>
<div class="cs-stack-list">
<div><strong>Trading API</strong><span>Paper account state, live option chains, multi-leg orders, fills, monitoring and exits</span><code>OrderClass.MLEG</code></div>
<div><strong>MCP</strong><span>Audited account, position, market-clock and order-status tools</span><code>FastMCP</code></div>
<div><strong>CLI</strong><span>Preflight, reconciliation, runtime control and signed operational receipts</span><code>fail closed</code></div>
</div>
</section>

<section class="cs-overview-footer">
<div><span>MANDATE</span><strong>${starting_nav:,.0f} Alpaca paper account</strong></div>
<div><span>UNIVERSE</span><strong>{universe}</strong></div>
<div><span>EVIDENCE RULE</span><strong>Only broker-confirmed closes count as competition P&amp;L</strong></div>
</section>
</main>"""


def render_overview_page() -> None:
    """Render the default judge landing page without broker credentials."""
    settings = load_config("config/competition.yaml")
    starting_nav = float(settings.mandate.competition_initial_nav)
    hard_risk_dollars = starting_nav * float(settings.risk.hard_max_risk_nav_pct)
    st.markdown(
        judge_overview_html(
            starting_nav=starting_nav,
            hard_risk_dollars=hard_risk_dollars,
            max_entries_per_day=settings.mandate.max_new_entries_per_day,
            symbols=list(settings.competition.daily_volatility_symbols),
        ),
        unsafe_allow_html=True,
    )
