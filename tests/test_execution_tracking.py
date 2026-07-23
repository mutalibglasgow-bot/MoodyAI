from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import (
    DecisionService,
    ExecutionService,
    LearningLedger,
    RecommendationService,
)


class ExecutionTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp_dir.name) / "moodyai.db")
        recommendation_service = RecommendationService(self.ledger)
        self.recommendation, _ = recommendation_service.record_lead_recommendation_once(
            lead={"id": 456, "name": "Execution Lead", "stage": "New"},
            score=75,
            predicted_class="WARM",
            recommended_action="Call the lead.",
            policy_version="lead-score-v1.0",
            feature_contributions={"base": 35, "phone_available": 15},
            source_mode="test",
        )
        self.decisions = DecisionService(self.ledger)
        self.executions = ExecutionService(self.ledger)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_requires_approved_decision(self) -> None:
        with self.assertRaises(ValueError):
            self.executions.record_execution(
                recommendation_id=self.recommendation.recommendation_id,
                action_type="call",
                status="completed",
            )

    def test_records_execution_after_acceptance(self) -> None:
        self.decisions.record_decision(
            recommendation_id=self.recommendation.recommendation_id,
            status="accepted",
        )
        execution = self.executions.record_execution(
            recommendation_id=self.recommendation.recommendation_id,
            action_type="call",
            status="completed",
            notes="Spoke for five minutes.",
            external_system="follow_up_boss",
            external_reference="note-123",
        )
        self.assertEqual(execution.status, "completed")
        self.assertEqual(self.ledger.count_executions(), 1)
        self.assertEqual(
            self.ledger.get_latest_execution(self.recommendation.recommendation_id),
            execution,
        )

    def test_modified_decision_allows_execution(self) -> None:
        self.decisions.record_decision(
            recommendation_id=self.recommendation.recommendation_id,
            status="modified",
            selected_action="Send a text instead.",
        )
        execution = self.executions.record_execution(
            recommendation_id=self.recommendation.recommendation_id,
            action_type="text",
            status="started",
        )
        self.assertEqual(execution.action_type, "text")

    def test_preserves_execution_history(self) -> None:
        self.decisions.record_decision(
            recommendation_id=self.recommendation.recommendation_id,
            status="accepted",
        )
        first = self.executions.record_execution(
            recommendation_id=self.recommendation.recommendation_id,
            action_type="call",
            status="started",
            performed_at="2026-07-22T18:00:00+00:00",
        )
        second = self.executions.record_execution(
            recommendation_id=self.recommendation.recommendation_id,
            action_type="call",
            status="completed",
            performed_at="2026-07-22T18:05:00+00:00",
        )
        history = self.ledger.list_executions(self.recommendation.recommendation_id)
        self.assertEqual([item.execution_id for item in history], [first.execution_id, second.execution_id])
        self.assertEqual(self.ledger.get_latest_execution(self.recommendation.recommendation_id), second)

    def test_rejects_invalid_status(self) -> None:
        self.decisions.record_decision(
            recommendation_id=self.recommendation.recommendation_id,
            status="accepted",
        )
        with self.assertRaises(ValueError):
            self.executions.record_execution(
                recommendation_id=self.recommendation.recommendation_id,
                action_type="call",
                status="sent",
            )


if __name__ == "__main__":
    unittest.main()
