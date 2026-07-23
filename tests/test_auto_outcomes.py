from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import DecisionService, ExecutionService, LearningLedger, RecommendationService
from moodyai_learning.auto_outcomes import FUBAutoOutcomeService


class AutoOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.tmp.name) / "learning.db")
        rec_service = RecommendationService(self.ledger)
        self.rec, _ = rec_service.record_lead_recommendation_once(
            lead={"id": 42, "name": "Test Lead", "stage": "Lead"},
            score=80,
            predicted_class="HOT",
            recommended_action="Call today.",
            policy_version="lead-score-v1.0",
            feature_contributions={"base": 35},
            source_mode="live",
            prediction_window_days=14,
        )
        DecisionService(self.ledger).record_decision(
            recommendation_id=self.rec.recommendation_id,
            status="accepted",
        )
        ExecutionService(self.ledger).record_execution(
            recommendation_id=self.rec.recommendation_id,
            action_type="call",
            status="completed",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_stage_change_records_high_confidence_outcome(self):
        service = FUBAutoOutcomeService(
            self.ledger,
            get_person=lambda **_: {"person": {"id": 42, "stage": "Under Contract", "updated": "2026-07-23T10:00:00Z"}},
        )
        result = service.sync()
        self.assertEqual(result["imported_count"], 1)
        outcome = self.ledger.get_latest_outcome(self.rec.recommendation_id)
        self.assertEqual(outcome.outcome_type, "under_contract")
        self.assertEqual(outcome.source, "follow_up_boss")

    def test_unchanged_stage_creates_no_outcome(self):
        service = FUBAutoOutcomeService(
            self.ledger,
            get_person=lambda **_: {"person": {"id": 42, "stage": "Lead", "updated": "2026-07-23T10:00:00Z"}},
        )
        result = service.sync()
        self.assertEqual(result["imported_count"], 0)
        self.assertIsNone(self.ledger.get_latest_outcome(self.rec.recommendation_id))

    def test_same_stage_signal_is_idempotent(self):
        service = FUBAutoOutcomeService(
            self.ledger,
            get_person=lambda **_: {"person": {"id": 42, "stage": "Active Client", "updated": "2026-07-23T10:00:00Z"}},
        )
        self.assertEqual(service.sync()["imported_count"], 1)
        self.assertEqual(service.sync()["imported_count"], 0)
        self.assertEqual(len(self.ledger.list_outcomes(self.rec.recommendation_id)), 1)

    def test_ambiguous_stage_is_ignored(self):
        service = FUBAutoOutcomeService(
            self.ledger,
            get_person=lambda **_: {"person": {"id": 42, "stage": "Nurture", "updated": "2026-07-23T10:00:00Z"}},
        )
        result = service.sync()
        self.assertEqual(result["imported_count"], 0)
        self.assertEqual(result["ignored_count"], 1)


if __name__ == "__main__":
    unittest.main()
