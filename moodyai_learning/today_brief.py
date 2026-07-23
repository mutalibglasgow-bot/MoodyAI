from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def build_today_brief(leads_payload: dict[str, Any], *, max_items: int = 5) -> dict[str, Any]:
    """Turn the current actionable queue into a restrained daily operating brief."""
    if max_items < 1:
        raise ValueError("max_items must be at least 1")

    raw_items = leads_payload.get("items", []) if isinstance(leads_payload, dict) else []
    items = [item for item in raw_items if isinstance(item, dict) and item.get("needs_attention", True)]
    items.sort(key=lambda item: _integer(item.get("score")), reverse=True)
    selected = items[:max_items]

    action_needed = [item for item in selected if item.get("workflow_state") == "action_needed"]
    awaiting_outcome = [item for item in selected if item.get("workflow_state") == "awaiting_outcome"]
    hot = [item for item in selected if str(item.get("temperature", "")).upper() in {"HOT", "HIGH"}]

    if not selected:
        headline = "Nothing needs your attention right now."
        guidance = "MoodyAI is still watching Follow Up Boss in the background."
    elif action_needed:
        headline = f"{len(action_needed)} lead{'s' if len(action_needed) != 1 else ''} need action today."
        guidance = "Start with the first lead. The list is already ranked by urgency."
    else:
        headline = f"{len(awaiting_outcome)} recent action{'s' if len(awaiting_outcome) != 1 else ''} need a result."
        guidance = "Only confirm an outcome when Follow Up Boss cannot determine it automatically."

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": leads_payload.get("mode", "unknown") if isinstance(leads_payload, dict) else "unknown",
        "headline": headline,
        "guidance": guidance,
        "counts": {
            "needs_action": len(action_needed),
            "awaiting_outcome": len(awaiting_outcome),
            "high_priority": len(hot),
            "shown": len(selected),
            "suppressed": _integer(leads_payload.get("suppressed_count", 0)) if isinstance(leads_payload, dict) else 0,
        },
        "items": selected,
    }
