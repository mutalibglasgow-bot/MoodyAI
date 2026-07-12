import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


KNOWLEDGE_FILES = [
    "knowledge/playbooks/area_recommender.md",
    "knowledge/areas/temple.md",
    "knowledge/areas/belton.md",
    "knowledge/areas/salado.md",
    "knowledge/client_personas/overwhelmed_medical_resident.md",
    "knowledge/client_personas/established_attending_physician.md",
    "knowledge/client_personas/military_family_pcs.md",
    "knowledge/opportunities/employment/bsw_medical_residents.md",
    "knowledge/opportunities/employment/new_attending_physicians.md",
]


MAX_QUESTIONS = 5


def load_knowledge():
    combined = []

    for path in KNOWLEDGE_FILES:
        if os.path.exists(path):
            with open(path, "r") as file:
                combined.append(f"\n\n--- FILE: {path} ---\n")
                combined.append(file.read())

    return "\n".join(combined)


def plan_next_question(conversation_history):
    knowledge = load_knowledge()

    prompt = f"""
You are RealEstateAI's Conversation Manager.

Your job is to conduct a short, adaptive real estate relocation consultation.

You are NOT trying to collect every possible detail.
You are trying to collect only the information that changes the recommendation.

Use this knowledge base:
{knowledge}

Conversation so far:
{conversation_history}

Core rule:
Ask another question ONLY if the answer could materially change one of these:
- client persona
- buy vs rent guidance
- best-fit community
- urgency
- budget realism
- first follow-up strategy
- trust-building content to send

Do NOT ask questions just because information is incomplete.

Stop when you know enough to make a useful recommendation.

Hard limits:
- Ask only one question at a time.
- Never ask more than 5 total questions.
- Do not repeat questions.
- Do not ask about details that will not change the recommendation.
- If confidence is 85 or higher and the remaining missing info would not change the recommendation, stop.
- If the client gives a short answer, infer what you can and ask only the highest-value follow-up.
- Sound like Moody: calm, helpful, direct, not salesy.

Return valid JSON only:

{{
  "known_facts": [],
  "likely_persona": "",
  "likely_opportunity": "",
  "confidence": 0,
  "decision_confidence": {{
    "client_type": 0,
    "timeline": 0,
    "budget": 0,
    "community_recommendation": 0,
    "buy_vs_rent": 0,
    "follow_up_strategy": 0
  }},
  "material_missing_information": [],
  "ready_for_plan": false,
  "reason_to_stop_or_continue": "",
  "next_question": ""
}}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


def run_conversation():
    print("\n====================================")
    print("REAL ESTATE AI CONVERSATION MANAGER")
    print("====================================")
    print("\nAdaptive consultation prototype.")
    print("\nTell me about your move. What brings you to Bell County?")

    conversation = []

    first_question = "Tell me about your move. What brings you to Bell County?"
    first_answer = input("\n> ").strip()

    conversation.append({"role": "assistant", "content": first_question})
    conversation.append({"role": "client", "content": first_answer})

    questions_asked = 1

    while True:
        print("\nThinking...\n")

        result_text = plan_next_question(conversation)

        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            print("AI returned non-JSON response:")
            print(result_text)
            break

        print("Known Facts:")
        for fact in result.get("known_facts", []):
            print(f"- {fact}")

        print(f"\nLikely Persona: {result.get('likely_persona')}")
        print(f"Likely Opportunity: {result.get('likely_opportunity')}")
        print(f"Confidence: {result.get('confidence')}%")

        print("\nDecision Confidence:")
        for key, value in result.get("decision_confidence", {}).items():
            print(f"- {key}: {value}%")

        print(f"\nReason: {result.get('reason_to_stop_or_continue')}")

        if result.get("ready_for_plan") or questions_asked >= MAX_QUESTIONS:
            print("\nReady for relocation plan.")
            print("\nFinal Conversation History:")
            print(json.dumps(conversation, indent=2))
            break

        question = result.get("next_question", "")

        if not question:
            print("\nNo next question returned. Stopping.")
            print("\nFinal Conversation History:")
            print(json.dumps(conversation, indent=2))
            break

        print(f"\nNext Question:\n{question}")

        answer = input("\n> ").strip()

        conversation.append({"role": "assistant", "content": question})
        conversation.append({"role": "client", "content": answer})

        questions_asked += 1


if __name__ == "__main__":
    run_conversation()
