from dotenv import load_dotenv
import os
import requests

# Load .env automatically
load_dotenv()

API_KEY = os.getenv("FOLLOWUPBOSS_API_KEY")

BASE_URL = "https://api.followupboss.com/v1"


def get_people(limit=10):
    if not API_KEY:
        raise ValueError(
            "FOLLOWUPBOSS_API_KEY not found in .env"
        )

    response = requests.get(
        f"{BASE_URL}/people",
        auth=(API_KEY, ""),
        params={"limit": limit}
    )

    response.raise_for_status()

    return response.json()

def create_note(person_id, subject, body):
    if not API_KEY:
        raise ValueError("FOLLOWUPBOSS_API_KEY not found in .env")

    response = requests.post(
        f"{BASE_URL}/notes",
        auth=(API_KEY, ""),
        json={
            "personId": person_id,
            "subject": subject,
            "body": body,
            "isHtml": False
        }
    )

    response.raise_for_status()
    return response.json()
def create_task(person_id, description, due_date=None):
    if not API_KEY:
        raise ValueError("FOLLOWUPBOSS_API_KEY not found in .env")

    payload = {
        "personId": person_id,
        "description": description,
    }

    if due_date:
        payload["dueDate"] = due_date

    response = requests.post(
        f"{BASE_URL}/tasks",
        auth=(API_KEY, ""),
        json=payload
    )

    response.raise_for_status()
    return response.json()
