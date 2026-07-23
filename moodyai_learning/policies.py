from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .models import utc_now_iso
from .repository import LearningLedger

DEFAULT_WEIGHTS: dict[str, float] = {
    "base": 35.0,
    "phone_available": 15.0,
    "email_available": 10.0,
    "website_visits_3_plus": 20.0,
    "high_intent_stage": 15.0,
}
DEFAULT_THRESHOLDS: dict[str, float] = {"hot": 80.0, "warm": 55.0}


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    version: str
    weights: dict[str, float]
    thresholds: dict[str, float]
    status: str
    parent_version: str | None
    created_from_proposal: str | None
    created_at: str
    activated_at: str | None = None
    retired_at: str | None = None


class PolicyRegistry:
    """Versioned scoring policies with explicit activation and rollback."""

    def __init__(self, ledger: LearningLedger) -> None:
        self.ledger = ledger
        self._initialize_schema()
        self._seed_default_policy()

    def _initialize_schema(self) -> None:
        with self.ledger._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS scoring_policies (
                    version TEXT PRIMARY KEY,
                    parent_version TEXT,
                    status TEXT NOT NULL CHECK (status IN ('active', 'candidate', 'retired')),
                    weights_json TEXT NOT NULL,
                    thresholds_json TEXT NOT NULL,
                    created_from_proposal TEXT,
                    created_at TEXT NOT NULL,
                    activated_at TEXT,
                    retired_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_policy
                ON scoring_policies(status) WHERE status = 'active';

                CREATE TABLE IF NOT EXISTS policy_backtests (
                    backtest_id TEXT PRIMARY KEY,
                    candidate_version TEXT NOT NULL,
                    baseline_version TEXT NOT NULL,
                    sample_size INTEGER NOT NULL,
                    baseline_accuracy REAL,
                    candidate_accuracy REAL,
                    baseline_hot_precision REAL,
                    candidate_hot_precision REAL,
                    changed_predictions INTEGER NOT NULL,
                    passed INTEGER NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS policy_activation_events (
                    event_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL CHECK (action IN ('activate', 'rollback')),
                    policy_version TEXT NOT NULL,
                    previous_version TEXT,
                    actor TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _seed_default_policy(self) -> None:
        with self.ledger._connect() as connection:
            row = connection.execute(
                "SELECT version FROM scoring_policies WHERE status = 'active' LIMIT 1"
            ).fetchone()
            if row:
                return
            connection.execute(
                """
                INSERT OR IGNORE INTO scoring_policies (
                    version, parent_version, status, weights_json, thresholds_json,
                    created_from_proposal, created_at, activated_at, retired_at
                ) VALUES (?, NULL, 'active', ?, ?, NULL, ?, ?, NULL)
                """,
                (
                    "lead-score-v1.0",
                    json.dumps(DEFAULT_WEIGHTS, sort_keys=True),
                    json.dumps(DEFAULT_THRESHOLDS, sort_keys=True),
                    utc_now_iso(),
                    utc_now_iso(),
                ),
            )

    def get_active_policy(self) -> ScoringPolicy:
        with self.ledger._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scoring_policies WHERE status = 'active' LIMIT 1"
            ).fetchone()
        if not row:
            raise RuntimeError("no active scoring policy")
        return self._row_to_policy(row)

    def get_policy(self, version: str) -> ScoringPolicy | None:
        with self.ledger._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scoring_policies WHERE version = ?", (version,)
            ).fetchone()
        return self._row_to_policy(row) if row else None

    def list_policies(self) -> list[ScoringPolicy]:
        with self.ledger._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scoring_policies ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_policy(row) for row in rows]

    def create_candidate_from_proposal(self, proposal_id: str) -> ScoringPolicy:
        proposal = self.ledger.get_policy_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"policy proposal not found: {proposal_id}")
        if proposal.status != "approved":
            raise ValueError("proposal must be approved before creating a candidate policy")
        existing = self.get_policy(proposal.proposed_policy_version)
        if existing:
            return existing
        baseline = self.get_policy(proposal.current_policy_version)
        if baseline is None:
            raise KeyError(f"baseline policy not found: {proposal.current_policy_version}")
        weights = dict(baseline.weights)
        weights[proposal.feature_name] = float(proposal.proposed_weight)
        created_at = utc_now_iso()
        with self.ledger._connect() as connection:
            connection.execute(
                """
                INSERT INTO scoring_policies (
                    version, parent_version, status, weights_json, thresholds_json,
                    created_from_proposal, created_at, activated_at, retired_at
                ) VALUES (?, ?, 'candidate', ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    proposal.proposed_policy_version,
                    baseline.version,
                    json.dumps(weights, sort_keys=True),
                    json.dumps(baseline.thresholds, sort_keys=True),
                    proposal_id,
                    created_at,
                ),
            )
        return self.get_policy(proposal.proposed_policy_version)  # type: ignore[return-value]

    def backtest(self, candidate_version: str, *, minimum_sample: int = 8) -> dict[str, Any]:
        candidate = self.get_policy(candidate_version)
        if candidate is None:
            raise KeyError(f"candidate policy not found: {candidate_version}")
        if candidate.status != "candidate":
            raise ValueError("only candidate policies can be backtested")
        baseline = self.get_policy(candidate.parent_version or "")
        if baseline is None:
            raise KeyError("candidate baseline policy not found")

        evaluations = {
            item.recommendation_id: item
            for item in self.ledger.list_evaluations(limit=1000)
            if item.result_class in {"positive", "negative"}
        }
        rows = [
            recommendation
            for recommendation in self.ledger.list_recommendations(limit=1000)
            if recommendation.recommendation_id in evaluations
            and recommendation.policy_version == baseline.version
        ]
        baseline_correct = candidate_correct = 0
        baseline_hot_correct = candidate_hot_correct = 0
        baseline_hot_total = candidate_hot_total = 0
        changed = 0
        details: list[dict[str, Any]] = []
        for recommendation in rows:
            actual_positive = evaluations[recommendation.recommendation_id].result_class == "positive"
            baseline_class = recommendation.predicted_class.upper()
            candidate_score, candidate_class, _ = score_snapshot(
                recommendation.input_snapshot, candidate
            )
            if baseline_class != candidate_class:
                changed += 1
            baseline_prediction = baseline_class in {"HOT", "WARM"}
            candidate_prediction = candidate_class in {"HOT", "WARM"}
            baseline_correct += int(baseline_prediction == actual_positive)
            candidate_correct += int(candidate_prediction == actual_positive)
            if baseline_class == "HOT":
                baseline_hot_total += 1
                baseline_hot_correct += int(actual_positive)
            if candidate_class == "HOT":
                candidate_hot_total += 1
                candidate_hot_correct += int(actual_positive)
            details.append({
                "recommendation_id": recommendation.recommendation_id,
                "actual_positive": actual_positive,
                "baseline_class": baseline_class,
                "candidate_class": candidate_class,
                "candidate_score": candidate_score,
            })

        sample = len(rows)
        rate = lambda n, d: round(n / d, 4) if d else None
        baseline_accuracy = rate(baseline_correct, sample)
        candidate_accuracy = rate(candidate_correct, sample)
        baseline_hot_precision = rate(baseline_hot_correct, baseline_hot_total)
        candidate_hot_precision = rate(candidate_hot_correct, candidate_hot_total)
        sufficient = sample >= minimum_sample
        non_degrading = (
            sufficient
            and candidate_accuracy is not None
            and baseline_accuracy is not None
            and candidate_accuracy >= baseline_accuracy
        )
        passed = bool(non_degrading)
        payload = {
            "candidate_version": candidate.version,
            "baseline_version": baseline.version,
            "sample_size": sample,
            "minimum_sample": minimum_sample,
            "sufficient_data": sufficient,
            "baseline_accuracy": baseline_accuracy,
            "candidate_accuracy": candidate_accuracy,
            "baseline_hot_precision": baseline_hot_precision,
            "candidate_hot_precision": candidate_hot_precision,
            "changed_predictions": changed,
            "passed": passed,
            "automatic_activation": False,
            "details": details,
        }
        digest = hashlib.sha256(
            json.dumps({k: v for k, v in payload.items() if k != "details"}, sort_keys=True).encode()
        ).hexdigest()[:20]
        with self.ledger._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO policy_backtests (
                    backtest_id, candidate_version, baseline_version, sample_size,
                    baseline_accuracy, candidate_accuracy, baseline_hot_precision,
                    candidate_hot_precision, changed_predictions, passed, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"backtest_{digest}", candidate.version, baseline.version, sample,
                    baseline_accuracy, candidate_accuracy, baseline_hot_precision,
                    candidate_hot_precision, changed, int(passed),
                    json.dumps(payload, sort_keys=True), utc_now_iso(),
                ),
            )
        return payload

    def activate(
        self,
        candidate_version: str,
        *,
        actor: str = "Moody",
        reason: str | None = None,
    ) -> ScoringPolicy:
        candidate = self.get_policy(candidate_version)
        if candidate is None:
            raise KeyError(f"candidate policy not found: {candidate_version}")
        if candidate.status != "candidate":
            raise ValueError("only candidate policies can be activated")
        with self.ledger._connect() as connection:
            backtest = connection.execute(
                """
                SELECT * FROM policy_backtests
                WHERE candidate_version = ? ORDER BY created_at DESC LIMIT 1
                """, (candidate_version,)
            ).fetchone()
            if not backtest or not bool(backtest["passed"]):
                raise ValueError("candidate must pass a backtest before activation")
            active = connection.execute(
                "SELECT version FROM scoring_policies WHERE status = 'active' LIMIT 1"
            ).fetchone()
            previous = active["version"] if active else None
            now = utc_now_iso()
            if previous:
                connection.execute(
                    "UPDATE scoring_policies SET status = 'retired', retired_at = ? WHERE version = ?",
                    (now, previous),
                )
            connection.execute(
                "UPDATE scoring_policies SET status = 'active', activated_at = ?, retired_at = NULL WHERE version = ?",
                (now, candidate_version),
            )
            event_id = self._event_id("activate", candidate_version, previous, now)
            connection.execute(
                """
                INSERT INTO policy_activation_events
                (event_id, action, policy_version, previous_version, actor, reason, created_at)
                VALUES (?, 'activate', ?, ?, ?, ?, ?)
                """, (event_id, candidate_version, previous, actor, reason, now)
            )
        return self.get_active_policy()

    def rollback(
        self,
        target_version: str,
        *,
        actor: str = "Moody",
        reason: str | None = None,
    ) -> ScoringPolicy:
        target = self.get_policy(target_version)
        if target is None:
            raise KeyError(f"rollback policy not found: {target_version}")
        active = self.get_active_policy()
        if target.version == active.version:
            return active
        now = utc_now_iso()
        with self.ledger._connect() as connection:
            connection.execute(
                "UPDATE scoring_policies SET status = 'retired', retired_at = ? WHERE version = ?",
                (now, active.version),
            )
            connection.execute(
                "UPDATE scoring_policies SET status = 'active', activated_at = ?, retired_at = NULL WHERE version = ?",
                (now, target.version),
            )
            event_id = self._event_id("rollback", target.version, active.version, now)
            connection.execute(
                """
                INSERT INTO policy_activation_events
                (event_id, action, policy_version, previous_version, actor, reason, created_at)
                VALUES (?, 'rollback', ?, ?, ?, ?, ?)
                """, (event_id, target.version, active.version, actor, reason, now)
            )
        return self.get_active_policy()

    @staticmethod
    def _event_id(action: str, version: str, previous: str | None, created_at: str) -> str:
        digest = hashlib.sha256(
            json.dumps([action, version, previous, created_at]).encode()
        ).hexdigest()[:20]
        return f"policy_event_{digest}"

    @staticmethod
    def _row_to_policy(row: Any) -> ScoringPolicy:
        return ScoringPolicy(
            version=row["version"],
            parent_version=row["parent_version"],
            status=row["status"],
            weights=json.loads(row["weights_json"]),
            thresholds=json.loads(row["thresholds_json"]),
            created_from_proposal=row["created_from_proposal"],
            created_at=row["created_at"],
            activated_at=row["activated_at"],
            retired_at=row["retired_at"],
        )


def score_snapshot(snapshot: dict[str, Any], policy: ScoringPolicy) -> tuple[int, str, dict[str, float]]:
    stage = str(snapshot.get("stage") or "New").lower()
    try:
        visits = int(snapshot.get("website_visits") or snapshot.get("websiteVisits") or 0)
    except (TypeError, ValueError):
        visits = 0
    flags = {
        "base": True,
        "phone_available": bool(snapshot.get("has_phone") or snapshot.get("phone") or snapshot.get("phones")),
        "email_available": bool(snapshot.get("has_email") or snapshot.get("email") or snapshot.get("emails")),
        "website_visits_3_plus": visits >= 3,
        "high_intent_stage": "cash" in stage or "appointment" in stage,
    }
    contributions = {
        name: float(policy.weights.get(name, 0.0)) if present else 0.0
        for name, present in flags.items()
    }
    score = min(int(sum(contributions.values())), 100)
    hot = float(policy.thresholds.get("hot", 80.0))
    warm = float(policy.thresholds.get("warm", 55.0))
    predicted = "HOT" if score >= hot else "WARM" if score >= warm else "COLD"
    return score, predicted, contributions
