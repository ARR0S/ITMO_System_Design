"""Two-stage business policy for safe support-ticket automation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from support_ticket_poc.models import (
    ClassificationPrediction,
    EligibilityAction,
    EligibilityDecision,
    FinalAction,
    PIIInspection,
    PolicyDecision,
    ProcessingStatus,
    RiskLevel,
)


@dataclass(frozen=True, slots=True)
class CategoryPolicy:
    """Business-owned route and risk configuration for one category."""

    team: str
    risk: RiskLevel


class PolicyEngine:
    """Apply business safety rules independently of model prediction."""

    def __init__(
        self,
        category_policies: Mapping[str, CategoryPolicy],
        classification_threshold: float,
    ) -> None:
        if not 0.0 <= classification_threshold <= 1.0:
            raise ValueError("classification_threshold must be between 0.0 and 1.0")
        self._category_policies = dict(category_policies)
        self._classification_threshold = classification_threshold

    def evaluate_eligibility(
        self,
        prediction: ClassificationPrediction,
        pii_inspection: PIIInspection,
    ) -> EligibilityDecision:
        """Decide whether processing may continue to retrieval and generation."""
        category_policy = self._category_policies.get(prediction.category)
        if category_policy is None:
            return self._human_review_eligibility(
                reason=(
                    f"No business policy is configured for category "
                    f"'{prediction.category}'."
                ),
                team=None,
                risk=None,
            )

        # High business impact must override even a highly confident prediction.
        if category_policy.risk is RiskLevel.HIGH:
            return self._human_review_eligibility(
                reason=(
                    f"Category '{prediction.category}' is high risk and always requires "
                    "human review."
                ),
                team=category_policy.team,
                risk=category_policy.risk,
            )

        if prediction.confidence < self._classification_threshold:
            return self._human_review_eligibility(
                reason=(
                    f"Classifier confidence {prediction.confidence:.2f} is below the "
                    f"{self._classification_threshold:.2f} threshold."
                ),
                team=category_policy.team,
                risk=category_policy.risk,
            )

        if not pii_inspection.safe_for_external_processing:
            return self._human_review_eligibility(
                reason="PII cannot be processed safely by an external service.",
                team=category_policy.team,
                risk=category_policy.risk,
            )

        return EligibilityDecision(
            action=EligibilityAction.CONTINUE_TO_RETRIEVAL,
            status=None,
            team=category_policy.team,
            risk=category_policy.risk,
            reason="Eligibility checks passed; continue to knowledge retrieval.",
        )

    def make_final_decision(
        self,
        *,
        relevant_source_found: bool,
        llm_available: bool,
        output_valid: bool,
    ) -> PolicyDecision:
        """Choose the final action after retrieval and generation facts are known."""
        if not relevant_source_found:
            return PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                status=ProcessingStatus.WAITING_FOR_HUMAN,
                reason="No relevant knowledge source was found; human review is required.",
            )

        # Routing remains useful when optional generation is unavailable.
        if not llm_available:
            return PolicyDecision(
                action=FinalAction.ROUTE_ONLY,
                status=ProcessingStatus.DEGRADED,
                reason=(
                    "LLM is unavailable after successful classification and routing; "
                    "continue with route-only degraded processing."
                ),
            )

        if not output_valid:
            return PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                status=ProcessingStatus.WAITING_FOR_HUMAN,
                reason="Generated output failed validation; human review is required.",
            )

        return PolicyDecision(
            action=FinalAction.AUTO_ANSWER,
            status=ProcessingStatus.AUTO_RESOLVED,
            reason=(
                "A relevant source was found, the LLM was available, and the generated "
                "output passed validation."
            ),
        )

    @staticmethod
    def _human_review_eligibility(
        reason: str,
        team: str | None,
        risk: RiskLevel | None,
    ) -> EligibilityDecision:
        return EligibilityDecision(
            action=EligibilityAction.HUMAN_REVIEW,
            status=ProcessingStatus.WAITING_FOR_HUMAN,
            team=team,
            risk=risk,
            reason=reason,
        )
