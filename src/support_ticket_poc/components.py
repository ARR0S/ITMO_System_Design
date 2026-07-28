"""Deterministic local components for the Stage 2 vertical slice."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from support_ticket_poc.interfaces import LLMUnavailableError
from support_ticket_poc.models import (
    ClassificationPrediction,
    KnowledgeFragment,
    PIIInspection,
    Ticket,
)


class TicketValidationError(ValueError):
    """Raised when a ticket is missing a required value."""


class TicketValidator:
    """Validate the minimal required ticket fields."""

    def validate(self, ticket: Ticket) -> None:
        """Reject tickets without a stable identifier or meaningful text."""
        if not ticket.ticket_id.strip():
            raise TicketValidationError("ticket_id must not be empty")
        if not ticket.text.strip():
            raise TicketValidationError("ticket text must not be empty")


class RegexPIIDetector:
    """Mask a narrow set of explicit PII patterns for the local PoC."""

    _email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    _phone_pattern = re.compile(r"(?<!\w)(?:\+?\d[\d\s()\-]{7,}\d)(?!\w)")
    _payment_card_pattern = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

    def inspect(self, text: str) -> PIIInspection:
        """Return masked text and whether it is safe for external processing."""
        detected_types: list[str] = []
        safe_text = text

        if self._payment_card_pattern.search(safe_text):
            detected_types.append("payment_card")
            safe_text = self._payment_card_pattern.sub("[PAYMENT_CARD_UNSAFE]", safe_text)

        if self._email_pattern.search(safe_text):
            detected_types.append("email")
            safe_text = self._email_pattern.sub("[EMAIL]", safe_text)

        if self._phone_pattern.search(safe_text):
            detected_types.append("phone")
            safe_text = self._phone_pattern.sub("[PHONE]", safe_text)

        return PIIInspection(
            detected=bool(detected_types),
            safe_text=safe_text,
            safe_for_external_processing="payment_card" not in detected_types,
            detected_types=tuple(detected_types),
        )


class MockClassifier:
    """Return deterministic category predictions for the approved scenarios."""

    model_version = "mock-classifier-v1"
    _payment_keywords = (
        "верните деньги",
        "возврат",
        "списан",
        "списание",
        "платеж",
        "оплата",
    )
    _notification_keywords = ("уведомлен", "email", "рассылк")

    def classify(self, ticket: Ticket) -> ClassificationPrediction:
        """Classify by explicit keywords without applying route or risk policy."""
        normalized_text = ticket.text.lower()
        if any(keyword in normalized_text for keyword in self._payment_keywords):
            return ClassificationPrediction(
                category="payment_refund",
                confidence=0.99,
                model_version=self.model_version,
            )
        if any(keyword in normalized_text for keyword in self._notification_keywords):
            return ClassificationPrediction(
                category="notification_settings",
                confidence=0.95,
                model_version=self.model_version,
            )
        return ClassificationPrediction(
            category="unconfigured",
            confidence=0.40,
            model_version=self.model_version,
        )


@dataclass(frozen=True, slots=True)
class _KnowledgeEntry:
    document_id: str
    chunk_id: str
    document_version: str
    source_name: str
    keywords: tuple[str, ...]
    text: str


class KeywordRetriever:
    """Retrieve the best local fragment using deterministic keyword overlap."""

    def __init__(self, knowledge_base_path: str | Path | None = None) -> None:
        knowledge_resource = (
            Path(knowledge_base_path)
            if knowledge_base_path is not None
            else files("support_ticket_poc").joinpath("data/knowledge_base.json")
        )
        with knowledge_resource.open(encoding="utf-8") as knowledge_file:
            records = json.load(knowledge_file)
        self._entries = tuple(
            _KnowledgeEntry(
                document_id=record["document_id"],
                chunk_id=record["chunk_id"],
                document_version=record["document_version"],
                source_name=record["source_name"],
                keywords=tuple(record["keywords"]),
                text=record["text"],
            )
            for record in records
        )
        self.call_count = 0

    def retrieve(self, safe_text: str) -> KnowledgeFragment | None:
        """Return the highest-scoring fragment with at least one keyword match."""
        self.call_count += 1
        normalized_text = safe_text.lower()
        best_entry: _KnowledgeEntry | None = None
        best_match_count = 0

        for entry in self._entries:
            match_count = sum(
                keyword.lower() in normalized_text for keyword in entry.keywords
            )
            if match_count > best_match_count:
                best_entry = entry
                best_match_count = match_count

        if best_entry is None:
            return None

        return KnowledgeFragment(
            document_id=best_entry.document_id,
            chunk_id=best_entry.chunk_id,
            document_version=best_entry.document_version,
            text=best_entry.text,
            relevance=best_match_count / len(best_entry.keywords),
            source_name=best_entry.source_name,
        )


class MockLLMClient:
    """Generate a deterministic grounded response or simulate unavailability."""

    version = "mock-llm-v1"

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.call_count = 0

    def generate(self, safe_text: str, fragment: KnowledgeFragment) -> str:
        """Return only retrieved guidance, or raise the approved failure type."""
        self.call_count += 1
        if not self._available:
            raise LLMUnavailableError("Mock LLM is unavailable")
        return f"Ответ на основании базы знаний: {fragment.text}"


class SimpleOutputValidator:
    """Check the minimal grounded-output contract used only by the PoC."""

    def validate(self, output: str, fragment: KnowledgeFragment) -> bool:
        """Require a non-empty answer that explicitly incorporates its source text."""
        return bool(output.strip()) and fragment.text in output
