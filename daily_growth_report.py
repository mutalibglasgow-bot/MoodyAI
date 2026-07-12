from dotenv import load_dotenv
from openai import OpenAI
import os
import csv
from datetime import datetime

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def read_csv(path):
    with open(path, "r") as file:
        return list(csv.DictReader(file))


seo_data = read_csv("data/seo/sample_seo.csv")
social_data = read_csv("data/social/sample_social.csv")

prompt = f"""
You are Moody Glasgow's Real Estate Growth Agent.

Moody is a Realtor in Temple and Belton, Texas.

His goal:
Generate new clients from SEO, social media, and local authority content.

SEO Data:
{seo_data}

Social Media Data:
{social_data}

Create a daily action report.

Return this exact format:

DAILY GROWTH REPORT

Summary:
Top Opportunity:
SEO Actions:
Social Media Actions:
Lead Generation Actions:
Top 5 Prioritized Actions:
"""

response = client.responses.create(
    model="gpt-4.1-mini",
    input=prompt
)

report = response.output_text

os.makedirs("data/reports", exist_ok=True)

filename = f"data/reports/growth_report_{datetime.now().strftime('%Y-%m-%d')}.txt"

with open(filename, "w") as file:
    file.write(report)

print(report)
print(f"\nSaved to: {filename}")
