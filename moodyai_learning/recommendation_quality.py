from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _parse_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stage_text(person: dict[str, Any]) -> str:
    return str(person.get("stage") or "New").strip().lower()


def build_specific_action(person: dict[str, Any], predicted_class: str) -> str:
    """Return a stable, plain-language next action from CRM facts."""
    name = str(person.get("name") or person.get("displayName") or "this lead").strip()
    first_name = name.split()[0] if name else "this lead"
    stage = _stage_text(person)
    source = str(person.get("source") or "").lower()
    has_phone = bool(person.get("phone") or person.get("phones"))
    has_email = bool(person.get("email") or person.get("emails"))

    if any(token in stage for token in ("consult", "appointment", "showing")):
        return f"Call {first_name} to confirm the appointment, timing, and the one decision they need help making next."
    if any(token in stage for token in ("active client", "active buyer", "active seller")):
        return f"Contact {first_name} with one concrete update and confirm the next milestone."
    if any(token in stage for token in ("under contract", "pending", "escrow")):
        return f"Send {first_name} a transaction update and confirm the next deadline."
    if any(token in stage for token in ("closed", "past client")):
        return f"Send {first_name} a brief check-in and ask whether anyone they know needs real-estate help."
    if "seller" in source or "seller" in stage:
        if has_phone:
            return f"Call {first_name} and confirm selling timing, property condition, and the outcome they want."
        return f"Email {first_name} three focused questions about selling timing, property condition, and desired outcome."
    if any(token in source for token in ("buyer", "realtor.com", "zillow")) or "buyer" in stage:
        if has_phone:
            return f"Call {first_name} and ask what changed in the search, target timing, and must-have criteria."
        return f"Email {first_name} three matched options and ask which best reflects what they need now."
    if predicted_class.lower() in {"hot", "high"} and has_phone:
        return f"Call {first_name} today and ask the single most important question blocking their next move."
    if has_phone:
        return f"Send {first_name} a personal text, then call if there is no reply."
    if has_email:
        return f"Email {first_name} one useful, specific offer of help and ask a direct timing question."
    return f"Review {first_name}'s record and add valid contact information before taking further action."


def build_why_now(person: dict[str, Any], score: int, predicted_class: str) -> str:
    stage = str(person.get("stage") or "New")
    source = str(person.get("source") or "Unknown source")
    visits = int(person.get("websiteVisits") or 0)
    activity = person.get("lastActivity") or person.get("created")
    parts = [f"{predicted_class} priority with a score of {score}", f"currently in {stage}"]
    if visits > 0:
        parts.append(f"{visits} recorded website visit{'s' if visits != 1 else ''}")
    if activity:
        parts.append("recent CRM activity is present")
    parts.append(f"originated from {source}")
    return "; ".join(parts) + "."


@dataclass(frozen=True, slots=True)
class AttentionState:
    needs_attention: bool
    workflow_state: str
    suppression_reason: str | None


def determine_attention_state(
    *,
    recommendation_created_at: str,
    last_activity: Any,
    execution: Any | None,
    outcome: Any | None,
    evaluation: Any | None,
    recent_activity_grace_minutes: int = 10,
) -> AttentionState:
    """Prevent duplicate work while preserving genuinely unresolved outcomes."""
    if outcome is not None or evaluation is not None:
        return AttentionState(False, "resolved", "A result has already been recorded.")
    if execution is not None:
        return AttentionState(True, "awaiting_outcome", None)

    created = _parse_time(recommendation_created_at)
    activity = _parse_time(last_activity)
    if created and activity:
        delta_seconds = (activity - created).total_seconds()
        if delta_seconds > recent_activity_grace_minutes * 60:
            return AttentionState(
                False,
                "recent_activity_detected",
                "Follow Up Boss shows activity after this recommendation; waiting for sync attribution before recommending duplicate work.",
            )
    return AttentionState(True, "action_needed", None)
