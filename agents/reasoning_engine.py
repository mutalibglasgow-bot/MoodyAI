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


def reason_about_client(client_scenario):
    knowledge = load_knowledge()

    prompt = f"""
You are RealEstateAI, Moody Glasgow's Bell County real estate reasoning engine.

Your job is to think like a top-producing relocation-focused Realtor.

Use the knowledge base below to advise Moody.

Knowledge Base:
{knowledge}

Client Scenario:
{client_scenario}

Return this exact format:

CLIENT TYPE:

LIKELY MOTIVATION:

BEST AREA RECOMMENDATION:

WHY THIS AREA FITS:

AREAS TO ALSO CONSIDER:

AREAS TO AVOID:

BEST FIRST MESSAGE FROM MOODY:

BEST CONTENT TO SEND:

RECOMMENDED NEXT STEP:

EXPECTED COMMISSION PIPELINE ASSESSMENT:
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


if __name__ == "__main__":
    scenario = input("Describe the client scenario:\n\n")
    result = reason_about_client(scenario)
    print("\n" + result)
