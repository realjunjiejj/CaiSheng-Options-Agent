"""Shadow-Book Counterfactual Evaluator for CaiSheng Options Alpha."""

from datetime import datetime, timezone
import uuid
from typing import Any

from volagent.domain.decision_record import DecisionRecord, ShadowBookRecord, ShadowProposal
from volagent.domain.enums import Decision
from volagent.domain.strategies import StrategyCandidate
from volagent.execution.ledger import ExecutionLedger


class ShadowBookEvaluator:
    """Evaluates chosen vs counterfactual strategy performance against realized outcomes."""

    def __init__(self, ledger: ExecutionLedger | None = None):
        self.ledger = ledger

    def evaluate_shadow_record(
        self,
        decision_record: DecisionRecord,
        actual_post_event_move_pct: float,
        actual_post_event_iv_crush_pts: float,
        straddle_entry_price: float = 4.00,
        butterfly_entry_credit: float = 2.50,
        butterfly_wing_width: float = 5.00,
    ) -> ShadowBookRecord:
        """Evaluate selected and counterfactual payoffs against observed move and IV crush."""
        spot = decision_record.snapshot.spot
        move_dollars = abs(spot * actual_post_event_move_pct) if spot > 0 else 5.0

        # Long Straddle Payoff: max(0, move_dollars) - straddle_entry_price (per share, * 100)
        straddle_exit = move_dollars
        straddle_pnl = (straddle_exit - straddle_entry_price) * 100.0

        # Iron Butterfly Payoff: butterfly_entry_credit - max(0, min(butterfly_wing_width, move_dollars))
        butterfly_loss = max(0.0, min(butterfly_wing_width, move_dollars))
        butterfly_pnl = (butterfly_entry_credit - butterfly_loss) * 100.0

        selected_action = decision_record.selected_action
        selected_pnl = 0.0
        if selected_action == "LONG_STRADDLE":
            selected_pnl = straddle_pnl
        elif selected_action == "SHORT_IRON_BUTTERFLY":
            selected_pnl = butterfly_pnl
        elif selected_action == "NO_TRADE":
            selected_pnl = 0.0

        proposals = [
            ShadowProposal(
                strategy="LONG_STRADDLE",
                executable=True,
                simulated_entry_price=straddle_entry_price,
                simulated_exit_price=round(straddle_exit, 2),
                counterfactual_pnl_dollars=round(straddle_pnl, 2),
                rejection_reason="Not selected" if selected_action != "LONG_STRADDLE" else "Selected strategy",
            ),
            ShadowProposal(
                strategy="SHORT_IRON_BUTTERFLY",
                executable=True,
                simulated_entry_price=butterfly_entry_credit,
                simulated_exit_price=round(butterfly_loss, 2),
                counterfactual_pnl_dollars=round(butterfly_pnl, 2),
                rejection_reason="Not selected" if selected_action != "SHORT_IRON_BUTTERFLY" else "Selected strategy",
            ),
        ]

        record = ShadowBookRecord(
            shadow_id=f"shd-{uuid.uuid4().hex[:12]}",
            event_id=decision_record.snapshot.event_id,
            symbol=decision_record.snapshot.symbol,
            selected_action=selected_action,
            selected_strategy_pnl=round(selected_pnl, 2),
            counterfactual_proposals=proposals,
            actual_post_event_move=actual_post_event_move_pct,
            actual_iv_crush_points=actual_post_event_iv_crush_pts,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )

        if self.ledger:
            self.ledger.record_shadow_book_record(record)

        return record
