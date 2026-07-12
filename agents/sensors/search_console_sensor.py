from typing import List
from openai import OpenAI
from dotenv import load_dotenv
import os

from agents.sensors.base_sensor import BaseSensor, Signal

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class SearchConsoleSensor(BaseSensor):
    name = "Search Console Sensor"

    def collect(self) -> List[Signal]:
        reports = self.read_recent_text_files("data/reports", limit=5)
        history = self.read_file("data/intelligence/history.json")

        context = f"""
=== RECENT REPORTS ===
{reports}

=== INTELLIGENCE HISTORY ===
{history}
"""

        if not context.strip():
            return []

        prompt = f"""
You are the Search Console / SEO Demand Sensor for RealEstateAI.

Your job is to identify search behavior signals that predict future real estate demand.

Focus on:
- BSW searches
- physician relocation searches
- Belton seller searches
- Fort Cavazos searches
- Temple vs Belton searches
- luxury searches
- Lake Belton searches
- first-time buyer searches
- new construction searches
- property tax searches
- FSBO searches

Do NOT recommend actions yet.
Only extract signals.

Context:
{context}

Return valid JSON only:

{{
  "signals": [
    {{
      "signal_name": "",
      "source": "Google Search Console / SEO Reports",
      "signal_type": "Search Demand",
      "summary": "",
      "why_it_matters": "",
      "affected_opportunities": [],
      "likely_client_types": [],
      "future_questions_people_will_ask": [],
      "time_horizon": "",
      "confidence": 0.0,
      "business_value_score": 0
    }}
  ]
}}
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        data = self.parse_json(response.output_text)

        if not data:
            return []

        results = []

        for item in data.get("signals", []):
            results.append(Signal(**item))

        return results