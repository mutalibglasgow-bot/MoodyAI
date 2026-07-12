from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta
import os
import json

from services.search_console import get_search_console_service
from services.followupboss import get_people
from agents.intelligence_agent import build_intelligence
from agents.trend_engine import save_daily_snapshot, compare_to_previous
from agents.content_manager import get_next_content_actions

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SITE_URL = "https://texashomesbymoody.com/"


def get_gsc_data():
    service = get_search_console_service()

    end_date = datetime.now().date() - timedelta(days=2)
    start_date = end_date - timedelta(days=28)

    request = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": ["query"],
        "rowLimit": 75,
    }

    response = service.searchanalytics().query(
        siteUrl=SITE_URL,
        body=request,
    ).execute()

    items = []

    for row in response.get("rows", []):
        items.append({
            "label": row["keys"][0],
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0),
            "position": row.get("position", 99),
        })

    return items


def get_fub_leads():
    people = get_people(limit=25)
    leads = []

    for person in people["people"]:
        leads.append({
            "id": person.get("id"),
            "name": person.get("name"),
            "firstName": person.get("firstName"),
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
        })

    return leads


def generate_ai_report(intelligence, trend_report, content_backlog):
    prompt = f"""
You are Moody Glasgow's Bell County Real Estate Intelligence Agent.

Moody is a Realtor serving Temple, Belton, Bell County, BSW medical professionals,
Fort Cavazos military families, local sellers, buyers, and relocation clients.

Your job is not to summarize data.
Your job is to tell Moody where to spend time today to get future clients.

Current Intelligence:
{json.dumps(intelligence, indent=2)}

Trend Report:
{json.dumps(trend_report, indent=2)}

Content Backlog:
{json.dumps(content_backlog, indent=2)}

Rules:
- Be direct.
- Prioritize client acquisition.
- Separate urgent lead follow-up from long-term content work.
- Mention trends only if they change what Moody should do.
- Use the content backlog when recommending content.
- Do not recommend completed backlog items.
- Do not create a generic SEO report.
- Make actions specific enough that Moody can execute them today.

Return this format exactly:

MOODY DAILY REAL ESTATE INTELLIGENCE REPORT

Executive Summary:

TODAY — Immediate Lead Actions:
1.
2.
3.

THIS WEEK — Content / Marketing Actions:
1.
2.
3.

WATCHLIST — Demand Streams:
1.
2.
3.

Top Opportunity Today:

Why It Matters:

Top Content Backlog Item:

Top 5 Actions:
1.
2.
3.
4.
5.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


def main():
    print("Pulling Search Console data...")
    search_items = get_gsc_data()

    print("Pulling Follow Up Boss leads...")
    leads = get_fub_leads()

    print("Loading content backlog...")
    content_backlog = get_next_content_actions(limit=5)

    print("Building intelligence...")
    intelligence = build_intelligence(search_items, leads)

    print("Saving trend snapshot...")
    snapshot = save_daily_snapshot(intelligence)

    print("Comparing trends...")
    trend_report = compare_to_previous(snapshot)

    print("Generating AI report...")
    report = generate_ai_report(
        intelligence=intelligence,
        trend_report=trend_report,
        content_backlog=content_backlog,
    )

    os.makedirs("data/reports", exist_ok=True)

    filename = (
        "data/reports/intelligence_report_"
        f"{datetime.now().strftime('%Y-%m-%d')}.txt"
    )

    with open(filename, "w") as file:
        file.write(report)

    print("\n" + report)
    print(f"\nSaved to: {filename}")


if __name__ == "__main__":
    main()
