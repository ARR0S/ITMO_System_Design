"""Business-outcome tests for the two-stage PolicyEngine."""

from support_ticket_poc.models import (
    ClassificationPrediction,
    EligibilityAction,
    FinalAction,
    PIIInspection,
    ProcessingStatus,
    RiskLevel,
)
from support_ticket_poc.policy import CategoryPolicy, PolicyEngine


CLASSIFICATION_THRESHOLD = 0.80


def make_engine() -> PolicyEngine:
    return PolicyEngine(
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
        classification_threshold=CLASSIFICATION_THRESHOLD,
    )


def make_prediction(category: str, confidence: float) -> ClassificationPrediction:
    return ClassificationPrediction(
        category=category,
        confidence=confidence,
        model_version="mock-classifier-v1",
    )


def make_pii_inspection(*, safe: bool) -> PIIInspection:
    return PIIInspection(
        detected=not safe,
        safe_text="safe ticket text" if safe else "unsafe ticket text",
        safe_for_external_processing=safe,
        detected_types=() if safe else ("unmaskable_identifier",),
    )


def test_high_risk_requires_human_review_despite_high_confidence() -> None:
    decision = make_engine().evaluate_eligibility(
        make_prediction("payment_refund", confidence=0.99),
        make_pii_inspection(safe=True),
    )

    assert decision.action is EligibilityAction.HUMAN_REVIEW
    assert decision.status is ProcessingStatus.WAITING_FOR_HUMAN
    assert decision.team == "billing_support"
    assert decision.risk is RiskLevel.HIGH


def test_low_confidence_requires_human_review() -> None:
    decision = make_engine().evaluate_eligibility(
        make_prediction("notification_settings", confidence=0.79),
        make_pii_inspection(safe=True),
    )

    assert decision.action is EligibilityAction.HUMAN_REVIEW
    assert decision.status is ProcessingStatus.WAITING_FOR_HUMAN


def test_unsafe_pii_requires_human_review_at_threshold_boundary() -> None:
    decision = make_engine().evaluate_eligibility(
        make_prediction("notification_settings", confidence=0.80),
        make_pii_inspection(safe=False),
    )

    assert decision.action is EligibilityAction.HUMAN_REVIEW
    assert decision.status is ProcessingStatus.WAITING_FOR_HUMAN


def test_safe_ticket_at_threshold_is_eligible_for_retrieval() -> None:
    decision = make_engine().evaluate_eligibility(
        make_prediction("notification_settings", confidence=0.80),
        make_pii_inspection(safe=True),
    )

    assert decision.action is EligibilityAction.CONTINUE_TO_RETRIEVAL
    assert decision.status is None
    assert decision.team == "general_support"
    assert decision.risk is RiskLevel.LOW


def test_unknown_category_requires_human_review() -> None:
    decision = make_engine().evaluate_eligibility(
        make_prediction("unknown_category", confidence=0.99),
        make_pii_inspection(safe=True),
    )

    assert decision.action is EligibilityAction.HUMAN_REVIEW
    assert decision.status is ProcessingStatus.WAITING_FOR_HUMAN
    assert decision.team is None
    assert decision.risk is None
    assert decision.reason
    assert "no business policy" in decision.reason.lower()


def test_successful_slow_path_allows_automatic_answer() -> None:
    decision = make_engine().make_final_decision(
        relevant_source_found=True,
        llm_available=True,
        output_valid=True,
    )

    assert decision.action is FinalAction.AUTO_ANSWER
    assert decision.status is ProcessingStatus.AUTO_RESOLVED


def test_llm_unavailable_falls_back_to_route_only() -> None:
    decision = make_engine().make_final_decision(
        relevant_source_found=True,
        llm_available=False,
        output_valid=False,
    )

    assert decision.action is FinalAction.ROUTE_ONLY
    assert decision.status is ProcessingStatus.DEGRADED


def test_missing_relevant_source_requires_human_review() -> None:
    decision = make_engine().make_final_decision(
        relevant_source_found=False,
        llm_available=True,
        output_valid=True,
    )

    assert decision.action is FinalAction.HUMAN_REVIEW
    assert decision.status is ProcessingStatus.WAITING_FOR_HUMAN


def test_invalid_generated_output_requires_human_review() -> None:
    decision = make_engine().make_final_decision(
        relevant_source_found=True,
        llm_available=True,
        output_valid=False,
    )

    assert decision.action is FinalAction.HUMAN_REVIEW
    assert decision.status is ProcessingStatus.WAITING_FOR_HUMAN
