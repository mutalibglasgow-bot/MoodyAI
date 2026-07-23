from dotenv import load_dotenv
import os
from typing import Any

import requests

load_dotenv()

API_KEY = os.getenv("FOLLOWUPBOSS_API_KEY")
BASE_URL = "https://api.followupboss.com/v1"


def _get(resource: str, *, params: dict[str, Any]) -> dict[str, Any]:
    if not API_KEY:
        raise ValueError("FOLLOWUPBOSS_API_KEY not found in .env")
    response = requests.get(
        f"{BASE_URL}/{resource}",
        auth=(API_KEY, ""),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected Follow Up Boss response for {resource}")
    return payload


def get_people(limit: int = 10) -> dict[str, Any]:
    return _get("people", params={"limit": limit})


def get_person(*, person_id: int) -> dict[str, Any]:
    return _get(f"people/{person_id}", params={})


def get_calls(*, person_id: int, limit: int = 100) -> dict[str, Any]:
    return _get("calls", params={"personId": person_id, "limit": min(limit, 100)})


def get_text_messages(*, person_id: int, limit: int = 100) -> dict[str, Any]:
    return _get("textMessages", params={"personId": person_id, "limit": min(limit, 100)})


def get_events(*, person_id: int, limit: int = 100) -> dict[str, Any]:
    return _get("events", params={"personId": person_id, "limit": min(limit, 100)})


def create_note(person_id, subject, body):
    if not API_KEY:
        raise ValueError("FOLLOWUPBOSS_API_KEY not found in .env")
    response = requests.post(
        f"{BASE_URL}/notes",
        auth=(API_KEY, ""),
        json={"personId": person_id, "subject": subject, "body": body, "isHtml": False},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def create_task(person_id, description, due_date=None):
    if not API_KEY:
        raise ValueError("FOLLOWUPBOSS_API_KEY not found in .env")
    payload = {"personId": person_id, "description": description}
    if due_date:
        payload["dueDate"] = due_date
    response = requests.post(
        f"{BASE_URL}/tasks",
        auth=(API_KEY, ""),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
