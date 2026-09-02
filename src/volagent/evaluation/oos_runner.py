"""Rigorous out-of-sample historical evaluation runner for CaiSheng."""

import csv
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from typing import Any
import zoneinfo

import numpy as np

from alpaca.data.enums import DataFeed
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from volagent.config import load_config
from volagent.domain.enums import DataMode, EventTiming
from volagent.domain.events import EarningsEvent
from volagent.evaluation.historical_bar_replay import AlpacaHistoricalBarReplayAdapter
from volagent.graph.builder import VolAgentWorkflow
from volagent.provenance import Provenance, compute_canonical_hash

from volagent.config import PROJECT_ROOT
NY_TZ = zoneinfo.ZoneInfo("America/New_York")

HISTORICAL_EARNINGS_DATES = {
    "AAPL": ["2022-01-27", "2022-04-28", "2022-07-28", "2022-10-27", "2023-02-02", "2023-05-04", "2023-08-03", "2023-11-02", "2024-02-01", "2024-05-02", "2024-08-01", "2024-10-31"],
    "MSFT": ["2022-01-25", "2022-04-26", "2022-07-26", "2022-10-25", "2023-01-24", "2023-04-25", "2023-07-25", "2023-10-24", "2024-01-30", "2024-04-25", "2024-07-30", "2024-10-30"],
    "GOOGL": ["2022-02-01", "2022-04-26", "2022-07-26", "2022-10-25", "2023-02-02", "2023-04-25", "2023-07-25", "2023-10-24", "2024-01-30", "2024-04-25", "2024-07-23", "2024-10-29"],
    "AMZN": ["2022-02-03", "2022-04-28", "2022-07-28", "2022-10-27", "2023-02-02", "2023-04-27", "2023-08-03", "2023-10-26", "2024-02-01", "2024-04-30", "2024-08-01", "2024-10-31"],
    "META": ["2022-02-02", "2022-04-27", "2022-07-27", "2022-10-26", "2023-02-01", "2023-04-26", "2023-07-26", "2023-10-25", "2024-02-01", "2024-04-24", "2024-07-31", "2024-10-30"],
    "NVDA": ["2022-02-16", "2022-05-25", "2022-08-24", "2022-11-16", "2023-02-22", "2023-05-24", "2023-08-23", "2023-11-21", "2024-02-21", "2024-05-22", "2024-08-28"],
    "AMD": ["2022-02-01", "2022-05-03", "2022-08-02", "2022-11-01", "2023-01-31", "2023-05-02", "2023-08-01", "2023-10-31", "2024-01-30", "2024-04-30", "2024-07-30", "2024-10-29"],
    "INTC": ["2022-01-27", "2022-04-28", "2022-07-28", "2022-10-27", "2023-01-26", "2023-04-27", "2023-07-27", "2023-10-26", "2024-01-25", "2024-04-25", "2024-08-01", "2024-10-31"],
    "QCOM": ["2022-02-02", "2022-04-27", "2022-07-27", "2022-11-02", "2023-02-01", "2023-05-03", "2023-08-02", "2023-11-01", "2024-01-31", "2024-05-01", "2024-07-31", "2024-11-06"],
    "CRM": ["2022-03-01", "2022-05-31", "2022-08-24", "2022-11-30", "2023-03-01", "2023-05-31", "2023-08-23", "2023-11-29", "2024-02-28", "2024-05-29", "2024-08-28"],
    "ADBE": ["2022-03-22", "2022-06-16", "2022-09-15", "2022-12-15", "2023-03-15", "2023-06-15", "2023-09-14", "2023-12-13", "2024-03-14", "2024-06-13", "2024-09-12"],
    "TSLA": ["2022-01-26", "2022-04-20", "2022-07-20", "2022-10-19", "2023-01-25", "2023-04-19", "2023-07-19", "2023-10-18", "2024-01-24", "2024-04-23", "2024-07-23", "2024-10-23"],
    "SBUX": ["2022-02-01", "2022-05-03", "2022-08-02", "2022-11-03", "2023-02-02", "2023-05-02", "2023-08-01", "2023-11-02", "2024-01-30", "2024-04-30", "2024-07-30", "2024-10-30"],
    "NKE": ["2022-03-21", "2022-06-27", "2022-09-29", "2022-12-21", "2023-03-21", "2023-06-29", "2023-09-28", "2023-12-21", "2024-03-21", "2024-06-27", "2024-10-01"],
    "NFLX": ["2022-01-20", "2022-04-19", "2022-07-19", "2022-10-18", "2023-01-19", "2023-04-18", "2023-07-19", "2023-10-18", "2024-01-23", "2024-04-18", "2024-07-18", "2024-10-17"],
    "V": ["2022-01-27", "2022-04-26", "2022-07-26", "2022-10-25", "2023-01-26", "2023-04-25", "2023-07-25", "2023-10-24", "2024-01-25", "2024-04-23", "2024-07-23", "2024-10-29"],
    "MA": ["2022-01-27", "2022-04-28", "2022-07-28", "2022-10-27", "2023-01-26", "2023-04-27", "2023-07-27", "2023-10-26", "2024-01-31", "2024-05-01", "2024-07-31", "2024-10-31"],
    "COIN": ["2022-02-24", "2022-05-10", "2022-08-09", "2022-11-03", "2023-02-21", "2023-05-04", "2023-08-03", "2023-11-02", "2024-02-15", "2024-05-02", "2024-08-01", "2024-10-30"],
    "GILD": ["2022-02-01", "2022-04-28", "2022-08-02", "2022-10-27", "2023-02-02", "2023-04-27", "2023-08-03", "2023-11-07", "2024-02-06", "2024-04-25", "2024-08-08", "2024-11-06"],
    "CAT": ["2022-01-28", "2022-04-28", "2022-08-02", "2022-10-27", "2023-01-31", "2023-04-27", "2023-08-01", "2023-10-31", "2024-02-05", "2024-04-25", "2024-08-06", "2024-10-30"],
}

