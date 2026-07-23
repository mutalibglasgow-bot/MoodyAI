from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .decisions import DecisionService
from .executions import ExecutionService
from .outcomes import OutcomeService

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fub_auto_sync_log (
    source_kind TEXT NOT NULL,
    external_reference TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    status TEXT NOT NULL,
    action TEXT,
    execution_id TEXT,
    outcome_id TEXT,
    details_json TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (source_kind, external_reference)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FUBAutoSyncService:
    """Automatically records clear FUB activity with no duplicate user entry.

    A detected outbound action is treated as implicit acceptance of the related
    recommendation. Ambiguous behavioral events are ignored rather than shown
    as extra work. Clear outcomes are recorded only when the evidence is strong.
    """

    def __init__(self, ledger: Any, preview_service: Any) -> None:
        self.ledger = ledger
        self.preview_service = preview_service
        self.decisions = DecisionService(ledger)
        self.executions = ExecutionService(ledger)
        self.outcomes = OutcomeService(ledger)
        self._initialize()

    @property
    def database_path(self) -> Path:
        return Path(self.ledger.database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            connection.commit()

    def _already_seen(self, source_kind: str, external_reference: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM fub_auto_sync_log WHERE source_kind=? AND external_reference=?",
                (source_kind, external_reference),
            ).fetchone()
        return row is not None

    def _log(
        self,
        candidate: dict[str, Any],
        *,
        status: str,
        action: str | None = None,
        execution_id: str | None = None,
        outcome_id: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO fub_auto_sync_log (
                    source_kind, external_reference, recommendation_id, status,
                    action, execution_id, outcome_id, details_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate["source_kind"],
                    str(candidate["external_reference"]),
                    candidate["recommendation_id"],
                    status,
                    action,
                    execution_id,
                    outcome_id,
                    json.dumps(candidate, sort_keys=True, default=str),
                    _now(),
                ),
            )
            connection.commit()

    def sync(self, *, limit: int = 50) -> dict[str, Any]:
        preview = self.preview_service.preview(limit=limit)
        imported: list[dict[str, Any]] = []
        ignored = 0
        errors: list[dict[str, Any]] = []

        for candidate in preview.get("items", []):
            kind = str(candidate.get("source_kind") or "")
            ref = str(candidate.get("external_reference") or "")
            if not kind or not ref or self._already_seen(kind, ref):
                continue

            execution_payload = candidate.get("proposed_execution")
            outcome_payload = candidate.get("proposed_outcome")
            recommendation_id = candidate["recommendation_id"]
            raw = candidate.get("raw_summary") or {}
            incoming = bool(raw.get("isIncoming"))

            try:
                execution_id = None
                outcome_id = None
                action_label = None

                # Outbound calls/texts are clear actions. Acting in FUB is itself
                # evidence that the recommendation was accepted.
                clear_outbound_action = bool(execution_payload) and not incoming and kind in {"call", "text"}
                if clear_outbound_action:
                    decision = self.ledger.get_latest_decision(recommendation_id)
                    if decision is None or decision.status not in {"accepted", "modified"}:
                        self.decisions.record_decision(
                            recommendation_id=recommendation_id,
                            status="accepted",
                            selected_action=execution_payload.get("action_type"),
                            reason="Action was detected in Follow Up Boss; no duplicate confirmation required.",
                            decided_by="MoodyAI FUB sync",
                            decided_at=candidate.get("observed_at"),
                        )

                    execution = self.executions.record_execution(
                        recommendation_id=recommendation_id,
                        action_type=execution_payload["action_type"],
                        status=execution_payload.get("status", "completed"),
                        notes=execution_payload.get("notes"),
                        external_system="follow_up_boss",
                        external_reference=execution_payload.get("external_reference"),
                        performed_by="Follow Up Boss sync",
                        performed_at=candidate.get("observed_at"),
                    )
                    execution_id = execution.execution_id
                    action_label = execution.action_type

                    # Only import outcomes when FUB supplies a clear, structured result.
                    if outcome_payload and float(candidate.get("match_confidence") or 0) >= 0.85:
                        outcome, _ = self.outcomes.record_outcome_with_status(
                            recommendation_id=recommendation_id,
                            outcome_type=outcome_payload["outcome_type"],
                            source="follow_up_boss",
                            attribution_confidence=float(outcome_payload.get("attribution_confidence", 0.8)),
                            notes=outcome_payload.get("notes"),
                            observed_at=candidate.get("observed_at"),
                        )
                        outcome_id = outcome.outcome_id

                    self._log(
                        candidate,
                        status="imported",
                        action=action_label,
                        execution_id=execution_id,
                        outcome_id=outcome_id,
                    )
                    imported.append(
                        {
                            "recommendation_id": recommendation_id,
                            "activity": action_label,
                            "observed_at": candidate.get("observed_at"),
                            "execution_id": execution_id,
                            "outcome_id": outcome_id,
                        }
                    )
                    continue

                # Incoming messages can be a clear response, but only attach them
                # when the recommendation already has a completed action.
                if incoming and outcome_payload and float(candidate.get("match_confidence") or 0) >= 0.9:
                    completed = any(
                        item.status == "completed"
                        for item in self.ledger.list_executions(recommendation_id)
                    )
                    if completed:
                        outcome, _ = self.outcomes.record_outcome_with_status(
                            recommendation_id=recommendation_id,
                            outcome_type=outcome_payload["outcome_type"],
                            source="follow_up_boss",
                            attribution_confidence=float(outcome_payload.get("attribution_confidence", 0.9)),
                            notes=outcome_payload.get("notes"),
                            observed_at=candidate.get("observed_at"),
                        )
                        outcome_id = outcome.outcome_id
                        self._log(candidate, status="imported", action="response", outcome_id=outcome_id)
                        imported.append(
                            {
                                "recommendation_id": recommendation_id,
                                "activity": "response",
                                "observed_at": candidate.get("observed_at"),
                                "execution_id": None,
                                "outcome_id": outcome_id,
                            }
                        )
                        continue

                # Behavioral events and uncertain matches should not create work.
                self._log(candidate, status="ignored", action=None)
                ignored += 1
            except Exception as exc:  # keep the rest of the sync useful
                errors.append(
                    {
                        "candidate_id": candidate.get("candidate_id"),
                        "recommendation_id": recommendation_id,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }
                )

        return {
            "mode": "automatic_fub_sync",
            "duplicate_entry_required": False,
            "imported_count": len(imported),
            "ignored_count": ignored,
            "error_count": len(errors),
            "imported": imported,
            "errors": errors,
            "source_errors": preview.get("errors", []),
        }
