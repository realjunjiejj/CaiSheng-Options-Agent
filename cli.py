"""CaiSheng: Standalone Terminal CLI Runner with typed error envelopes."""

import argparse
from datetime import timedelta
import json
from pathlib import Path
import sys

from volagent.config import load_config
from volagent.domain.enums import Decision
from volagent.errors import DataUnavailableError, ValidationError, VolAgentException
from volagent.graph.builder import VolAgentWorkflow


def main() -> None:
    parser = argparse.ArgumentParser(description="CaiSheng Options Alpha CLI")
    parser.add_argument("--symbol", type=str, default="NVDA", help="Target underlying ticker (e.g. NVDA, TSLA, AAPL)")
    parser.add_argument("--scenario", type=str, default=None, help="Explicit scenario ID (e.g. SCENARIO-NVDA-2024Q2-AMC)")
    parser.add_argument("--preflight", action="store_true", help="Run Alpaca operations preflight check and export receipt")
    parser.add_argument("--reconcile", action="store_true", help="Run post-market close daily reconciliation and export receipt")
    parser.add_argument(
        "--lockbox",
        action="store_true",
        help="Verify Alpaca's official CLI, read-only MCP V2, and official skills",
    )
    competition_group = parser.add_mutually_exclusive_group()
    competition_group.add_argument(
        "--competition-arm",
        action="store_true",
        help="Issue a time-limited paper-only competition authorization; does not place an order",
    )
    competition_group.add_argument(
        "--competition-disarm",
        action="store_true",
        help="Revoke new-entry authorization while leaving position monitoring active",
    )
    competition_group.add_argument(
        "--competition-status",
        action="store_true",
        help="Validate and display the current competition authorization receipt",
    )
    parser.add_argument(
        "--competition-config",
        default="config/competition.yaml",
        help="Competition policy file bound into the authorization receipt",
    )
    parser.add_argument(
        "--arm-hours",
        type=int,
        default=None,
        help="Authorization duration, capped by the competition configuration",
    )
    parser.add_argument(
        "--economic-evidence",
        action="store_true",
        help="Build and export the claim-safe economic-evidence receipt",
    )
    parser.add_argument("--output-json", action="store_true", help="Print pure raw decision receipt JSON to stdout")

    args = parser.parse_args()
    out_stream = sys.stderr if args.output_json else sys.stdout

    if args.competition_arm or args.competition_disarm or args.competition_status:
        from volagent.competition import (
            issue_competition_lease,
            read_competition_status,
            revoke_competition_lease,
        )

        settings = load_config(args.competition_config)
        if args.competition_disarm:
            receipt = revoke_competition_lease(
                path=settings.competition.lease_path,
                settings=settings,
            )
        else:
            from volagent.data.alpaca_sdk import AlpacaPortfolioAdapter

            adapter = AlpacaPortfolioAdapter(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
                paper=True,
            )
            snapshot = adapter.fetch_portfolio_snapshot()
        if args.competition_arm:
            if snapshot.is_stale or not snapshot.account_id:
                raise SystemExit(
                    "Competition arming failed: a fresh authenticated Alpaca paper account snapshot is required."
                )
            duration_hours = args.arm_hours or settings.competition.arm_duration_hours
            if duration_hours > settings.competition.arm_duration_hours:
                raise SystemExit(
                    f"Competition arming failed: duration exceeds the {settings.competition.arm_duration_hours}h policy cap."
                )
            receipt = issue_competition_lease(
                path=settings.competition.lease_path,
                settings=settings,
                paper_account_id=snapshot.account_id,
                starting_nav=snapshot.initial_nav,
                current_equity=snapshot.equity,
                duration=timedelta(hours=duration_hours),
            )
        elif args.competition_status:
            receipt = read_competition_status(
                path=settings.competition.lease_path,
                settings=settings,
                paper_account_id=snapshot.account_id if not snapshot.is_stale else None,
            )
        if args.output_json:
            sys.stdout.write(json.dumps(receipt, indent=2) + "\n")
        else:
            print(f"CaiSheng Competition Mode: {receipt['status']}")
            print(f"  - Paper only: {receipt.get('paper_only', True)}")
            print(f"  - Submission authorized: {receipt['submission_authorized']}")
            print(f"  - Expires: {receipt.get('expires_at') or '—'}")
            print(f"  - Reason: {receipt['reason']}")
            limits = receipt.get("risk_limits", {})
            if limits:
                print(f"  - Recommended / hard max loss: ${limits['recommended_loss_per_trade']:.0f} / ${limits['hard_loss_per_trade']:.0f}")
                print(f"  - Max new entries: {limits['max_new_entries_per_day']} per day")
        return

    if args.economic_evidence:
        from volagent.evaluation.profitability import (
            build_current_economic_evidence,
            write_economic_evidence_receipt,
        )

        receipt = build_current_economic_evidence()
        output_path = Path(__file__).resolve().parent / "data" / "evaluation" / "economic_evidence_receipt.json"
        write_economic_evidence_receipt(receipt, output_path)
        if args.output_json:
            sys.stdout.write(json.dumps(receipt, indent=2) + "\n")
        else:
            competition = receipt["competition"]
            print("📈 CaiSheng Economic Evidence Receipt")
            print(f"  - Competition realized P&L: ${competition['realized_pnl']:+,.2f}")
            print(f"  - Broker-confirmed closed trades: {competition['closed_trades_count']}")
            print(f"  - Status: {competition['status']}")
            print(f"  - Receipt: {output_path}")
            print(f"  - SHA-256: {receipt['receipt_hash']}")
        return

    if args.lockbox:
        from volagent.integrations.alpaca_lockbox import run_alpaca_technology_lockbox

        receipt = run_alpaca_technology_lockbox(load_config())
        if args.output_json:
            sys.stdout.write(json.dumps(receipt, indent=2) + "\n")
        else:
            print(f"🔐 CaiSheng Alpaca Technology Lockbox: {receipt['overall_status']}")
            for name, component in receipt["components"].items():
                print(f"  - [{component['status']}] {name}")
            print(f"  - Paper-only execution boundary: {'LOCKED' if receipt['paper_only'] else 'FAIL'}")
        if receipt.get("overall_status") != "PASS":
            sys.exit(1)
        return

    if args.preflight:
        from volagent.cli.preflight import run_cli_preflight
        receipt = run_cli_preflight()
        if args.output_json:
            sys.stdout.write(json.dumps(receipt, indent=2) + "\n")
        else:
            print(f"✈️ CaiSheng Alpaca Preflight Status: {receipt['overall_status']}")
            for chk in receipt["checks"]:
                print(f"  - [{chk['status']}] {chk['check']}: {chk['details']}")
        if receipt.get("overall_status") != "CLEAN":
            sys.exit(1)
        return

    if args.reconcile:
        from volagent.cli.reconcile import run_cli_reconciliation
        receipt = run_cli_reconciliation()
        if args.output_json:
            sys.stdout.write(json.dumps(receipt, indent=2) + "\n")
        else:
            print(f"⚖️ CaiSheng Daily Reconciliation Status: {receipt['overall_status']}")
            print(f"  - Matched orders: {receipt.get('matched_order_count', 0)}")
            print(f"  - Matched positions: {receipt.get('matched_position_count', 0)}")
            if receipt.get("orphan_broker_orders", 0) > 0:
                print(f"  - Orphan broker orders: {receipt['orphan_broker_orders']}")
            if receipt.get("orphan_broker_positions", 0) > 0:
                print(f"  - Orphan broker positions: {receipt['orphan_broker_positions']}")
        if receipt.get("overall_status") != "CLEAN":
            sys.exit(1)
        return



    # P1-17 Fix: Enforce symbol and scenario consistency
    if args.scenario and args.symbol:
        sc_upper = args.scenario.upper()
        sym_upper = args.symbol.upper()
        if sym_upper not in sc_upper and sc_upper.replace("SCENARIO-", "").split("-")[0] != sym_upper:
            msg = f"Mismatched --symbol '{args.symbol}' and --scenario '{args.scenario}'. Symbol must match scenario underlying."
            if args.output_json:
                sys.stdout.write(json.dumps({"status": "error", "error_type": "ValidationError", "message": msg}, indent=2) + "\n")
            else:
                print(f"❌ Error: {msg}", file=sys.stderr)
            sys.exit(1)

    try:
        config = load_config()
        if args.scenario:
            config.volagent_replay_scenario_id = args.scenario
        else:
            config.volagent_replay_scenario_id = f"SCENARIO-{args.symbol}"

        print(f"\n========================================================", file=out_stream)
        print(f"🚀 Launching CaiSheng Options Alpha for {args.symbol}...", file=out_stream)
        print(f"========================================================\n", file=out_stream)

        workflow = VolAgentWorkflow(config=config)

        result = workflow.run({"symbol": args.symbol})

        final_decision = result["final_decision"]
        cand = result.get("approved_candidate")
        forecast = result.get("move_forecast")
        risk_rep = result.get("risk_report")
        actual_symbol = result.get("underlying").symbol if result.get("underlying") else args.symbol

        print(f"✅ Run ID:               {result.get('run_id')}", file=out_stream)
        if forecast:
            print(f"📊 Market Implied Move:  {forecast.implied_move_pct*100:.1f}%", file=out_stream)
            print(f"🎯 Forecast Median Move: {forecast.median_abs_move_pct*100:.1f}% (Edge: {forecast.edge_pct_spot*100:+.2f}%)", file=out_stream)
        if "long_vol_thesis" in result and "short_vol_thesis" in result:
            print(f"⚖️ Dialectical Debate:   Long Vol Conf: {result['long_vol_thesis'].confidence*100:.1f}% | Short Vol Conf: {result['short_vol_thesis'].confidence*100:.1f}%", file=out_stream)
        if "critic_report" in result:
            print(f"🛡️ Critic Recommendation:{result['critic_report'].recommendation.upper()}", file=out_stream)
        print(f"🏆 Final Decision:       {final_decision.value.upper()}", file=out_stream)
        if risk_rep:
            print(f"🛡️ Risk Gate Status:     {risk_rep.overall_status.value.upper()} (Approved Qty: {risk_rep.approved_quantity})", file=out_stream)

        if cand:
            print(f"💰 Max Loss:             ${cand.max_loss:.2f}", file=out_stream)
            print(f"📈 Expected P&L:         ${cand.expected_pnl:.2f}", file=out_stream)
            print(f"📐 Delta / Vega:         Δ: {cand.net_delta:.1f} | V: ${cand.net_vega:.1f}/pt", file=out_stream)

        if risk_rep and risk_rep.rejection_reasons:
            print(f"❌ Rejection Reasons:    {'; '.join(risk_rep.rejection_reasons)}", file=out_stream)

        print(f"\n========================================================\n", file=out_stream)

        if args.output_json:
            receipt_data = {
                "run_id": result.get("run_id"),
                "symbol": actual_symbol,
                "final_decision": final_decision.value,
                "abstention_reason": result.get("abstention_reason", "none"),
                "implied_move_pct": forecast.implied_move_pct if forecast else None,
                "forecast_median_pct": forecast.median_abs_move_pct if forecast else None,
                "risk_status": risk_rep.overall_status.value if risk_rep else "FAIL",
                "approved_quantity": risk_rep.approved_quantity if risk_rep else 0,
                "provenance_hash": result.get("artifact_hashes", {}).get("scenario_file", ""),
                "rejection_reasons": result.get("rejection_reasons", []),
            }
            sys.stdout.write(json.dumps(receipt_data, indent=2) + "\n")

    except DataUnavailableError as e:
        if args.output_json:
            sys.stdout.write(json.dumps({"status": "error", "error_type": "DataUnavailableError", "message": str(e)}, indent=2) + "\n")
        else:
            print(f"❌ Data Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if args.output_json:
            sys.stdout.write(json.dumps({"status": "error", "error_type": type(e).__name__, "message": str(e)}, indent=2) + "\n")
        else:
            print(f"❌ Execution Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
