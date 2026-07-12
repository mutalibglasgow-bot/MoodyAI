from dotenv import load_dotenv
from openai import OpenAI
from services.followupboss import get_people, create_note
from datetime import datetime
import os
import json

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# Get leads
people = get_people(limit=25)

# Score leads
ranked = []

for person in people["people"]:

    stage = person.get("stage", "")
    tags = person.get("tags", [])
    visits = person.get("websiteVisits", 0)

    score = 0

    if stage == "Freshly Claimed":
        score += 50

    elif stage == "Consult Set":
        score += 45

    elif stage == "Sourcing Cash Offers":
        score += 40

    elif stage == "Hot Nurture":
        score += 35

    elif stage == "Warm Nurture":
        score += 25

    if visits >= 5:
        score += 20

    if "Consult Check" in tags:
        score += 15

    if "Listed" in tags:
        score += 20

    ranked.append((score, person))

# Highest score first
ranked.sort(reverse=True, key=lambda x: x[0])

report = []

report.append("MOODY AI MORNING BRIEF")
report.append("=" * 50)
report.append(f"Generated: {datetime.now()}")
report.append("")

# Analyze top leads
for score, person in ranked[:10]:

    lead_summary = {
        "name": person.get("name"),
        "stage": person.get("stage"),
        "type": person.get("type"),
        "source": person.get("source"),
        "tags": person.get("tags"),
        "websiteVisits": person.get("websiteVisits"),
        "lastActivity": person.get("lastActivity"),
        "city": (
            person.get("addresses", [{}])[0].get("city")
            if person.get("addresses")
            else None
        ),
    }

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"""
You are Moody Glasgow's AI real estate assistant.

Analyze this lead:

{json.dumps(lead_summary, indent=2)}

Return:

Priority:
Reason:
Recommended Action:
Suggested Text:
"""
    )

    ai_analysis = response.output_text

    # Save note to Follow Up Boss
    try:
        create_note(
            person_id=person["id"],
            subject="AI Morning Brief",
            body=ai_analysis
        )
        note_status = "✓ Note saved to Follow Up Boss"

    except Exception as e:
        note_status = f"✗ Failed to save note: {e}"

    report.append("-" * 50)
    report.append(f"Lead: {lead_summary['name']}")
    report.append(f"Score: {score}")
    report.append(note_status)
    report.append("")
    report.append(ai_analysis)
    report.append("")

# Save report
os.makedirs("data", exist_ok=True)

filename = (
    f"data/morning_brief_"
    f"{datetime.now().strftime('%Y-%m-%d')}.txt"
)

with open(filename, "w") as file:
    file.write("\n".join(report))

print("\n".join(report))
print(f"\nReport saved to: {filename}")
