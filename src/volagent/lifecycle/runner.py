"""Autonomous Lifecycle Runner orchestrating Scanner, Watcher, Monitor, and Reporters under SingleRuntimeLock."""

from datetime import datetime, timezone
import json
import logging
from typing import Any

from volagent.domain.enums import ExecutionStatus
from volagent.config import VolAgentSettings, load_config
from volagent.competition import competition_submission_permitted, read_competition_status
from volagent.domain.portfolio import PortfolioSnapshot
from volagent.errors import ExecutionError
from volagent.execution.ledger import ExecutionLedger
from volagent.execution.runtime_lock import SingleRuntimeLock
from volagent.evaluation.benchmark_book import (
    lock_benchmark_intent,
    settle_due_benchmark_intents,
)
from volagent.lifecycle.monitor import PositionMonitor
from volagent.lifecycle.reporters import ClosedTradeReporter, DailyReconciliationReporter
from volagent.lifecycle.scanner import EventScanner
from volagent.lifecycle.watcher import OrderWatcher

logger = logging.getLogger(__name__)


def classify_submission_status(status: ExecutionStatus) -> str:
    """Classify a broker receipt without overstating an ambiguous submission."""
    if status in {
        ExecutionStatus.ACCEPTED,
        ExecutionStatus.PARTIALLY_FILLED,
        ExecutionStatus.FILLED,
    }:
        return "acknowledged"
    if status == ExecutionStatus.REJECTED:
        return "rejected"
    if status == ExecutionStatus.UNKNOWN:
        return "unknown"
    return "other"


def benchmark_decision_time(
    *,
    is_live_mode: bool,
    cycle_time: datetime,
    post_fetch_time: datetime,
) -> datetime:
    """Return the quote cutoff for benchmark locking in live or replay mode."""
    return post_fetch_time if is_live_mode else cycle_time


