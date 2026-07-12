from dotenv import load_dotenv
from openai import OpenAI
from services.followupboss import get_people
from datetime import datetime
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

people = get_people(limit=25)

report = []

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

Return this exact format:

Priority:
Reason:
Recommended Action:
Suggested Text:
"""
    )

    report.append(f"""
====================
Lead: {lead_summary['name']}
Stage: {lead_summary['stage']}
City: {lead_summary['city']}
Visits: {lead_summary['websiteVisits']}

{response.output_text}
""")

today = datetime.now().strftime("%Y-%m-%d")
filename = f"data/daily_lead_report_{today}.txt"

os.makedirs("data", exist_ok=True)

with open(filename, "w") as file:
    file.write("\n".join(report))

print(f"Daily lead report saved to: {filename}")
