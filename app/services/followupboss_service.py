import requests

from app.core.settings import FOLLOWUPBOSS_KEY

BASE_URL = "https://api.followupboss.com/v1"


class FollowUpBossService:

    def __init__(self):
        self.auth = (FOLLOWUPBOSS_KEY, "")

    def get_latest_leads(self, limit=5):
        response = requests.get(
            f"{BASE_URL}/people",
            params={"limit": limit},
            auth=self.auth,
            headers={"Accept": "application/json"},
        )

        response.raise_for_status()
        data = response.json()

        clean_people = []

        for person in data.get("people", []):
            emails = person.get("emails", [])
            phones = person.get("phones", [])

            clean_people.append({
                "id": person.get("id"),
                "name": person.get("displayName"),
                "email": emails[0].get("value") if emails else None,
                "phone": phones[0].get("value") if phones else None,
                "stage": person.get("stage"),
                "source": person.get("source"),
                "created": person.get("created"),
            })

        return clean_people

    def get_person(self, person_id):
        response = requests.get(
            f"{BASE_URL}/people/{person_id}",
            auth=self.auth,
            headers={"Accept": "application/json"},
        )

        response.raise_for_status()
        return response.json()