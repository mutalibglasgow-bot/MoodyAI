from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from typing import Any

from .models import PolicyProposalRecord, utc_now_iso
from .repository import LearningLedger


class PolicyAdaptationService:
    """Creates evidence-backed policy proposals without activating them.

    A proposal compares evaluated outcomes when a scoring feature was present
    versus absent. It never edits lead_scoring.py and never changes the active
    policy automatically.
    """

    def __init__(self, ledger: LearningLedger) -> None:
        self.ledger = ledger

    def generate_proposals(
        self,
        *,
        policy_version: str = "lead-score-v1.0",
        minimum_total_sample: int = 8,
        minimum_group_sample: int = 3,
        minimum_effect: float = 0.15,
        weight_step: float = 5.0,
    ) -> dict[str, Any]:
        recommendations = [
            item
            for item in self.ledger.list_recommendations(limit=1000)
            if item.policy_version == policy_version
        ]
        evaluation_by_id = {
            item.recommendation_id: item
            for item in self.ledger.list_evaluations(limit=1000)
            if item.policy_version == policy_version
            and item.result_class in {"positive", "negative"}
        }
        usable = [
            item for item in recommendations if item.recommendation_id in evaluation_by_id
        ]

        if len(usable) < minimum_total_sample:
            return {
                "policy_version": policy_version,
                "usable_evaluations": len(usable),
                "minimum_total_sample": minimum_total_sample,
                "generated": 0,
                "insufficient_data": True,
                "reason": "Not enough evaluated recommendations to propose a policy change.",
                "automatic_activation": False,
                "items": [],
            }

        feature_rows: dict[str, list[tuple[bool, bool, float]]] = defaultdict(list)
        for recommendation in usable:
            evaluation = evaluation_by_id[recommendation.recommendation_id]
            is_positive = evaluation.result_class == "positive"
            for feature, contribution in recommendation.feature_contributions.items():
                if feature == "base":
                    continue
                contribution_value = float(contribution)
                feature_rows[feature].append(
                    (contribution_value > 0, is_positive, contribution_value)
                )

        proposals: list[PolicyProposalRecord] = []
        diagnostics: list[dict[str, Any]] = []
        for feature, rows in sorted(feature_rows.items()):
            present = [row for row in rows if row[0]]
            absent = [row for row in rows if not row[0]]
            if len(present) < minimum_group_sample or len(absent) < minimum_group_sample:
                diagnostics.append(
                    {
                        "feature": feature,
                        "status": "insufficient_group_sample",
                        "present_sample": len(present),
                        "absent_sample": len(absent),
                    }
                )
                continue

            present_positive = sum(1 for _, positive, _ in present if positive)
            absent_positive = sum(1 for _, positive, _ in absent if positive)
            present_rate = present_positive / len(present)
            absent_rate = absent_positive / len(absent)
            effect = present_rate - absent_rate
            current_weight = max((weight for _, _, weight in present), default=0.0)

            if abs(effect) < minimum_effect:
                diagnostics.append(
                    {
                        "feature": feature,
                        "status": "effect_below_threshold",
                        "effect_size": round(effect, 4),
                        "minimum_effect": minimum_effect,
                    }
                )
                continue

            direction = "increase" if effect > 0 else "decrease"
            proposed_weight = max(
                0.0,
                min(40.0, current_weight + weight_step if effect > 0 else current_weight - weight_step),
            )
            if proposed_weight == current_weight:
                continue

            proposal_payload = {
                "current_policy_version": policy_version,
                "proposed_policy_version": self._next_version(policy_version),
                "feature_name": feature,
                "current_weight": current_weight,
                "proposed_weight": proposed_weight,
                "direction": direction,
                "sample_size": len(rows),
                "feature_present_sample": len(present),
                "feature_absent_sample": len(absent),
                "feature_positive_rate": round(present_rate, 4),
                "baseline_positive_rate": round(absent_rate, 4),
                "effect_size": round(effect, 4),
                "minimum_effect": minimum_effect,
                "rationale": (
                    f"{feature} was associated with a {present_rate:.1%} positive-outcome rate "
                    f"versus {absent_rate:.1%} when absent across {len(rows)} evaluated recommendations."
                ),
                "status": "awaiting_approval",
                "created_at": utc_now_iso(),
            }
            digest = hashlib.sha256(
                json.dumps(
                    {
                        "policy": policy_version,
                        "feature": feature,
                        "current_weight": current_weight,
                        "proposed_weight": proposed_weight,
                        "sample_size": len(rows),
                        "present_rate": round(present_rate, 4),
                        "absent_rate": round(absent_rate, 4),
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()[:20]
            proposal = PolicyProposalRecord(
                proposal_id=f"prop_{digest}",
                **proposal_payload,
            )
            self.ledger.save_policy_proposal(proposal)
            proposals.append(proposal)

        return {
            "policy_version": policy_version,
            "usable_evaluations": len(usable),
            "minimum_total_sample": minimum_total_sample,
            "generated": len(proposals),
            "insufficient_data": False,
            "automatic_activation": False,
            "items": [asdict(item) for item in proposals],
            "diagnostics": diagnostics,
        }

    def review_proposal(
        self,
        proposal_id: str,
        *,
        status: str,
        reason: str | None = None,
        reviewed_by: str = "Moody",
    ) -> PolicyProposalRecord:
        if status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")
        proposal = self.ledger.get_policy_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"policy proposal not found: {proposal_id}")
        return self.ledger.review_policy_proposal(
            proposal_id,
            status=status,
            reviewed_by=reviewed_by,
            review_reason=reason,
            reviewed_at=utc_now_iso(),
        )

    @staticmethod
    def _next_version(policy_version: str) -> str:
        prefix, separator, version = policy_version.rpartition("v")
        if separator and "." in version:
            major, _, minor = version.partition(".")
            if major.isdigit() and minor.isdigit():
                return f"{prefix}v{major}.{int(minor) + 1}"
        return f"{policy_version}.candidate"
