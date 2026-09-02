"""Position Monitor evaluating open strategies, exit triggers, and broker position reconciliation."""

from datetime import datetime, time, timezone
import json
import logging
import math
from typing import Any

from volagent.domain.enums import BrokerTarget, Decision, ExecutionStatus
from volagent.domain.execution import OrderPlan, VerifiedPositionLeg, VerifiedStrategyPositionSnapshot
from volagent.domain.market import OptionContractSnapshot
from volagent.domain.lifecycle import ExitTrigger, ExitTriggerType, PositionMonitorReport
from volagent.errors import ExecutionError
from volagent.execution.alpaca import (
    AlpacaPaperBroker,
    SimulatedPaperBroker,
    create_closing_order_service,
    parse_occ_underlying,
)
from volagent.execution.ledger import ExecutionLedger




logger = logging.getLogger(__name__)


class PositionMonitor:
    """Monitors active broker positions and triggers disciplined exits based on mathematical rules."""

    def __init__(
        self,
        ledger: ExecutionLedger,
        trading_client: Any | None = None,
        market_data_adapter: Any | None = None,
        profit_target_pct: float = 0.50,  # 50% max profit
        stop_loss_pct: float = 1.00,       # 100% max loss
        settings: Any | None = None,
    ):
        self.ledger = ledger
        self.trading_client = trading_client
        self.market_data_adapter = market_data_adapter
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.settings = settings

    def _fetch_exact_close_snapshots(
        self, entry_plan: OrderPlan
    ) -> dict[str, OptionContractSnapshot]:
        """Fetch fresh quotes for every exact contract in a live entry plan."""
        from volagent.config import load_config
        from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter

        if self.market_data_adapter is not None:
            adapter = self.market_data_adapter
        else:
            settings = self.settings or load_config()
            adapter = AlpacaLiveMarketAdapter(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
                stock_feed=settings.market_data.stock_feed,
                options_feed=settings.market_data.options_feed,
            )
        underlying = adapter.get_underlying_snapshot(entry_plan.symbol)
        if underlying is None:
            raise ExecutionError("Cannot close live strategy: fresh underlying snapshot unavailable.")
        expirations = [leg.expiration for leg in entry_plan.legs]
        chain = adapter.get_option_chain(
            entry_plan.symbol,
            min(expirations),
            max(expirations),
            underlying.price,
        )
        required = {leg.contract_symbol for leg in entry_plan.legs}
        exact = {snap.symbol: snap for snap in chain if snap.symbol in required}
        missing = sorted(required - set(exact))
        if missing:
            raise ExecutionError(
                f"Cannot close live strategy: fresh exact-contract quotes missing for {missing}."
            )
        return exact

    @staticmethod
    def _mark_from_executable_quotes(
        entry_plan: OrderPlan,
        snapshots: dict[str, OptionContractSnapshot],
        quantity: int | None = None,
    ) -> tuple[float, float, float]:
        """Return close-price magnitude, gross P&L, and risk basis from executable quotes."""
        close_cashflow_per_unit = 0.0
        for leg in entry_plan.legs:
            snapshot = snapshots.get(leg.contract_symbol)
            if snapshot is None:
                raise ExecutionError(
                    f"Cannot mark strategy: quote missing for {leg.contract_symbol}."
                )
            if (
                not math.isfinite(snapshot.bid)
                or not math.isfinite(snapshot.ask)
                or snapshot.bid < 0
                or snapshot.ask < snapshot.bid
            ):
                raise ExecutionError(
                    f"Cannot mark strategy: invalid quote for {leg.contract_symbol}."
                )
            quote_time = snapshot.quote_time
            if quote_time.tzinfo is None:
                quote_time = quote_time.replace(tzinfo=timezone.utc)
            quote_age = (
                datetime.now(timezone.utc) - quote_time.astimezone(timezone.utc)
            ).total_seconds()
            if quote_age < -2.0 or quote_age > 30.0:
                raise ExecutionError(
                    f"Cannot mark strategy: quote for {leg.contract_symbol} is stale or temporally invalid."
                )
            if leg.side.value == "buy":
                close_cashflow_per_unit += snapshot.bid * leg.ratio_qty
            else:
                close_cashflow_per_unit -= snapshot.ask * leg.ratio_qty

        entry_cashflow_per_unit = (
            -entry_plan.limit_price
            if entry_plan.net_price_convention.value == "debit"
            else entry_plan.limit_price
        )
        effective_quantity = quantity if quantity is not None else entry_plan.quantity
        gross_pnl = (
            entry_cashflow_per_unit + close_cashflow_per_unit
        ) * 100.0 * effective_quantity
        plan_risk_basis = (
            entry_plan.estimated_cost_dollars
            if entry_plan.net_price_convention.value == "debit"
            else entry_plan.max_loss_dollars
        )
        risk_basis = plan_risk_basis * effective_quantity / entry_plan.quantity
        return abs(close_cashflow_per_unit), gross_pnl, risk_basis

    @staticmethod
    def _verified_strategy_quantity(
        entry_plan: OrderPlan,
        verified_snapshot: VerifiedStrategyPositionSnapshot,
    ) -> int:
        """Derive complete strategy units from exact broker leg quantities."""
        positions = {position.contract_symbol: position for position in verified_snapshot.positions}
        unit_counts: list[int] = []
        for leg in entry_plan.legs:
            position = positions.get(leg.contract_symbol)
            if position is None:
                raise ExecutionError(
                    f"Cannot mark strategy: broker position missing for {leg.contract_symbol}."
                )
            expected_side = "long" if leg.side.value == "buy" else "short"
            if position.side.lower() != expected_side:
                raise ExecutionError(
                    f"Cannot mark strategy: broker side for {leg.contract_symbol} is not {expected_side}."
                )
            units = position.qty // leg.ratio_qty
            if units <= 0:
                raise ExecutionError(
                    f"Cannot mark strategy: broker quantity is zero for {leg.contract_symbol}."
                )
            unit_counts.append(units)
        if len(set(unit_counts)) != 1:
            raise ExecutionError(
                f"Cannot mark strategy: asymmetric multi-leg fill quantities {unit_counts}."
            )
        return unit_counts[0]

    def build_broker_position_snapshot(
        self,
        strategy_id: str,
        symbol: str,
        expected_contracts: set[str] | None = None,
    ) -> VerifiedStrategyPositionSnapshot:
        """Fetch authoritative broker positions for the exact strategy contracts."""
        now = datetime.now(timezone.utc)
        verified_legs: list[VerifiedPositionLeg] = []

        if self.trading_client:
            try:
                positions = self.trading_client.get_all_positions()
                for pos in positions:
                    pos_sym = str(getattr(pos, "symbol", ""))
                    # Exact contract matching if available, else exact OCC underlying matching
                    matches = (pos_sym in expected_contracts) if expected_contracts else (parse_occ_underlying(pos_sym) == symbol.upper())
                    if matches:
                        qty = int(getattr(pos, "qty", 0))
                        side = "long" if qty > 0 else "short"
                        avg_price = float(getattr(pos, "avg_entry_price", 0.0))
                        verified_legs.append(
                            VerifiedPositionLeg(
                                contract_symbol=pos_sym,
                                symbol=symbol.upper(),
                                qty=abs(qty),
                                side=side,
                                avg_entry_price=avg_price,
                            )
                        )
            except Exception as exc:
                logger.error(f"Error fetching broker positions: {exc}")

        return VerifiedStrategyPositionSnapshot(
            strategy_id=strategy_id,
            symbol=symbol.upper(),
            timestamp=now,
            positions=verified_legs,
            evidence_source="alpaca_paper",
        )


    def evaluate_exit_trigger(
        self,
        strategy_row: dict[str, Any],
        verified_snapshot: VerifiedStrategyPositionSnapshot,
        current_time: datetime | None = None,
        current_mark_price: float | None = None,
    ) -> ExitTrigger | None:
        """Evaluate profit target, stop loss, post-event time, or safety halt exit triggers."""
        now = current_time or datetime.now(timezone.utc)

        # 1. Safety Halt Check
        is_halted, halt_reason = self.ledger.is_system_halted()
        if is_halted:
            return ExitTrigger(
                trigger_type=ExitTriggerType.SAFETY_HALT,
                reason=f"Safety halt active: {halt_reason}",
                triggered_at=now,
                action_required=True,
            )

        # 2. Check if broker positions exist
        if not verified_snapshot.positions:
            return None

        # 3. Post-Event Time Stop (Morning after earnings event: >= 09:30 ET / 13:30 UTC next trading day)
        created_at_str = str(strategy_row.get("created_at", ""))
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                now_utc = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
                holding_hours = (now_utc - created_at).total_seconds() / 3600.0
                is_next_day_or_later = now_utc.date() > created_at.date()
                if (holding_hours >= 14.0 or is_next_day_or_later) and now_utc.time() >= time(13, 30):
                    return ExitTrigger(
                        trigger_type=ExitTriggerType.POST_EVENT_EXPIRATION,
                        reason=f"Post-event evaluation time reached (holding duration {holding_hours:.1f}h)",
                        triggered_at=now_utc,
                        action_required=True,
                    )
            except Exception:
                pass


        # 4. Profit Target and Max Loss Evaluation
        if current_mark_price is not None:
            try:
                entry_limit = float(strategy_row.get("limit_price", 0.0))
                plan_json = strategy_row.get("full_order_plan")
                plan = {}
                if plan_json:
                    plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
                    if entry_limit <= 0:
                        entry_limit = float(plan.get("limit_price", 0.0))

                decision = str(strategy_row.get("decision") or plan.get("decision") or "long_straddle").lower()
                qty = int(strategy_row.get("quantity") or plan.get("quantity") or 1)
                convention = str(plan.get("net_price_convention", "debit")).lower()
                is_credit = convention == "credit"
                unrealized_pnl = (
                    (entry_limit - current_mark_price)
                    if is_credit
                    else (current_mark_price - entry_limit)
                ) * 100.0 * qty
                profit_basis = entry_limit * 100.0 * qty
                plan_quantity = max(1, int(plan.get("quantity") or qty))
                max_loss = float(plan.get("max_loss_dollars") or profit_basis)
                max_loss *= qty / plan_quantity
                loss_limit = max_loss * self.stop_loss_pct
                label = decision.replace("_", " ").title()

                if entry_limit > 0 and unrealized_pnl >= profit_basis * self.profit_target_pct:
                    return ExitTrigger(
                        trigger_type=ExitTriggerType.PROFIT_TARGET,
                        reason=f"{label} profit target reached (+${unrealized_pnl:.2f})",
                        triggered_at=now,
                        estimated_pnl_dollars=unrealized_pnl,
                        action_required=True,
                    )
                if entry_limit > 0 and unrealized_pnl <= -loss_limit:
                    return ExitTrigger(
                        trigger_type=ExitTriggerType.MAX_LOSS,
                        reason=f"{label} stop loss breached (-${abs(unrealized_pnl):.2f})",
                        triggered_at=now,
                        estimated_pnl_dollars=unrealized_pnl,
                        action_required=True,
                    )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Cannot evaluate P&L exit trigger: %s", exc)


        return None


    def monitor_and_close_strategy(
        self,
        strategy_row: dict[str, Any],
        verified_snapshot: VerifiedStrategyPositionSnapshot,
        current_time: datetime | None = None,
        current_mark_price: float | None = None,
    ) -> PositionMonitorReport:
        """Monitor one strategy and dispatch closing order if trigger fired."""
        now = current_time or datetime.now(timezone.utc)
        strategy_id = strategy_row.get("strategy_id") or strategy_row.get("fingerprint", "")
        symbol = strategy_row.get("symbol", "UNKNOWN")
        dec_str = strategy_row.get("decision", "long_straddle")
        decision = Decision(dec_str) if dec_str in [d.value for d in Decision] else Decision.LONG_STRADDLE

        plan_json = strategy_row.get("full_order_plan")
        entry_plan = None
        close_snapshots = None
        computed_pnl = None
        risk_basis = None
        effective_quantity = int(strategy_row.get("quantity", 1))
        if plan_json:
            plan_dict = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
            entry_plan = OrderPlan.model_validate(plan_dict)
            if verified_snapshot.positions:
                effective_quantity = self._verified_strategy_quantity(
                    entry_plan, verified_snapshot
                )
            if (
                current_mark_price is None
                and verified_snapshot.positions
                and entry_plan.broker_target == BrokerTarget.ALPACA_PAPER
            ):
                close_snapshots = self._fetch_exact_close_snapshots(entry_plan)
                current_mark_price, computed_pnl, risk_basis = self._mark_from_executable_quotes(
                    entry_plan, close_snapshots, quantity=effective_quantity
                )

        evaluation_row = dict(strategy_row)
        evaluation_row["quantity"] = effective_quantity
        trigger = self.evaluate_exit_trigger(
            strategy_row=evaluation_row,
            verified_snapshot=verified_snapshot,
            current_time=now,
            current_mark_price=current_mark_price,
        )

        entry_limit = float(strategy_row.get("limit_price", 0.0))
        quantity = effective_quantity
        mark = current_mark_price if current_mark_price is not None else entry_limit
        if computed_pnl is not None:
            pnl = computed_pnl
            entry_cost = float(risk_basis or 0.0)
        else:
            is_credit = bool(
                entry_plan and entry_plan.net_price_convention.value == "credit"
            )
            pnl = ((entry_limit - mark) if is_credit else (mark - entry_limit)) * 100.0 * quantity
            entry_cost = (
                float(entry_plan.max_loss_dollars)
                if is_credit and entry_plan is not None
                else entry_limit * 100.0 * quantity
            )
            if is_credit and entry_plan is not None:
                entry_cost *= quantity / entry_plan.quantity
        pnl_pct = (pnl / entry_cost) if entry_cost > 0 else 0.0

        report = PositionMonitorReport(
            strategy_id=strategy_id,
            symbol=symbol,
            decision=decision,
            verified_snapshot=verified_snapshot,
            current_mark=mark,
            entry_cost=entry_cost,
            unrealized_pnl_dollars=pnl,
            unrealized_pnl_pct=pnl_pct,
            holding_duration_seconds=0.0,
            exit_trigger=trigger,
            evaluated_at=now,
            status="EXIT_PENDING" if trigger else "OPEN",
        )

        # If an exit trigger is active, construct closing order
        if trigger and trigger.action_required and verified_snapshot.positions:
            if plan_json:
                try:
                    if entry_plan is None:
                        plan_dict = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
                        entry_plan = OrderPlan.model_validate(plan_dict)
                    entry_row = self.ledger.get_order_by_client_order_id(
                        entry_plan.client_order_id
                    )
                    if (
                        entry_plan.broker_target == BrokerTarget.SIMULATED_LOCAL
                        and entry_row
                        and entry_row.get("status") == ExecutionStatus.PREVIEWED.value
                    ):
                        # A verified synthetic position can be reconciled into
                        # the local ledger before closing. Never do this for an
                        # Alpaca paper intent: broker fills remain authoritative.
                        self.ledger.approve_order(
                            entry_plan.approval_token,
                            actor="position_monitor_simulated_reconciliation",
                        )
                        SimulatedPaperBroker(ledger=self.ledger).submit_simulated_order(
                            entry_plan
                        )
                    if entry_plan.broker_target == BrokerTarget.ALPACA_PAPER and close_snapshots is None:
                        close_snapshots = self._fetch_exact_close_snapshots(entry_plan)
                    close_plan = create_closing_order_service(
                        entry_plan=entry_plan,
                        verified_positions=verified_snapshot,
                        contract_snapshots=close_snapshots,
                        net_closing_limit_price=max(0.01, mark),
                        ledger=self.ledger,
                        broker_target=entry_plan.broker_target,
                    )
                    
                    # Approve the closing order plan in ledger
                    self.ledger.approve_order(close_plan.approval_token, actor="position_monitor")

                    receipt = None
                    if entry_plan.broker_target == BrokerTarget.ALPACA_PAPER:
                        broker = AlpacaPaperBroker(
                            ledger=self.ledger,
                            allow_order_submission=True,
                            paper=True,
                            settings=self.settings,
                        )
                        if self.trading_client:
                            broker._trading_client = self.trading_client
                        receipt = broker.submit_paper_order(close_plan)
                    else:
                        sim_broker = SimulatedPaperBroker(ledger=self.ledger)
                        receipt = sim_broker.submit_simulated_order(close_plan)

                    if receipt and receipt.status in (ExecutionStatus.FILLED, ExecutionStatus.SIMULATED):
                        from volagent.lifecycle.watcher import OrderWatcher

                        close_row = self.ledger.get_order_by_client_order_id(
                            close_plan.client_order_id
                        )
                        finalized = bool(
                            close_row
                            and OrderWatcher(
                                ledger=self.ledger,
                                trading_client=self.trading_client,
                            ).finalize_filled_close(close_row)
                        )
                        if finalized:
                            report = report.model_copy(update={"status": "CLOSED"})
                        else:
                            report = report.model_copy(update={"status": "EXIT_FAILED"})
                except Exception as exc:
                    logger.error(f"Failed to execute automated close for {strategy_id}: {exc}")
                    report = report.model_copy(update={"status": "EXIT_FAILED"})


        return report
