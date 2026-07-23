from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import LearningLedger, RecommendationService
from moodyai_learning.decisions import DecisionService
from moodyai_learning.executions import ExecutionService
from moodyai_learning.integration import normalize_and_record_lead
from moodyai_learning.outcomes import OutcomeService
from moodyai_learning.recommendation_quality import build_specific_action, determine_attention_state


class RecommendationQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp_dir.name) / "learning.db")
        self.service = RecommendationService(self.ledger)
        self.lead = {
            "id": 99,
            "name": "Kevin Wise",
            "stage": "Consult Set",
            "source": "Orchard - Seller Intake",
            "phone": "555-0100",
            "websiteVisits": 2,
            "created": "2026-07-20T12:00:00Z",
            "lastActivity": "2026-07-20T12:00:00Z",
            "tags": [],
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_action_is_specific_to_stage_and_person(self) -> None:
        action = build_specific_action(self.lead, "hot")
        self.assertIn("Kevin", action)
        self.assertIn("confirm the appointment", action)

    def test_same_snapshot_does_not_create_duplicate_recommendation(self) -> None:
        first = normalize_and_record_lead(self.lead, recommendation_service=self.service)
        second = normalize_and_record_lead(self.lead, recommendation_service=self.service)
        self.assertEqual(first["recommendation_id"], second["recommendation_id"])
        self.assertEqual(self.ledger.count_recommendations(), 1)

    def test_detected_execution_keeps_only_outcome_question_actionable(self) -> None:
        item = normalize_and_record_lead(self.lead, recommendation_service=self.service)
        DecisionService(self.ledger).record_decision(
            recommendation_id=item["recommendation_id"], status="accepted"
        )
        ExecutionService(self.ledger).record_execution(
            recommendation_id=item["recommendation_id"],
            action_type="call",
            status="completed",
            external_system="follow_up_boss",
            performed_at="2026-07-20T13:00:00Z",
        )
        current = normalize_and_record_lead(self.lead, recommendation_service=self.service)
        self.assertTrue(current["needs_attention"])
        self.assertEqual(current["workflow_state"], "awaiting_outcome")

    def test_recorded_outcome_suppresses_finished_work(self) -> None:
        item = normalize_and_record_lead(self.lead, recommendation_service=self.service)
        DecisionService(self.ledger).record_decision(
            recommendation_id=item["recommendation_id"], status="accepted"
        )
        ExecutionService(self.ledger).record_execution(
            recommendation_id=item["recommendation_id"],
            action_type="call",
            status="completed",
            external_system="follow_up_boss",
            performed_at="2026-07-20T13:00:00Z",
        )
        OutcomeService(self.ledger).record_outcome(
            recommendation_id=item["recommendation_id"],
            outcome_type="replied",
            source="test",
            attribution_confidence=1.0,
        )
        current = normalize_and_record_lead(self.lead, recommendation_service=self.service)
        self.assertFalse(current["needs_attention"])
        self.assertEqual(current["workflow_state"], "resolved")

    def test_newer_unattributed_crm_activity_temporarily_suppresses_duplicate(self) -> None:
        state = determine_attention_state(
            recommendation_created_at="2026-07-20T12:00:00Z",
            last_activity="2026-07-20T13:00:00Z",
            execution=None,
            outcome=None,
            evaluation=None,
        )
        self.assertFalse(state.needs_attention)
        self.assertEqual(state.workflow_state, "recent_activity_detected")



if __name__ == "__main__":
    unittest.main()
