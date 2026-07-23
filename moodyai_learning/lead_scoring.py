from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .policies import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, ScoringPolicy, score_snapshot

LEAD_POLICY_VERSION = "lead-score-v1.0"
DEFAULT_RECOMMENDED_ACTION = "Review the lead context and make a personal follow-up today."


@dataclass(frozen=True, slots=True)
class LeadScoreResult:
    score: int
    predicted_class: str
    recommended_action: str
    feature_contributions: dict[str, float]
    policy_version: str


def default_policy() -> ScoringPolicy:
    return ScoringPolicy(
        version=LEAD_POLICY_VERSION,
        weights=dict(DEFAULT_WEIGHTS),
        thresholds=dict(DEFAULT_THRESHOLDS),
        status="active",
        parent_version=None,
        created_from_proposal=None,
        created_at="built-in",
    )


def score_lead(person: dict[str, Any], policy: ScoringPolicy | None = None) -> LeadScoreResult:
    selected = policy or default_policy()
    score, predicted_class, contributions = score_snapshot(person, selected)
    return LeadScoreResult(
        score=score,
        predicted_class=predicted_class,
        recommended_action=DEFAULT_RECOMMENDED_ACTION,
        feature_contributions=contributions,
        policy_version=selected.version,
    )
