from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

with open("knowledge/bell_county.txt", "r") as file:
    knowledge = file.read()

with open("prompts/real_estate_assistant.txt", "r") as file:
    system_prompt = file.read()

lead_name = input("Lead name: ")
lead_type = input("Buyer, seller, or relocation? ")
lead_message = input("What did the lead say? ")

response = client.responses.create(
    model="gpt-4.1-mini",
    input=f"""
{system_prompt}

Local knowledge:
{knowledge}

Create a warm, professional response for this real estate lead.

Lead name:
{lead_name}

Lead type:
{lead_type}

Lead message:
{lead_message}

Rules:
- Keep it under 120 words
- Sound like Moody Glasgow
- Be helpful but not pushy
- End with one simple question
"""
)

suggested_response = response.output_text

print("\nSuggested response:\n")
print(suggested_response)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"data/responses/{lead_name}_{timestamp}.txt"

with open(filename, "w") as file:
    file.write(f"Lead name: {lead_name}\n")
    file.write(f"Lead type: {lead_type}\n")
    file.write(f"Lead message: {lead_message}\n\n")
    file.write("Suggested response:\n")
    file.write(suggested_response)

print(f"\nSaved to: {filename}")
