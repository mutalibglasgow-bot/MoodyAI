from dotenv import load_dotenv
from openai import OpenAI
from services.followupboss import get_people
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

people = get_people(limit=25)

ranked = []

for person in people["people"]:

    score = 0

    stage = person.get("stage", "")
    visits = person.get("websiteVisits", 0)

    if stage in ["Freshly Claimed", "Consult Set", "Sourcing Cash Offers"]:
        score += 40

    if visits >= 5:
        score += 25

    ranked.append((score, person))

ranked.sort(reverse=True, key=lambda x: x[0])

for score, person in ranked[:10]:

    name = person.get("name")
    stage = person.get("stage")
    city = ""

    if person.get("addresses"):
        city = person["addresses"][0].get("city", "")

    prompt = f"""
Write a short text message from Moody Glasgow.

Lead:
{name}

Stage:
{stage}

City:
{city}

Requirements:
- Friendly
- Personal
- Not pushy
- Under 60 words
- End with a question
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    print("\n======================")
    print(name)
    print("----------------------")
    print(response.output_text)
