from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import LearningLedger, RecommendationService
from moodyai_learning.executions import ExecutionService
from moodyai_learning.integration import normalize_and_record_lead


class RecommendationContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp_dir.name) / "learning.db")
        self.service = RecommendationService(self.ledger)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def lead(last_activity: str, *, stage: str = "Consult Set") -> dict:
        return {
            "id": 379953,
            "name": "Kevin Wise",
            "stage": stage,
            "source": "Orchard - Seller Intake",
            "phone": "555-0100",
            "email": "kevin@example.com",
            "websiteVisits": 0,
            "lastActivity": last_activity,
            "created": "2026-07-01T12:00:00Z",
            "tags": [],
        }

    def test_last_activity_change_reuses_recommendation(self) -> None:
        first = normalize_and_record_lead(
            self.lead("2026-07-22T20:00:00Z"), recommendation_service=self.service
        )
        second = normalize_and_record_lead(
            self.lead("2026-07-22T21:59:43Z"), recommendation_service=self.service
        )
        self.assertEqual(first["recommendation_id"], second["recommendation_id"])
        self.assertFalse(second["recommendation_recorded"])
        self.assertEqual(self.ledger.count_recommendations(), 1)

    def test_material_stage_change_can_create_new_recommendation(self) -> None:
        first = normalize_and_record_lead(
            self.lead("2026-07-22T20:00:00Z"), recommendation_service=self.service
        )
        second = normalize_and_record_lead(
            self.lead("2026-07-22T21:00:00Z", stage="Appointment Set"),
            recommendation_service=self.service,
        )
        self.assertNotEqual(first["recommendation_id"], second["recommendation_id"])

    def test_detected_execution_surfaces_across_recommendation_history(self) -> None:
        original = normalize_and_record_lead(
            self.lead("2026-07-22T20:00:00Z"), recommendation_service=self.service
        )
        execution_service = ExecutionService(self.ledger)
        # Auto-sync records implicit approval before execution in production.
        from moodyai_learning.decisions import DecisionService
        DecisionService(self.ledger).record_decision(
            recommendation_id=original["recommendation_id"], status="accepted"
        )
        execution_service.record_execution(
            recommendation_id=original["recommendation_id"],
            action_type="call",
            status="completed",
            external_system="follow_up_boss",
            external_reference="call:599539",
            performed_by="Follow Up Boss sync",
            performed_at="2026-07-22T21:56:03Z",
        )
        # A materially changed record can exist, but the lead view must retain
        # the latest detected activity across the history.
        current = normalize_and_record_lead(
            self.lead("2026-07-22T21:59:43Z", stage="Appointment Set"),
            recommendation_service=self.service,
        )
        self.assertIsNotNone(current["execution"])
        self.assertEqual(current["execution"]["external_reference"], "call:599539")
        self.assertEqual(
            current["execution_recommendation_id"], original["recommendation_id"]
        )


if __name__ == "__main__":
    unittest.main()
