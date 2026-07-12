from dotenv import load_dotenv

load_dotenv()

from services.followupboss import get_people

people = get_people(limit=10)

for person in people["people"]:

    name = person.get("name", "Unknown")
    stage = person.get("stage", "")
    tags = person.get("tags", [])
    website_visits = person.get("websiteVisits", 0)

    priority = "Low"

    if stage in ["Freshly Claimed", "Consult Set"]:
        priority = "High"
    elif website_visits >= 5:
        priority = "Medium"

    print("\n----------------")
    print(f"Name: {name}")
    print(f"Stage: {stage}")
    print(f"Visits: {website_visits}")
    print(f"Tags: {tags}")
    print(f"Priority: {priority}")
