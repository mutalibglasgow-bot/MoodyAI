import json

from openai import OpenAI
from app.core.settings import OPENAI_KEY, OPENAI_MODEL

client = OpenAI(api_key=OPENAI_KEY)


class OpenAIService:

    def summarize_lead(self, lead):

        prompt = f"""
You are MoodyAI, the AI assistant for Moody Glasgow.

IMPORTANT INFORMATION:

Moody Glasgow
Brokerage: Orchard Realty
Phone: 512-890-0145
Website: https://texashomesbymoody.com

RULES:

- Never use placeholders like [Your Name]
- Never use placeholders like [Your Company]
- Never use placeholders like [Your Phone]
- Never use the lead's phone number as Moody's phone number
- Never use the lead's email address as Moody's email address
- Return ONLY valid JSON
- Do not include markdown
- Do not include explanations

Return JSON in this format:

{{
    "lead_type":"",
    "priority":"",
    "summary":"",
    "recommended_action":"",
    "email_subject":"",
    "email_body":"",
    "sms":""
}}

Lead:

{lead}
"""

        response = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt
        )

        text = response.output_text

        try:
            return json.loads(text)

        except Exception:

            return {
                "lead_type": "Unknown",
                "priority": "Unknown",
                "summary": text,
                "recommended_action": "",
                "email_subject": "",
                "email_body": "",
                "sms": ""
            }