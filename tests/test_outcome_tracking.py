from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import (
    DecisionService,
    ExecutionService,
    LearningLedger,
    OutcomeService,
    RecommendationService,
)


class OutcomeTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp_dir.name) / "moodyai.db")
        recommendations = RecommendationService(self.ledger)
        self.recommendation, _ = recommendations.record_lead_recommendation_once(
            lead={"id": 789, "name": "Outcome Lead", "stage": "New"},
            score=90,
            predicted_class="HOT",
            recommended_action="Call the lead.",
            policy_version="lead-score-v1.0",
            feature_contributions={"base": 35, "stage_signal": 15},
            source_mode="test",
        )
        self.decisions = DecisionService(self.ledger)
        self.executions = ExecutionService(self.ledger)
        self.outcomes = OutcomeService(self.ledger)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _complete_execution(self) -> None:
        self.decisions.record_decision(
            recommendation_id=self.recommendation.recommendation_id,
            status="accepted",
        )
        self.executions.record_execution(
            recommendation_id=self.recommendation.recommendation_id,
            action_type="call",
            status="completed",
        )

    def test_requires_completed_execution(self) -> None:
        with self.assertRaises(ValueError):
            self.outcomes.record_outcome(
                recommendation_id=self.recommendation.recommendation_id,
                outcome_type="replied",
            )

    def test_records_outcome_after_completed_execution(self) -> None:
        self._complete_execution()
        outcome = self.outcomes.record_outcome(
            recommendation_id=self.recommendation.recommendation_id,
            outcome_type="appointment_booked",
            source="follow_up_boss",
            attribution_confidence=0.8,
            notes="Appointment booked after the call.",
        )
        self.assertEqual(outcome.outcome_type, "appointment_booked")
        self.assertEqual(self.ledger.count_outcomes(), 1)
        self.assertEqual(
            self.ledger.get_latest_outcome(self.recommendation.recommendation_id),
            outcome,
        )

    def test_preserves_outcome_history(self) -> None:
        self._complete_execution()
        first = self.outcomes.record_outcome(
            recommendation_id=self.recommendation.recommendation_id,
            outcome_type="replied",
            observed_at="2026-07-22T18:00:00+00:00",
        )
        second = self.outcomes.record_outcome(
            recommendation_id=self.recommendation.recommendation_id,
            outcome_type="appointment_booked",
            observed_at="2026-07-23T18:00:00+00:00",
        )
        history = self.ledger.list_outcomes(self.recommendation.recommendation_id)
        self.assertEqual([item.outcome_id for item in history], [first.outcome_id, second.outcome_id])
        self.assertEqual(self.ledger.get_latest_outcome(self.recommendation.recommendation_id), second)

    def test_rejects_invalid_outcome_type(self) -> None:
        self._complete_execution()
        with self.assertRaises(ValueError):
            self.outcomes.record_outcome(
                recommendation_id=self.recommendation.recommendation_id,
                outcome_type="maybe",
            )

    def test_rejects_invalid_attribution_confidence(self) -> None:
        self._complete_execution()
        with self.assertRaises(ValueError):
            self.outcomes.record_outcome(
                recommendation_id=self.recommendation.recommendation_id,
                outcome_type="replied",
                attribution_confidence=1.5,
            )


if __name__ == "__main__":
    unittest.main()
