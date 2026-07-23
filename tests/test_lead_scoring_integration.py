from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import (
    LEAD_POLICY_VERSION,
    LearningLedger,
    RecommendationService,
    normalize_and_record_lead,
    score_lead,
)


class LeadScoringTests(unittest.TestCase):
    def test_preserves_existing_hot_lead_rules(self) -> None:
        result = score_lead(
            {
                "id": 123,
                "stage": "Appointment Canceled",
                "websiteVisits": 7,
                "phone": "2545550100",
                "email": "lead@example.com",
            }
        )
        self.assertEqual(result.score, 95)
        self.assertEqual(result.predicted_class, "HOT")
        self.assertEqual(result.feature_contributions["base"], 35)
        self.assertEqual(result.feature_contributions["website_visits_3_plus"], 20)
        self.assertEqual(result.feature_contributions["high_intent_stage"], 15)

    def test_invalid_website_visits_does_not_crash(self) -> None:
        result = score_lead({"id": 123, "websiteVisits": "not-a-number"})
        self.assertEqual(result.score, 35)
        self.assertEqual(result.predicted_class, "COLD")


class LeadLedgerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "moodyai.db"
        self.ledger = LearningLedger(database_path)
        self.service = RecommendationService(self.ledger)
        self.lead = {
            "id": 364385,
            "name": "Crystal Rymer",
            "stage": "Sourcing Cash Offers",
            "source": "Orchard - Seller Intake",
            "websiteVisits": 4,
            "phone": "2545550100",
            "email": "crystal@example.com",
            "lastActivity": "2026-07-21T15:00:00Z",
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dashboard_refresh_is_idempotent(self) -> None:
        first = normalize_and_record_lead(
            self.lead,
            recommendation_service=self.service,
            source_mode="live",
        )
        second = normalize_and_record_lead(
            self.lead,
            recommendation_service=self.service,
            source_mode="live",
        )

        self.assertEqual(first["recommendation_id"], second["recommendation_id"])
        self.assertTrue(first["recommendation_recorded"])
        self.assertFalse(second["recommendation_recorded"])
        self.assertEqual(self.ledger.count_recommendations(), 1)
        self.assertEqual(first["policy_version"], LEAD_POLICY_VERSION)

    def test_changed_lead_snapshot_creates_new_recommendation(self) -> None:
        first = normalize_and_record_lead(
            self.lead,
            recommendation_service=self.service,
            source_mode="live",
        )
        changed = dict(self.lead)
        changed["websiteVisits"] = 8
        second = normalize_and_record_lead(
            changed,
            recommendation_service=self.service,
            source_mode="live",
        )

        self.assertNotEqual(first["recommendation_id"], second["recommendation_id"])
        self.assertEqual(self.ledger.count_recommendations(), 2)


if __name__ == "__main__":
    unittest.main()
