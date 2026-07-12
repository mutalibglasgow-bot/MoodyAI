from services.followupboss import get_people

people = get_people(limit=25)

ranked = []

for person in people["people"]:
    name = person.get("name", "Unknown")
    stage = person.get("stage", "")
    tags = person.get("tags", [])
    visits = person.get("websiteVisits", 0)
    last_activity = person.get("lastActivity", "")
    city = person.get("addresses", [{}])[0].get("city") if person.get("addresses") else ""

    score = 0

    if stage in ["Freshly Claimed", "Consult Set", "Sourcing Cash Offers"]:
        score += 40

    if visits >= 5:
        score += 25

    if "Consult Check" in tags:
        score += 20

    if "Listed" in tags:
        score += 20

    if city in ["Temple", "Belton", "Harker Heights", "Killeen"]:
        score += 10

    ranked.append({
        "score": score,
        "name": name,
        "stage": stage,
        "city": city,
        "visits": visits,
        "tags": tags,
        "last_activity": last_activity,
    })

ranked.sort(key=lambda x: x["score"], reverse=True)

print("\nTODAY'S PRIORITY LEADS\n")

for lead in ranked[:10]:
    print("--------------------")
    print(f"Score: {lead['score']}")
    print(f"Name: {lead['name']}")
    print(f"Stage: {lead['stage']}")
    print(f"City: {lead['city']}")
    print(f"Visits: {lead['visits']}")
    print(f"Tags: {lead['tags']}")
    print(f"Last Activity: {lead['last_activity']}")
