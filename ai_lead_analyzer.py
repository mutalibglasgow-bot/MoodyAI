from dotenv import load_dotenv
from openai import OpenAI
from services.followupboss import get_people
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

people = get_people(limit=10)

for person in people["people"]:
    lead_summary = {
        "name": person.get("name"),
        "stage": person.get("stage"),
        "type": person.get("type"),
        "source": person.get("source"),
        "tags": person.get("tags"),
        "websiteVisits": person.get("websiteVisits"),
        "lastActivity": person.get("lastActivity"),
        "city": person.get("addresses", [{}])[0].get("city") if person.get("addresses") else None,
    }

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"""
You are Moody Glasgow's real estate sales assistant.

Analyze this Follow Up Boss lead:

{json.dumps(lead_summary, indent=2)}

Return:
- Priority: High, Medium, or Low
- Reason
- Recommended next action
- Suggested text message under 75 words
"""
    )

    print("\n====================")
    print(f"Lead: {lead_summary['name']}")
    print(response.output_text)
