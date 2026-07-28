"""Domain models shared by the PoC policy and replaceable components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TicketChannel(str, Enum):
    """Supported ticket ingestion channels."""

    CHAT = "CHAT"
    EMAIL = "EMAIL"
    WEB = "WEB"
    MOBILE = "MOBILE"


class RiskLevel(str, Enum):
    """Business impact of an incorrect automated decision."""

    LOW = "LOW"
    HIGH = "HIGH"


class FinalAction(str, Enum):
    """Approved final actions for the PoC."""

    AUTO_ANSWER = "AUTO_ANSWER"
    ROUTE_ONLY = "ROUTE_ONLY"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ProcessingStatus(str, Enum):
    """Approved processing statuses for the PoC."""

    AUTO_RESOLVED = "AUTO_RESOLVED"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    DEGRADED = "DEGRADED"


class EligibilityAction(str, Enum):
    """Possible outcomes before retrieval or generation is attempted."""

    CONTINUE_TO_RETRIEVAL = "CONTINUE_TO_RETRIEVAL"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass(frozen=True, slots=True)
class Ticket:
    """Normalized support ticket accepted by the application layer."""

    ticket_id: str
    text: str
    channel: TicketChannel
    created_at: datetime
    title: str | None = None


@dataclass(frozen=True, slots=True)
class ClassificationPrediction:
    """Classifier output kept separate from the business decision."""

    category: str
    confidence: float
    model_version: str


@dataclass(frozen=True, slots=True)
class PIIInspection:
    """Result of checking and preparing text for external processing."""

    detected: bool
    safe_text: str
    safe_for_external_processing: bool
    detected_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeFragment:
    """An identifiable knowledge-base fragment returned by retrieval."""

    document_id: str
    chunk_id: str
    document_version: str
    text: str
    relevance: float
    source_name: str


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """Safety gate result produced before retrieval and LLM generation."""

    action: EligibilityAction
    status: ProcessingStatus | None
    team: str | None
    risk: RiskLevel | None
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Final business action after slow-path facts are known."""

    action: FinalAction
    status: ProcessingStatus
    reason: str


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    """Completed business outcome returned by ticket processing."""

    ticket_id: str
    category: str
    confidence: float
    model_version: str
    team: str | None
    risk: RiskLevel | None
    action: FinalAction
    status: ProcessingStatus
    reason: str
    answer: str | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """Original request and decision context for a support operator."""

    ticket: Ticket
    prediction: ClassificationPrediction
    team: str | None
    risk: RiskLevel | None
    reason: str


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Structured decision record that intentionally excludes raw ticket text."""

    occurred_at: datetime
    ticket_id: str
    category: str
    confidence: float
    classifier_version: str
    team: str | None
    risk: RiskLevel | None
    source_ids: tuple[str, ...]
    llm_status: str
    action: FinalAction
    status: ProcessingStatus
    reason: str
