"""Judge-facing controlled ablation scoreboard."""

import html
import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from volagent.evaluation.evaluator import B3, B4, FULL, evaluate_benchmarks
from volagent.evaluation.benchmark_book import (
    SettledBenchmarkReceipt,
    aggregate_benchmark_receipts,
)
from volagent.evaluation.profitability import build_economic_evidence, build_latest_trade_story
from volagent.execution.ledger import ExecutionLedger


from volagent.config import PROJECT_ROOT


@st.cache_data(ttl=300, show_spinner=False)
def get_cached_benchmarks() -> dict:
    """Cache the deterministic replay so reruns and tab switches are instant."""
    return evaluate_benchmarks()


def _pnl_chart(summary: list[dict]) -> go.Figure:
    colors = {
        FULL: "#059669",  # Emerald 600 for CaiSheng
        B3: "#DC2626",    # Crimson for Single LLM
        B4: "#D97706",    # Amber for Unconstrained
    }
    models = [row["Model Benchmark"] for row in summary]
    pnl = [row["pnl_value"] for row in summary]
    breaches = [row["risk_breaches_value"] for row in summary]
    labels = [name.replace("CaiSheng ", "").replace("ALWAYS_", "") for name in models]

    figure = go.Figure(go.Bar(
        x=labels,
        y=pnl,
        marker_color=[colors.get(name, "#64748B") for name in models],
        customdata=breaches,
        text=[f"${value:+,.0f}" for value in pnl],
        textposition="outside",
        hovertemplate="%{x}<br>Executable P&L: $%{y:,.2f}<br>Risk breaches: %{customdata}<extra></extra>",
    ))
    figure.add_hline(y=0, line_width=1, line_color="#CBD5E1")
    figure.update_layout(
        height=340,
        margin=dict(l=20, r=20, t=30, b=70),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(color="#0F172A", family="Inter"),
        xaxis=dict(title=None, tickangle=-20, gridcolor="#F1F5F9", tickfont=dict(color="#475569")),
        yaxis=dict(title="Executable net P&L ($)", gridcolor="#F1F5F9", tickfont=dict(color="#475569")),
        showlegend=False,
    )
    return figure


def evidence_ladder_rows(receipt: dict) -> list[dict[str, str]]:
    """Return the compact claim-safe evidence table shown to judges."""
    tiers = receipt["profitability"]["tiers"]
    synthetic = tiers["synthetic_replay"]
    historical = receipt.get("historical_predictive_validation") or {}
    competition = receipt["competition"]
    full_account_pnl = competition.get("full_account_net_pnl")
    account_pnl_claim = (
        f"${float(full_account_pnl):+,.2f}"
        if full_account_pnl is not None
        else "Awaiting verified equity"
    )
    governed_pnl = float(
        competition.get("governed_closed_trade_pnl", competition.get("realized_pnl", 0.0))
    )
    return [
        {
            "Evidence": "Controlled synthetic replay",
            "Coverage": f"{synthetic['trades_count']} valid replay trades",
            "P&L claim": f"${synthetic['net_pnl']:+,.2f}",
            "Permitted conclusion": synthetic["allowed_claim"],
        },
        {
            "Evidence": "Historical predictive validation",
            "Coverage": f"{historical.get('evaluated_events_count', 0)} locked forecasts",
            "P&L claim": "Not claimed",
            "Permitted conclusion": historical.get("verdict", "No historical result available"),
        },
        {
            "Evidence": "Alpaca paper competition",
            "Coverage": (
                f"Full account equity · {competition['closed_trades_count']} "
                "governed broker-confirmed closed trades"
            ),
            "P&L claim": account_pnl_claim,
            "Permitted conclusion": (
                f"Full-account result; governed closed-trade P&L: ${governed_pnl:+,.2f}. "
                "Unattributed and unrealized activity is not claimed as CaiSheng alpha."
            ),
        },
    ]


