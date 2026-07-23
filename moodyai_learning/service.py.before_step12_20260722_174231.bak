from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import RecommendationRecord, utc_now_iso
from .repository import LearningLedger


class RecommendationService:
    """Creates immutable recommendation records from scored entities."""

    def __init__(self, ledger: LearningLedger) -> None:
        self.ledger = ledger

    def record_lead_recommendation(
        self,
        *,
        lead: dict[str, Any],
        score: float,
        predicted_class: str,
        recommended_action: str,
        policy_version: str,
        feature_contributions: dict[str, float],
        source_mode: str,
        prediction_window_days: int = 14,
        created_at: str | None = None,
    ) -> tuple[RecommendationRecord, bool]:
        """Record a time-specific recommendation.

        This retains Step 1 behavior: created_at participates in the ID, so a
        caller can deliberately create a separate historical prediction.
        """
        timestamp = created_at or utc_now_iso()
        entity_id, snapshot = self._prepare_lead(lead)
        recommendation_id = self._build_recommendation_id(
            entity_type="lead",
            entity_id=entity_id,
            policy_version=policy_version,
            created_at=timestamp,
            input_snapshot=snapshot,
        )
        return self._save(
            recommendation_id=recommendation_id,
            entity_id=entity_id,
            snapshot=snapshot,
            score=score,
            predicted_class=predicted_class,
            recommended_action=recommended_action,
            policy_version=policy_version,
            feature_contributions=feature_contributions,
            source_mode=source_mode,
            prediction_window_days=prediction_window_days,
            created_at=timestamp,
        )

    def record_lead_recommendation_once(
        self,
        *,
        lead: dict[str, Any],
        score: float,
        predicted_class: str,
        recommended_action: str,
        policy_version: str,
        feature_contributions: dict[str, float],
        source_mode: str,
        prediction_window_days: int = 14,
        created_at: str | None = None,
    ) -> tuple[RecommendationRecord, bool]:
        """Record one recommendation per unique lead snapshot and policy.

        Dashboard refreshes return the same recommendation ID until one of the
        decision-relevant lead fields changes or the scoring policy changes.
        """
        timestamp = created_at or utc_now_iso()
        entity_id, snapshot = self._prepare_lead(lead)
        recommendation_id = self._build_snapshot_recommendation_id(
            entity_type="lead",
            entity_id=entity_id,
            policy_version=policy_version,
            input_snapshot=self._continuity_snapshot(snapshot),
            score=score,
            predicted_class=predicted_class,
            recommended_action=recommended_action,
            feature_contributions=feature_contributions,
        )
        return self._save(
            recommendation_id=recommendation_id,
            entity_id=entity_id,
            snapshot=snapshot,
            score=score,
            predicted_class=predicted_class,
            recommended_action=recommended_action,
            policy_version=policy_version,
            feature_contributions=feature_contributions,
            source_mode=source_mode,
            prediction_window_days=prediction_window_days,
            created_at=timestamp,
        )

    def _save(
        self,
        *,
        recommendation_id: str,
        entity_id: str,
        snapshot: dict[str, Any],
        score: float,
        predicted_class: str,
        recommended_action: str,
        policy_version: str,
        feature_contributions: dict[str, float],
        source_mode: str,
        prediction_window_days: int,
        created_at: str,
    ) -> tuple[RecommendationRecord, bool]:
        record = RecommendationRecord(
            recommendation_id=recommendation_id,
            entity_type="lead",
            entity_id=entity_id,
            policy_version=policy_version,
            score=float(score),
            predicted_class=predicted_class,
            recommended_action=recommended_action,
            prediction_window_days=prediction_window_days,
            input_snapshot=snapshot,
            feature_contributions=feature_contributions,
            source_mode=source_mode,
            created_at=created_at,
        )
        inserted = self.ledger.save_recommendation(record)
        if not inserted:
            existing = self.ledger.get_recommendation(recommendation_id)
            if existing is not None:
                return existing, False
        return record, inserted

    @classmethod
    def _prepare_lead(cls, lead: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        entity_id = str(lead.get("id") or "").strip()
        if not entity_id:
            raise ValueError("lead must include a stable id")
        return entity_id, cls._lead_snapshot(lead)

    @staticmethod
    def _lead_snapshot(lead: dict[str, Any]) -> dict[str, Any]:
        """Capture only decision-relevant fields available at prediction time."""
        return {
            "id": lead.get("id"),
            "name": lead.get("name") or lead.get("displayName"),
            "stage": lead.get("stage"),
            "source": lead.get("source"),
            "website_visits": lead.get("websiteVisits", 0),
            "last_activity": lead.get("lastActivity"),
            "created": lead.get("created"),
            "has_phone": bool(lead.get("phone") or lead.get("phones")),
            "has_email": bool(lead.get("email") or lead.get("emails")),
            "tags": lead.get("tags") or [],
        }

    @staticmethod
    def _continuity_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        """Return only fields that should create a new recommendation lifecycle.

        Volatile CRM bookkeeping fields such as ``last_activity`` and ``created``
        are deliberately excluded. A call or text updates lastActivity in FUB;
        that action must complete the current recommendation rather than create a
        new empty recommendation.
        """
        return {
            "id": snapshot.get("id"),
            "stage": snapshot.get("stage"),
            "source": snapshot.get("source"),
            "website_visits": snapshot.get("website_visits", 0),
            "has_phone": bool(snapshot.get("has_phone")),
            "has_email": bool(snapshot.get("has_email")),
            "tags": snapshot.get("tags") or [],
        }

    @staticmethod
    def _build_recommendation_id(
        *,
        entity_type: str,
        entity_id: str,
        policy_version: str,
        created_at: str,
        input_snapshot: dict[str, Any],
    ) -> str:
        payload = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "policy_version": policy_version,
            "created_at": created_at,
            "input_snapshot": input_snapshot,
        }
        return RecommendationService._hash_id(payload)

    @staticmethod
    def _build_snapshot_recommendation_id(
        *,
        entity_type: str,
        entity_id: str,
        policy_version: str,
        input_snapshot: dict[str, Any],
        score: float,
        predicted_class: str,
        recommended_action: str,
        feature_contributions: dict[str, float],
    ) -> str:
        payload = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "policy_version": policy_version,
            "input_snapshot": input_snapshot,
            "score": float(score),
            "predicted_class": predicted_class,
            "recommended_action": recommended_action,
            "feature_contributions": feature_contributions,
        }
        return RecommendationService._hash_id(payload)

    @staticmethod
    def _hash_id(payload: dict[str, Any]) -> str:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
        return f"rec_{digest}"
