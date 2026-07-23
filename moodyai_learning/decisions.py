from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from .models import DECISION_STATUSES, DecisionRecord, utc_now_iso
from .repository import LearningLedger


class DecisionService:
    """Records immutable human feedback events for recommendations."""

    def __init__(self, ledger: LearningLedger) -> None:
        self.ledger = ledger

    def record_decision(
        self,
        *,
        recommendation_id: str,
        status: str,
        selected_action: str | None = None,
        reason: str | None = None,
        decided_by: str = "Moody",
        decided_at: str | None = None,
    ) -> DecisionRecord:
        clean_status = status.strip().lower()
        if clean_status not in DECISION_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(DECISION_STATUSES))}")
        timestamp = decided_at or utc_now_iso()
        payload = {
            "recommendation_id": recommendation_id,
            "status": clean_status,
            "selected_action": (selected_action or "").strip() or None,
            "reason": (reason or "").strip() or None,
            "decided_by": decided_by.strip() or "Moody",
            "decided_at": timestamp,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        record = DecisionRecord(decision_id=f"dec_{digest}", **payload)
        inserted = self.ledger.save_decision(record)
        if not inserted:
            existing = self.ledger.get_latest_decision(recommendation_id)
            if existing and existing.decision_id == record.decision_id:
                return existing
        return record

    def latest_decision_dict(self, recommendation_id: str) -> dict[str, object] | None:
        record = self.ledger.get_latest_decision(recommendation_id)
        return asdict(record) if record else None
