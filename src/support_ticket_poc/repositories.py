"""Explicit in-memory repositories for the local PoC."""

from __future__ import annotations

from datetime import datetime, timezone

from support_ticket_poc.models import (
    AuditEvent,
    ClassificationPrediction,
    FinalAction,
    ProcessingResult,
    ProcessingStatus,
    ReviewItem,
    RiskLevel,
    Ticket,
)


class InMemoryTicketRepository:
    """Store original tickets and completed results by stable ticket ID."""

    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}
        self._results: dict[str, ProcessingResult] = {}

    def save(self, ticket: Ticket) -> None:
        """Preserve the first original ticket received for an identifier."""
        self._tickets.setdefault(ticket.ticket_id, ticket)

    def get(self, ticket_id: str) -> Ticket | None:
        """Return the stored original ticket."""
        return self._tickets.get(ticket_id)

    def save_result(self, result: ProcessingResult) -> None:
        """Store the first completed result for idempotent replay."""
        if result.ticket_id not in self._tickets:
            raise ValueError("the original ticket must be saved before its result")
        self._results.setdefault(result.ticket_id, result)

    def get_result(self, ticket_id: str) -> ProcessingResult | None:
        """Return a stored completed result."""
        return self._results.get(ticket_id)

    @property
    def ticket_count(self) -> int:
        """Return the number of unique original tickets."""
        return len(self._tickets)

    @property
    def result_count(self) -> int:
        """Return the number of unique completed results."""
        return len(self._results)


class InMemoryReviewRepository:
    """Store one human-review item per ticket."""

    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}

    def add(
        self,
        ticket: Ticket,
        prediction: ClassificationPrediction,
        team: str | None,
        risk: RiskLevel | None,
        reason: str,
    ) -> None:
        """Add the original request and resolved decision context for an operator."""
        self._items.setdefault(
            ticket.ticket_id,
            ReviewItem(
                ticket=ticket,
                prediction=prediction,
                team=team,
                risk=risk,
                reason=reason,
            ),
        )

    @property
    def items(self) -> tuple[ReviewItem, ...]:
        """Return review items in insertion order for inspection."""
        return tuple(self._items.values())


class InMemoryAuditRepository:
    """Store structured audit events without copying raw ticket text."""

    def __init__(self) -> None:
        self._events: dict[str, AuditEvent] = {}

    def record(
        self,
        ticket_id: str,
        prediction: ClassificationPrediction,
        team: str | None,
        risk: RiskLevel | None,
        source_ids: tuple[str, ...],
        llm_status: str,
        action: FinalAction,
        status: ProcessingStatus,
        reason: str,
    ) -> None:
        """Record the first completed decision for a ticket."""
        self._events.setdefault(
            ticket_id,
            AuditEvent(
                occurred_at=datetime.now(timezone.utc),
                ticket_id=ticket_id,
                category=prediction.category,
                confidence=prediction.confidence,
                classifier_version=prediction.model_version,
                team=team,
                risk=risk,
                source_ids=source_ids,
                llm_status=llm_status,
                action=action,
                status=status,
                reason=reason,
            ),
        )

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """Return audit events in insertion order for inspection."""
        return tuple(self._events.values())
