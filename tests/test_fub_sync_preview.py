from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import LearningLedger, RecommendationService
from moodyai_learning.fub_sync import FUBSyncPreviewService


class FUBSyncPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp.name) / "test.db")
        self.service = RecommendationService(self.ledger)
        self.recommendation, _ = self.service.record_lead_recommendation(
            lead={"id": 42, "name": "Test Lead", "stage": "Lead"},
            score=90,
            predicted_class="HOT",
            recommended_action="Call now",
            policy_version="lead-score-v1.0",
            prediction_window_days=14,
            feature_contributions={"base": 35},
            source_mode="test",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _service(self, calls=None, texts=None, events=None):
        return FUBSyncPreviewService(
            self.ledger,
            get_calls=lambda **_: {"calls": calls or []},
            get_text_messages=lambda **_: {"textMessages": texts or []},
            get_events=lambda **_: {"events": events or []},
        )

    def test_preview_is_read_only_and_maps_call(self) -> None:
        result = self._service(calls=[{
            "id": 10,
            "created": "2099-01-01T00:00:00Z",
            "isIncoming": False,
            "outcome": "Interested",
            "note": "Good conversation",
        }]).preview()
        self.assertFalse(result["writes_performed"])
        self.assertEqual(result["candidate_count"], 1)
        item = result["items"][0]
        self.assertEqual(item["proposed_execution"]["action_type"], "call")
        self.assertEqual(item["proposed_outcome"]["outcome_type"], "qualified_conversation")
        self.assertEqual(self.ledger.count_executions(), 0)
        self.assertEqual(self.ledger.count_outcomes(), 0)

    def test_incoming_text_maps_to_reply(self) -> None:
        result = self._service(texts=[{
            "id": 20,
            "created": "2099-01-01T00:00:00Z",
            "isIncoming": True,
        }]).preview()
        self.assertEqual(result["items"][0]["proposed_outcome"]["outcome_type"], "replied")
        self.assertTrue(result["items"][0]["review_required"])

    def test_event_payload_is_parsed(self) -> None:
        result = self._service(events=[{
            "id": 30,
            "occurred": "2099-01-01T00:00:00Z",
            "type": "Viewed Page",
        }]).preview()
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["items"][0]["source_kind"], "event")

    def test_old_activity_is_ignored(self) -> None:
        result = self._service(calls=[{"id": 10, "created": "2000-01-01T00:00:00Z"}]).preview()
        self.assertEqual(result["candidate_count"], 0)

    def test_fetches_each_source_once_per_person(self) -> None:
        self.service.record_lead_recommendation(
            lead={"id": 42, "name": "Test Lead", "stage": "Hot Lead"},
            score=95,
            predicted_class="HOT",
            recommended_action="Call again",
            policy_version="lead-score-v1.0",
            prediction_window_days=14,
            feature_contributions={"base": 35, "stage": 15},
            source_mode="test",
        )
        counts = {"calls": 0, "texts": 0, "events": 0}

        def calls(**_):
            counts["calls"] += 1
            return {"calls": []}

        def texts(**_):
            counts["texts"] += 1
            return {"textMessages": []}

        def events(**_):
            counts["events"] += 1
            return {"events": []}

        FUBSyncPreviewService(
            self.ledger,
            get_calls=calls,
            get_text_messages=texts,
            get_events=events,
        ).preview()
        self.assertEqual(counts, {"calls": 1, "texts": 1, "events": 1})

    def test_one_activity_maps_to_latest_eligible_recommendation(self) -> None:
        older = self.recommendation
        newer, _ = self.service.record_lead_recommendation(
            lead={"id": 42, "name": "Test Lead", "stage": "Hot Lead"},
            score=95,
            predicted_class="HOT",
            recommended_action="Call again",
            policy_version="lead-score-v1.0",
            prediction_window_days=14,
            feature_contributions={"base": 35, "stage": 15},
            source_mode="test",
        )
        result = self._service(calls=[{
            "id": 99,
            "created": "2099-01-01T00:00:00Z",
        }]).preview()
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["items"][0]["recommendation_id"], newer.recommendation_id)
        self.assertNotEqual(result["items"][0]["recommendation_id"], older.recommendation_id)


if __name__ == "__main__":
    unittest.main()