def account_truth_html(receipt: dict) -> str:
    """Render account-wide P&L before any governed-trade or replay evidence."""
    competition = receipt.get("competition") or {}
    equity = competition.get("current_equity")
    full_pnl = competition.get("full_account_net_pnl")
    governed_pnl = float(
        competition.get("governed_closed_trade_pnl", competition.get("realized_pnl", 0.0))
    )
    difference = competition.get("unattributed_and_unrealized_difference")

    def money(value: object) -> str:
        return f"${float(value):+,.2f}" if value is not None else "AWAITING VERIFIED EQUITY"

    full_color = "#059669" if full_pnl is not None and float(full_pnl) >= 0.0 else "#DC2626"
    return f"""<section style="border:1px solid #E2E8F0;background:#FFFFFF;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.04);padding:18px 22px;margin-bottom:20px;">
<div style="font-family:'JetBrains Mono',monospace;color:#D97706;font-size:.76em;font-weight:800;letter-spacing:0.06em;margin-bottom:12px;">ALPACA ACCOUNT TRUTH · $100,000 MANDATE</div>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;font-family:'JetBrains Mono',monospace;">
<div><span style="color:#64748B;font-size:.70em;">CURRENT EQUITY</span><br><strong style="font-size:1.15em;color:#0F172A;">{f'${float(equity):,.2f}' if equity is not None else 'UNVERIFIED'}</strong></div>
<div><span style="color:#64748B;font-size:.70em;">FULL ALPACA ACCOUNT P&amp;L</span><br><strong style="font-size:1.15em;color:{full_color};">{money(full_pnl)}</strong></div>
<div><span style="color:#64748B;font-size:.70em;">GOVERNED CLOSED-TRADE P&amp;L</span><br><strong style="font-size:1.15em;color:#0F172A;">{money(governed_pnl)}</strong></div>
<div><span style="color:#64748B;font-size:.70em;">UNATTRIBUTED / UNREALIZED DIFFERENCE</span><br><strong style="font-size:1.15em;color:#64748B;">{money(difference)}</strong></div>
</div>
<div style="color:#64748B;font-size:.80em;margin-top:12px;border-top:1px solid #F1F5F9;padding-top:8px;">The full-account result is the headline. Only broker-confirmed entry-to-exit lifecycles count as governed CaiSheng P&amp;L; replay remains separate.</div>
</section>"""


def trade_story_html(story: dict) -> str:
    """Render the four judge questions as one compact, evidence-labelled trade tape."""
    what = story["what"]
    why = story["why"]
    risk = story["risk"]
    result = story["result"]
    pnl = float(result.get("net_pnl") or 0.0)
    result_class = "cs-story-profit" if pnl > 0.0 else "cs-story-loss" if pnl < 0.0 else "cs-story-flat"
    contracts = " · ".join(str(value) for value in what.get("contracts", []))
    contract_line = f"<div class=\"cs-story-contracts\">{html.escape(contracts)}</div>" if contracts else ""

    def stop(index: str, question: str, headline: str, detail: str, extra_class: str = "") -> str:
        return f"""<div class="cs-story-stop {extra_class}">
<div class="cs-story-index">{index}</div>
<div class="cs-story-question">{html.escape(question)}</div>
<div class="cs-story-value">{html.escape(headline)}</div>
<div class="cs-story-detail">{html.escape(detail)}</div>
</div>"""

    return f"""<section class="cs-story-shell" aria-label="30-second judge trade answer">
<div class="cs-story-header">
<div>
<div class="cs-story-kicker">30-SECOND JUDGE ANSWER</div>
<div class="cs-story-title">Four answers. Broker evidence only.</div>
</div>
<div class="cs-story-evidence">{html.escape(str(story['evidence_label']))}</div>
</div>
<div class="cs-story-tape">
{stop('01', 'WHAT DID IT TRADE?', str(what['headline']), str(what.get('detail', '')))}
{stop('02', 'WHY DID IT TRADE?', str(why['headline']), str(why.get('detail', '')))}
{stop('03', 'HOW MUCH WAS AT RISK?', str(risk['headline']), str(risk.get('detail', '')))}
{stop('04', 'HOW MUCH DID IT MAKE?', str(result['headline']), str(result.get('detail', '')), result_class)}
</div>
{contract_line}
</section>"""


