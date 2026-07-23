from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import (
    DecisionRecord,
    EvaluationRecord,
    ExecutionRecord,
    OutcomeRecord,
    PolicyProposalRecord,
    RecommendationRecord,
)


class _ClosingConnection(sqlite3.Connection):
    """Commit or roll back, then close when leaving a with block."""

    def __exit__(self, exc_type, exc_value, traceback):  # type: ignore[no-untyped-def]
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
    predicted_class TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    prediction_window_days INTEGER NOT NULL CHECK (prediction_window_days > 0),
    input_snapshot_json TEXT NOT NULL,
    feature_contributions_json TEXT NOT NULL,
    source_mode TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL,
    UNIQUE(entity_type, entity_id, policy_version, created_at)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_entity
ON recommendations(entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_recommendations_policy
ON recommendations(policy_version, created_at);

CREATE TABLE IF NOT EXISTS recommendation_decisions (
    decision_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'modified', 'rejected', 'deferred')),
    selected_action TEXT,
    reason TEXT,
    decided_by TEXT NOT NULL DEFAULT 'Moody',
    decided_at TEXT NOT NULL,
    FOREIGN KEY (recommendation_id)
        REFERENCES recommendations(recommendation_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_decisions_recommendation_time
ON recommendation_decisions(recommendation_id, decided_at DESC);

CREATE TABLE IF NOT EXISTS recommendation_executions (
    execution_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('started', 'completed', 'failed', 'canceled')),
    notes TEXT,
    external_system TEXT,
    external_reference TEXT,
    performed_by TEXT NOT NULL DEFAULT 'Moody',
    performed_at TEXT NOT NULL,
    FOREIGN KEY (recommendation_id)
        REFERENCES recommendations(recommendation_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_executions_recommendation_time
ON recommendation_executions(recommendation_id, performed_at DESC);

CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    outcome_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL,
    outcome_type TEXT NOT NULL,
    outcome_value REAL,
    source TEXT NOT NULL,
    attribution_confidence REAL NOT NULL CHECK (attribution_confidence >= 0 AND attribution_confidence <= 1),
    notes TEXT,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (recommendation_id)
        REFERENCES recommendations(recommendation_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_outcomes_recommendation_time
ON recommendation_outcomes(recommendation_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS recommendation_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL UNIQUE,
    policy_version TEXT NOT NULL,
    predicted_class TEXT NOT NULL,
    score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
    highest_outcome TEXT,
    outcome_rank INTEGER,
    result_class TEXT NOT NULL CHECK (result_class IN ('positive', 'negative', 'invalid', 'unknown')),
    prediction_correct INTEGER,
    action_effective INTEGER,
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY (recommendation_id)
        REFERENCES recommendations(recommendation_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_evaluations_policy_time
ON recommendation_evaluations(policy_version, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS policy_change_proposals (
    proposal_id TEXT PRIMARY KEY,
    current_policy_version TEXT NOT NULL,
    proposed_policy_version TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    current_weight REAL NOT NULL,
    proposed_weight REAL NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('increase', 'decrease')),
    sample_size INTEGER NOT NULL,
    feature_present_sample INTEGER NOT NULL,
    feature_absent_sample INTEGER NOT NULL,
    feature_positive_rate REAL NOT NULL,
    baseline_positive_rate REAL NOT NULL,
    effect_size REAL NOT NULL,
    minimum_effect REAL NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('awaiting_approval', 'approved', 'rejected')),
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by TEXT,
    review_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_policy_proposals_status_time
ON policy_change_proposals(status, created_at DESC);
"""


class LearningLedger:
    """SQLite-backed persistence for recommendations and human decisions."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def save_recommendation(self, record: RecommendationRecord) -> bool:
        statement = """
        INSERT OR IGNORE INTO recommendations (
            recommendation_id, entity_type, entity_id, policy_version, score,
            predicted_class, recommended_action, prediction_window_days,
            input_snapshot_json, feature_contributions_json, source_mode, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = (
            record.recommendation_id,
            record.entity_type,
            record.entity_id,
            record.policy_version,
            record.score,
            record.predicted_class,
            record.recommended_action,
            record.prediction_window_days,
            json.dumps(record.input_snapshot, sort_keys=True, default=str),
            json.dumps(record.feature_contributions, sort_keys=True, default=str),
            record.source_mode,
            record.created_at,
        )
        with self._connect() as connection:
            cursor = connection.execute(statement, values)
            return cursor.rowcount == 1

    def get_recommendation(self, recommendation_id: str) -> RecommendationRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM recommendations WHERE recommendation_id = ?",
                (recommendation_id,),
            ).fetchone()
        return self._row_to_recommendation(row) if row else None

    def list_recommendations(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[RecommendationRecord]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        clauses: list[str] = []
        values: list[object] = []
        if entity_type is not None:
            clauses.append("entity_type = ?")
            values.append(entity_type)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            values.append(entity_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM recommendations {where} ORDER BY created_at DESC LIMIT ?",
                values,
            ).fetchall()
        return [self._row_to_recommendation(row) for row in rows]

    def count_recommendations(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM recommendations").fetchone()
        return int(row["count"])

    def save_decision(self, record: DecisionRecord) -> bool:
        if self.get_recommendation(record.recommendation_id) is None:
            raise KeyError(f"recommendation not found: {record.recommendation_id}")
        statement = """
        INSERT OR IGNORE INTO recommendation_decisions (
            decision_id, recommendation_id, status, selected_action,
            reason, decided_by, decided_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as connection:
            cursor = connection.execute(
                statement,
                (
                    record.decision_id,
                    record.recommendation_id,
                    record.status,
                    record.selected_action,
                    record.reason,
                    record.decided_by,
                    record.decided_at,
                ),
            )
            return cursor.rowcount == 1

    def get_latest_decision(self, recommendation_id: str) -> DecisionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM recommendation_decisions
                WHERE recommendation_id = ?
                ORDER BY decided_at DESC, rowid DESC
                LIMIT 1
                """,
                (recommendation_id,),
            ).fetchone()
        return self._row_to_decision(row) if row else None

    def list_decisions(self, recommendation_id: str) -> list[DecisionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recommendation_decisions
                WHERE recommendation_id = ?
                ORDER BY decided_at ASC, rowid ASC
                """,
                (recommendation_id,),
            ).fetchall()
        return [self._row_to_decision(row) for row in rows]

    def count_decisions(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM recommendation_decisions"
            ).fetchone()
        return int(row["count"])


    def save_execution(self, record: ExecutionRecord) -> bool:
        if self.get_recommendation(record.recommendation_id) is None:
            raise KeyError(f"recommendation not found: {record.recommendation_id}")
        statement = """
        INSERT OR IGNORE INTO recommendation_executions (
            execution_id, recommendation_id, action_type, status, notes,
            external_system, external_reference, performed_by, performed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as connection:
            cursor = connection.execute(
                statement,
                (
                    record.execution_id,
                    record.recommendation_id,
                    record.action_type,
                    record.status,
                    record.notes,
                    record.external_system,
                    record.external_reference,
                    record.performed_by,
                    record.performed_at,
                ),
            )
            return cursor.rowcount == 1

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM recommendation_executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        return self._row_to_execution(row) if row else None

    def get_latest_execution(self, recommendation_id: str) -> ExecutionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM recommendation_executions
                WHERE recommendation_id = ?
                ORDER BY performed_at DESC, rowid DESC
                LIMIT 1
                """,
                (recommendation_id,),
            ).fetchone()
        return self._row_to_execution(row) if row else None

    def list_executions(self, recommendation_id: str) -> list[ExecutionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recommendation_executions
                WHERE recommendation_id = ?
                ORDER BY performed_at ASC, rowid ASC
                """,
                (recommendation_id,),
            ).fetchall()
        return [self._row_to_execution(row) for row in rows]

    def count_executions(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM recommendation_executions"
            ).fetchone()
        return int(row["count"])

    def save_outcome(self, record: OutcomeRecord) -> bool:
        if self.get_recommendation(record.recommendation_id) is None:
            raise KeyError(f"recommendation not found: {record.recommendation_id}")
        statement = """
        INSERT OR IGNORE INTO recommendation_outcomes (
            outcome_id, recommendation_id, outcome_type, outcome_value,
            source, attribution_confidence, notes, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as connection:
            cursor = connection.execute(
                statement,
                (
                    record.outcome_id,
                    record.recommendation_id,
                    record.outcome_type,
                    record.outcome_value,
                    record.source,
                    record.attribution_confidence,
                    record.notes,
                    record.observed_at,
                ),
            )
            return cursor.rowcount == 1

    def get_outcome(self, outcome_id: str) -> OutcomeRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM recommendation_outcomes WHERE outcome_id = ?",
                (outcome_id,),
            ).fetchone()
        return self._row_to_outcome(row) if row else None

    def get_latest_outcome(self, recommendation_id: str) -> OutcomeRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM recommendation_outcomes
                WHERE recommendation_id = ?
                ORDER BY observed_at DESC, rowid DESC
                LIMIT 1
                """,
                (recommendation_id,),
            ).fetchone()
        return self._row_to_outcome(row) if row else None

    def list_outcomes(self, recommendation_id: str) -> list[OutcomeRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recommendation_outcomes
                WHERE recommendation_id = ?
                ORDER BY observed_at ASC, rowid ASC
                """,
                (recommendation_id,),
            ).fetchall()
        return [self._row_to_outcome(row) for row in rows]

    def count_outcomes(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM recommendation_outcomes"
            ).fetchone()
        return int(row["count"])

    def save_evaluation(self, record: EvaluationRecord) -> bool:
        if self.get_recommendation(record.recommendation_id) is None:
            raise KeyError(f"recommendation not found: {record.recommendation_id}")
        statement = """
        INSERT INTO recommendation_evaluations (
            evaluation_id, recommendation_id, policy_version, predicted_class,
            score, highest_outcome, outcome_rank, result_class,
            prediction_correct, action_effective, evaluated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(recommendation_id) DO UPDATE SET
            policy_version = excluded.policy_version,
            predicted_class = excluded.predicted_class,
            score = excluded.score,
            highest_outcome = excluded.highest_outcome,
            outcome_rank = excluded.outcome_rank,
            result_class = excluded.result_class,
            prediction_correct = excluded.prediction_correct,
            action_effective = excluded.action_effective,
            evaluated_at = excluded.evaluated_at
        """
        with self._connect() as connection:
            connection.execute(
                statement,
                (
                    record.evaluation_id,
                    record.recommendation_id,
                    record.policy_version,
                    record.predicted_class,
                    record.score,
                    record.highest_outcome,
                    record.outcome_rank,
                    record.result_class,
                    None if record.prediction_correct is None else int(record.prediction_correct),
                    None if record.action_effective is None else int(record.action_effective),
                    record.evaluated_at,
                ),
            )
        return True

    def get_evaluation_for_recommendation(
        self, recommendation_id: str
    ) -> EvaluationRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM recommendation_evaluations WHERE recommendation_id = ?",
                (recommendation_id,),
            ).fetchone()
        return self._row_to_evaluation(row) if row else None

    def list_evaluations(self, *, limit: int = 1000) -> list[EvaluationRecord]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recommendation_evaluations ORDER BY evaluated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_evaluation(row) for row in rows]

    def count_evaluations(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM recommendation_evaluations"
            ).fetchone()
        return int(row["count"])


    def save_policy_proposal(self, record: PolicyProposalRecord) -> bool:
        statement = """
        INSERT OR IGNORE INTO policy_change_proposals (
            proposal_id, current_policy_version, proposed_policy_version,
            feature_name, current_weight, proposed_weight, direction, sample_size,
            feature_present_sample, feature_absent_sample, feature_positive_rate,
            baseline_positive_rate, effect_size, minimum_effect, rationale, status,
            created_at, reviewed_at, reviewed_by, review_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as connection:
            cursor = connection.execute(statement, (
                record.proposal_id, record.current_policy_version,
                record.proposed_policy_version, record.feature_name,
                record.current_weight, record.proposed_weight, record.direction,
                record.sample_size, record.feature_present_sample,
                record.feature_absent_sample, record.feature_positive_rate,
                record.baseline_positive_rate, record.effect_size,
                record.minimum_effect, record.rationale, record.status,
                record.created_at, record.reviewed_at, record.reviewed_by,
                record.review_reason,
            ))
            return cursor.rowcount == 1

    def get_policy_proposal(self, proposal_id: str) -> PolicyProposalRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM policy_change_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return self._row_to_policy_proposal(row) if row else None

    def list_policy_proposals(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[PolicyProposalRecord]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if status is None:
            query = "SELECT * FROM policy_change_proposals ORDER BY created_at DESC LIMIT ?"
            values = (limit,)
        else:
            query = "SELECT * FROM policy_change_proposals WHERE status = ? ORDER BY created_at DESC LIMIT ?"
            values = (status, limit)
        with self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_policy_proposal(row) for row in rows]

    def review_policy_proposal(
        self, proposal_id: str, *, status: str, reviewed_by: str,
        review_reason: str | None, reviewed_at: str
    ) -> PolicyProposalRecord:
        if status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE policy_change_proposals
                SET status = ?, reviewed_by = ?, review_reason = ?, reviewed_at = ?
                WHERE proposal_id = ?
                """,
                (status, reviewed_by, review_reason, reviewed_at, proposal_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"policy proposal not found: {proposal_id}")
        result = self.get_policy_proposal(proposal_id)
        assert result is not None
        return result

    @staticmethod
    def _row_to_recommendation(row: sqlite3.Row) -> RecommendationRecord:
        return RecommendationRecord(
            recommendation_id=row["recommendation_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            policy_version=row["policy_version"],
            score=float(row["score"]),
            predicted_class=row["predicted_class"],
            recommended_action=row["recommended_action"],
            prediction_window_days=int(row["prediction_window_days"]),
            input_snapshot=json.loads(row["input_snapshot_json"]),
            feature_contributions=json.loads(row["feature_contributions_json"]),
            source_mode=row["source_mode"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_execution(row: sqlite3.Row) -> ExecutionRecord:
        return ExecutionRecord(
            execution_id=row["execution_id"],
            recommendation_id=row["recommendation_id"],
            action_type=row["action_type"],
            status=row["status"],
            notes=row["notes"],
            external_system=row["external_system"],
            external_reference=row["external_reference"],
            performed_by=row["performed_by"],
            performed_at=row["performed_at"],
        )

    @staticmethod
    def _row_to_outcome(row: sqlite3.Row) -> OutcomeRecord:
        return OutcomeRecord(
            outcome_id=row["outcome_id"],
            recommendation_id=row["recommendation_id"],
            outcome_type=row["outcome_type"],
            outcome_value=float(row["outcome_value"]) if row["outcome_value"] is not None else None,
            source=row["source"],
            attribution_confidence=float(row["attribution_confidence"]),
            notes=row["notes"],
            observed_at=row["observed_at"],
        )

    @staticmethod
    def _row_to_evaluation(row: sqlite3.Row) -> EvaluationRecord:
        return EvaluationRecord(
            evaluation_id=row["evaluation_id"],
            recommendation_id=row["recommendation_id"],
            policy_version=row["policy_version"],
            predicted_class=row["predicted_class"],
            score=float(row["score"]),
            highest_outcome=row["highest_outcome"],
            outcome_rank=int(row["outcome_rank"]) if row["outcome_rank"] is not None else None,
            result_class=row["result_class"],
            prediction_correct=(bool(row["prediction_correct"]) if row["prediction_correct"] is not None else None),
            action_effective=(bool(row["action_effective"]) if row["action_effective"] is not None else None),
            evaluated_at=row["evaluated_at"],
        )

    @staticmethod
    def _row_to_decision(row: sqlite3.Row) -> DecisionRecord:
        return DecisionRecord(
            decision_id=row["decision_id"],
            recommendation_id=row["recommendation_id"],
            status=row["status"],
            selected_action=row["selected_action"],
            reason=row["reason"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
        )

    @staticmethod
    def _row_to_policy_proposal(row: sqlite3.Row) -> PolicyProposalRecord:
        return PolicyProposalRecord(
            proposal_id=row["proposal_id"],
            current_policy_version=row["current_policy_version"],
            proposed_policy_version=row["proposed_policy_version"],
            feature_name=row["feature_name"],
            current_weight=float(row["current_weight"]),
            proposed_weight=float(row["proposed_weight"]),
            direction=row["direction"],
            sample_size=int(row["sample_size"]),
            feature_present_sample=int(row["feature_present_sample"]),
            feature_absent_sample=int(row["feature_absent_sample"]),
            feature_positive_rate=float(row["feature_positive_rate"]),
            baseline_positive_rate=float(row["baseline_positive_rate"]),
            effect_size=float(row["effect_size"]),
            minimum_effect=float(row["minimum_effect"]),
            rationale=row["rationale"],
            status=row["status"],
            created_at=row["created_at"],
            reviewed_at=row["reviewed_at"],
            reviewed_by=row["reviewed_by"],
            review_reason=row["review_reason"],
        )
