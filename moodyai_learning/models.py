from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp suitable for persistence."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class RecommendationRecord:
    recommendation_id: str
    entity_type: str
    entity_id: str
    policy_version: str
    score: float
    predicted_class: str
    recommended_action: str
    prediction_window_days: int
    input_snapshot: dict[str, Any]
    feature_contributions: dict[str, float]
    created_at: str
    source_mode: str = "unknown"

    def __post_init__(self) -> None:
        if not self.recommendation_id.strip():
            raise ValueError("recommendation_id is required")
        if not self.entity_type.strip():
            raise ValueError("entity_type is required")
        if not self.entity_id.strip():
            raise ValueError("entity_id is required")
        if not self.policy_version.strip():
            raise ValueError("policy_version is required")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if self.prediction_window_days <= 0:
            raise ValueError("prediction_window_days must be greater than zero")
        if not isinstance(self.input_snapshot, dict):
            raise TypeError("input_snapshot must be a dictionary")
        if not isinstance(self.feature_contributions, dict):
            raise TypeError("feature_contributions must be a dictionary")


DECISION_STATUSES = frozenset({"accepted", "modified", "rejected", "deferred"})


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str
    recommendation_id: str
    status: str
    selected_action: str | None
    reason: str | None
    decided_at: str
    decided_by: str = "Moody"

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id is required")
        if not self.recommendation_id.strip():
            raise ValueError("recommendation_id is required")
        if self.status not in DECISION_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(DECISION_STATUSES))}")
        if self.status == "modified" and not (self.selected_action or "").strip():
            raise ValueError("selected_action is required when status is modified")
        if self.selected_action is not None and len(self.selected_action) > 2000:
            raise ValueError("selected_action must be 2000 characters or fewer")
        if self.reason is not None and len(self.reason) > 4000:
            raise ValueError("reason must be 4000 characters or fewer")


EXECUTION_STATUSES = frozenset({"started", "completed", "failed", "canceled"})


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    execution_id: str
    recommendation_id: str
    action_type: str
    status: str
    notes: str | None
    external_system: str | None
    external_reference: str | None
    performed_at: str
    performed_by: str = "Moody"

    def __post_init__(self) -> None:
        if not self.execution_id.strip():
            raise ValueError("execution_id is required")
        if not self.recommendation_id.strip():
            raise ValueError("recommendation_id is required")
        if not self.action_type.strip():
            raise ValueError("action_type is required")
        if self.status not in EXECUTION_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(EXECUTION_STATUSES))}")
        if self.notes is not None and len(self.notes) > 4000:
            raise ValueError("notes must be 4000 characters or fewer")
        if self.external_system is not None and len(self.external_system) > 200:
            raise ValueError("external_system must be 200 characters or fewer")
        if self.external_reference is not None and len(self.external_reference) > 500:
            raise ValueError("external_reference must be 500 characters or fewer")


OUTCOME_TYPES = frozenset({
    "no_response",
    "replied",
    "qualified_conversation",
    "appointment_booked",
    "active_client",
    "under_contract",
    "closed",
    "not_interested",
    "invalid_lead",
    "already_has_agent",
    "wrong_number",
})


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    outcome_id: str
    recommendation_id: str
    outcome_type: str
    outcome_value: float | None
    source: str
    attribution_confidence: float
    notes: str | None
    observed_at: str

    def __post_init__(self) -> None:
        if not self.outcome_id.strip():
            raise ValueError("outcome_id is required")
        if not self.recommendation_id.strip():
            raise ValueError("recommendation_id is required")
        if self.outcome_type not in OUTCOME_TYPES:
            raise ValueError(f"outcome_type must be one of: {', '.join(sorted(OUTCOME_TYPES))}")
        if not self.source.strip():
            raise ValueError("source is required")
        if not 0 <= self.attribution_confidence <= 1:
            raise ValueError("attribution_confidence must be between 0 and 1")
        if self.notes is not None and len(self.notes) > 4000:
            raise ValueError("notes must be 4000 characters or fewer")


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    evaluation_id: str
    recommendation_id: str
    policy_version: str
    predicted_class: str
    score: float
    highest_outcome: str | None
    outcome_rank: int | None
    result_class: str
    prediction_correct: bool | None
    action_effective: bool | None
    evaluated_at: str

    def __post_init__(self) -> None:
        if not self.evaluation_id.strip():
            raise ValueError("evaluation_id is required")
        if not self.recommendation_id.strip():
            raise ValueError("recommendation_id is required")
        if not self.policy_version.strip():
            raise ValueError("policy_version is required")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if self.result_class not in {"positive", "negative", "invalid", "unknown"}:
            raise ValueError("invalid result_class")


POLICY_PROPOSAL_STATUSES = frozenset({"awaiting_approval", "approved", "rejected"})


@dataclass(frozen=True, slots=True)
class PolicyProposalRecord:
    proposal_id: str
    current_policy_version: str
    proposed_policy_version: str
    feature_name: str
    current_weight: float
    proposed_weight: float
    direction: str
    sample_size: int
    feature_present_sample: int
    feature_absent_sample: int
    feature_positive_rate: float
    baseline_positive_rate: float
    effect_size: float
    minimum_effect: float
    rationale: str
    status: str
    created_at: str
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.proposal_id.strip():
            raise ValueError("proposal_id is required")
        if self.status not in POLICY_PROPOSAL_STATUSES:
            raise ValueError("invalid policy proposal status")
        if self.direction not in {"increase", "decrease"}:
            raise ValueError("direction must be increase or decrease")
        if self.sample_size < 1:
            raise ValueError("sample_size must be positive")
        if not 0 <= self.feature_positive_rate <= 1:
            raise ValueError("feature_positive_rate must be between 0 and 1")
        if not 0 <= self.baseline_positive_rate <= 1:
            raise ValueError("baseline_positive_rate must be between 0 and 1")