def benchmark_tape_html(aggregate: dict, *, locked_count: int) -> str:
    """Render the judge-level answer for point-in-time locked policy comparisons."""
    opportunities = int(aggregate.get("opportunities", 0))
    policies = list(aggregate.get("policies", []))
    evidence_label = "SHADOW · NOT COMPETITION P&L"

    def stop(index: str, question: str, headline: str, detail: str, extra_class: str = "") -> str:
        return f"""<div class="cs-story-stop {extra_class}">
<div class="cs-story-index">{index}</div>
<div class="cs-story-question">{html.escape(question)}</div>
<div class="cs-story-value">{html.escape(headline)}</div>
<div class="cs-story-detail">{html.escape(detail)}</div>
</div>"""

    if not opportunities or not policies:
        tape = "".join(
            (
                stop("01", "LOCKED BEFORE OUTCOME", f"{locked_count} locked", "Exact contracts, entry quotes, risk and exit time are sealed."),
                stop("02", "SETTLED OPPORTUNITIES", "0 settled", "Fresh common exit quotes are still required."),
                stop("03", "POLICIES COMPARED", "7 policies", "No trade, stock, long vol, short vol, implied anchor, no residual, Full."),
                stop("04", "EVIDENCE STATUS", "AWAITING SETTLEMENT", "No economic superiority claim is permitted yet.", "cs-story-flat"),
            )
        )
    else:
        full = next(row for row in policies if row["policy_id"] == "FULL_CAISHENG")
        alternatives = [row for row in policies if row["policy_id"] != "FULL_CAISHENG"]
        best = max(alternatives, key=lambda row: float(row.get("net_pnl", 0.0)))
        full_pnl = float(full.get("net_pnl", 0.0))
        best_pnl = float(best.get("net_pnl", 0.0))
        edge = full_pnl - best_pnl
        edge_class = "cs-story-profit" if edge > 0 else "cs-story-loss" if edge < 0 else "cs-story-flat"
        tape = "".join(
            (
                stop("01", "FULL CAISHENG", f"${full_pnl:+,.2f}", f"{full.get('trades', 0)} shadow trades across {opportunities} paired opportunities."),
                stop("02", "BEST ALTERNATIVE", f"${best_pnl:+,.2f}", str(best["policy_id"])),
                stop("03", "EDGE VS BEST", f"${edge:+,.2f}", "Full minus the best locked alternative.", edge_class),
                stop("04", "PAIRED SAMPLE", f"{opportunities} settled", f"{locked_count} live intents locked in the ledger."),
            )
        )

    return f"""<section class="cs-story-shell" aria-label="Locked shadow benchmark comparison">
<div class="cs-story-header">
<div>
<div class="cs-story-kicker">LOCKED POLICY TEST</div>
<div class="cs-story-title">Did CaiSheng beat a fair alternative?</div>
</div>
<div class="cs-story-evidence">{html.escape(evidence_label)}</div>
</div>
<div class="cs-story-tape">{tape}</div>
</section>"""


def _shadow_policy_chart(policies: list[dict]) -> go.Figure:
    """Compact signed-P&L chart; one focal color and neutral controls."""
    labels = [str(row["policy_id"]).replace("FULL_", "").replace("CAISHENG_", "") for row in policies]
    values = [float(row.get("net_pnl", 0.0)) for row in policies]
    colors = ["#059669" if row["policy_id"] == "FULL_CAISHENG" else "#94A3B8" for row in policies]
    custom = [
        [int(row.get("trades", 0)), float(row.get("max_drawdown", 0.0)), float(row.get("spread_fees_slippage", 0.0))]
        for row in policies
    ]
    figure = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colors,
            customdata=custom,
            text=[f"${value:+,.0f}" for value in values],
            textposition="outside",
            hovertemplate=(
                "%{y}<br>Shadow net P&L: $%{x:,.2f}<br>Trades: %{customdata[0]}"
                "<br>Max drawdown: $%{customdata[1]:,.2f}<br>Costs: $%{customdata[2]:,.2f}<extra></extra>"
            ),
        )
    )
    figure.add_vline(x=0, line_width=1, line_color="#CBD5E1")
    figure.update_layout(
        height=300,
        margin=dict(l=20, r=55, t=15, b=30),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(color="#0F172A", family="Inter", size=11),
        xaxis=dict(title="Locked shadow net P&L ($)", gridcolor="#F1F5F9", tickfont=dict(color="#475569")),
        yaxis=dict(title=None, autorange="reversed", gridcolor="#F1F5F9", tickfont=dict(color="#475569")),
        showlegend=False,
    )
    return figure


def _load_historical_results() -> dict:
    path = PROJECT_ROOT / "data" / "evaluation" / "oos_evaluation_results.json"
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _current_economic_evidence(replay_results: dict) -> dict:
    ledger = ExecutionLedger()
    metadata = ledger.get_or_init_competition_metadata(starting_nav=100_000.0)
    snapshot = ledger.get_latest_portfolio_snapshot()
    current_equity = None
    if snapshot and not snapshot.get("is_stale"):
        current_equity = snapshot.get("equity")
    return build_economic_evidence(
        replay_results=replay_results,
        historical_results=_load_historical_results(),
        closed_trades=ledger.list_closed_trades(),
        starting_nav=float(metadata.get("starting_nav", 100_000.0)),
        current_equity=current_equity,
    )


