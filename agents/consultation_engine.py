import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


KNOWLEDGE_FILES = [
    "knowledge/opportunities/employment/bsw_medical_residents.md",
    "knowledge/opportunities/employment/new_attending_physicians.md",
    "knowledge/areas/temple.md",
    "knowledge/areas/belton.md",
    "knowledge/areas/salado.md",
    "knowledge/playbooks/area_recommender.md",
    "knowledge/client_personas/overwhelmed_medical_resident.md",
    "knowledge/client_personas/established_attending_physician.md",
    "knowledge/client_personas/military_family_pcs.md",
]


def load_knowledge():
    combined = []

    for path in KNOWLEDGE_FILES:
        if os.path.exists(path):
            with open(path, "r") as file:
                combined.append(f"\n\n--- FILE: {path} ---\n")
                combined.append(file.read())

    return "\n".join(combined)


def ask(question):
    print("\n" + question)
    return input("> ").strip()


def run_consultation():
    print("\n====================================")
    print("BELL COUNTY RELOCATION PLANNER")
    print("====================================")
    print(
        "\nI'll ask a few questions, then create a personalized "
        "relocation plan for Temple, Belton, Salado, and the surrounding area."
    )

    answers = {}

    answers["reason_for_move"] = ask(
        "What brings you to Bell County? "
        "(BSW, Fort Cavazos, new job, family, retirement, buying first home, other)"
    )

    answers["household"] = ask(
        "Who is making the move? "
        "(just me, couple, family with children, empty nest, retiring)"
    )

    answers["timeline"] = ask(
        "When do you need to move? "
        "(immediately, 30 days, 60 days, 90 days, just researching)"
    )

    answers["work_location"] = ask(
        "Where will you or your spouse/partner be working?"
    )

    answers["budget"] = ask(
        "What is your approximate home budget or rent budget?"
    )

    answers["buy_or_rent"] = ask(
        "Are you planning to buy, rent first, or unsure?"
    )

    answers["schools"] = ask(
        "Do schools matter for this move? If yes, tell me how important they are."
    )

    answers["priorities"] = ask(
        "Pick your top priorities: commute, schools, more house, lower taxes, "
        "small-town feel, luxury, lake access, privacy, new construction, "
        "investment potential, walkability, outdoor recreation."
    )

    answers["concerns"] = ask(
        "What are you most worried about with this move?"
    )

    answers["lifestyle"] = ask(
        "Describe your ideal lifestyle in Bell County."
    )

    return answers


def generate_relocation_plan(answers):
    knowledge = load_knowledge()

    prompt = f"""
You are RealEstateAI, Moody Glasgow's Bell County relocation consultation engine.

You are not a chatbot.
You are a trusted relocation advisor.

Use the knowledge base and consultation answers to create a personalized relocation plan.

Your philosophy:
- Client first.
- Trust first.
- Never push someone to buy if renting makes more sense.
- Recommend buying only when it fits the client's timeline, goals, finances, and life situation.
- Explain trade-offs honestly.
- Think like a top-producing Bell County relocation advisor.
- Optimize for long-term trust and Expected Relationship Value.

Knowledge Base:
{knowledge}

Consultation Answers:
{answers}

Return this exact format:

PERSONALIZED BELL COUNTY RELOCATION PLAN

CLIENT SUMMARY:

LIKELY CLIENT PERSONA:

PRIMARY MOTIVATION:

URGENCY LEVEL:

BUY VS RENT GUIDANCE:

BEST-FIT COMMUNITY:
Area:
Confidence:
Why:

SECONDARY COMMUNITIES TO CONSIDER:
1.
2.

AREAS THAT MAY NOT FIT:

KEY TRADE-OFFS:

LIKELY CONCERNS:
1.
2.
3.

MOODY'S ADVISORY NOTES:

RECOMMENDED CONTENT TO SEND:
1.
2.
3.
4.

RECOMMENDED VIDEOS:
1.
2.
3.

RECOMMENDED NEXT QUESTIONS:
1.
2.
3.
4.
5.

RECOMMENDED NEXT STEP:

EXPECTED RELATIONSHIP VALUE ASSESSMENT:

FOLLOW UP BOSS NOTE:
Write a concise CRM note summarizing the client, motivation, timeline, recommended area, concerns, and next action.

FIRST MESSAGE FROM MOODY:
Write a warm, helpful first text or email under 120 words.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


def main():
    answers = run_consultation()
    print("\nGenerating personalized relocation plan...\n")
    plan = generate_relocation_plan(answers)

    print(plan)

    os.makedirs("data/consultations", exist_ok=True)

    filename = "data/consultations/latest_relocation_plan.txt"

    with open(filename, "w") as file:
        file.write(plan)

    print(f"\nSaved to: {filename}")


if __name__ == "__main__":
    main()
