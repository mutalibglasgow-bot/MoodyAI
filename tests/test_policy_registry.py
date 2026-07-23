from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning import LearningLedger, PolicyRegistry
from moodyai_learning.models import PolicyProposalRecord, utc_now_iso


class PolicyRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = LearningLedger(Path(self.temp.name) / "learning.db")
        self.registry = PolicyRegistry(self.ledger)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def approved_proposal(self) -> PolicyProposalRecord:
        proposal = PolicyProposalRecord(
            proposal_id="prop_test",
            current_policy_version="lead-score-v1.0",
            proposed_policy_version="lead-score-v1.1",
            feature_name="website_visits_3_plus",
            current_weight=20,
            proposed_weight=25,
            direction="increase",
            sample_size=10,
            feature_present_sample=5,
            feature_absent_sample=5,
            feature_positive_rate=.6,
            baseline_positive_rate=.2,
            effect_size=.4,
            minimum_effect=.15,
            rationale="test",
            status="approved",
            created_at=utc_now_iso(),
            reviewed_at=utc_now_iso(),
            reviewed_by="Moody",
        )
        self.ledger.save_policy_proposal(proposal)
        return proposal

    def test_seeds_v1_as_active(self) -> None:
        active = self.registry.get_active_policy()
        self.assertEqual(active.version, "lead-score-v1.0")
        self.assertEqual(active.status, "active")

    def test_creates_candidate_from_approved_proposal(self) -> None:
        proposal = self.approved_proposal()
        candidate = self.registry.create_candidate_from_proposal(proposal.proposal_id)
        self.assertEqual(candidate.status, "candidate")
        self.assertEqual(candidate.weights["website_visits_3_plus"], 25)
        self.assertEqual(self.registry.get_active_policy().version, "lead-score-v1.0")

    def test_rejects_unapproved_proposal(self) -> None:
        proposal = PolicyProposalRecord(
            proposal_id="prop_waiting",
            current_policy_version="lead-score-v1.0",
            proposed_policy_version="lead-score-v1.1",
            feature_name="email_available",
            current_weight=10,
            proposed_weight=15,
            direction="increase",
            sample_size=10,
            feature_present_sample=5,
            feature_absent_sample=5,
            feature_positive_rate=.6,
            baseline_positive_rate=.2,
            effect_size=.4,
            minimum_effect=.15,
            rationale="test",
            status="awaiting_approval",
            created_at=utc_now_iso(),
        )
        self.ledger.save_policy_proposal(proposal)
        with self.assertRaises(ValueError):
            self.registry.create_candidate_from_proposal(proposal.proposal_id)

    def test_activation_requires_passing_backtest(self) -> None:
        proposal = self.approved_proposal()
        candidate = self.registry.create_candidate_from_proposal(proposal.proposal_id)
        with self.assertRaises(ValueError):
            self.registry.activate(candidate.version)

    def test_rollback_changes_active_policy(self) -> None:
        proposal = self.approved_proposal()
        candidate = self.registry.create_candidate_from_proposal(proposal.proposal_id)
        with self.ledger._connect() as connection:
            connection.execute("UPDATE scoring_policies SET status='retired' WHERE version='lead-score-v1.0'")
            connection.execute("UPDATE scoring_policies SET status='active' WHERE version=?", (candidate.version,))
        active = self.registry.rollback("lead-score-v1.0", reason="test")
        self.assertEqual(active.version, "lead-score-v1.0")
