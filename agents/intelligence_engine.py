import os
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SIGNALS_FILE = "data/signals/latest_signals.json"
PLAYBOOK_DIR = "knowledge/opportunity_playbooks"
LEADING_INDICATORS_DIR = "knowledge/leading_indicators"


def read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r") as file:
        return file.read()


def load_signals():
    return read_file(SIGNALS_FILE)


def load_markdown_tree(folder, limit=40):
    if not os.path.exists(folder):
        return ""

    files = []

    for root, _, filenames in os.walk(folder):
        for filename in filenames:
            if filename.endswith(".md"):
                files.append(os.path.join(root, filename))

    files.sort()

    output = []

    for path in files[:limit]:
        output.append(f"\n\n--- FILE: {path} ---\n")
        output.append(read_file(path))

    return "\n".join(output)


def clean_json_text(text):
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.replace("```json", "", 1).strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```", "", 1).strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    return cleaned


def generate_intelligence():
    signals = load_signals()
    playbooks = load_markdown_tree(PLAYBOOK_DIR, limit=40)
    leading_indicators = load_markdown_tree(LEADING_INDICATORS_DIR, limit=20)

    prompt = f"""
You are the RealEstateAI Intelligence Engine.

Your job is to connect signals into market hypotheses.

Do NOT simply repeat signals.
Do NOT recommend tasks yet.
Do NOT say "follow up with leads" unless it supports a larger hypothesis.

Your job is to answer:

What patterns are emerging?
What do these signals predict?
Who will need Moody soon?
What questions will those people ask before they know they need a Realtor?
Where is the hidden opportunity?
What could competitors be missing?

Inputs:

TODAY'S SIGNALS:
{signals}

OPPORTUNITY PLAYBOOKS:
{playbooks}

LEADING INDICATORS:
{leading_indicators}

Create market hypotheses.

A hypothesis is a reasoned prediction, not a task.

Examples:
- "Belton seller demand is becoming more listing-oriented because FSBO searches, high-equity homeowner behavior, and CRM cash-offer leads are converging."
- "BSW physician relocation remains the highest-authority niche, but current demand is mid-term rather than immediate."
- "Builder activity plus affordability searches suggest move-up buyers may become active if incentives continue."

Return valid JSON only:

{{
  "generated_at": "{datetime.now().isoformat()}",
  "hypotheses": [
    {{
      "hypothesis_name": "",
      "summary": "",
      "supporting_signals": [],
      "predicted_client_need": "",
      "future_questions_people_will_ask": [],
      "affected_opportunities": [],
      "time_horizon": "",
      "revenue_potential": 0,
      "listing_potential": 0,
      "high_price_potential": 0,
      "time_efficiency": 0,
      "moody_advantage": 0,
      "competition_risk": 0,
      "confidence": 0.0,
      "overall_intelligence_score": 0
    }}
  ]
}}

Scoring:
- All scores except confidence must be 0-100.
- confidence must be 0.0-1.0.
- Prioritize Moody's stated business priorities:
  1. Make money.
  2. Get listings.
  3. Prioritize high-priced listings.
  4. Use Moody's time efficiently.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    cleaned = clean_json_text(response.output_text)

    try:
        parsed = json.loads(cleaned)
        return parsed
    except json.JSONDecodeError:
        return {
            "generated_at": datetime.now().isoformat(),
            "error": "AI returned invalid JSON",
            "raw_output": response.output_text,
            "hypotheses": [],
        }


def save_intelligence(intelligence):
    os.makedirs("data/intelligence", exist_ok=True)

    latest_path = "data/intelligence/latest_intelligence.json"
    dated_path = f"data/intelligence/intelligence_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"

    with open(latest_path, "w") as file:
        json.dump(intelligence, file, indent=2)

    with open(dated_path, "w") as file:
        json.dump(intelligence, file, indent=2)

    return latest_path, dated_path


def main():
    print("Loading latest signals...")
    print("Connecting signals into intelligence...\n")

    intelligence = generate_intelligence()

    hypotheses = intelligence.get("hypotheses", [])

    hypotheses.sort(
        key=lambda h: h.get("overall_intelligence_score", 0),
        reverse=True,
    )

    intelligence["hypotheses"] = hypotheses

    print("MARKET HYPOTHESES")
    print("=" * 50)

    for i, h in enumerate(hypotheses, start=1):
        print(f"\n{i}. {h.get('hypothesis_name')}")
        print(f"   Score: {h.get('overall_intelligence_score')}")
        print(f"   Confidence: {h.get('confidence')}")
        print(f"   Time Horizon: {h.get('time_horizon')}")
        print(f"   Summary: {h.get('summary')}")

    latest_path, dated_path = save_intelligence(intelligence)

    print(f"\nSaved latest intelligence to: {latest_path}")
    print(f"Saved dated intelligence to: {dated_path}")


if __name__ == "__main__":
    main()