class LifecycleRunner:
    """Single-instance autonomous options alpha lifecycle runtime."""

    def __init__(
        self,
        ledger: ExecutionLedger | None = None,
        trading_client: Any | None = None,
        lock_path: str | None = None,
        settings: VolAgentSettings | None = None,
    ):
        self.settings = settings
        scanner_settings = settings.competition if settings is not None else None
        self.ledger = ledger or ExecutionLedger()
        self.trading_client = trading_client
        self.lock = SingleRuntimeLock(lock_path=lock_path)
        self.scanner = EventScanner(
            trading_client=self.trading_client,
            daily_volatility_symbols=(scanner_settings.daily_volatility_symbols if scanner_settings else None),
            daily_scan_start_et=(scanner_settings.scan_start_et if scanner_settings else "10:15"),
            daily_scan_end_et=(scanner_settings.scan_end_et if scanner_settings else "14:30"),
        )
        self.watcher = OrderWatcher(ledger=self.ledger, trading_client=self.trading_client)
        self.monitor = PositionMonitor(
            ledger=self.ledger,
            trading_client=self.trading_client,
            settings=settings,
        )
        self.trade_reporter = ClosedTradeReporter(ledger=self.ledger)
        self.daily_reporter = DailyReconciliationReporter(ledger=self.ledger, trading_client=self.trading_client)

    def run_cycle(
        self,
        calendar: dict[str, Any] | None = None,
        current_time: datetime | None = None,
        scan_opportunities: bool = True,
    ) -> dict[str, Any]:
        """Execute one lifecycle iteration; monitoring may explicitly suppress new scans."""
        with self.lock:
            now = current_time or datetime.now(timezone.utc)
            cfg = self.settings or load_config()
            results = {
                "timestamp": now.isoformat(),
                "market_open": self.scanner.is_market_open(now),
                "events_found": 0,
                "orders_synced": 0,
                "orders_canceled_at_cutoff": 0,
                "orders_canceled_for_halt": 0,
                "positions_monitored": 0,
                "exits_triggered": 0,
                "reconciliation_status": "CLEAN",
                "previews_created": 0,
                "decisions_generated": 0,
                "entries_submitted": 0,
                "submission_attempts": 0,
                "entries_unknown": 0,
                "rejected_entries": 0,
                "abstentions": 0,
                "benchmark_intents_locked": 0,
                "benchmark_intent_failures": 0,
                "benchmark_settlements": {"due": 0, "settled": 0, "pending": 0, "errors": []},
                "errors": [],
                "competition_authorization": {
                    "status": "DISABLED" if not cfg.competition.enabled else "DISARMED",
                    "submission_authorized": False,
                    "reason": "Competition mode disabled" if not cfg.competition.enabled else "Authorization not checked",
                },
            }

            configured_mode = str(cfg.volagent_data_mode).strip().lower()
            is_live_mode = configured_mode == "live"
            if cfg.competition.enabled and is_live_mode:
                from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter

                settlement_adapter = AlpacaLiveMarketAdapter(
                    api_key=cfg.alpaca_api_key,
                    secret_key=cfg.alpaca_secret_key,
                    stock_feed=cfg.market_data.stock_feed,
                    options_feed=cfg.market_data.options_feed,
                )
                market_open, _ = settlement_adapter.get_market_status()
                if market_open:
                    results["benchmark_settlements"] = settle_due_benchmark_intents(
                        ledger=self.ledger,
                        market_adapter=settlement_adapter,
                        now=now,
                    )

            # 1. Order Watcher Sync
            watcher_counts = self.watcher.sync_active_orders()
            results["orders_synced"] = watcher_counts.get("synced", 0)
            halted, halt_reason = self.ledger.is_system_halted()
            if halted:
                halt_cancellations = self.watcher.cancel_open_entry_orders(
                    reason=f"Safety halt before position exits: {halt_reason}"
                )
                results["orders_canceled_for_halt"] = len(halt_cancellations)
            else:
                cutoff_cancellations = self.watcher.cancel_expired_entry_orders(
                    current_time=now
                )
                results["orders_canceled_at_cutoff"] = len(cutoff_cancellations)

            # 2. Position Monitor
            open_positions = self.ledger.list_open_positions()
            results["positions_monitored"] = len(open_positions)
            for pos_row in open_positions:
                strat_id = pos_row.get("strategy_id") or pos_row.get("fingerprint", "")
                sym = pos_row.get("symbol", "")
                try:
                    raw_plan = pos_row.get("full_order_plan")
                    plan_data = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
                    expected_contracts = {
                        str(leg["contract_symbol"])
                        for leg in (plan_data or {}).get("legs", [])
                        if leg.get("contract_symbol")
                    }
                except (TypeError, ValueError, KeyError) as exc:
                    results["errors"].append(f"{sym}: invalid persisted OrderPlan: {exc}")
                    continue
                if not expected_contracts:
                    results["errors"].append(f"{sym}: no exact contracts in persisted OrderPlan")
                    continue
                try:
                    snap = self.monitor.build_broker_position_snapshot(
                        strat_id, sym, expected_contracts=expected_contracts
                    )
                    mon_report = self.monitor.monitor_and_close_strategy(
                        pos_row, snap, current_time=now
                    )
                    if mon_report.exit_trigger:
                        results["exits_triggered"] += 1
                    if mon_report.status == "EXIT_FAILED":
                        results["errors"].append(
                            f"{sym}: exit triggered but close submission/accounting failed"
                        )
                        results["cycle_status"] = "ERROR"
                except Exception as exc:
                    logger.error("Position monitoring failed for %s: %s", sym, exc)
                    results["errors"].append(f"{sym}: position monitoring failed: {exc}")
                    results["cycle_status"] = "ERROR"
                    continue

            # 3. Event Scanner & Autonomous Opportunity Pipeline
            if scan_opportunities and (calendar or cfg.competition.enabled):
                eligible = self.scanner.scan_eligible_events(calendar, current_time=now) if calendar else []
                if cfg.competition.enabled:
                    eligible.extend(self.scanner.scan_daily_volatility_opportunities(current_time=now))
                results["events_found"] = len(eligible)

                from volagent.graph.builder import VolAgentWorkflow
                from volagent.domain.enums import Decision, BrokerTarget, DataMode
                from volagent.quant.allocator import PortfolioAllocator, CandidateEvaluation
                from volagent.data.alpaca_sdk import AlpacaPortfolioAdapter
                from volagent.execution.alpaca import build_order_plan, AlpacaPaperBroker

                is_live_mode = configured_mode == DataMode.LIVE.value
                if is_live_mode:
                    adapter = AlpacaPortfolioAdapter(
                        api_key=cfg.alpaca_api_key,
                        secret_key=cfg.alpaca_secret_key,
                        paper=cfg.alpaca_paper_trade,
                    )
                    if self.trading_client:
                        adapter._trading_client = self.trading_client
                    portfolio_snap = adapter.fetch_portfolio_snapshot(ledger=self.ledger)
                    if portfolio_snap.is_stale:
                        results["cycle_status"] = "ERROR"
                        results["errors"].append(
                            "Live lifecycle blocked: fresh authenticated Alpaca portfolio snapshot unavailable."
                        )
                        return results
                    results["competition_authorization"] = read_competition_status(
                        path=cfg.competition.lease_path,
                        settings=cfg,
                        paper_account_id=portfolio_snap.account_id,
                        now=now,
                    ) if cfg.competition.enabled else results["competition_authorization"]
                else:
                    # Replay analysis is deterministic and never contacts the
                    # broker.  This NAV is explicitly synthetic and is carried
                    # into the resulting replay DecisionRecord.
                    portfolio_snap = PortfolioSnapshot(
                        equity=100000.0,
                        cash=100000.0,
                        buying_power=100000.0,
                        initial_nav=100000.0,
                        high_water_equity=100000.0,
                        timestamp=now,
                        account_id="replay-synthetic",
                    )

                workflow = VolAgentWorkflow(config=cfg)
                candidate_evals: list[CandidateEvaluation] = []
                candidate_context: dict[str, dict[str, Any]] = {}

                for ev in eligible:
                    try:
                        initial_inputs = {
                            "symbol": ev.symbol,
                            "event": ev,
                            "now": now,
                            "mode": DataMode.LIVE if is_live_mode else DataMode.REPLAY_SYNTHETIC,
                            "portfolio_snapshot": portfolio_snap,
                            "ledger": self.ledger,
                        }
                        out = workflow.run(initial_inputs)
                        results["decisions_generated"] += 1

                        underlying = out.get("underlying")
                        decision_record = out.get("decision_record")
                        if underlying is None or decision_record is None:
                            raise ExecutionError(
                                "Benchmark lock blocked: workflow did not return an underlying snapshot and decision record."
                            )
                        # Live market data is fetched after the lifecycle cycle starts,
                        # so use a post-fetch cutoff. Replay remains pinned to the
                        # deterministic lifecycle clock.
                        decision_time = benchmark_decision_time(
                            is_live_mode=is_live_mode,
                            cycle_time=now,
                            post_fetch_time=datetime.now(timezone.utc),
                        )
                        common_risk_budget = min(
                            float(portfolio_snap.equity) * float(cfg.risk.hard_max_risk_nav_pct),
                            float(cfg.mandate.recommended_max_loss_per_strategy),
                        )
                        try:
                            benchmark_intent = lock_benchmark_intent(
                                opportunity_id=getattr(ev, "event_id", f"evt-{ev.symbol}"),
                                decision_id=decision_record.decision_id,
                                decision_time=decision_time,
                                exit_time=ev.exit_time,
                                underlying=underlying,
                                option_chain=out.get("option_chain", []),
                                candidates=out.get("candidates", []),
                                approved_candidate=out.get("approved_candidate"),
                                final_decision=out.get("final_decision", Decision.NO_TRADE),
                                starting_nav=float(cfg.mandate.competition_initial_nav),
                                risk_budget=common_risk_budget,
                                fee_per_contract=float(cfg.execution.fee_per_contract),
                                slippage_per_contract=float(cfg.execution.slippage_per_contract),
                                data_mode=DataMode.LIVE.value if is_live_mode else DataMode.REPLAY_SYNTHETIC.value,
                            )
                            self.ledger.record_benchmark_intent(benchmark_intent)
                        except Exception as benchmark_exc:
                            raise ExecutionError(
                                f"Benchmark lock blocked: {benchmark_exc}"
                            ) from benchmark_exc
                        results["benchmark_intents_locked"] += 1

                        app_cand = out.get("approved_candidate")
                        final_dec = out.get("final_decision", Decision.NO_TRADE)
                        if final_dec == Decision.NO_TRADE or not app_cand or app_cand.quantity <= 0:
                            results["abstentions"] += 1
                        else:
                            edge_pct = getattr(app_cand, "executable_edge_pct", 0.05)
                            candidate_evals.append(
                                CandidateEvaluation(
                                    symbol=ev.symbol,
                                    event_id=ev.event_id if hasattr(ev, "event_id") else f"evt-{ev.symbol}",
                                    candidate=app_cand,
                                    decision=final_dec,
                                    executable_edge_pct=edge_pct,
                                    max_loss_dollars=app_cand.max_loss,
                                    risk_adjusted_score=app_cand.risk_adjusted_score or 1.0,
                                    proposals=[],
                                    rejection_reasons=[],
                                )
                            )
                            candidate_context[app_cand.strategy_id] = out
                    except Exception as exc:
                        logger.error(f"Error processing lifecycle candidate {ev.symbol}: {exc}")
                        if "Benchmark lock blocked" in str(exc) or "benchmark" in type(exc).__name__.lower():
                            results["benchmark_intent_failures"] += 1
                        results["errors"].append(f"{ev.symbol}: {exc}")
                        results["cycle_status"] = "ERROR"

                # Allocate among multiple candidates using PortfolioAllocator
                if candidate_evals:
                    allocator = PortfolioAllocator(mandate=cfg.mandate)
                    alloc_res = allocator.rank_and_allocate(
                        evaluations=candidate_evals,
                        current_equity=portfolio_snap.equity,
                        currently_reserved_risk=portfolio_snap.reserved_risk_dollars,
                        today_entry_count=portfolio_snap.new_entries_today_count,
                    )

                    results["rejected_entries"] += len(alloc_res.rejected_candidates)

                    for cand in alloc_res.accepted_candidates:
                        out = candidate_context[cand.strategy_id]
                        target = BrokerTarget.ALPACA_PAPER if is_live_mode else BrokerTarget.SIMULATED_LOCAL
                        chain_by_symbol = {
                            snap.symbol: snap for snap in out.get("option_chain", [])
                        }
                        decision_record = out.get("decision_record")
                        plan = build_order_plan(
                            candidate=cand,
                            broker_target=target,
                            ledger=self.ledger,
                            contract_snapshots=chain_by_symbol if target == BrokerTarget.ALPACA_PAPER else None,
                            decision_id=getattr(decision_record, "decision_id", "dec-lifecycle"),
                            event_id=getattr(decision_record, "snapshot", None).event_id
                            if getattr(decision_record, "snapshot", None) else "evt-lifecycle",
                            risk_reservation_ref=getattr(out.get("portfolio_risk_report"), "risk_reservation_ref", None),
                        )
                        results["previews_created"] += 1

                        # A disabled global switch means preview-only.  Replay
                        # mode also never reaches Alpaca.  Human approval, when
                        # configured, leaves the plan PREVIEWED for the cockpit.
                        can_auto_submit = competition_submission_permitted(
                            settings=cfg,
                            status=results["competition_authorization"],
                            is_live_mode=is_live_mode,
                        )
                        if can_auto_submit:
                            self.ledger.record_approval(plan.approval_token, approver="lifecycle_runner")
                            broker = AlpacaPaperBroker(
                                api_key=cfg.alpaca_api_key,
                                secret_key=cfg.alpaca_secret_key,
                                ledger=self.ledger,
                                allow_order_submission=True,
                                paper=True,
                                settings=cfg,
                            )
                            if self.trading_client:
                                broker._trading_client = self.trading_client
                            results["submission_attempts"] += 1
                            try:
                                receipt = broker.submit_paper_order(plan)
                            except Exception as exc:
                                persisted = self.ledger.get_order_by_client_order_id(
                                    plan.client_order_id
                                )
                                try:
                                    persisted_status = ExecutionStatus(
                                        persisted.get("status", "unknown") if persisted else "unknown"
                                    )
                                except ValueError:
                                    persisted_status = ExecutionStatus.UNKNOWN
                                persisted_outcome = classify_submission_status(persisted_status)
                                if persisted_outcome == "rejected":
                                    results["rejected_entries"] += 1
                                else:
                                    results["entries_unknown"] += 1
                                results["errors"].append(
                                    f"{cand.strategy_id}: broker submission ambiguous or failed: {exc}"
                                )
                                results["cycle_status"] = "ERROR"
                                continue
                            outcome = classify_submission_status(receipt.status)
                            if outcome == "acknowledged":
                                results["entries_submitted"] += 1
                            elif outcome == "rejected":
                                results["rejected_entries"] += 1
                            elif outcome == "unknown":
                                results["entries_unknown"] += 1
                                results["cycle_status"] = "ERROR"
                            else:
                                results["errors"].append(
                                    f"{cand.strategy_id}: unexpected broker receipt status {receipt.status.value}"
                                )
                                results["cycle_status"] = "ERROR"

            # 4. Daily Reconciliation
            if self.trading_client:
                recon = self.daily_reporter.generate_daily_report()
                results["reconciliation_status"] = recon.get("status", "CLEAN")

            return results
