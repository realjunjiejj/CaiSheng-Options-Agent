"""VolAgent Alpha: Standalone Terminal CLI Runner."""

import argparse
import json
import sys

from volagent.config import load_config
from volagent.domain.enums import Decision
from volagent.graph.builder import VolAgentWorkflow


def main() -> None:
    parser = argparse.ArgumentParser(description="VolAgent Alpha Multi-Agent Volatility Trading Desk CLI")
    parser.add_argument("--symbol", type=str, default="NVDA", help="Target underlying ticker (e.g. NVDA, TSLA, AAPL)")
    parser.add_argument("--scenario", type=str, default=None, help="Explicit scenario ID (e.g. SCENARIO-NVDA-2024Q2-AMC)")
    parser.add_argument("--output-json", action="store_true", help="Print pure raw decision receipt JSON to stdout")

    args = parser.parse_args()

    config = load_config()
    if args.scenario:
        config.volagent_replay_scenario_id = args.scenario
    else:
        config.volagent_replay_scenario_id = f"SCENARIO-{args.symbol}"

    out_stream = sys.stderr if args.output_json else sys.stdout

    print(f"\n========================================================", file=out_stream)
    print(f"🚀 Launching VolAgent Alpha Multi-Agent Graph for {args.symbol}...", file=out_stream)
    print(f"========================================================\n", file=out_stream)

    workflow = VolAgentWorkflow(config=config)
    result = workflow.run({"symbol": args.symbol})

    final_decision = result["final_decision"]
    cand = result.get("approved_candidate")
    forecast = result["move_forecast"]
    risk_rep = result["risk_report"]

    print(f"✅ Run ID:               {result.get('run_id')}", file=out_stream)
    print(f"📊 Market Implied Move:  {forecast.implied_move_pct*100:.1f}%", file=out_stream)
    print(f"🎯 Forecast Median Move: {forecast.median_abs_move_pct*100:.1f}% (Edge: {forecast.edge_pct_spot*100:+.2f}%)", file=out_stream)
    print(f"⚖️ Dialectical Debate:   Long Vol Conf: {result['long_vol_thesis'].confidence*100:.1f}% | Short Vol Conf: {result['short_vol_thesis'].confidence*100:.1f}%", file=out_stream)
    print(f"🛡️ Critic Recommendation:{result['critic_report'].recommendation.upper()}", file=out_stream)
    print(f"🏆 Final Decision:       {final_decision.value.upper()}", file=out_stream)
    print(f"🛡️ Risk Gate Status:     {risk_rep.overall_status.value.upper()} (Approved Qty: {risk_rep.approved_quantity})", file=out_stream)

    if cand:
        print(f"💰 Max Loss:             ${cand.max_loss:.2f}", file=out_stream)
        print(f"📈 Expected P&L:         ${cand.expected_pnl:.2f}", file=out_stream)
        print(f"📐 Delta / Vega:         Δ: {cand.net_delta:.1f} | V: ${cand.net_vega:.1f}/pt", file=out_stream)

    if risk_rep.rejection_reasons:
        print(f"❌ Rejection Reasons:    {'; '.join(risk_rep.rejection_reasons)}", file=out_stream)

    print(f"\n========================================================\n", file=out_stream)

    if args.output_json:
        receipt_data = {
            "run_id": result.get("run_id"),
            "symbol": args.symbol,
            "final_decision": final_decision.value,
            "abstention_reason": result.get("abstention_reason", "none"),
            "implied_move_pct": forecast.implied_move_pct,
            "forecast_median_pct": forecast.median_abs_move_pct,
            "risk_status": risk_rep.overall_status.value,
            "approved_quantity": risk_rep.approved_quantity,
            "provenance_hash": result.get("artifact_hashes", {}).get("scenario_file", ""),
            "rejection_reasons": result.get("rejection_reasons", []),
        }
        sys.stdout.write(json.dumps(receipt_data, indent=2) + "\n")


if __name__ == "__main__":
    main()
