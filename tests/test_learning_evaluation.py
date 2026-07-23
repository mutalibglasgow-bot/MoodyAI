from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import (
    DecisionService,
    ExecutionService,
    LearningEvaluator,
    LearningLedger,
    OutcomeService,
    RecommendationService,
)


class LearningEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp_dir.name) / "moodyai.db")
        self.recommendations = RecommendationService(self.ledger)
        self.decisions = DecisionService(self.ledger)
        self.executions = ExecutionService(self.ledger)
        self.outcomes = OutcomeService(self.ledger)
        self.evaluator = LearningEvaluator(self.ledger)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _recommendation(self, *, lead_id: int, score: float, predicted_class: str):
        record, _ = self.recommendations.record_lead_recommendation_once(
            lead={"id": lead_id, "name": f"Lead {lead_id}", "stage": "New"},
            score=score,
            predicted_class=predicted_class,
            recommended_action="Call the lead.",
            policy_version="lead-score-v1.0",
            feature_contributions={"base": 35},
            source_mode="test",
        )
        self.decisions.record_decision(
            recommendation_id=record.recommendation_id,
            status="accepted",
        )
        self.executions.record_execution(
            recommendation_id=record.recommendation_id,
            action_type="call",
            status="completed",
        )
        return record

    def test_identical_outcome_submission_is_idempotent(self) -> None:
        recommendation = self._recommendation(lead_id=1, score=95, predicted_class="HOT")
        first, first_inserted = self.outcomes.record_outcome_with_status(
            recommendation_id=recommendation.recommendation_id,
            outcome_type="replied",
            notes="Lead replied.",
        )
        second, second_inserted = self.outcomes.record_outcome_with_status(
            recommendation_id=recommendation.recommendation_id,
            outcome_type="replied",
            notes="Lead replied.",
        )
        self.assertTrue(first_inserted)
        self.assertFalse(second_inserted)
        self.assertEqual(first.outcome_id, second.outcome_id)
        self.assertEqual(self.ledger.count_outcomes(), 1)

    def test_materially_different_outcomes_remain_separate(self) -> None:
        recommendation = self._recommendation(lead_id=2, score=95, predicted_class="HOT")
        self.outcomes.record_outcome(
            recommendation_id=recommendation.recommendation_id,
            outcome_type="replied",
        )
        self.outcomes.record_outcome(
            recommendation_id=recommendation.recommendation_id,
            outcome_type="appointment_booked",
        )
        self.assertEqual(self.ledger.count_outcomes(), 2)

    def test_hot_positive_prediction_is_correct(self) -> None:
        recommendation = self._recommendation(lead_id=3, score=95, predicted_class="HOT")
        self.outcomes.record_outcome(
            recommendation_id=recommendation.recommendation_id,
            outcome_type="appointment_booked",
        )
        evaluation = self.evaluator.evaluate_recommendation(recommendation.recommendation_id)
        self.assertIsNotNone(evaluation)
        assert evaluation is not None
        self.assertTrue(evaluation.prediction_correct)
        self.assertTrue(evaluation.action_effective)
        self.assertEqual(evaluation.highest_outcome, "appointment_booked")

    def test_hot_negative_prediction_is_false_positive(self) -> None:
        recommendation = self._recommendation(lead_id=4, score=95, predicted_class="HOT")
        self.outcomes.record_outcome(
            recommendation_id=recommendation.recommendation_id,
            outcome_type="not_interested",
        )
        evaluation = self.evaluator.evaluate_recommendation(recommendation.recommendation_id)
        assert evaluation is not None
        self.assertFalse(evaluation.prediction_correct)
        self.assertFalse(evaluation.action_effective)

    def test_summary_reports_learning_metrics(self) -> None:
        positive = self._recommendation(lead_id=5, score=95, predicted_class="HOT")
        negative = self._recommendation(lead_id=6, score=92, predicted_class="HOT")
        self.outcomes.record_outcome(
            recommendation_id=positive.recommendation_id,
            outcome_type="appointment_booked",
        )
        self.outcomes.record_outcome(
            recommendation_id=negative.recommendation_id,
            outcome_type="no_response",
        )
        result = self.evaluator.evaluate_all()
        self.assertEqual(result["evaluated"], 2)
        summary = self.evaluator.summary()
        self.assertEqual(summary["evaluated"], 2)
        self.assertEqual(summary["response_rate"], 0.5)
        self.assertEqual(summary["appointment_rate"], 0.5)
        self.assertEqual(summary["hot_lead_precision"], 0.5)
        self.assertEqual(summary["false_positive_rate"], 0.5)
        self.assertFalse(summary["automatic_policy_changes"])


if __name__ == "__main__":
    unittest.main()
