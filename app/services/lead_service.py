from app.services.followupboss_service import FollowUpBossService
from app.services.openai_service import OpenAIService


class LeadService:

    def __init__(self):
        self.fub = FollowUpBossService()
        self.ai = OpenAIService()

    def get_latest_action_plan(self):

        leads = self.fub.get_latest_leads(limit=1)

        if not leads:
            return {
                "message": "No leads found"
            }

        lead = leads[0]

        full_lead = self.fub.get_person(lead["id"])

        ai_summary = self.ai.summarize_lead(full_lead)

        score = 0
        reasons = []

        if full_lead.get("phones"):
            score += 20
            reasons.append("Phone available")

        if full_lead.get("emails"):
            score += 15
            reasons.append("Email available")

        if full_lead.get("addresses"):
            score += 25
            reasons.append("Address available")

        if full_lead.get("websiteVisits", 0) >= 3:
            score += 20
            reasons.append(
                f'{full_lead.get("websiteVisits")} website visits'
            )

        if "cash" in str(full_lead.get("stage", "")).lower():
            score += 15
            reasons.append("Cash offer lead")

        if full_lead.get("contacted", 0):
            score += 5
            reasons.append("Already contacted")

        temperature = "COLD"

        if score >= 80:
            temperature = "HOT"
        elif score >= 50:
            temperature = "WARM"

        return {
            "lead": full_lead,
            "score": score,
            "temperature": temperature,
            "reasons": reasons,
            "ai": ai_summary
        }