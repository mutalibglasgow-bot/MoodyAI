from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import DecisionService, LearningLedger, RecommendationService


class DecisionFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp_dir.name) / "moodyai.db")
        recommendation_service = RecommendationService(self.ledger)
        self.recommendation, _ = recommendation_service.record_lead_recommendation_once(
            lead={"id": 123, "name": "Test Lead", "stage": "New"},
            score=35,
            predicted_class="COLD",
            recommended_action="Review the lead context.",
            policy_version="lead-score-v1.0",
            feature_contributions={"base": 35},
            source_mode="test",
        )
        self.service = DecisionService(self.ledger)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_records_accepted_decision(self) -> None:
        decision = self.service.record_decision(
            recommendation_id=self.recommendation.recommendation_id,
            status="accepted",
        )
        self.assertEqual(decision.status, "accepted")
        self.assertEqual(self.ledger.count_decisions(), 1)
        self.assertEqual(
            self.ledger.get_latest_decision(self.recommendation.recommendation_id),
            decision,
        )

    def test_modified_requires_selected_action(self) -> None:
        with self.assertRaises(ValueError):
            self.service.record_decision(
                recommendation_id=self.recommendation.recommendation_id,
                status="modified",
            )

    def test_rejects_unknown_recommendation(self) -> None:
        with self.assertRaises(KeyError):
            self.service.record_decision(
                recommendation_id="rec_missing",
                status="rejected",
                reason="Not enough context",
            )

    def test_preserves_decision_history_and_latest_state(self) -> None:
        first = self.service.record_decision(
            recommendation_id=self.recommendation.recommendation_id,
            status="deferred",
            reason="Call tomorrow",
            decided_at="2026-07-22T18:00:00+00:00",
        )
        second = self.service.record_decision(
            recommendation_id=self.recommendation.recommendation_id,
            status="accepted",
            decided_at="2026-07-23T15:00:00+00:00",
        )
        history = self.ledger.list_decisions(self.recommendation.recommendation_id)
        self.assertEqual([item.decision_id for item in history], [first.decision_id, second.decision_id])
        self.assertEqual(self.ledger.get_latest_decision(self.recommendation.recommendation_id), second)


if __name__ == "__main__":
    unittest.main()
