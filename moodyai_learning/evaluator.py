from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .models import EvaluationRecord, OutcomeRecord, RecommendationRecord, utc_now_iso
from .repository import LearningLedger

POSITIVE_OUTCOMES = {
    "replied": 1,
    "qualified_conversation": 2,
    "appointment_booked": 3,
    "active_client": 4,
    "under_contract": 5,
    "closed": 6,
}
NEGATIVE_OUTCOMES = {
    "no_response": 0,
    "not_interested": 0,
    "already_has_agent": 0,
    "wrong_number": 0,
}
INVALID_OUTCOMES = {"invalid_lead"}


def _score_band(score: float) -> str:
    if score >= 90:
        return "90-100"
    if score >= 75:
        return "75-89"
    if score >= 50:
        return "50-74"
    return "0-49"


def _highest_outcome(outcomes: list[OutcomeRecord]) -> tuple[str | None, int | None, str]:
    if not outcomes:
        return None, None, "unevaluated"
    positive = [item for item in outcomes if item.outcome_type in POSITIVE_OUTCOMES]
    if positive:
        best = max(positive, key=lambda item: POSITIVE_OUTCOMES[item.outcome_type])
        return best.outcome_type, POSITIVE_OUTCOMES[best.outcome_type], "positive"
    negative = [item for item in outcomes if item.outcome_type in NEGATIVE_OUTCOMES]
    if negative:
        return negative[-1].outcome_type, 0, "negative"
    if any(item.outcome_type in INVALID_OUTCOMES for item in outcomes):
        return "invalid_lead", None, "invalid"
    return outcomes[-1].outcome_type, None, "unknown"


class LearningEvaluator:
    """Evaluates stored recommendations against observed outcomes."""

    def __init__(self, ledger: LearningLedger) -> None:
        self.ledger = ledger

    def evaluate_recommendation(self, recommendation_id: str) -> EvaluationRecord | None:
        recommendation = self.ledger.get_recommendation(recommendation_id)
        if recommendation is None:
            raise KeyError(f"recommendation not found: {recommendation_id}")
        outcomes = self.ledger.list_outcomes(recommendation_id)
        highest, rank, result_class = _highest_outcome(outcomes)
        if result_class == "unevaluated":
            return None

        predicted = recommendation.predicted_class.upper()
        prediction_correct: bool | None
        if result_class in {"invalid", "unknown"}:
            prediction_correct = None
        elif predicted in {"HOT", "WARM"}:
            prediction_correct = result_class == "positive"
        elif predicted == "COLD":
            prediction_correct = result_class == "negative"
        else:
            prediction_correct = None

        completed = [
            execution
            for execution in self.ledger.list_executions(recommendation_id)
            if execution.status == "completed"
        ]
        action_effective: bool | None
        if not completed or result_class in {"invalid", "unknown"}:
            action_effective = None
        else:
            action_effective = result_class == "positive"

        payload = {
            "recommendation_id": recommendation_id,
            "policy_version": recommendation.policy_version,
            "predicted_class": recommendation.predicted_class,
            "score": recommendation.score,
            "highest_outcome": highest,
            "outcome_rank": rank,
            "result_class": result_class,
            "prediction_correct": prediction_correct,
            "action_effective": action_effective,
            "evaluated_at": utc_now_iso(),
        }
        digest = hashlib.sha256(
            json.dumps(
                {
                    "recommendation_id": recommendation_id,
                    "policy_version": recommendation.policy_version,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:20]
        record = EvaluationRecord(evaluation_id=f"eval_{digest}", **payload)
        self.ledger.save_evaluation(record)
        return record

    def evaluate_all(self, *, limit: int = 1000) -> dict[str, int]:
        recommendations = self.ledger.list_recommendations(limit=limit)
        evaluated = 0
        skipped = 0
        for recommendation in recommendations:
            result = self.evaluate_recommendation(recommendation.recommendation_id)
            if result is None:
                skipped += 1
            else:
                evaluated += 1
        return {"evaluated": evaluated, "skipped_without_outcomes": skipped}

    def summary(self) -> dict[str, Any]:
        recommendations = self.ledger.list_recommendations(limit=1000)
        evaluations = self.ledger.list_evaluations(limit=1000)
        evaluation_by_id = {item.recommendation_id: item for item in evaluations}

        accepted_or_modified = 0
        executed = 0
        by_score_band: dict[str, dict[str, int]] = defaultdict(
            lambda: {"recommendations": 0, "evaluated": 0, "positive": 0, "correct": 0}
        )
        action_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"completed": 0, "positive": 0, "negative": 0}
        )

        for recommendation in recommendations:
            band = _score_band(recommendation.score)
            by_score_band[band]["recommendations"] += 1
            decision = self.ledger.get_latest_decision(recommendation.recommendation_id)
            if decision and decision.status in {"accepted", "modified"}:
                accepted_or_modified += 1
            completed_actions = [
                item
                for item in self.ledger.list_executions(recommendation.recommendation_id)
                if item.status == "completed"
            ]
            if completed_actions:
                executed += 1
            evaluation = evaluation_by_id.get(recommendation.recommendation_id)
            if evaluation:
                by_score_band[band]["evaluated"] += 1
                if evaluation.result_class == "positive":
                    by_score_band[band]["positive"] += 1
                if evaluation.prediction_correct is True:
                    by_score_band[band]["correct"] += 1
                for action in completed_actions:
                    action_stats[action.action_type]["completed"] += 1
                    if evaluation.result_class == "positive":
                        action_stats[action.action_type]["positive"] += 1
                    elif evaluation.result_class == "negative":
                        action_stats[action.action_type]["negative"] += 1

        usable = [item for item in evaluations if item.result_class in {"positive", "negative"}]
        positive = [item for item in usable if item.result_class == "positive"]
        appointment_plus = [
            item for item in usable if (item.outcome_rank or 0) >= POSITIVE_OUTCOMES["appointment_booked"]
        ]
        hot = [item for item in usable if item.predicted_class.upper() == "HOT"]
        hot_correct = [item for item in hot if item.prediction_correct is True]
        false_positive = [
            item
            for item in usable
            if item.predicted_class.upper() in {"HOT", "WARM"}
            and item.result_class == "negative"
        ]

        def rate(numerator: int, denominator: int) -> float | None:
            return round(numerator / denominator, 4) if denominator else None

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "recommendations": len(recommendations),
            "accepted_or_modified": accepted_or_modified,
            "executed": executed,
            "evaluated": len(evaluations),
            "usable_evaluations": len(usable),
            "positive_outcomes": len(positive),
            "response_rate": rate(len(positive), len(usable)),
            "appointment_rate": rate(len(appointment_plus), len(usable)),
            "hot_lead_precision": rate(len(hot_correct), len(hot)),
            "false_positive_rate": rate(len(false_positive), len(usable)),
            "by_score_band": dict(sorted(by_score_band.items())),
            "by_action_type": dict(sorted(action_stats.items())),
            "policy_versions": sorted({item.policy_version for item in recommendations}),
            "learning_mode": "measurement_only",
            "automatic_policy_changes": False,
        }

    def evaluation_dict(self, recommendation_id: str) -> dict[str, Any] | None:
        record = self.ledger.get_evaluation_for_recommendation(recommendation_id)
        return asdict(record) if record else None
