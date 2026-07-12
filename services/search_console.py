from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly"
]

SERVICE_ACCOUNT_FILE = "credentials/growth-agent.json"


def get_search_console_service():

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )

    service = build(
        "searchconsole",
        "v1",
        credentials=credentials
    )

    return service
