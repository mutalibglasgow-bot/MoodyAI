from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import LearningLedger, RecommendationService


class RecommendationLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "moodyai.db"
        self.ledger = LearningLedger(database_path)
        self.service = RecommendationService(self.ledger)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_records_recommendation_and_original_snapshot(self) -> None:
        lead = {
            "id": 1002,
            "name": "Kelsie Livingston",
            "stage": "Consultation Canceled",
            "source": "Website",
            "websiteVisits": 7,
            "lastActivity": "2026-07-21T12:00:00-05:00",
            "phones": [{"value": "2545550100"}],
            "emails": [{"value": "example@example.com"}],
        }

        record, inserted = self.service.record_lead_recommendation(
            lead=lead,
            score=100,
            predicted_class="HOT",
            recommended_action="Send a personal text, then call.",
            policy_version="lead-score-v1.0",
            feature_contributions={
                "base": 35,
                "phone": 15,
                "email": 10,
                "website_visits": 20,
                "stage_signal": 15,
            },
            source_mode="demo",
            created_at="2026-07-21T19:30:00+00:00",
        )

        self.assertTrue(inserted)
        stored = self.ledger.get_recommendation(record.recommendation_id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.entity_id, "1002")
        self.assertEqual(stored.policy_version, "lead-score-v1.0")
        self.assertEqual(stored.input_snapshot["website_visits"], 7)
        self.assertTrue(stored.input_snapshot["has_phone"])
        self.assertEqual(self.ledger.count_recommendations(), 1)

    def test_does_not_overwrite_same_recommendation(self) -> None:
        kwargs = dict(
            lead={"id": 44, "stage": "New"},
            score=40,
            predicted_class="COLD",
            recommended_action="Review manually.",
            policy_version="lead-score-v1.0",
            feature_contributions={"base": 35},
            source_mode="live",
            created_at="2026-07-21T19:30:00+00:00",
        )

        first, first_inserted = self.service.record_lead_recommendation(**kwargs)
        second, second_inserted = self.service.record_lead_recommendation(**kwargs)

        self.assertEqual(first.recommendation_id, second.recommendation_id)
        self.assertTrue(first_inserted)
        self.assertFalse(second_inserted)
        self.assertEqual(self.ledger.count_recommendations(), 1)

    def test_rejects_lead_without_stable_id(self) -> None:
        with self.assertRaises(ValueError):
            self.service.record_lead_recommendation(
                lead={"name": "No ID"},
                score=50,
                predicted_class="COLD",
                recommended_action="Review manually.",
                policy_version="lead-score-v1.0",
                feature_contributions={"base": 35},
                source_mode="live",
            )


if __name__ == "__main__":
    unittest.main()
