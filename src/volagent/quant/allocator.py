"""Deterministic Multi-Candidate Portfolio Allocator for CaiSheng Options Alpha."""

from dataclasses import dataclass, field
from typing import Any

from volagent.config import MandateConfig
from volagent.domain.decision_record import DecisionRecord, StrategyProposal
from volagent.domain.enums import Decision
from volagent.domain.strategies import StrategyCandidate


@dataclass(frozen=True)
class CandidateEvaluation:
    symbol: str
    event_id: str
    candidate: StrategyCandidate
    decision: Decision
    executable_edge_pct: float
    max_loss_dollars: float
    risk_adjusted_score: float
    proposals: list[StrategyProposal]
    rejection_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AllocationResult:
    accepted_candidates: list[StrategyCandidate]
    rejected_candidates: list[tuple[StrategyCandidate, str]]  # candidate, reason
    total_allocated_risk: float
    available_risk_remaining: float


class PortfolioAllocator:
    """Ranks candidate strategies across multiple events and allocates sizing within mandate limits."""

    def __init__(self, mandate: MandateConfig | None = None):
        self.mandate = mandate or MandateConfig()

    def rank_and_allocate(
        self,
        evaluations: list[CandidateEvaluation],
        current_equity: float = 100_000.0,
        currently_reserved_risk: float = 0.0,
        today_entry_count: int = 0,
    ) -> AllocationResult:
        """Rank all candidates by risk-adjusted executable edge and allocate capacity."""
        max_risk_dollars = current_equity * self.mandate.max_total_reserved_risk_nav_pct
        max_daily_entries = self.mandate.max_new_entries_per_day

        # 1. Filter to viable non-abstention candidates
        viable: list[CandidateEvaluation] = []
        rejected: list[tuple[StrategyCandidate, str]] = []

        for ev in evaluations:
            if ev.decision == Decision.NO_TRADE:
                reason = "; ".join(ev.rejection_reasons) if ev.rejection_reasons else "Abstention selected"
                rejected.append((ev.candidate, reason))
            elif ev.executable_edge_pct <= 0.0:
                rejected.append((ev.candidate, f"Non-positive executable edge ({ev.executable_edge_pct*100:+.2f}%)"))
            elif ev.candidate.quantity <= 0:
                rejected.append((ev.candidate, "Quantity is 0"))
            else:
                viable.append(ev)

        # 2. Sort viable candidates by risk_adjusted_score descending
        viable.sort(key=lambda x: x.risk_adjusted_score, reverse=True)

        accepted: list[StrategyCandidate] = []
        allocated_risk = 0.0
        active_entries = today_entry_count

        for item in viable:
            cand = item.candidate
            cand_loss = cand.max_loss

            # Check daily entry slots
            if active_entries >= max_daily_entries:
                rejected.append((cand, f"Max daily entry limit ({max_daily_entries}) reached"))
                continue

            # Check single strategy risk limit
            max_single_loss = current_equity * self.mandate.absolute_max_loss_nav_pct
            if cand_loss > max_single_loss:
                rejected.append((cand, f"Strategy max loss (${cand_loss:.2f}) exceeds single limit (${max_single_loss:.2f})"))
                continue


            # Check total portfolio reserved risk limit
            projected_total = currently_reserved_risk + allocated_risk + cand_loss
            if projected_total > max_risk_dollars:
                rejected.append((cand, f"Projected portfolio risk (${projected_total:.2f}) exceeds total limit (${max_risk_dollars:.2f})"))
                continue

            # Accept candidate
            accepted.append(cand)
            allocated_risk += cand_loss
            active_entries += 1

        remaining_risk = max(0.0, max_risk_dollars - (currently_reserved_risk + allocated_risk))

        return AllocationResult(
            accepted_candidates=accepted,
            rejected_candidates=rejected,
            total_allocated_risk=allocated_risk,
            available_risk_remaining=remaining_risk,
        )
