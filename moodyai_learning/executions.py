from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from .models import EXECUTION_STATUSES, ExecutionRecord, utc_now_iso
from .repository import LearningLedger


class ExecutionService:
    """Records immutable action-attempt events for approved recommendations."""

    def __init__(self, ledger: LearningLedger) -> None:
        self.ledger = ledger

    def record_execution(
        self,
        *,
        recommendation_id: str,
        action_type: str,
        status: str,
        notes: str | None = None,
        external_system: str | None = None,
        external_reference: str | None = None,
        performed_by: str = "Moody",
        performed_at: str | None = None,
    ) -> ExecutionRecord:
        recommendation = self.ledger.get_recommendation(recommendation_id)
        if recommendation is None:
            raise KeyError(f"recommendation not found: {recommendation_id}")

        decision = self.ledger.get_latest_decision(recommendation_id)
        if decision is None or decision.status not in {"accepted", "modified"}:
            raise ValueError(
                "recommendation must have a latest decision of accepted or modified "
                "before execution can be recorded"
            )

        clean_action_type = action_type.strip().lower()
        if not clean_action_type:
            raise ValueError("action_type is required")
        clean_status = status.strip().lower()
        if clean_status not in EXECUTION_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(EXECUTION_STATUSES))}"
            )
        timestamp = performed_at or utc_now_iso()
        payload = {
            "recommendation_id": recommendation_id,
            "action_type": clean_action_type,
            "status": clean_status,
            "notes": (notes or "").strip() or None,
            "external_system": (external_system or "").strip() or None,
            "external_reference": (external_reference or "").strip() or None,
            "performed_by": performed_by.strip() or "Moody",
            "performed_at": timestamp,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        record = ExecutionRecord(execution_id=f"exe_{digest}", **payload)
        inserted = self.ledger.save_execution(record)
        if not inserted:
            existing = self.ledger.get_execution(record.execution_id)
            if existing is not None:
                return existing
        return record

    def latest_execution_dict(self, recommendation_id: str) -> dict[str, object] | None:
        record = self.ledger.get_latest_execution(recommendation_id)
        return asdict(record) if record else None
