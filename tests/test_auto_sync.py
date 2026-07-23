from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import LearningLedger, RecommendationService
from moodyai_learning.auto_sync import FUBAutoSyncService


class FakePreview:
    def __init__(self, items): self.items = items
    def preview(self, *, limit=50): return {"items": self.items, "errors": []}


class AutoSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.tmp.name) / "learning.db")
        service = RecommendationService(self.ledger)
        self.rec, _ = service.record_lead_recommendation_once(
            lead={"id": 42, "name": "Test Lead", "stage": "New"},
            score=90,
            predicted_class="HOT",
            recommended_action="Call today.",
            policy_version="lead-score-v1.0",
            feature_contributions={"base": 35},
            source_mode="live",
            prediction_window_days=14,
        )

    def tearDown(self): self.tmp.cleanup()

    def candidate(self):
        return {
            "candidate_id": f"fub:call:123:{self.rec.recommendation_id}",
            "recommendation_id": self.rec.recommendation_id,
            "person_id": "42",
            "source_kind": "call",
            "external_reference": "123",
            "observed_at": "2026-07-22T18:17:08Z",
            "proposed_execution": {
                "action_type": "call", "status": "completed",
                "external_system": "follow_up_boss", "external_reference": "call:123",
                "notes": None,
            },
            "proposed_outcome": None,
            "match_confidence": 0.7,
            "raw_summary": {"isIncoming": False},
        }

    def test_outbound_call_implies_acceptance_and_records_execution(self):
        result = FUBAutoSyncService(self.ledger, FakePreview([self.candidate()])).sync()
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(self.ledger.get_latest_decision(self.rec.recommendation_id).status, "accepted")
        self.assertEqual(self.ledger.get_latest_execution(self.rec.recommendation_id).action_type, "call")

    def test_same_fub_activity_is_not_imported_twice(self):
        service = FUBAutoSyncService(self.ledger, FakePreview([self.candidate()]))
        self.assertEqual(service.sync()["imported_count"], 1)
        self.assertEqual(service.sync()["imported_count"], 0)
        self.assertEqual(len(self.ledger.list_executions(self.rec.recommendation_id)), 1)

    def test_behavioral_event_is_ignored_without_user_work(self):
        item = self.candidate()
        item.update({
            "candidate_id": f"fub:event:9:{self.rec.recommendation_id}",
            "source_kind": "event", "external_reference": "9",
            "proposed_execution": None, "match_confidence": 0.5,
            "raw_summary": {"type": "Viewed Page"},
        })
        result = FUBAutoSyncService(self.ledger, FakePreview([item])).sync()
        self.assertEqual(result["imported_count"], 0)
        self.assertEqual(result["ignored_count"], 1)
        self.assertIsNone(self.ledger.get_latest_decision(self.rec.recommendation_id))


if __name__ == "__main__": unittest.main()
