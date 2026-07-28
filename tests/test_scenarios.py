"""End-to-end tests for the deterministic Stage 2 vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from support_ticket_poc.components import (
    KeywordRetriever,
    MockClassifier,
    MockLLMClient,
    RegexPIIDetector,
    SimpleOutputValidator,
    TicketValidator,
)
from support_ticket_poc.models import (
    FinalAction,
    ProcessingStatus,
    RiskLevel,
    Ticket,
    TicketChannel,
)
from support_ticket_poc.observability import ProcessingCounters
from support_ticket_poc.policy import CategoryPolicy, PolicyEngine
from support_ticket_poc.repositories import (
    InMemoryAuditRepository,
    InMemoryReviewRepository,
    InMemoryTicketRepository,
)
from support_ticket_poc.service import TicketProcessingService


@dataclass(frozen=True, slots=True)
class ScenarioSystem:
    service: TicketProcessingService
    ticket_repository: InMemoryTicketRepository
    review_repository: InMemoryReviewRepository
    audit_repository: InMemoryAuditRepository
    retriever: KeywordRetriever
    llm_client: MockLLMClient
    counters: ProcessingCounters


def build_system(*, llm_available: bool = True) -> ScenarioSystem:
    ticket_repository = InMemoryTicketRepository()
    review_repository = InMemoryReviewRepository()
    audit_repository = InMemoryAuditRepository()
    retriever = KeywordRetriever()
    llm_client = MockLLMClient(available=llm_available)
    counters = ProcessingCounters()
    policy_engine = PolicyEngine(
        category_policies={
            "notification_settings": CategoryPolicy(
                team="general_support",
                risk=RiskLevel.LOW,
            ),
            "payment_refund": CategoryPolicy(
                team="billing_support",
                risk=RiskLevel.HIGH,
            ),
        },
        classification_threshold=0.80,
    )
    service = TicketProcessingService(
        validator=TicketValidator(),
        pii_detector=RegexPIIDetector(),
        classifier=MockClassifier(),
        policy_engine=policy_engine,
        retriever=retriever,
        llm_client=llm_client,
        output_validator=SimpleOutputValidator(),
        ticket_repository=ticket_repository,
        review_repository=review_repository,
        audit_repository=audit_repository,
        counters=counters,
    )
    return ScenarioSystem(
        service=service,
        ticket_repository=ticket_repository,
        review_repository=review_repository,
        audit_repository=audit_repository,
        retriever=retriever,
        llm_client=llm_client,
        counters=counters,
    )


def make_notification_ticket(ticket_id: str = "ticket-notifications") -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        text="Как отключить email-уведомления?",
        channel=TicketChannel.WEB,
        created_at=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
    )


def make_payment_ticket() -> Ticket:
    return Ticket(
        ticket_id="ticket-payment",
        text="Верните деньги за неизвестное списание с моей карты.",
        channel=TicketChannel.CHAT,
        created_at=datetime(2026, 7, 28, 12, 1, tzinfo=timezone.utc),
    )


def test_happy_path_auto_answers_from_identifiable_source() -> None:
    system = build_system()
    ticket = make_notification_ticket()

    result = system.service.process(ticket)

    assert result.action is FinalAction.AUTO_ANSWER
    assert result.status is ProcessingStatus.AUTO_RESOLVED
    assert result.category == "notification_settings"
    assert result.team == "general_support"
    assert result.risk is RiskLevel.LOW
    assert result.answer
    assert result.source_ids == ("kb-notifications",)
    assert system.ticket_repository.get(ticket.ticket_id) == ticket
    assert system.ticket_repository.get_result(ticket.ticket_id) == result
    assert len(system.audit_repository.events) == 1
    assert system.audit_repository.events[0].source_ids == ("kb-notifications",)
    assert system.review_repository.items == ()
    assert system.counters.auto_answers_total == 1
    assert system.counters.llm_calls_total == 1
    assert system.counters.llm_failures_total == 0


def test_high_risk_always_requires_human_review() -> None:
    system = build_system()
    ticket = make_payment_ticket()

    result = system.service.process(ticket)

    assert result.confidence == 0.99
    assert result.action is FinalAction.HUMAN_REVIEW
    assert result.status is ProcessingStatus.WAITING_FOR_HUMAN
    assert result.category == "payment_refund"
    assert result.team == "billing_support"
    assert result.risk is RiskLevel.HIGH
    assert result.answer is None
    assert len(system.review_repository.items) == 1
    assert system.review_repository.items[0].ticket == ticket
    assert len(system.audit_repository.events) == 1
    assert "high risk" in system.audit_repository.events[0].reason.lower()
    assert system.retriever.call_count == 0
    assert system.llm_client.call_count == 0
    assert system.counters.human_reviews_total == 1


def test_llm_failure_routes_ticket_in_degraded_mode() -> None:
    system = build_system(llm_available=False)
    ticket = make_notification_ticket("ticket-llm-failure")

    result = system.service.process(ticket)

    assert result.action is FinalAction.ROUTE_ONLY
    assert result.status is ProcessingStatus.DEGRADED
    assert result.answer is None
    assert result.category == "notification_settings"
    assert result.confidence == 0.95
    assert result.team == "general_support"
    assert result.risk is RiskLevel.LOW
    assert system.ticket_repository.get(ticket.ticket_id) == ticket
    assert result.source_ids == ("kb-notifications",)
    assert len(system.audit_repository.events) == 1
    audit_event = system.audit_repository.events[0]
    assert audit_event.source_ids == ("kb-notifications",)
    assert audit_event.llm_status == "UNAVAILABLE"
    assert "route-only" in audit_event.reason.lower()
    assert system.counters.llm_calls_total == 1
    assert system.counters.llm_failures_total == 1
    assert system.counters.route_only_total == 1


def test_duplicate_completed_ticket_is_idempotent() -> None:
    system = build_system()
    ticket = make_notification_ticket("ticket-duplicate")

    first_result = system.service.process(ticket)
    replayed_result = system.service.process(ticket)

    assert replayed_result is first_result
    assert system.ticket_repository.ticket_count == 1
    assert system.ticket_repository.result_count == 1
    assert len(system.audit_repository.events) == 1
    assert system.review_repository.items == ()
    assert system.retriever.call_count == 1
    assert system.llm_client.call_count == 1
    assert system.counters.auto_answers_total == 1
