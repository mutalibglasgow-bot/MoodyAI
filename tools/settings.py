from pathlib import Path
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
FOLLOWUPBOSS_KEY = os.getenv("FOLLOWUPBOSS_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")