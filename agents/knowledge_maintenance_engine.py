import os
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

KNOWLEDGE_PATHS = [
    "knowledge/opportunities",
    "knowledge/areas",
    "knowledge/client_personas",
    "knowledge/playbooks",
]

SIGNAL_FILES = [
    "data/intelligence/history.json",
]


def read_file(path):
    if not os.path.exists(path):
        return ""

    with open(path, "r") as file:
        return file.read()


def find_knowledge_files():
    files = []

    for folder in KNOWLEDGE_PATHS:
        if not os.path.exists(folder):
            continue

        for root, _, filenames in os.walk(folder):
            for filename in filenames:
                if filename.endswith(".md"):
                    files.append(os.path.join(root, filename))

    return files


def load_recent_reports(limit=3):
    reports_dir = "data/reports"

    if not os.path.exists(reports_dir):
        return ""

    reports = [
        os.path.join(reports_dir, f)
        for f in os.listdir(reports_dir)
        if f.endswith(".txt")
    ]

    reports.sort(reverse=True)

    combined = []

    for path in reports[:limit]:
        combined.append(f"\n\n--- REPORT: {path} ---\n")
        combined.append(read_file(path))

    return "\n".join(combined)


def load_signals():
    combined = []

    for path in SIGNAL_FILES:
        combined.append(f"\n\n--- SIGNAL FILE: {path} ---\n")
        combined.append(read_file(path))

    combined.append(load_recent_reports())

    return "\n".join(combined)


def review_file(path, signals):
    content = read_file(path)

    prompt = f"""
You are RealEstateAI's Knowledge Maintenance Engine.

Your job is to review one knowledge file and decide whether it needs updates.

Do NOT rewrite the whole file.
Do NOT overwrite anything.
Only recommend updates for Moody to approve.

Knowledge File Path:
{path}

Knowledge File Content:
{content}

Recent Business Signals:
{signals}

Review the file for:
- outdated assumptions
- missing local intelligence
- missing client objections
- missing AI monitoring rules
- missing revenue or relationship value logic
- missing content opportunities
- missing update triggers
- recommendations that no longer match business strategy

Return this exact format:

FILE:
{path}

STATUS:
Current / Needs Minor Update / Needs Major Update

WHY:

SUGGESTED UPDATES:
1.
2.
3.

SECTIONS TO ADD:

SECTIONS TO REVISE:

PRIORITY:
Low / Medium / High

DRAFT PATCH:
Write only the new or revised Markdown sections that Moody could paste into the file.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


def main():
    print("Finding knowledge files...")
    files = find_knowledge_files()

    print(f"Found {len(files)} knowledge files.")

    print("Loading recent signals...")
    signals = load_signals()

    results = []

    for path in files:
        print(f"Reviewing: {path}")
        result = review_file(path, signals)
        results.append(result)

    os.makedirs("data/knowledge_reviews", exist_ok=True)

    filename = (
        "data/knowledge_reviews/knowledge_review_"
        f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    )

    with open(filename, "w") as file:
        file.write("\n\n" + ("=" * 80) + "\n\n".join(results))

    print(f"\nKnowledge review saved to: {filename}")


if __name__ == "__main__":
    main()

