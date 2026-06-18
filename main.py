from fastapi import FastAPI
from app.services.lead_service import LeadService
from app.services.followupboss_service import FollowUpBossService
from app.services.openai_service import OpenAIService

app = FastAPI(
    title="MoodyAI",
    version="0.5.0"
)

fub = FollowUpBossService()
ai = OpenAIService()
lead_service = LeadService()

@app.get("/")
def root():
    return {
        "application": "MoodyAI",
        "status": "running",
        "version": "0.5.0"
    }

@app.get("/lead/latest/action-plan")
def latest_action_plan():
    return lead_service.get_latest_action_plan()

@app.get("/leads/latest")
def latest_leads():
    return fub.get_latest_leads(limit=5)


@app.get("/lead/latest")
def latest_lead():
    leads = fub.get_latest_leads(limit=1)

    if not leads:
        return {"message": "No leads found"}

    return leads[0]


@app.get("/lead/{person_id}")
def get_lead(person_id: int):
    return fub.get_person(person_id)


@app.get("/lead/latest/summary")
def latest_lead_summary():
    leads = fub.get_latest_leads(limit=1)

    if not leads:
        return {"message": "No leads found"}

    lead = leads[0]
    full_lead = fub.get_person(lead["id"])
    summary = ai.summarize_lead(full_lead)

    return {
        "lead": full_lead,
        "ai_summary": summary
    }


@app.get("/lead/latest/opportunity")
def latest_lead_opportunity():
    leads = fub.get_latest_leads(limit=1)

    if not leads:
        return {"message": "No leads found"}

    lead = leads[0]
    full_lead = fub.get_person(lead["id"])

    score = 0
    reasons = []

    if full_lead.get("phones"):
        score += 20
        reasons.append("Phone number available")

    if full_lead.get("emails"):
        score += 15
        reasons.append("Email address available")

    if full_lead.get("addresses"):
        score += 25
        reasons.append("Property address available")

    if full_lead.get("websiteVisits", 0) >= 3:
        score += 20
        reasons.append(f"{full_lead.get('websiteVisits')} website visits")

    if "cash" in str(full_lead.get("stage", "")).lower():
        score += 15
        reasons.append("Cash offer stage")

    if full_lead.get("contacted", 0) > 0:
        score += 5
        reasons.append("Already contacted")

    if score >= 80:
        temperature = "HOT"
    elif score >= 50:
        temperature = "WARM"
    else:
        temperature = "COLD"

    return {
        "lead_id": full_lead.get("id"),
        "name": full_lead.get("name"),
        "score": score,
        "temperature": temperature,
        "reasons": reasons,
        "recommended_action": "Call today and follow up with SMS/email."
    }