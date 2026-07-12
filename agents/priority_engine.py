import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SIGNALS_FILE = "data/signals/latest_signals.json"
INTELLIGENCE_FILE = "data/intelligence/latest_intelligence.json"
TRENDS_FILE = "data/history/latest_trends.json"
PLAYBOOK_DIR = "knowledge/opportunity_playbooks"


def read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r") as file:
        return file.read()


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
        output.append(f"\n\n--- PLAYBOOK: {path} ---\n")
        output.append(read_file(path))

    return "\n".join(output)


def generate_operations_report(signals, intelligence, playbooks):
    prompt = f"""
You are the RealEstateAI Operations Engine.

Your job is to help Moody maximize revenue from people who already know him.

This includes:
- Follow Up Boss leads
- existing leads
- past clients
- active buyers
- active sellers
- listing opportunities already in the pipeline
- immediate follow-up opportunities

Moody's priorities:
1. Make money.
2. Get listings.
3. Prioritize high-priced listings.
4. Use time efficiently.

IMPORTANT:
This report is allowed to mention specific CRM leads.
This report should be tactical and immediate.
Do not focus on long-term market trends here.

TODAY'S SIGNALS:
{signals}

TODAY'S INTELLIGENCE:
{intelligence}

OPPORTUNITY PLAYBOOKS:
{playbooks}

Return this exact format:

MOODY OPERATIONS REPORT

PURPOSE:
Maximize current business from people already in Moody's world.

TOP OPERATIONS PRIORITY TODAY:

WHY THIS MATTERS:

CURRENT LEADS / CLIENTS TO PRIORITIZE:
1.
2.
3.
4.
5.

LISTING OPPORTUNITIES INSIDE CURRENT PIPELINE:

HIGH-PRICE OPPORTUNITIES INSIDE CURRENT PIPELINE:

BEST ONE-HOUR OPERATIONS ACTION:

BEST HALF-DAY OPERATIONS ACTION:

WHAT IS COSTING MOODY MONEY RIGHT NOW:

LOW-VALUE OPERATIONS DISTRACTIONS:

FINAL OPERATIONS RECOMMENDATION:
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


def generate_growth_report(signals, intelligence, trends, playbooks):
    prompt = f"""
You are the RealEstateAI Growth Engine.

Your job is to help Moody create NEW clients who do not know him yet.

This report is NOT about current CRM leads.
This report is about future business, market intelligence, client attraction, and market ownership.

You must focus on:
- What changed
- What is accelerating
- What is cooling
- What is emerging
- What future clients will ask
- How Moody can get in front of them early
- How Moody becomes the obvious choice

Moody's growth priorities:
1. Find future clients before competitors.
2. Get in front of them early.
3. Become the obvious choice.
4. Create listings and high-value relationships.

IMPORTANT RULES:
- Do NOT mention specific Follow Up Boss lead names.
- Do NOT say "call hot leads."
- Do NOT optimize for current pipeline.
- This report must identify people who do NOT know Moody yet.
- Trends matter more than static facts.
- A signal is only important if it suggests future demand or new-client opportunity.
- If trend history is limited, say so clearly and still make the best judgment from available data.

TODAY'S SIGNALS:
{signals}

TODAY'S INTELLIGENCE:
{intelligence}

TREND HISTORY:
{trends}

OPPORTUNITY PLAYBOOKS:
{playbooks}

Return this exact format:

MOODY GROWTH INTELLIGENCE REPORT

PURPOSE:
Create new clients who do not know Moody yet.

WHAT CHANGED:
1.

2.

3.

4.

5.

TREND READ:
1-Day Trend:

7-Day Trend:

30-Day Trend:

Momentum Summary:

TOP NEW-CLIENT OPPORTUNITY:

WHY THIS OPPORTUNITY EXISTS NOW:

WHO WILL NEED MOODY SOON:

HOW MOODY GETS IN FRONT OF THEM:

HOW MOODY BECOMES THE OBVIOUS CHOICE:

TOP 5 FUTURE CLIENT OPPORTUNITIES:
1.
2.
3.
4.
5.

EMERGING QUESTIONS PEOPLE WILL ASK:
1.
2.
3.
4.
5.

BEST CONTENT TO CREATE NEXT:

BEST VIDEO TO RECORD NEXT:

BEST PARTNERSHIP TO PURSUE:

BEST GOOGLE BUSINESS PROFILE POST:

BEST LONG-TERM MARKET TO OWN:

WHAT COMPETITORS ARE LIKELY MISSING:

EXPECTED NEW-CLIENT BUSINESS IMPACT:

FINAL GROWTH RECOMMENDATION:
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


def save_report(path, content):
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)

    with open(path, "w") as file:
        file.write(content)


def main():
    print("Loading latest signals...")
    signals = read_file(SIGNALS_FILE)

    print("Loading latest intelligence...")
    intelligence = read_file(INTELLIGENCE_FILE)

    print("Loading trend history...")
    trends = read_file(TRENDS_FILE)

    print("Loading opportunity playbooks...")
    playbooks = load_markdown_tree(PLAYBOOK_DIR)

    print("Generating Operations Report...\n")
    operations_report = generate_operations_report(
        signals=signals,
        intelligence=intelligence,
        playbooks=playbooks,
    )

    print("Generating Growth Report...\n")
    growth_report = generate_growth_report(
        signals=signals,
        intelligence=intelligence,
        trends=trends,
        playbooks=playbooks,
    )

    save_report("data/priority_reports/latest_operations_report.txt", operations_report)
    save_report("data/priority_reports/latest_growth_report.txt", growth_report)

    combined_report = (
        "==============================\n"
        "MOODY OPERATIONS REPORT\n"
        "==============================\n\n"
        f"{operations_report}\n\n"
        "==============================\n"
        "MOODY GROWTH INTELLIGENCE REPORT\n"
        "==============================\n\n"
        f"{growth_report}"
    )

    save_report("data/priority_reports/latest_priority_report.txt", combined_report)

    print(combined_report)

    print("\nSaved:")
    print("data/priority_reports/latest_operations_report.txt")
    print("data/priority_reports/latest_growth_report.txt")
    print("data/priority_reports/latest_priority_report.txt")


if __name__ == "__main__":
    main()