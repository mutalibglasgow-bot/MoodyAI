from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import (
    DecisionService,
    ExecutionService,
    LearningEvaluator,
    LearningLedger,
    OutcomeService,
    PolicyAdaptationService,
    RecommendationService,
)


class PolicyAdaptationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp_dir.name) / "moodyai.db")
        self.recommendations = RecommendationService(self.ledger)
        self.decisions = DecisionService(self.ledger)
        self.executions = ExecutionService(self.ledger)
        self.outcomes = OutcomeService(self.ledger)
        self.evaluator = LearningEvaluator(self.ledger)
        self.adaptation = PolicyAdaptationService(self.ledger)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _add(self, lead_id: int, *, feature_present: bool, positive: bool) -> None:
        record, _ = self.recommendations.record_lead_recommendation_once(
            lead={"id": lead_id, "name": f"Lead {lead_id}", "stage": "New"},
            score=80 if feature_present else 60,
            predicted_class="HOT" if feature_present else "WARM",
            recommended_action="Call lead.",
            policy_version="lead-score-v1.0",
            feature_contributions={
                "base": 35,
                "website_visits_3_plus": 20 if feature_present else 0,
            },
            source_mode="test",
        )
        self.decisions.record_decision(
            recommendation_id=record.recommendation_id, status="accepted"
        )
        self.executions.record_execution(
            recommendation_id=record.recommendation_id,
            action_type="call",
            status="completed",
        )
        self.outcomes.record_outcome(
            recommendation_id=record.recommendation_id,
            outcome_type="replied" if positive else "no_response",
        )

    def test_insufficient_data_creates_no_proposal(self) -> None:
        self._add(1, feature_present=True, positive=True)
        self.evaluator.evaluate_all()
        result = self.adaptation.generate_proposals()
        self.assertTrue(result["insufficient_data"])
        self.assertEqual(result["generated"], 0)

    def test_strong_feature_creates_increase_proposal(self) -> None:
        for lead_id in range(1, 5):
            self._add(lead_id, feature_present=True, positive=True)
        for lead_id in range(5, 9):
            self._add(lead_id, feature_present=False, positive=False)
        self.evaluator.evaluate_all()
        result = self.adaptation.generate_proposals()
        self.assertFalse(result["insufficient_data"])
        self.assertEqual(result["generated"], 1)
        proposal = result["items"][0]
        self.assertEqual(proposal["feature_name"], "website_visits_3_plus")
        self.assertEqual(proposal["direction"], "increase")
        self.assertEqual(proposal["current_weight"], 20)
        self.assertEqual(proposal["proposed_weight"], 25)
        self.assertEqual(proposal["status"], "awaiting_approval")

    def test_proposal_generation_is_idempotent(self) -> None:
        for lead_id in range(1, 5):
            self._add(lead_id, feature_present=True, positive=True)
        for lead_id in range(5, 9):
            self._add(lead_id, feature_present=False, positive=False)
        self.evaluator.evaluate_all()
        first = self.adaptation.generate_proposals()
        second = self.adaptation.generate_proposals()
        self.assertEqual(first["items"][0]["proposal_id"], second["items"][0]["proposal_id"])
        self.assertEqual(len(self.ledger.list_policy_proposals()), 1)

    def test_human_can_approve_proposal_without_activation(self) -> None:
        for lead_id in range(1, 5):
            self._add(lead_id, feature_present=True, positive=True)
        for lead_id in range(5, 9):
            self._add(lead_id, feature_present=False, positive=False)
        self.evaluator.evaluate_all()
        proposal_id = self.adaptation.generate_proposals()["items"][0]["proposal_id"]
        reviewed = self.adaptation.review_proposal(
            proposal_id,
            status="approved",
            reason="Evidence is strong enough for a controlled candidate policy.",
        )
        self.assertEqual(reviewed.status, "approved")
        self.assertEqual(reviewed.current_policy_version, "lead-score-v1.0")
        self.assertEqual(reviewed.proposed_policy_version, "lead-score-v1.1")
        self.assertEqual(self.ledger.get_policy_proposal(proposal_id).status, "approved")

    def test_rejects_invalid_review_status(self) -> None:
        with self.assertRaises(ValueError):
            self.adaptation.review_proposal("missing", status="activate")


if __name__ == "__main__":
    unittest.main()
