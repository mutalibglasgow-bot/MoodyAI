from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from .models import OUTCOME_TYPES, OutcomeRecord, utc_now_iso
from .repository import LearningLedger


class OutcomeService:
    """Records observable business results linked to executed recommendations."""

    def __init__(self, ledger: LearningLedger) -> None:
        self.ledger = ledger

    def record_outcome_with_status(
        self,
        *,
        recommendation_id: str,
        outcome_type: str,
        source: str = "manual",
        outcome_value: float | None = None,
        attribution_confidence: float = 1.0,
        notes: str | None = None,
        observed_at: str | None = None,
    ) -> tuple[OutcomeRecord, bool]:
        recommendation = self.ledger.get_recommendation(recommendation_id)
        if recommendation is None:
            raise KeyError(f"recommendation not found: {recommendation_id}")

        executions = self.ledger.list_executions(recommendation_id)
        if not any(item.status == "completed" for item in executions):
            raise ValueError(
                "recommendation must have at least one completed execution "
                "before an outcome can be recorded"
            )

        clean_type = outcome_type.strip().lower()
        if clean_type not in OUTCOME_TYPES:
            raise ValueError(f"outcome_type must be one of: {', '.join(sorted(OUTCOME_TYPES))}")
        clean_source = source.strip().lower()
        if not clean_source:
            raise ValueError("source is required")
        if not 0 <= attribution_confidence <= 1:
            raise ValueError("attribution_confidence must be between 0 and 1")

        clean_notes = (notes or "").strip() or None
        # The semantic key intentionally excludes observed_at. Repeating the same POST
        # therefore returns the existing record instead of polluting the ledger.
        semantic_payload = {
            "recommendation_id": recommendation_id,
            "outcome_type": clean_type,
            "outcome_value": outcome_value,
            "source": clean_source,
            "attribution_confidence": float(attribution_confidence),
            "notes": clean_notes,
        }
        digest = hashlib.sha256(
            json.dumps(semantic_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
        outcome_id = f"out_{digest}"
        existing = self.ledger.get_outcome(outcome_id)
        if existing is not None:
            return existing, False

        record = OutcomeRecord(
            outcome_id=outcome_id,
            observed_at=observed_at or utc_now_iso(),
            **semantic_payload,
        )
        inserted = self.ledger.save_outcome(record)
        if not inserted:
            existing = self.ledger.get_outcome(record.outcome_id)
            if existing is not None:
                return existing, False
        return record, inserted

    def record_outcome(self, **kwargs: object) -> OutcomeRecord:
        record, _ = self.record_outcome_with_status(**kwargs)
        return record

    def latest_outcome_dict(self, recommendation_id: str) -> dict[str, object] | None:
        record = self.ledger.get_latest_outcome(recommendation_id)
        return asdict(record) if record else None