SPLIT_NAMES = ("train", "validation", "holdout")


def chronological_event_splits(events: list[dict[str, Any]]) -> dict[str, str]:
    """Assign chronological train/validation/holdout labels for future tuning.

    The runner does not tune parameters: every result is therefore an
    out-of-sample forecast for the fixed model version.  These labels prevent a
    future model-selection change from using the newest events as feedback.
    """
    ordered = sorted(events, key=lambda event: (event["cutoff_ny"], event["event_id"]))
    count = len(ordered)
    if count < 3:
        return {event["event_id"]: "holdout" for event in ordered}

    train_end = max(1, int(count * 0.60))
    validation_end = max(train_end + 1, int(count * 0.80))
    validation_end = min(validation_end, count - 1)
    splits: dict[str, str] = {}
    for index, event in enumerate(ordered):
        splits[event["event_id"]] = (
            "train" if index < train_end else "validation" if index < validation_end else "holdout"
        )
    return splits


def calibration_breakdown(rows: list[dict[str, Any]], buckets: int = 3) -> list[dict[str, Any]]:
    """Return an auditable reliability table without fitting to outcomes."""
    if not rows or buckets < 1:
        return []
    ordered = sorted(rows, key=lambda row: (row["agent_median_forecast"], row["event_id"]))
    groups = [group.tolist() for group in np.array_split(np.array(ordered, dtype=object), min(buckets, len(ordered)))]
    report: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        if not group:
            continue
        report.append({
            "bucket": f"forecast_quantile_{index}_of_{len(groups)}",
            "events": len(group),
            "mean_predicted_abs_move": round(float(np.mean([row["agent_median_forecast"] for row in group])), 5),
            "mean_realized_abs_move": round(float(np.mean([row["realized_abs_move"] for row in group])), 5),
            "mean_bias": round(float(np.mean([row["agent_median_forecast"] - row["realized_abs_move"] for row in group])), 5),
        })
    return report


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Persist the pre-reveal receipt without leaving a partial artifact."""
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2))
    temporary_path.replace(path)


def run_out_of_sample_evaluation(
    manifest_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run a fail-closed, point-in-time evaluation of the full LangGraph workflow.

    Historical option bars are useful for forecasting but cannot evidence fills,
    bid/ask spreads, historical OI, or executable P&L.  Events without valid
    pre-cutoff minute bars are excluded rather than proxied with a daily close.
    """
    cfg = load_config()
    if not cfg.alpaca_api_key or not cfg.alpaca_secret_key:
        return {"status": "error", "message": "Alpaca credentials are required for OOS evaluation."}

    m_path = Path(manifest_path) if manifest_path else PROJECT_ROOT / "data" / "evaluation" / "oos_universe_manifest.json"
    out_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "data" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(m_path.read_text())
    events = manifest["events"]
    manifest_hash = compute_canonical_hash(manifest)

    stock_client = StockHistoricalDataClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)
    bar_adapter = AlpacaHistoricalBarReplayAdapter(cfg.alpaca_api_key, cfg.alpaca_secret_key)
    symbols = sorted({event["symbol"] for event in events})
    sector_by_symbol = {event["symbol"]: event.get("sector", "Unknown") for event in events}
    min_date = min(date.fromisoformat(item) for values in HISTORICAL_EARNINGS_DATES.values() for item in values)
    max_date = max(date.fromisoformat(event["earnings_date"]) for event in events) + timedelta(days=7)
    daily = stock_client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=datetime.combine(min_date, time.min, tzinfo=timezone.utc),
        end=datetime.combine(max_date, time.max, tzinfo=timezone.utc),
        feed=DataFeed.IEX,
    ))
    daily_closes = {
        symbol: {bar.timestamp.date(): float(bar.close) for bar in daily.data.get(symbol, []) if float(bar.close) > 0.0}
        for symbol in symbols
    }

    prior_cache: dict[tuple[str, date], list[float]] = {}

    def prior_moves(symbol: str, as_of: date) -> list[float]:
        """Use only already-completed earnings reactions for this point in time."""
        key = (symbol, as_of)
        if key in prior_cache:
            return prior_cache[key]
        closes = daily_closes.get(symbol, {})
        available_dates = sorted(closes)
        moves: list[float] = []
        for raw_date in HISTORICAL_EARNINGS_DATES.get(symbol, []):
            event_date = date.fromisoformat(raw_date)
            if event_date >= as_of or event_date not in closes:
                continue
            next_dates = [candidate for candidate in available_dates if candidate > event_date]
            if next_dates:
                moves.append(abs(closes[next_dates[0]] / closes[event_date] - 1.0))
        prior_cache[key] = moves
        return moves

    def baseline_pool(as_of: date, sector: str | None = None) -> list[float]:
        selected = [symbol for symbol in symbols if sector is None or sector_by_symbol.get(symbol) == sector]
        return [move for symbol in selected for move in prior_moves(symbol, as_of)]

    def outcome_close(symbol: str, expected_close_ny: datetime) -> tuple[float, datetime] | None:
        cutoff = expected_close_ny.astimezone(timezone.utc)
        start = datetime.combine(expected_close_ny.date(), time.min, tzinfo=NY_TZ).astimezone(timezone.utc)
        response = stock_client.get_stock_bars(StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=start,
            end=cutoff,
            feed=DataFeed.IEX,
        ))
        bars = [bar for bar in response.data.get(symbol, []) if bar.timestamp.astimezone(timezone.utc) <= cutoff]
        if not bars:
            return None
        latest = max(bars, key=lambda bar: bar.timestamp)
        if (cutoff - latest.timestamp.astimezone(timezone.utc)).total_seconds() > 120:
            return None
        return float(latest.close), latest.timestamp.astimezone(timezone.utc)

    def agent_eligible_expiration(event_date: date) -> date:
        """Use the first Friday satisfying the agent's configured post-event DTE."""
        candidate = event_date + timedelta(days=cfg.contracts.min_dte_days)
        return candidate + timedelta(days=(4 - candidate.weekday()) % 7)

    proxy_cfg = cfg.model_copy(deep=True)
    # OI and volume are unavailable as-of in historical bar data.  These gates
    # are disabled only for forecast evaluation; results are never execution P&L.
    proxy_cfg.contracts = proxy_cfg.contracts.model_copy(update={"min_volume": 0, "min_open_interest": 0})
    workflow = VolAgentWorkflow(config=proxy_cfg)
    split_by_event_id = chronological_event_splits(events)
    locked_predictions: list[dict[str, Any]] = []
    eval_results: list[dict[str, Any]] = []
    excluded_events: list[dict[str, str]] = []

    for event_spec in events:
        event_id = event_spec["event_id"]
        symbol = event_spec["symbol"]
        sector = event_spec.get("sector", "Unknown")
        event_date = date.fromisoformat(event_spec["earnings_date"])
        # The original front expiry is retained in the manifest for audit. The
        # evaluation uses this deterministic expiration because the production
        # graph rejects contracts that violate its min-DTE rule.
        expiry = agent_eligible_expiration(event_date)
        cutoff_ny = datetime.strptime(event_spec["cutoff_ny"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=NY_TZ)
        cutoff = cutoff_ny.astimezone(timezone.utc)
        event_time = datetime.combine(event_date, time(16, 5), tzinfo=NY_TZ).astimezone(timezone.utc)
        close_ny = datetime.strptime(event_spec["next_close_ny"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=NY_TZ)

        try:
            snapshot = bar_adapter.build_snapshot(symbol, cutoff, expiry)
            ticker_history = prior_moves(symbol, event_date)
            sector_history = baseline_pool(event_date, sector)
            global_history = baseline_pool(event_date)
            if not ticker_history or not sector_history or not global_history:
                raise ValueError("Insufficient strictly-prior historical baseline observations")

            event_provenance = Provenance(
                source_name="OOS manifest event declaration",
                source_uri=event_spec.get("source_url"),
                retrieved_at=datetime.now(timezone.utc),
                observed_at=cutoff,
                effective_at=event_time,
                content_hash=compute_canonical_hash(event_spec),
                data_mode=DataMode.REPLAY_REAL,
            )
            earnings_event = EarningsEvent(
                event_id=event_id,
                symbol=symbol,
                fiscal_period=event_spec.get("fiscal_period"),
                event_time=event_time,
                timing=EventTiming.AFTER_MARKET_CLOSE,
                confirmed=True,
                decision_time=cutoff,
                exit_time=close_ny.astimezone(timezone.utc),
                provenance=event_provenance,
            )
            result = workflow.run({
                "symbol": symbol,
                "event": earnings_event,
                "underlying": snapshot.underlying,
                "option_chain": snapshot.option_chain,
                "historical_moves": ticker_history,
                "evidence": [],
                "mode": DataMode.REPLAY_REAL,
                "nav": 100_000.0,
            })
            forecast = result.get("move_forecast")
            metrics = result.get("feature_set", {}).get("implied_metrics")
            atm_call = result.get("feature_set", {}).get("atm_call")
            atm_put = result.get("feature_set", {}).get("atm_put")
            if not forecast or not metrics or not atm_call or not atm_put:
                raise ValueError("Full workflow returned no valid pre-event ATM forecast")

            pre_event_record = {
                "event_id": event_id,
                "symbol": symbol,
                "sector": sector,
                "evaluation_split": split_by_event_id[event_id],
                "earnings_date": event_spec["earnings_date"],
                "manifest_front_option_expiry": event_spec["front_option_expiry"],
                "selected_agent_expiration": expiry.isoformat(),
                "cutoff_utc": cutoff.isoformat(),
                "outcome_close_utc": close_ny.astimezone(timezone.utc).isoformat(),
                "spot_cutoff": snapshot.underlying.price,
                "underlying_bar_time": snapshot.underlying.quote_time.isoformat(),
                "option_bar_proxy": True,
                "atm_call_symbol": atm_call.symbol,
                "atm_call_bar_time": atm_call.quote_time.isoformat(),
                "atm_put_symbol": atm_put.symbol,
                "atm_put_bar_time": atm_put.quote_time.isoformat(),
                "prior_jumps_count": len(ticker_history),
                "agent_median_forecast": round(forecast.median_abs_move_pct, 5),
                "q20": round(forecast.q20_abs_move_pct, 5),
                "q80": round(forecast.q80_abs_move_pct, 5),
                "b0_hist_median": round(float(np.median(ticker_history)), 5),
                "b1_implied_move": round(metrics.implied_move_mid_pct, 5),
                "b2_sector_median": round(float(np.median(sector_history)), 5),
                "b3_global_median": round(float(np.median(global_history)), 5),
                "decision": result["final_decision"].value,
                "gate_status": result["risk_report"].overall_status.value,
                "abstention_reason": result.get("abstention_reason").value if result.get("abstention_reason") else None,
                "manifest_hash": manifest_hash,
                "model_version": forecast.model_version,
                "locked_at": datetime.now(timezone.utc).isoformat(),
                "source_url": event_spec.get("source_url", ""),
            }
            pre_event_record["forecast_hash"] = compute_canonical_hash(pre_event_record)
            locked_predictions.append(pre_event_record)
        except Exception as exc:
            excluded_events.append({
                "event_id": event_id,
                "symbol": symbol,
                "phase": "forecast_lock",
                "reason": f"{type(exc).__name__}: {exc}",
            })

    # Persist every point-in-time forecast before any post-event price is read.
    # This is intentionally a separate phase so a judge can inspect the sealed
    # receipt even if outcome collection fails later.
    lock_payload = {
        "protocol": {
            "name": "VolAgent point-in-time historical forecast evaluation",
            "forecast_phase": "Full LangGraph run on data at or before cutoff",
            "reveal_phase": "Next-session minute close fetched only after lock receipt is written",
            "execution_claim": "none; historical option bars are non-executable price proxies",
            "tuning_policy": "The runner performs no parameter fitting or post-hoc model selection.",
        },
        "manifest_hash": manifest_hash,
        "model_config": proxy_cfg.model_dump(mode="json", exclude={"alpaca_api_key", "alpaca_secret_key", "openai_api_key"}),
        "predictions": locked_predictions,
    }
    lock_payload["receipt_hash"] = compute_canonical_hash(lock_payload)
    _atomic_json_write(out_dir / "oos_locked_predictions.json", lock_payload)

    for pre_event_record in locked_predictions:
        try:
            close_ny = datetime.fromisoformat(pre_event_record["outcome_close_utc"]).astimezone(NY_TZ)
            revealed = outcome_close(pre_event_record["symbol"], close_ny)
            if revealed is None:
                raise ValueError("Missing timely next-session-close minute bar")
            next_close, next_close_time = revealed
            realized_move = abs(next_close / pre_event_record["spot_cutoff"] - 1.0)
            b0 = pre_event_record["b0_hist_median"]
            b1 = pre_event_record["b1_implied_move"]
            b2 = pre_event_record["b2_sector_median"]
            b3 = pre_event_record["b3_global_median"]
            agent_forecast = pre_event_record["agent_median_forecast"]
            eval_results.append({
                **pre_event_record,
                "next_close": next_close,
                "next_close_bar_time": next_close_time.isoformat(),
                "realized_abs_move": round(realized_move, 5),
                "abs_error_agent": round(abs(agent_forecast - realized_move), 5),
                "abs_error_b0": round(abs(b0 - realized_move), 5),
                "abs_error_b1": round(abs(b1 - realized_move), 5),
                "abs_error_b2": round(abs(b2 - realized_move), 5),
                "abs_error_b3": round(abs(b3 - realized_move), 5),
                "sq_error_agent": round((agent_forecast - realized_move) ** 2, 7),
                "sq_error_b0": round((b0 - realized_move) ** 2, 7),
                "sq_error_b1": round((b1 - realized_move) ** 2, 7),
                "sq_error_b2": round((b2 - realized_move) ** 2, 7),
                "sq_error_b3": round((b3 - realized_move) ** 2, 7),
                "in_interval_60": bool(pre_event_record["q20"] <= realized_move <= pre_event_record["q80"]),
                "exceed_correct": bool((agent_forecast > b1) == (realized_move > b1)),
            })
        except Exception as exc:
            excluded_events.append({
                "event_id": pre_event_record["event_id"],
                "symbol": pre_event_record["symbol"],
                "phase": "outcome_reveal",
                "reason": f"{type(exc).__name__}: {exc}",
            })

    # 7. Aggregate Statistics
    n_events = len(eval_results)
    if n_events == 0:
        return {"status": "error", "message": "No valid events evaluated.", "excluded_events": excluded_events}

    agent_ae = [r["abs_error_agent"] for r in eval_results]
    b0_ae = [r["abs_error_b0"] for r in eval_results]
    b1_ae = [r["abs_error_b1"] for r in eval_results]
    b2_ae = [r["abs_error_b2"] for r in eval_results]
    b3_ae = [r["abs_error_b3"] for r in eval_results]

    agent_se = [r["sq_error_agent"] for r in eval_results]
    b0_se = [r["sq_error_b0"] for r in eval_results]
    b1_se = [r["sq_error_b1"] for r in eval_results]
    b2_se = [r["sq_error_b2"] for r in eval_results]
    b3_se = [r["sq_error_b3"] for r in eval_results]

    mae_agent = float(np.mean(agent_ae))
    mae_b0 = float(np.mean(b0_ae))
    mae_b1 = float(np.mean(b1_ae))
    mae_b2 = float(np.mean(b2_ae))
    mae_b3 = float(np.mean(b3_ae))

    rmse_agent = float(np.sqrt(np.mean(agent_se)))
    rmse_b0 = float(np.sqrt(np.mean(b0_se)))
    rmse_b1 = float(np.sqrt(np.mean(b1_se)))
    rmse_b2 = float(np.sqrt(np.mean(b2_se)))
    rmse_b3 = float(np.sqrt(np.mean(b3_se)))

    med_ae_agent = float(np.median(agent_ae))
    med_ae_b0 = float(np.median(b0_ae))
    med_ae_b1 = float(np.median(b1_ae))
    med_ae_b2 = float(np.median(b2_ae))
    med_ae_b3 = float(np.median(b3_ae))

    win_rate_vs_b0 = float(np.mean([1 if r["abs_error_agent"] < r["abs_error_b0"] else 0 for r in eval_results]))
    win_rate_vs_b1 = float(np.mean([1 if r["abs_error_agent"] < r["abs_error_b1"] else 0 for r in eval_results]))
    win_rate_vs_b2 = float(np.mean([1 if r["abs_error_agent"] < r["abs_error_b2"] else 0 for r in eval_results]))
    win_rate_vs_b3 = float(np.mean([1 if r["abs_error_agent"] < r["abs_error_b3"] else 0 for r in eval_results]))

    mean_forecast = float(np.mean([r["agent_median_forecast"] for r in eval_results]))
    mean_realized = float(np.mean([r["realized_abs_move"] for r in eval_results]))
    bias_agent = mean_forecast - mean_realized

    coverage_60 = float(np.mean([1 if r["in_interval_60"] else 0 for r in eval_results]))
    exceed_accuracy = float(np.mean([1 if r["exceed_correct"] else 0 for r in eval_results]))

    def split_metric_snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
        """A compact snapshot used to prevent accidental holdout cherry-picking."""
        if not rows:
            return {"evaluated_events_count": 0}
        return {
            "evaluated_events_count": len(rows),
            "mae_agent": round(float(np.mean([row["abs_error_agent"] for row in rows])), 5),
            "mae_b0_hist_median": round(float(np.mean([row["abs_error_b0"] for row in rows])), 5),
            "mae_b1_implied_move": round(float(np.mean([row["abs_error_b1"] for row in rows])), 5),
            "interval_60_coverage_pct": round(
                float(np.mean([1 if row["in_interval_60"] else 0 for row in rows])) * 100, 2
            ),
            "agent_wins_vs_implied_pct": round(
                float(np.mean([1 if row["abs_error_agent"] < row["abs_error_b1"] else 0 for row in rows])) * 100, 2
            ),
        }

    split_metrics = {
        split: split_metric_snapshot([row for row in eval_results if row["evaluation_split"] == split])
        for split in SPLIT_NAMES
    }
    calibration_by_split = {
        split: calibration_breakdown([row for row in eval_results if row["evaluation_split"] == split])
        for split in SPLIT_NAMES
    }

    # Bootstrap by earnings date, not individual events, because companies
    # reporting on the same date share a market regime and are not IID.
    rng = np.random.default_rng(42)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in eval_results:
        groups.setdefault(row["earnings_date"], []).append(row)
    cluster_rows = list(groups.values())
    boot_diff_b0, boot_diff_b1 = [], []
    for _ in range(10000):
        sampled = [cluster_rows[index] for index in rng.choice(len(cluster_rows), size=len(cluster_rows), replace=True)]
        flattened = [row for group in sampled for row in group]
        boot_diff_b0.append(float(np.mean([row["abs_error_agent"] - row["abs_error_b0"] for row in flattened])))
        boot_diff_b1.append(float(np.mean([row["abs_error_agent"] - row["abs_error_b1"] for row in flattened])))

    ci_b0 = (float(np.percentile(boot_diff_b0, 2.5)), float(np.percentile(boot_diff_b0, 97.5)))
    ci_b1 = (float(np.percentile(boot_diff_b1, 2.5)), float(np.percentile(boot_diff_b1, 97.5)))

    # Selective Accuracy (Traded vs Abstain)
    traded_events = [r for r in eval_results if r["decision"] != "no_trade"]
    abstain_events = [r for r in eval_results if r["decision"] == "no_trade"]

    traded_mae_agent = float(np.mean([r["abs_error_agent"] for r in traded_events])) if traded_events else 0.0
    traded_mae_b1 = float(np.mean([r["abs_error_b1"] for r in traded_events])) if traded_events else 0.0

    abstain_mae_agent = float(np.mean([r["abs_error_agent"] for r in abstain_events])) if abstain_events else 0.0
    abstain_mae_b1 = float(np.mean([r["abs_error_b1"] for r in abstain_events])) if abstain_events else 0.0

    # Verdict Determination
    if (
        n_events >= 30
        and
        mae_agent < mae_b0
        and mae_agent < mae_b1
        and ci_b0[1] < 0.0
        and ci_b1[1] < 0.0
        and 0.50 <= coverage_60 <= 0.70
    ):
        verdict = "Evidence of out-of-sample improvement, pending independent validation"
    elif n_events >= 30 and (
        (mae_agent < mae_b0 or mae_agent < mae_b1 or win_rate_vs_b1 > 0.50)
        and (ci_b0[0] <= 0.0 or ci_b1[0] <= 0.0)
    ):
        verdict = "Promising but statistically unproven"
    else:
        verdict = "No evidence of predictive alpha"

    summary = {
        "evaluated_events_count": n_events,
        "excluded_events_count": len(excluded_events),
        "metrics": {
            "mae": {
                "agent": round(mae_agent, 5),
                "b0_hist_median": round(mae_b0, 5),
                "b1_implied_move": round(mae_b1, 5),
                "b2_sector_median": round(mae_b2, 5),
                "b3_global_median": round(mae_b3, 5),
            },
            "rmse": {
                "agent": round(rmse_agent, 5),
                "b0_hist_median": round(rmse_b0, 5),
                "b1_implied_move": round(rmse_b1, 5),
                "b2_sector_median": round(rmse_b2, 5),
                "b3_global_median": round(rmse_b3, 5),
            },
            "median_absolute_error": {
                "agent": round(med_ae_agent, 5),
                "b0_hist_median": round(med_ae_b0, 5),
                "b1_implied_move": round(med_ae_b1, 5),
                "b2_sector_median": round(med_ae_b2, 5),
                "b3_global_median": round(med_ae_b3, 5),
            },
            "win_rate": {
                "vs_b0_hist_median": round(win_rate_vs_b0, 4),
                "vs_b1_implied_move": round(win_rate_vs_b1, 4),
                "vs_b2_sector_median": round(win_rate_vs_b2, 4),
                "vs_b3_global_median": round(win_rate_vs_b3, 4),
            },
            "bias": {
                "mean_forecast": round(mean_forecast, 5),
                "mean_realized": round(mean_realized, 5),
                "forecast_bias": round(bias_agent, 5),
            },
            "calibration": {
                "nominal_interval_pct": 60.0,
                "empirical_coverage_pct": round(coverage_60 * 100, 2),
                "exceedance_directional_accuracy_pct": round(exceed_accuracy * 100, 2),
                "reliability_by_forecast_bucket": calibration_breakdown(eval_results),
            },
            "bootstrap_95ci_mae_diff": {
                "agent_minus_b0": [round(ci_b0[0], 5), round(ci_b0[1], 5)],
                "agent_minus_b1": [round(ci_b1[0], 5), round(ci_b1[1], 5)],
                "method": "cluster bootstrap by earnings date",
            },
            "selective_prediction": {
                "traded_events_count": len(traded_events),
                "traded_mae_agent": round(traded_mae_agent, 5),
                "traded_mae_b1": round(traded_mae_b1, 5),
                "abstain_events_count": len(abstain_events),
                "abstain_mae_agent": round(abstain_mae_agent, 5),
                "abstain_mae_b1": round(abstain_mae_b1, 5),
            },
        },
        "chronological_splits": {
            "policy": "First 60% train, next 20% validation, newest 20% holdout by decision cutoff.",
            "purpose": "Reserved for future model selection; this runner performs no parameter fitting.",
            "metrics": split_metrics,
            "calibration": calibration_by_split,
        },
        "verdict_scope": (
            "Fixed-model exploratory out-of-sample result. If any parameter is selected after inspecting "
            "these results, report performance only on the untouched holdout split."
        ),
        "verdict": verdict,
    }

    # Save output artifacts
    results_payload = {
        "protocol": {
            "data_cutoff_rule": "Every underlying and option observation must be timestamped at or before cutoff.",
            "forecast_lock_rule": "Predictions are written to oos_locked_predictions.json before outcome retrieval.",
            "option_data_limitation": "Historical option bars are non-executable price proxies; this is not a P&L backtest.",
            "claim_limit": "The fixed-model full sample is exploratory out-of-sample evidence. A tuned model must be judged on the untouched holdout split.",
            "lock_receipt_file": "oos_locked_predictions.json",
            "lock_receipt_hash": lock_payload["receipt_hash"],
        },
        "summary": summary,
        "events": eval_results,
        "excluded_events": excluded_events,
    }

    json_path = out_dir / "oos_evaluation_results.json"
    with open(json_path, "w") as f:
        json.dump(results_payload, f, indent=2)

    # Save summary CSV
    csv_path = out_dir / "oos_evaluation_summary.csv"
    if eval_results:
        headers = [
            "event_id", "symbol", "sector", "evaluation_split", "earnings_date", "cutoff_utc", "spot_cutoff",
            "prior_jumps_count", "agent_median_forecast", "q20", "q80",
            "b0_hist_median", "b1_implied_move", "b2_sector_median", "b3_global_median",
            "realized_abs_move", "abs_error_agent", "abs_error_b0",
            "abs_error_b1", "abs_error_b2", "abs_error_b3", "in_interval_60", "exceed_correct",
            "decision", "gate_status", "abstention_reason", "model_version", "forecast_hash"
        ]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for r in eval_results:
                writer.writerow(r)

    return results_payload


if __name__ == "__main__":
    print("Starting Out-Of-Sample Historical Evaluation...")
    res = run_out_of_sample_evaluation()
    print("\n=================== OUT-OF-SAMPLE EVALUATION SUMMARY ===================")
    print(json.dumps(res["summary"], indent=2))
