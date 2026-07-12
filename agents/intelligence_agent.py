TOPIC_RULES = {
    "BSW / Physician Relocation": [
        "bsw", "baylor scott", "white", "physician", "resident",
        "medical", "hospital", "doctor", "baylor"
    ],
    "Fort Cavazos / Military PCS": [
        "fort cavazos", "fort hood", "pcs", "military", "va loan",
        "killeen", "harker heights"
    ],
    "Belton Sellers": [
        "belton", "home value", "sell", "fsbo", "realtor",
        "property tax", "tax rate"
    ],
    "Temple Buyers": [
        "temple", "homes for sale", "neighborhoods", "new homes",
        "cost of living"
    ],
    "Lake / Luxury": [
        "lake belton", "waterfront", "luxury", "acreage", "land"
    ],
}


def classify_topic(text):
    text = (text or "").lower()

    for topic, keywords in TOPIC_RULES.items():
        for keyword in keywords:
            if keyword in text:
                return topic

    return "General Real Estate"


def score_search_console_item(item):
    clicks = item.get("clicks", 0)
    impressions = item.get("impressions", 0)
    position = item.get("position", 99)
    ctr = item.get("ctr", 0)

    score = 0

    if 5 <= position <= 15:
        score += 45
    elif 15 < position <= 30:
        score += 25
    elif position < 5:
        score += 20

    if impressions >= 100:
        score += 30
    elif impressions >= 50:
        score += 25
    elif impressions >= 10:
        score += 15

    if clicks > 0:
        score += 20

    if ctr >= 0.03:
        score += 15

    return score


def score_lead(person):
    score = 0

    stage = person.get("stage", "")
    tags = person.get("tags", [])
    visits = person.get("websiteVisits", 0)

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
        score += 25
    elif visits >= 2:
        score += 10

    if "Consult Check" in tags:
        score += 15

    if "Listed" in tags:
        score += 20

    return score


def recommend_seo_action(topic, item):
    position = item.get("position", 99)

    if topic == "BSW / Physician Relocation":
        return (
            "Create or improve physician relocation content. Add FAQ schema, "
            "neighborhood comparison, commute times to BSW, resident housing guidance, "
            "and a matching short video."
        )

    if topic == "Fort Cavazos / Military PCS":
        return (
            "Create PCS relocation content focused on VA buyers, quick move timelines, "
            "Fort Cavazos commute zones, schools, and Harker Heights/Killeen/Belton options."
        )

    if topic == "Belton Sellers":
        return (
            "Create seller content around home value, FSBO comparison, cash offer alternatives, "
            "net proceeds, and current Belton market conditions."
        )

    if topic == "Lake / Luxury":
        return (
            "Create lifestyle content around Lake Belton, acreage, waterfront homes, "
            "luxury neighborhoods, and move-up buyer intent."
        )

    if position <= 15:
        return (
            "This is close to page one. Improve title, meta description, internal links, "
            "FAQ section, and add a stronger call to action."
        )

    return "Monitor this topic and build supporting content if impressions increase."


def recommend_lead_action(lead):
    first_name = lead.get("firstName") or lead.get("name", "there").split(" ")[0]
    stage = lead.get("stage", "")
    visits = lead.get("websiteVisits", 0)

    if visits >= 5:
        return f"Call or text {first_name} today. High website activity suggests active intent."

    if stage in ["Freshly Claimed", "Consult Set", "Sourcing Cash Offers"]:
        return f"Follow up with {first_name} today with a clear next step."

    return f"Send {first_name} a light nurture message."


def build_intelligence(search_items, leads):
    opportunities = []

    for item in search_items:
        label = item.get("label", "")
        topic = classify_topic(label)
        score = score_search_console_item(item)

        opportunities.append({
            "type": "SEO Opportunity",
            "topic": topic,
            "label": label,
            "score": score,
            "reason": (
                f"Position {round(item.get('position', 0), 1)}, "
                f"{item.get('impressions', 0)} impressions, "
                f"{item.get('clicks', 0)} clicks, "
                f"CTR {round(item.get('ctr', 0) * 100, 2)}%"
            ),
            "recommended_action": recommend_seo_action(topic, item),
        })

    for lead in leads:
        score = score_lead(lead)

        opportunities.append({
            "type": "Lead Opportunity",
            "topic": "Follow Up Boss",
            "label": lead.get("name", "Unknown Lead"),
            "score": score,
            "reason": (
                f"Stage: {lead.get('stage')}, "
                f"Visits: {lead.get('websiteVisits')}, "
                f"Tags: {lead.get('tags')}"
            ),
            "recommended_action": recommend_lead_action(lead),
        })

    opportunities.sort(key=lambda x: x["score"], reverse=True)

    topic_scores = {}

    for opportunity in opportunities:
        topic = opportunity["topic"]
        topic_scores[topic] = topic_scores.get(topic, 0) + opportunity["score"]

    ranked_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)

    return {
        "ranked_topics": ranked_topics,
        "opportunities": opportunities,
        "top_actions": opportunities[:5],
    }
