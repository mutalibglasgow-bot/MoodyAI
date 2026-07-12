import os
import requests
from datetime import datetime
from dotenv import load_dotenv

from agents.sensors.base_sensor import Signal

load_dotenv()

FUB_API_KEY = os.getenv("FUB_API_KEY")
BASE_URL = "https://api.followupboss.com/v1"


def fub_get(endpoint, params=None):
    if not FUB_API_KEY:
        raise ValueError("Missing FUB_API_KEY in .env")

    response = requests.get(
        f"{BASE_URL}{endpoint}",
        auth=(FUB_API_KEY, ""),
        params=params or {},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


class FollowUpBossSensor:
    name = "Follow Up Boss Sensor"

    def collect(self):
        people_data = fub_get("/people", params={"limit": 25})
        people = people_data.get("people", [])

        signals = []

        hot_people = []

        for person in people:
            name = person.get("name", "Unknown")
            stage = person.get("stage", "")
            source = person.get("source", "")
            last_activity = person.get("lastActivity", "")
            price = person.get("price")

            text = f"{name} {stage} {source}".lower()

            score = 0

            if "cash" in text:
                score += 30
            if "seller" in text:
                score += 25
            if "listing" in text:
                score += 25
            if "consult" in text:
                score += 20
            if "bsw" in text or "baylor" in text or "physician" in text:
                score += 20
            if "hot" in text:
                score += 20
            if last_activity:
                score += 10
            if price:
                score += 10

            if score >= 35:
                hot_people.append({
                    "name": name,
                    "stage": stage,
                    "source": source,
                    "last_activity": last_activity,
                    "price": price,
                    "score": score,
                })

        if hot_people:
            names = ", ".join([p["name"] for p in hot_people[:5]])

            signals.append(
                Signal(
                    signal_name="High-Intent Follow Up Boss Leads Detected",
                    source="Follow Up Boss API",
                    signal_type="Lead Activity",
                    summary=f"Detected {len(hot_people)} high-intent leads. Top leads: {names}.",
                    why_it_matters=(
                        "These leads may represent immediate revenue opportunities. "
                        "They should be prioritized because they are already in Moody's pipeline."
                    ),
                    affected_opportunities=[
                        "Local Home Sellers",
                        "Move-Up Buyers",
                        "High-Equity Homeowners",
                        "BSW / Physician Relocation",
                    ],
                    likely_client_types=[
                        "Motivated sellers",
                        "Cash offer leads",
                        "Relocation buyers",
                        "High-intent prospects",
                    ],
                    future_questions_people_will_ask=[
                        "What is my home worth?",
                        "Should I sell now?",
                        "What are my options?",
                        "Who can help me move quickly?",
                    ],
                    time_horizon="Immediate",
                    confidence=0.9,
                    business_value_score=95,
                    generated_at=datetime.now().isoformat(),
                )
            )

        return signals