def _current_trade_story() -> dict:
    ledger = ExecutionLedger()
    closed_trades = ledger.list_closed_trades()
    orders: dict[str, dict] = {}
    for trade in closed_trades:
        for field in ("entry_order_id", "exit_order_id"):
            client_order_id = str(trade.get(field, ""))
            if client_order_id:
                order = ledger.get_order_by_client_order_id(client_order_id)
                if order:
                    orders[client_order_id] = order
    return build_latest_trade_story(closed_trades, ledger.list_decision_records(), orders)


def _current_live_benchmark_evidence() -> tuple[dict, int]:
    """Load only live shadow evidence; replay records never enter this comparison."""
    ledger = ExecutionLedger()
    locked_count = 0
    for row in ledger.list_benchmark_intents():
        try:
            payload = json.loads(row["raw_payload"])
            if payload.get("data_mode") == "live":
                locked_count += 1
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
    receipts: list[SettledBenchmarkReceipt] = []
    for row in ledger.list_benchmark_outcomes():
        try:
            receipt = SettledBenchmarkReceipt.model_validate_json(row["raw_payload"])
            if receipt.data_mode == "live":
                receipts.append(receipt)
        except (KeyError, TypeError, ValueError):
            continue
    return aggregate_benchmark_receipts(receipts), locked_count


def render_scoreboard_page() -> None:
    with st.spinner("Running sealed replay on first load…"):
        results = get_cached_benchmarks()

    summary = results.get("summary", [])

    receipt = _current_economic_evidence(results)
    st.markdown(account_truth_html(receipt), unsafe_allow_html=True)

    story = _current_trade_story()
    st.markdown(trade_story_html(story), unsafe_allow_html=True)

    shadow_aggregate, shadow_locked_count = _current_live_benchmark_evidence()
    st.markdown(
        benchmark_tape_html(shadow_aggregate, locked_count=shadow_locked_count),
        unsafe_allow_html=True,
    )
    if shadow_aggregate.get("opportunities"):
        st.plotly_chart(
            _shadow_policy_chart(shadow_aggregate["policies"]),
            width="stretch",
            config={"displayModeBar": False},
        )

    ladder = evidence_ladder_rows(receipt)
    synthetic_tier = receipt["profitability"]["tiers"]["synthetic_replay"]
    historical = receipt.get("historical_predictive_validation") or {}

    st.markdown("### Supporting validation")
    st.caption("Useful context—not Alpaca competition P&L.")
    historical_column, replay_column = st.columns(2)
    historical_column.metric(
        "Historical forecast check",
        f"{historical.get('evaluated_events_count', 0)} events",
    )
    historical_column.caption(str(historical.get("verdict", "Unavailable")))
    replay_column.metric(
        "Controlled safety replay",
        f"${synthetic_tier['net_pnl']:+,.0f}",
    )
    replay_column.caption(f"{synthetic_tier['trades_count']} synthetic trades · not competition P&L")

    with st.expander("Technical proof and downloadable receipts", expanded=False):
        st.markdown("#### Claim boundaries")
        st.dataframe(ladder, width="stretch", hide_index=True)
        st.markdown("#### Broker lineage")
        st.json(story["proof"])

        receipt_column, ablation_column = st.columns(2)
        receipt_column.download_button(
            "Download economic receipt",
            data=json.dumps(receipt, indent=2),
            file_name="caisheng_economic_evidence_receipt.json",
            mime="application/json",
        )
        ablation_column.download_button(
            "Download ablation receipt",
            data=json.dumps(results, indent=2),
            file_name="caisheng_ablation_receipt.json",
            mime="application/json",
        )
        st.download_button(
            "Download locked shadow benchmark receipt",
            data=json.dumps(shadow_aggregate, indent=2),
            file_name="caisheng_locked_shadow_benchmarks.json",
            mime="application/json",
        )

        if results.get("evaluation_errors"):
            st.error(f"{len(results['evaluation_errors'])} replay scenario(s) failed evaluation.")
        if summary:
            st.markdown("#### Risk-gate ablation")
            st.caption(
                "Synthetic functional test only. Every variant uses the same snapshots, contracts, seed, and accounting."
            )
            st.plotly_chart(_pnl_chart(summary), width="stretch", config={"displayModeBar": False})
            st.dataframe(results.get("variant_controls", []), width="stretch", hide_index=True)
