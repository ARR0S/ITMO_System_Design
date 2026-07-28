"""Minimal in-memory counters for completed PoC outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from support_ticket_poc.models import FinalAction


@dataclass(slots=True)
class ProcessingCounters:
    """Track required scenario and LLM outcome counts without external tooling."""

    tickets_total: int = 0
    auto_answers_total: int = 0
    human_reviews_total: int = 0
    route_only_total: int = 0
    llm_calls_total: int = 0
    llm_failures_total: int = 0
    pii_detected_total: int = 0

    def record_completed(
        self,
        *,
        action: FinalAction,
        llm_called: bool,
        llm_failed: bool,
        pii_detected: bool,
    ) -> None:
        """Increment counters once after a ticket reaches a completed outcome."""
        self.tickets_total += 1
        self.llm_calls_total += int(llm_called)
        self.llm_failures_total += int(llm_failed)
        self.pii_detected_total += int(pii_detected)

        if action is FinalAction.AUTO_ANSWER:
            self.auto_answers_total += 1
        elif action is FinalAction.HUMAN_REVIEW:
            self.human_reviews_total += 1
        elif action is FinalAction.ROUTE_ONLY:
            self.route_only_total += 1
