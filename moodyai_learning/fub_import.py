from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .executions import ExecutionService
from .outcomes import OutcomeService

_REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS fub_sync_candidate_reviews (
    candidate_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    external_reference TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved', 'rejected')),
    import_outcome INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    reviewed_by TEXT NOT NULL DEFAULT 'Moody',
    reviewed_at TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    execution_id TEXT,
    outcome_id TEXT,
    FOREIGN KEY (recommendation_id)
        REFERENCES recommendations(recommendation_id)
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_fub_review_external
ON fub_sync_candidate_reviews(source_kind, external_reference);

CREATE INDEX IF NOT EXISTS idx_fub_review_status_time
ON fub_sync_candidate_reviews(status, reviewed_at DESC);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FUBSyncImportService:
    """Review and import FUB preview candidates into the learning ledger."""

    def __init__(self, ledger: Any, preview_service: Any) -> None:
        self.ledger = ledger
        self.preview_service = preview_service
        self.execution_service = ExecutionService(ledger)
        self.outcome_service = OutcomeService(ledger)
        self._initialize()

    @property
    def database_path(self) -> Path:
        return Path(self.ledger.database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(_REVIEW_SCHEMA)
            connection.commit()

    def list_reviews(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        values: list[Any] = []
        where = ""
        if status is not None:
            clean_status = status.strip().lower()
            if clean_status not in {"approved", "rejected"}:
                raise ValueError("status must be approved or rejected")
            where = "WHERE status = ?"
            values.append(clean_status)
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM fub_sync_candidate_reviews {where} ORDER BY reviewed_at DESC LIMIT ?",
                values,
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_review(self, candidate_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM fub_sync_candidate_reviews WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def review_candidate(
        self,
        candidate_id: str,
        *,
        status: str,
        import_outcome: bool = False,
        reason: str | None = None,
        reviewed_by: str = "Moody",
        preview_limit: int = 100,
    ) -> dict[str, Any]:
        clean_status = status.strip().lower()
        if clean_status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")

        existing = self.get_review(candidate_id)
        if existing is not None:
            return {"recorded": False, "duplicate": True, "review": existing}

        preview = self.preview_service.preview(limit=preview_limit)
        candidate = next(
            (item for item in preview.get("items", []) if item.get("candidate_id") == candidate_id),
            None,
        )
        if candidate is None:
            raise KeyError(f"FUB sync candidate not found: {candidate_id}")

        execution_id: str | None = None
        outcome_id: str | None = None

        if clean_status == "approved":
            execution_payload = candidate.get("proposed_execution")
            if not execution_payload:
                raise ValueError("approved candidate has no proposed execution")
            execution = self.execution_service.record_execution(
                recommendation_id=candidate["recommendation_id"],
                action_type=execution_payload["action_type"],
                status=execution_payload.get("status", "completed"),
                notes=execution_payload.get("notes"),
                external_system=execution_payload.get("external_system", "follow_up_boss"),
                external_reference=execution_payload.get("external_reference"),
                performed_by="Follow Up Boss sync",
                performed_at=candidate.get("observed_at"),
            )
            execution_id = execution.execution_id

            outcome_payload = candidate.get("proposed_outcome")
            if import_outcome and outcome_payload:
                outcome, _ = self.outcome_service.record_outcome_with_status(
                    recommendation_id=candidate["recommendation_id"],
                    outcome_type=outcome_payload["outcome_type"],
                    source=outcome_payload.get("source", "follow_up_boss"),
                    attribution_confidence=float(outcome_payload.get("attribution_confidence", 0.5)),
                    notes=outcome_payload.get("notes"),
                    observed_at=candidate.get("observed_at"),
                )
                outcome_id = outcome.outcome_id

        reviewed_at = _utc_now_iso()
        payload = (
            candidate_id,
            candidate["recommendation_id"],
            str(candidate["person_id"]),
            candidate["source_kind"],
            str(candidate["external_reference"]),
            clean_status,
            1 if import_outcome else 0,
            (reason or "").strip() or None,
            reviewed_by.strip() or "Moody",
            reviewed_at,
            json.dumps(candidate, sort_keys=True, default=str),
            execution_id,
            outcome_id,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO fub_sync_candidate_reviews (
                        candidate_id, recommendation_id, person_id, source_kind,
                        external_reference, status, import_outcome, reason,
                        reviewed_by, reviewed_at, candidate_json,
                        execution_id, outcome_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                connection.commit()
        except sqlite3.IntegrityError:
            existing = self.get_review(candidate_id)
            if existing is None:
                with self._connect() as connection:
                    row = connection.execute(
                        "SELECT * FROM fub_sync_candidate_reviews WHERE source_kind = ? AND external_reference = ?",
                        (candidate["source_kind"], str(candidate["external_reference"])),
                    ).fetchone()
                existing = self._row_to_dict(row) if row else None
            return {"recorded": False, "duplicate": True, "review": existing}

        review = self.get_review(candidate_id)
        return {"recorded": True, "duplicate": False, "review": review}

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "candidate_id": row["candidate_id"],
            "recommendation_id": row["recommendation_id"],
            "person_id": row["person_id"],
            "source_kind": row["source_kind"],
            "external_reference": row["external_reference"],
            "status": row["status"],
            "import_outcome": bool(row["import_outcome"]),
            "reason": row["reason"],
            "reviewed_by": row["reviewed_by"],
            "reviewed_at": row["reviewed_at"],
            "candidate": json.loads(row["candidate_json"]),
            "execution_id": row["execution_id"],
            "outcome_id": row["outcome_id"],
        }
