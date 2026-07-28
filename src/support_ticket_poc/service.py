"""Application orchestration for deterministic ticket processing."""

from __future__ import annotations

from support_ticket_poc.components import TicketValidator
from support_ticket_poc.interfaces import (
    AuditRepository,
    Classifier,
    LLMClient,
    LLMUnavailableError,
    OutputValidator,
    PIIDetector,
    Retriever,
    ReviewRepository,
    TicketRepository,
)
from support_ticket_poc.models import (
    ClassificationPrediction,
    EligibilityAction,
    FinalAction,
    PIIInspection,
    PolicyDecision,
    ProcessingResult,
    RiskLevel,
    Ticket,
)
from support_ticket_poc.observability import ProcessingCounters
from support_ticket_poc.policy import PolicyEngine


class TicketProcessingService:
    """Coordinate the approved fast path, slow path, and safe fallback."""

    def __init__(
        self,
        *,
        validator: TicketValidator,
        pii_detector: PIIDetector,
        classifier: Classifier,
        policy_engine: PolicyEngine,
        retriever: Retriever,
        llm_client: LLMClient,
        output_validator: OutputValidator,
        ticket_repository: TicketRepository,
        review_repository: ReviewRepository,
        audit_repository: AuditRepository,
        counters: ProcessingCounters,
    ) -> None:
        self._validator = validator
        self._pii_detector = pii_detector
        self._classifier = classifier
        self._policy_engine = policy_engine
        self._retriever = retriever
        self._llm_client = llm_client
        self._output_validator = output_validator
        self._ticket_repository = ticket_repository
        self._review_repository = review_repository
        self._audit_repository = audit_repository
        self._counters = counters

    def process(self, ticket: Ticket) -> ProcessingResult:
        """Process one ticket and return an idempotently stored business result."""
        stored_result = self._ticket_repository.get_result(ticket.ticket_id)
        if stored_result is not None:
            return stored_result

        self._validator.validate(ticket)
        self._ticket_repository.save(ticket)

        pii_inspection = self._pii_detector.inspect(ticket.text)
        prediction = self._classifier.classify(ticket)
        eligibility = self._policy_engine.evaluate_eligibility(
            prediction,
            pii_inspection,
        )

        if eligibility.action is EligibilityAction.HUMAN_REVIEW:
            if eligibility.status is None:
                raise RuntimeError("human-review eligibility must have a final status")
            decision = PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                status=eligibility.status,
                reason=eligibility.reason,
            )
            return self._complete(
                ticket=ticket,
                prediction=prediction,
                pii_inspection=pii_inspection,
                team=eligibility.team,
                risk=eligibility.risk,
                decision=decision,
                answer=None,
                source_ids=(),
                llm_status="NOT_CALLED",
                llm_called=False,
                llm_failed=False,
            )

        fragment = self._retriever.retrieve(pii_inspection.safe_text)
        if fragment is None:
            decision = self._policy_engine.make_final_decision(
                relevant_source_found=False,
                llm_available=True,
                output_valid=False,
            )
            return self._complete(
                ticket=ticket,
                prediction=prediction,
                pii_inspection=pii_inspection,
                team=eligibility.team,
                risk=eligibility.risk,
                decision=decision,
                answer=None,
                source_ids=(),
                llm_status="NOT_CALLED",
                llm_called=False,
                llm_failed=False,
            )

        source_ids = (fragment.document_id,)
        try:
            answer = self._llm_client.generate(pii_inspection.safe_text, fragment)
        except LLMUnavailableError:
            decision = self._policy_engine.make_final_decision(
                relevant_source_found=True,
                llm_available=False,
                output_valid=False,
            )
            return self._complete(
                ticket=ticket,
                prediction=prediction,
                pii_inspection=pii_inspection,
                team=eligibility.team,
                risk=eligibility.risk,
                decision=decision,
                answer=None,
                source_ids=source_ids,
                llm_status="UNAVAILABLE",
                llm_called=True,
                llm_failed=True,
            )

        output_valid = self._output_validator.validate(answer, fragment)
        decision = self._policy_engine.make_final_decision(
            relevant_source_found=True,
            llm_available=True,
            output_valid=output_valid,
        )
        return self._complete(
            ticket=ticket,
            prediction=prediction,
            pii_inspection=pii_inspection,
            team=eligibility.team,
            risk=eligibility.risk,
            decision=decision,
            answer=answer if decision.action is FinalAction.AUTO_ANSWER else None,
            source_ids=source_ids,
            llm_status="AVAILABLE",
            llm_called=True,
            llm_failed=False,
        )

    def _complete(
        self,
        *,
        ticket: Ticket,
        prediction: ClassificationPrediction,
        pii_inspection: PIIInspection,
        team: str | None,
        risk: RiskLevel | None,
        decision: PolicyDecision,
        answer: str | None,
        source_ids: tuple[str, ...],
        llm_status: str,
        llm_called: bool,
        llm_failed: bool,
    ) -> ProcessingResult:
        result = ProcessingResult(
            ticket_id=ticket.ticket_id,
            category=prediction.category,
            confidence=prediction.confidence,
            model_version=prediction.model_version,
            team=team,
            risk=risk,
            action=decision.action,
            status=decision.status,
            reason=decision.reason,
            answer=answer,
            source_ids=source_ids,
        )
        self._ticket_repository.save_result(result)

        if decision.action is FinalAction.HUMAN_REVIEW:
            self._review_repository.add(
                ticket,
                prediction,
                team,
                risk,
                decision.reason,
            )

        self._audit_repository.record(
            ticket.ticket_id,
            prediction,
            team,
            risk,
            source_ids,
            llm_status,
            decision.action,
            decision.status,
            decision.reason,
        )
        self._counters.record_completed(
            action=decision.action,
            llm_called=llm_called,
            llm_failed=llm_failed,
            pii_detected=pii_inspection.detected,
        )
        return result
