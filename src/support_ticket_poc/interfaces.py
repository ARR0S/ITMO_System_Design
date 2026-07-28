"""Replaceable component contracts for the future PoC vertical slice."""

from __future__ import annotations

from typing import Protocol

from support_ticket_poc.models import (
    ClassificationPrediction,
    EligibilityDecision,
    KnowledgeFragment,
    PIIInspection,
    PolicyDecision,
    RiskLevel,
    Ticket,
)


class LLMUnavailableError(RuntimeError):
    """Raised when generation cannot run because the LLM is unavailable."""


class Classifier(Protocol):
    """Predict a ticket category and confidence."""

    def classify(self, ticket: Ticket) -> ClassificationPrediction:
        """Return a model prediction without applying business policy."""
        ...


class PIIDetector(Protocol):
    """Prepare ticket text for safe external processing."""

    def inspect(self, text: str) -> PIIInspection:
        """Return detected PII details and the safe form of the text."""
        ...


class Retriever(Protocol):
    """Find an approved knowledge fragment for a ticket."""

    def retrieve(self, safe_text: str) -> KnowledgeFragment | None:
        """Return the best relevant fragment, or none when no source qualifies."""
        ...


class LLMClient(Protocol):
    """Generate text using only safely processed text and retrieved context."""

    def generate(self, safe_text: str, fragment: KnowledgeFragment) -> str:
        """Return grounded text or raise LLMUnavailableError when unavailable."""
        ...


class OutputValidator(Protocol):
    """Check generated output before the final policy decision."""

    def validate(self, output: str, fragment: KnowledgeFragment) -> bool:
        """Return whether generated output passes the approved checks."""
        ...


class TicketRepository(Protocol):
    """Persist original tickets before optional slow-path processing."""

    def save(self, ticket: Ticket) -> None:
        """Store the original accepted ticket."""
        ...

    def get(self, ticket_id: str) -> Ticket | None:
        """Return a stored ticket by its stable identifier."""
        ...


class ReviewRepository(Protocol):
    """Store tickets that require a support operator."""

    def add(
        self,
        ticket: Ticket,
        prediction: ClassificationPrediction,
        team: str,
        risk: RiskLevel,
        reason: str,
    ) -> None:
        """Add the original ticket and escalation context for review."""
        ...


class AuditRepository(Protocol):
    """Record facts and reasons needed to audit a policy decision."""

    def record(
        self,
        ticket_id: str,
        prediction: ClassificationPrediction,
        risk: RiskLevel,
        decision: EligibilityDecision | PolicyDecision,
        source: KnowledgeFragment | None = None,
    ) -> None:
        """Persist the decision inputs, source, outcome, and human-readable reason."""
        ...
