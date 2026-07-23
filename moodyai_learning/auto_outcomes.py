from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .outcomes import OutcomeService

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fub_auto_outcome_log (
    person_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    signal_value TEXT NOT NULL,
    external_reference TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    outcome_type TEXT,
    outcome_id TEXT,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (signal_type, external_reference)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _stage_outcome(stage: Any) -> str | None:
    value = _normalize(stage)
    if not value:
        return None
    rules = (
        (("closed", "closed won", "sold"), "closed"),
        (("under contract", "pending contract", "pending sale"), "under_contract"),
        (("active client", "signed client", "buyer agreement signed", "listing agreement signed"), "active_client"),
        (("appointment booked", "appointment set", "consultation set", "consult set"), "appointment_booked"),
    )
    for labels, outcome in rules:
        if value in labels:
            return outcome
    return None


def _person_from_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    person = payload.get("person")
    if isinstance(person, dict):
        return person
    if "id" in payload:
        return payload
    return None


class FUBAutoOutcomeService:
    """Record only high-confidence outcomes already visible in Follow Up Boss.

    Current stage is compared with the stage snapshot that existed when the
    recommendation was made. Unchanged stages create no outcome. Only a small,
    explicit set of strong stage labels is automated.
    """

    def __init__(self, ledger: Any, *, get_person: Callable[..., Any]) -> None:
        self.ledger = ledger
        self.get_person = get_person
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

    def _seen(self, signal_type: str, external_reference: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM fub_auto_outcome_log WHERE signal_type=? AND external_reference=?",
                (signal_type, external_reference),
            ).fetchone()
        return row is not None

    def _log(
        self,
        *,
        person_id: str,
        signal_type: str,
        signal_value: str,
        external_reference: str,
        recommendation_id: str,
        status: str,
        outcome_type: str | None,
        outcome_id: str | None,
        details: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO fub_auto_outcome_log (
                    person_id, signal_type, signal_value, external_reference,
                    recommendation_id, outcome_type, outcome_id, status,
                    details_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    person_id,
                    signal_type,
                    signal_value,
                    external_reference,
                    recommendation_id,
                    outcome_type,
                    outcome_id,
                    status,
                    json.dumps(details, sort_keys=True, default=str),
                    _now(),
                ),
            )
            connection.commit()

    def sync(self, *, limit: int = 100) -> dict[str, Any]:
        recommendations = self.ledger.list_recommendations(entity_type="lead", limit=limit)

        # A stage outcome belongs to the latest recommendation for each lead that
        # has a completed action. This keeps the result attached to the real work.
        by_person: dict[str, Any] = {}
        for recommendation in recommendations:
            if recommendation.entity_id in by_person:
                continue
            completed = any(
                execution.status == "completed"
                for execution in self.ledger.list_executions(recommendation.recommendation_id)
            )
            if completed:
                by_person[recommendation.entity_id] = recommendation

        imported: list[dict[str, Any]] = []
        ignored = 0
        errors: list[dict[str, Any]] = []

        for person_id, recommendation in by_person.items():
            try:
                person = _person_from_payload(self.get_person(person_id=int(person_id)))
                if person is None:
                    raise ValueError("Unexpected Follow Up Boss person response")

                current_stage = str(person.get("stage") or "").strip()
                baseline_stage = str(recommendation.input_snapshot.get("stage") or "").strip()
                outcome_type = _stage_outcome(current_stage)
                observed_at = str(person.get("updated") or person.get("lastActivity") or _now())
                external_reference = f"{person_id}:{_normalize(current_stage)}:{observed_at}"

                if self._seen("stage", external_reference):
                    continue

                details = {
                    "current_stage": current_stage,
                    "baseline_stage": baseline_stage,
                    "person_updated": observed_at,
                }

                if not outcome_type or _normalize(current_stage) == _normalize(baseline_stage):
                    self._log(
                        person_id=person_id,
                        signal_type="stage",
                        signal_value=current_stage,
                        external_reference=external_reference,
                        recommendation_id=recommendation.recommendation_id,
                        status="ignored",
                        outcome_type=None,
                        outcome_id=None,
                        details=details,
                    )
                    ignored += 1
                    continue

                outcome, inserted = self.outcomes.record_outcome_with_status(
                    recommendation_id=recommendation.recommendation_id,
                    outcome_type=outcome_type,
                    source="follow_up_boss",
                    attribution_confidence=0.95,
                    notes=f"Automatically mapped from FUB stage change: {baseline_stage or '(none)'} → {current_stage}",
                    observed_at=observed_at,
                )
                self._log(
                    person_id=person_id,
                    signal_type="stage",
                    signal_value=current_stage,
                    external_reference=external_reference,
                    recommendation_id=recommendation.recommendation_id,
                    status="imported" if inserted else "duplicate",
                    outcome_type=outcome_type,
                    outcome_id=outcome.outcome_id,
                    details=details,
                )
                if inserted:
                    imported.append(
                        {
                            "person_id": person_id,
                            "recommendation_id": recommendation.recommendation_id,
                            "outcome_type": outcome_type,
                            "outcome_id": outcome.outcome_id,
                            "source": "stage",
                            "observed_at": observed_at,
                        }
                    )
            except Exception as exc:
                errors.append(
                    {
                        "person_id": person_id,
                        "recommendation_id": recommendation.recommendation_id,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }
                )

        return {
            "mode": "automatic_fub_outcomes",
            "manual_entry_required": False,
            "people_scanned": len(by_person),
            "imported_count": len(imported),
            "ignored_count": ignored,
            "error_count": len(errors),
            "imported": imported,
            "errors": errors,
        }
