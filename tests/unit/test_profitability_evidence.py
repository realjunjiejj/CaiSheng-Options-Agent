"""Behavior tests for CaiSheng's evidence-tiered profitability report."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from volagent.evaluation.profitability import (
    build_economic_evidence,
    build_latest_trade_story,
    build_profitability_report,
    outcomes_from_closed_trades,
    write_economic_evidence_receipt,
)
from volagent.ui.pages.scoreboard import (
    competition_evidence_pending_html,
    controlled_validation_html,
    evidence_ladder_rows,
    trade_story_html,
)


def test_profitability_report_never_blends_evidence_tiers():
    outcomes = [
        {
            "trade_id": "sim-1",
            "event_id": "evt-sim",
            "symbol": "AAA",
            "strategy": "long_straddle",
            "closed_at": "2026-08-25T20:00:00+00:00",
            "net_pnl": 125.0,
            "max_loss": 500.0,
            "evidence_tier": "synthetic_replay",
        },
        {
            "trade_id": "proxy-1",
            "event_id": "evt-proxy",
            "symbol": "BBB",
            "strategy": "long_straddle",
            "closed_at": "2026-08-26T20:00:00+00:00",
            "net_pnl": -40.0,
            "max_loss": 400.0,
            "evidence_tier": "historical_bar_proxy",
        },
        {
            "trade_id": "paper-1",
            "event_id": "evt-paper",
            "symbol": "CCC",
            "strategy": "short_iron_butterfly",
            "closed_at": "2026-08-27T20:00:00+00:00",
            "net_pnl": 30.0,
            "max_loss": 300.0,
            "evidence_tier": "alpaca_paper",
            "entry_order_id": "alpaca-entry-1",
            "exit_order_id": "alpaca-exit-1",
            "entry_broker_order_id": "broker-entry-1",
            "exit_broker_order_id": "broker-exit-1",
        },
    ]

    report = build_profitability_report(outcomes, starting_nav=100_000.0)

    assert report.competition_pnl == 30.0
    assert report.tiers["alpaca_paper"]["net_pnl"] == 30.0
    assert report.tiers["synthetic_replay"]["net_pnl"] == 125.0
    assert report.tiers["historical_bar_proxy"]["net_pnl"] == -40.0
    assert report.tiers["alpaca_paper"]["allowed_claim"] == "Broker-confirmed Alpaca paper competition P&L"
    assert report.tiers["synthetic_replay"]["allowed_claim"] != report.tiers["alpaca_paper"]["allowed_claim"]


def test_unverified_paper_outcome_is_excluded_from_competition_pnl():
    report = build_profitability_report(
        [
            {
                "trade_id": "paper-without-close-receipt",
                "event_id": "evt-paper",
                "symbol": "AAA",
                "strategy": "long_straddle",
                "closed_at": "2026-08-27T20:00:00+00:00",
                "net_pnl": 900.0,
                "max_loss": 500.0,
                "evidence_tier": "alpaca_paper",
                "entry_order_id": "alpaca-entry-1",
                "exit_order_id": "",
            }
        ]
    )

    assert report.competition_pnl == 0.0
    assert report.tiers["alpaca_paper"]["trades_count"] == 0
    assert report.tiers["alpaca_paper"]["excluded_count"] == 1
    assert report.tiers["alpaca_paper"]["status"] == "NO_BROKER_CONFIRMED_CLOSED_TRADES"


def test_trade_economics_are_computed_from_closed_outcomes():
    outcomes = []
    for index, (pnl, risk) in enumerate(((100.0, 500.0), (-50.0, 400.0), (25.0, 300.0)), start=1):
        outcomes.append(
            {
                "trade_id": f"paper-{index}",
                "event_id": f"evt-{index}",
                "symbol": "AAA",
                "strategy": "long_straddle",
                "closed_at": f"2026-08-2{index}T20:00:00+00:00",
                "net_pnl": pnl,
                "max_loss": risk,
                "evidence_tier": "alpaca_paper",
                "entry_order_id": f"entry-{index}",
                "exit_order_id": f"exit-{index}",
                "entry_broker_order_id": f"broker-entry-{index}",
                "exit_broker_order_id": f"broker-exit-{index}",
            }
        )

    metrics = build_profitability_report(outcomes).tiers["alpaca_paper"]

    assert metrics["net_pnl"] == 75.0
    assert metrics["return_on_starting_nav_pct"] == pytest.approx(0.075)
    assert metrics["win_rate_pct"] == pytest.approx(200 / 3)
    assert metrics["profit_factor"] == 2.5
    assert metrics["average_trade_pnl"] == 25.0
    assert metrics["return_on_total_max_risk_pct"] == 6.25
    assert metrics["max_drawdown_dollars"] == 50.0
    assert metrics["cvar_95_dollars"] == -50.0


def test_closed_trade_ledger_rows_map_to_broker_evidence():
    outcomes = outcomes_from_closed_trades(
        [
            {
                "trade_id": "trd-1",
                "event_id": "evt-1",
                "symbol": "AAPL",
                "decision": "long_straddle",
                "closed_at": "2026-08-28T20:00:00+00:00",
                "net_realized_pnl_dollars": 42.5,
                "max_loss_budget": 500.0,
                "entry_order_id": "alpaca-entry",
                "exit_order_id": "alpaca-exit",
                "raw_payload": json.dumps(
                    {
                        "raw_execution_receipt": {
                            "entry_broker_order_id": "broker-entry",
                            "exit_broker_order_id": "broker-exit",
                        }
                    }
                ),
            }
        ]
    )

    assert outcomes == [
        {
            "trade_id": "trd-1",
            "event_id": "evt-1",
            "symbol": "AAPL",
            "strategy": "long_straddle",
            "closed_at": "2026-08-28T20:00:00+00:00",
            "net_pnl": 42.5,
            "max_loss": 500.0,
            "evidence_tier": "alpaca_paper",
            "entry_order_id": "alpaca-entry",
            "exit_order_id": "alpaca-exit",
            "entry_broker_order_id": "broker-entry",
            "exit_broker_order_id": "broker-exit",
        }
    ]


def test_economic_evidence_keeps_forecast_validation_out_of_historical_pnl():
    replay = {
        "rows": [
            {
                "scenario_id": "sim-1",
                "event": {"event_time": "2026-08-20T20:00:00+00:00"},
                "underlying": {"symbol": "AAA"},
                "volagent": {
                    "decision": "long_straddle",
                    "pnl_value": 125.0,
                    "max_loss_value": 500.0,
                    "status": "VALID",
                },
            }
        ]
    }
    historical = {
        "summary": {
            "evaluated_events_count": 38,
            "excluded_events_count": 2,
            "verdict": "Promising but statistically unproven",
            "metrics": {"mae": {"agent": 0.04573, "b1_implied_move": 0.04452}},
        }
    }

    receipt = build_economic_evidence(
        replay_results=replay,
        historical_results=historical,
        closed_trades=[],
        starting_nav=100_000.0,
    )

    assert receipt["profitability"]["tiers"]["synthetic_replay"]["net_pnl"] == 125.0
    assert receipt["profitability"]["tiers"]["historical_bar_proxy"]["net_pnl"] == 0.0
    assert receipt["historical_predictive_validation"]["evaluated_events_count"] == 38
    assert receipt["competition"]["realized_pnl"] == 0.0
    assert receipt["competition"]["governed_closed_trade_pnl"] == 0.0
    assert receipt["competition"]["full_account_net_pnl"] is None
    assert receipt["competition"]["full_account_return_pct"] is None
    assert receipt["competition"]["status"] == "AWAITING_BROKER_CONFIRMED_CLOSED_TRADES"
    assert len(receipt["receipt_hash"]) == 64


def test_economic_receipt_leads_with_full_account_truth_not_governed_subset():
    receipt = build_economic_evidence(
        replay_results={},
        historical_results={},
        closed_trades=[],
        starting_nav=100_000.0,
        current_equity=88_268.10,
    )

    competition = receipt["competition"]
    assert competition["full_account_net_pnl"] == -11_731.90
    assert competition["full_account_return_pct"] == -11.7319
    assert competition["governed_closed_trade_pnl"] == 0.0
    assert competition["unattributed_and_unrealized_difference"] == -11_731.90
    assert competition["realized_pnl"] == 0.0  # Backward-compatible governed alias.


def test_bootstrap_interval_is_deterministic_for_identical_trade_outcomes():
    outcomes = [
        {
            "trade_id": f"paper-{index}",
            "event_id": f"evt-{index}",
            "symbol": "AAA",
            "strategy": "long_straddle",
            "closed_at": f"2026-08-2{index}T20:00:00+00:00",
            "net_pnl": 10.0,
            "max_loss": 100.0,
            "evidence_tier": "alpaca_paper",
            "entry_order_id": f"entry-{index}",
            "exit_order_id": f"exit-{index}",
            "entry_broker_order_id": f"broker-entry-{index}",
            "exit_broker_order_id": f"broker-exit-{index}",
        }
        for index in range(1, 4)
    ]

    metrics = build_profitability_report(outcomes).tiers["alpaca_paper"]

    assert metrics["mean_trade_pnl_bootstrap_95ci"] == [10.0, 10.0]
    assert metrics["bootstrap_method"] == "cluster bootstrap by close date; deterministic seed 42"


def test_client_ids_without_broker_fill_ids_do_not_count_as_competition_pnl():
    report = build_profitability_report(
        [
            {
                "trade_id": "client-only",
                "event_id": "evt-1",
                "symbol": "AAA",
                "strategy": "long_straddle",
                "closed_at": "2026-08-28T20:00:00+00:00",
                "net_pnl": 100.0,
                "max_loss": 500.0,
                "evidence_tier": "alpaca_paper",
                "entry_order_id": "client-entry",
                "exit_order_id": "client-exit",
            }
        ]
    )

    assert report.competition_pnl == 0.0
    assert report.tiers["alpaca_paper"]["excluded_count"] == 1


def test_judge_ladder_labels_economic_claims_by_evidence_quality():
    receipt = build_economic_evidence(
        replay_results={
            "rows": [
                {
                    "scenario": "AAA replay",
                    "symbol": "AAA",
                    "volagent": {
                        "decision": "long_straddle",
                        "pnl_value": 125.0,
                        "max_loss": "$500.00",
                        "status": "VALID",
                    },
                }
            ]
        },
        historical_results={
            "summary": {
                "evaluated_events_count": 38,
                "verdict": "Promising but statistically unproven",
            }
        },
        closed_trades=[],
    )

    rows = evidence_ladder_rows(receipt)

    assert rows[0]["Evidence"] == "Controlled synthetic replay"
    assert rows[0]["P&L claim"] == "$+125.00"
    assert rows[1]["P&L claim"] == "Not claimed"
    assert rows[1]["Coverage"] == "38 locked forecasts"
    assert rows[2]["Evidence"] == "Alpaca paper competition"
    assert "0 governed broker-confirmed closed trades" in rows[2]["Coverage"]


def test_evidence_receipt_uses_full_account_pnl_as_the_alpaca_headline():
    receipt = build_economic_evidence(
        replay_results={},
        historical_results={},
        closed_trades=[],
        starting_nav=100_000.0,
        current_equity=88_268.10,
    )

    row = evidence_ladder_rows(receipt)[2]

    assert row["P&L claim"] == "$-11,731.90"
    assert "full account" in row["Coverage"].lower()
    assert "governed closed-trade P&L: $+0.00" in row["Permitted conclusion"]


def test_scoreboard_keeps_dense_evidence_hidden_by_default():
    source = (Path(__file__).parents[2] / "src/volagent/ui/pages/scoreboard.py").read_text()

    assert 'st.expander("Technical proof and downloadable receipts", expanded=False)' in source
    assert 'st.markdown("## Economic Evidence Ladder")' not in source
    assert 'st.markdown("## Controlled Ablation Evidence")' not in source
    assert 'st.markdown("### Ablation ladder")' not in source
    assert "ALPACA ACCOUNT TRUTH" not in source


def test_economic_evidence_receipt_is_written_atomically(tmp_path):
    receipt = build_economic_evidence(
        replay_results={},
        historical_results={},
        closed_trades=[],
    )
    output = tmp_path / "economic_evidence.json"

    written = write_economic_evidence_receipt(receipt, output)

    assert written == output
    assert json.loads(output.read_text()) == receipt
    assert not output.with_suffix(".json.tmp").exists()


def test_cli_exports_the_canonical_economic_evidence(monkeypatch, capsys, tmp_path):
    import volagent.evaluation.profitability as profitability

    cli_path = Path(__file__).resolve().parents[2] / "cli.py"
    spec = importlib.util.spec_from_file_location("caisheng_cli_for_test", cli_path)
    assert spec and spec.loader
    caisheng_cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(caisheng_cli)

    receipt = {
        "schema_version": "caisheng.economic_evidence.v1",
        "competition": {"realized_pnl": 0.0},
        "receipt_hash": "a" * 64,
    }
    written: list[object] = []
    monkeypatch.setattr(profitability, "build_current_economic_evidence", lambda: receipt, raising=False)
    monkeypatch.setattr(
        profitability,
        "write_economic_evidence_receipt",
        lambda value, path: written.append((value, path)) or tmp_path / "receipt.json",
    )
    monkeypatch.setattr(sys, "argv", ["cli.py", "--economic-evidence", "--output-json"])

    caisheng_cli.main()

    assert json.loads(capsys.readouterr().out) == receipt
    assert written and written[0][0] == receipt


def test_latest_trade_story_answers_what_why_risk_and_result_from_receipts():
    closed_trade = {
        "trade_id": "trd-1",
        "event_id": "evt-1",
        "symbol": "AAPL",
        "decision": "long_straddle",
        "entry_order_id": "client-entry",
        "exit_order_id": "client-exit",
        "quantity": 1,
        "gross_realized_pnl_dollars": 170.0,
        "fees_and_slippage": 2.0,
        "net_realized_pnl_dollars": 168.0,
        "realized_return_pct": 0.311111,
        "max_loss_budget": 540.0,
        "holding_hours": 18.4,
        "closed_at": "2026-08-28T20:00:00+00:00",
        "raw_payload": json.dumps(
            {
                "raw_execution_receipt": {
                    "entry_broker_order_id": "broker-entry",
                    "exit_broker_order_id": "broker-exit",
                }
            }
        ),
    }
    decision = {
        "event_id": "evt-1",
        "symbol": "AAPL",
        "artifact_hash": "d" * 64,
        "raw_payload": json.dumps(
            {
                "snapshot": {"event_id": "evt-1", "symbol": "AAPL"},
                "volatility_view": {
                    "expected_move_median_pct": 0.078,
                    "implied_move_bid_pct": 0.058,
                    "implied_move_ask_pct": 0.060,
                },
                "risk": {"current_equity": 100_000.0},
                "critic": {"recommendation": "continue"},
            }
        ),
    }
    entry_order = {
        "client_order_id": "client-entry",
        "broker_order_id": "broker-entry",
        "average_price": 5.40,
        "filled_quantity": 1,
        "filled_at": "2026-08-27T20:01:00+00:00",
        "full_order_plan": json.dumps(
            {
                "legs": [
                    {"contract_symbol": "AAPL260904C00230000", "side": "buy"},
                    {"contract_symbol": "AAPL260904P00230000", "side": "buy"},
                ]
            }
        ),
    }
    exit_order = {
        "client_order_id": "client-exit",
        "broker_order_id": "broker-exit",
        "average_price": 7.10,
        "filled_quantity": 1,
        "filled_at": "2026-08-28T14:31:00+00:00",
    }

    story = build_latest_trade_story(
        [closed_trade],
        [decision],
        {"client-entry": entry_order, "client-exit": exit_order},
    )

    assert story["status"] == "BROKER_CONFIRMED"
    assert story["what"]["headline"] == "AAPL · LONG STRADDLE"
    assert story["what"]["contracts"] == ["AAPL260904C00230000", "AAPL260904P00230000"]
    assert story["why"]["forecast_move_pct"] == 7.8
    assert story["why"]["implied_move_pct"] == 5.9
    assert story["why"]["edge_percentage_points"] == 1.9
    assert story["risk"]["max_loss"] == 540.0
    assert story["risk"]["nav_pct"] == 0.54
    assert story["result"]["net_pnl"] == 168.0
    assert story["result"]["return_on_risk_pct"] == pytest.approx(31.1111)
    assert story["proof"]["entry_broker_order_id"] == "broker-entry"


def test_trade_story_empty_state_answers_all_four_questions_honestly():
    story = build_latest_trade_story([], [], {})

    assert story["status"] == "AWAITING_FIRST_CLOSE"
    assert story["what"]["headline"] == "No Alpaca trade closed yet"
    assert story["why"]["headline"] == "No execution claim"
    assert story["risk"]["max_loss"] == 0.0
    assert story["result"]["net_pnl"] == 0.0


def test_trade_story_html_exposes_the_four_judge_answers_above_the_fold():
    markup = trade_story_html(build_latest_trade_story([], [], {}))

    assert "30-SECOND JUDGE ANSWER" in markup
    assert "WHAT DID IT TRADE?" in markup
    assert "WHY DID IT TRADE?" in markup
    assert "HOW MUCH WAS AT RISK?" in markup
    assert "HOW MUCH DID IT MAKE?" in markup
    assert "No Alpaca trade closed yet" in markup
    assert "ALPACA PAPER · NO BROKER-CONFIRMED CLOSE" in markup


def test_empty_competition_evidence_collapses_to_one_status_line():
    markup = competition_evidence_pending_html()

    assert "Competition evidence pending" in markup
    assert "0 broker-confirmed closed trades" in markup
    assert "0 settled benchmark comparisons" in markup
    assert "WHAT DID IT TRADE?" not in markup
    assert "LOCKED POLICY TEST" not in markup


def test_controlled_validation_is_concise_and_claim_safe():
    markup = controlled_validation_html(
        {"net_pnl": 2044.0, "trades_count": 4},
        [
            {
                "Model Benchmark": "CaiSheng (Full)",
                "risk_breaches_value": 0,
            }
        ],
    )

    assert "$+2,044" in markup
    assert "4" in markup
    assert "0" in markup
    assert "Synthetic functional replay" in markup
    assert "not competition P&amp;L" in markup
