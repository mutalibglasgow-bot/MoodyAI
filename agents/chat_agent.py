from dotenv import load_dotenv
from openai import OpenAI
import os

# Load environment variables
load_dotenv()

# Create OpenAI client
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

print("================================")
print("      Moody AI is Ready")
print("================================")

while True:

    question = input("\nYou: ")

    if question.lower() in ["exit", "quit"]:
        break

    try:

        response = client.responses.create(
            model="gpt-5",
            input=question
        )

        print("\nMoody AI:")

        print(response.output_text)

    except Exception as e:

        print("\nERROR:")
        print(e)