from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import DecisionService, LearningLedger, RecommendationService
from moodyai_learning.fub_import import FUBSyncImportService


class _Preview:
    def __init__(self, candidate):
        self.candidate = candidate

    def preview(self, *, limit=100):
        return {"items": [self.candidate]}


class FUBSyncImportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp_dir.name) / "test.db")
        service = RecommendationService(self.ledger)
        recommendation, _ = service.record_lead_recommendation_once(
            lead={"id": 376845, "name": "Test Lead", "stage": "Active"},
            policy_version="lead-score-v1.0",
            score=90,
            predicted_class="HOT",
            recommended_action="Call today",
            prediction_window_days=14,
            feature_contributions={"base": 35},
            source_mode="live",
        )
        self.rid = recommendation.recommendation_id
        DecisionService(self.ledger).record_decision(
            recommendation_id=self.rid,
            status="accepted",
            reason="Approve outreach",
        )
        self.candidate = {
            "candidate_id": f"fub:call:599115:{self.rid}",
            "recommendation_id": self.rid,
            "person_id": "376845",
            "source_kind": "call",
            "external_reference": "599115",
            "observed_at": "2026-07-22T18:17:08Z",
            "proposed_execution": {
                "action_type": "call",
                "status": "completed",
                "external_system": "follow_up_boss",
                "external_reference": "call:599115",
                "notes": None,
            },
            "proposed_outcome": None,
            "match_confidence": 0.7,
            "review_required": True,
            "reason": "Matched",
            "raw_summary": {"id": "599115"},
        }
        self.service = FUBSyncImportService(self.ledger, _Preview(self.candidate))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_approved_candidate_creates_execution(self):
        result = self.service.review_candidate(
            self.candidate["candidate_id"], status="approved"
        )
        self.assertTrue(result["recorded"])
        executions = self.ledger.list_executions(self.rid)
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].external_reference, "call:599115")

    def test_duplicate_candidate_is_not_imported_twice(self):
        first = self.service.review_candidate(self.candidate["candidate_id"], status="approved")
        second = self.service.review_candidate(self.candidate["candidate_id"], status="approved")
        self.assertTrue(first["recorded"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(self.ledger.list_executions(self.rid)), 1)

    def test_rejected_candidate_creates_no_execution(self):
        result = self.service.review_candidate(
            self.candidate["candidate_id"], status="rejected", reason="Wrong match"
        )
        self.assertTrue(result["recorded"])
        self.assertEqual(len(self.ledger.list_executions(self.rid)), 0)


if __name__ == "__main__":
    unittest.main()
