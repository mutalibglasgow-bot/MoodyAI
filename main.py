from fastapi import FastAPI
from services.followupboss_service import FollowUpBossService

app = FastAPI(
    title="MoodyAI",
    version="0.4"
)

fub = FollowUpBossService()


@app.get("/")
def home():
    return {
        "status": "running"
    }


@app.get("/leads/latest")
def latest_leads():
    return fub.get_latest_leads()


@app.get("/lead/latest")
def latest_lead():
    leads = fub.get_latest_leads(1)

    if not leads:
        return {
            "message": "No leads found."
        }

    return leads[0]