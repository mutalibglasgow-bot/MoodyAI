import os
import requests

from tools.config import *

BASE_URL = "https://api.followupboss.com/v1"

API_KEY = os.getenv("FOLLOWUPBOSS_API_KEY")


def get_people(limit=5):

    response = requests.get(
        f"{BASE_URL}/people",
        auth=(API_KEY, "")
    )

    response.raise_for_status()

    data = response.json()

    return data