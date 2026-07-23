from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, TypeVar

from .lead_scoring import score_lead
from .policies import PolicyRegistry
from .service import RecommendationService

T = TypeVar("T")


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.min
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return datetime.min


def _latest_across_history(
    records: list[Any],
    getter: Callable[[str], T | None],
    time_attribute: str,
) -> tuple[T | None, str | None]:
    latest: T | None = None
    latest_recommendation_id: str | None = None
    latest_time = datetime.min
    for record in records:
        item = getter(record.recommendation_id)
        if item is None:
            continue
        item_time = _parse_time(getattr(item, time_attribute, None))
        if item_time >= latest_time:
            latest = item
            latest_time = item_time
            latest_recommendation_id = record.recommendation_id
    return latest, latest_recommendation_id


def normalize_and_record_lead(
    person: dict[str, Any],
    *,
    recommendation_service: RecommendationService,
    source_mode: str = "live",
    policy_registry: PolicyRegistry | None = None,
) -> dict[str, Any]:
    """Normalize a lead and expose one continuous lifecycle across its history."""
    active_policy = policy_registry.get_active_policy() if policy_registry else None
    result = score_lead(person, policy=active_policy)
    record, inserted = recommendation_service.record_lead_recommendation_once(
        lead=person,
        score=result.score,
        predicted_class=result.predicted_class,
        recommended_action=result.recommended_action,
        policy_version=result.policy_version,
        feature_contributions=result.feature_contributions,
        source_mode=source_mode,
        prediction_window_days=14,
    )
    ledger = recommendation_service.ledger
    history = ledger.list_recommendations(
        entity_type="lead", entity_id=str(person.get("id") or ""), limit=100
    )

    # The current recommendation owns the recommendation itself, while detected
    # activity and outcomes follow the lead across prior recommendation records.
    latest_decision = ledger.get_latest_decision(record.recommendation_id)
    latest_execution, execution_recommendation_id = _latest_across_history(
        history, ledger.get_latest_execution, "performed_at"
    )
    latest_outcome, outcome_recommendation_id = _latest_across_history(
        history, ledger.get_latest_outcome, "observed_at"
    )
    latest_evaluation, evaluation_recommendation_id = _latest_across_history(
        history, ledger.get_evaluation_for_recommendation, "evaluated_at"
    )

    return {
        "id": person.get("id"),
        "name": person.get("name") or person.get("displayName") or "Unnamed lead",
        "stage": str(person.get("stage") or "New"),
        "source": person.get("source") or "Unknown",
        "temperature": result.predicted_class,
        "score": result.score,
        "lastActivity": person.get("lastActivity")
        or person.get("created")
        or "No recent activity",
        "recommendedAction": result.recommended_action,
        "recommendation_id": record.recommendation_id,
        "policy_version": record.policy_version,
        "recommendation_recorded": inserted,
        "feature_contributions": result.feature_contributions,
        "decision": asdict(latest_decision) if latest_decision else None,
        "execution": asdict(latest_execution) if latest_execution else None,
        "execution_recommendation_id": execution_recommendation_id,
        "outcome": asdict(latest_outcome) if latest_outcome else None,
        "outcome_recommendation_id": outcome_recommendation_id,
        "evaluation": asdict(latest_evaluation) if latest_evaluation else None,
        "evaluation_recommendation_id": evaluation_recommendation_id,
        "recommendation_history_count": len(history),
    }
