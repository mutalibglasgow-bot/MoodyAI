from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from moodyai_learning.health import build_health_report
from moodyai_learning.security import AuthConfig, SessionAuth
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from moodyai_learning import (
    DecisionService,
    ExecutionService,
    LearningEvaluator,
    LearningLedger,
    OutcomeService,
    PolicyAdaptationService,
    PolicyRegistry,
    RecommendationService,
    normalize_and_record_lead,
)
from moodyai_learning.fub_sync import FUBSyncPreviewService
from moodyai_learning.fub_import import FUBSyncImportService
from moodyai_learning.auto_sync import FUBAutoSyncService
from moodyai_learning.auto_outcomes import FUBAutoOutcomeService
from moodyai_learning.background_sync import BackgroundSyncCoordinator
from moodyai_learning.backups import DatabaseBackupCoordinator
from moodyai_learning.production import RequestLogMiddleware, configure_structured_logging, validate_startup
from moodyai_learning.paths import database_path, backup_directory

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
configure_structured_logging()

LEARNING_LEDGER = LearningLedger(database_path())
RECOMMENDATION_SERVICE = RecommendationService(LEARNING_LEDGER)
DECISION_SERVICE = DecisionService(LEARNING_LEDGER)
EXECUTION_SERVICE = ExecutionService(LEARNING_LEDGER)
OUTCOME_SERVICE = OutcomeService(LEARNING_LEDGER)
LEARNING_EVALUATOR = LearningEvaluator(LEARNING_LEDGER)
POLICY_ADAPTATION_SERVICE = PolicyAdaptationService(LEARNING_LEDGER)
POLICY_REGISTRY = PolicyRegistry(LEARNING_LEDGER)
STARTUP_VALIDATION_REPORT: dict[str, Any] = {}

app = FastAPI(
    title="MoodyAI",
    description="MoodyAI turns business signals into decisions—and decisions into action.",
    version="1.2.0",
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.add_middleware(RequestLogMiddleware)


PROTECTED_PREFIXES = ("/learning", "/api/learning", "/api/recommendations", "/api/leads")
AUTH_EXEMPT_PATHS = {"/login", "/logout", "/health", "/api/health"}


def _auth() -> SessionAuth | None:
    config = AuthConfig.from_environment()
    return SessionAuth(config) if config else None


@app.middleware("http")
async def protect_learning_console(request: Request, call_next):
    path = request.url.path
    protected = any(path == prefix or path.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)
    if not protected or path in AUTH_EXEMPT_PATHS:
        return await call_next(request)
    auth = _auth()
    if auth is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "MoodyAI authentication is not configured"}, status_code=503)
        return FileResponse(ROOT / "static" / "login.html", status_code=503)
    if auth.verify_token(request.cookies.get(auth.cookie_name)):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


def _run_background_learning_cycle() -> dict[str, Any]:
    """Run the same automatic FUB loop without requiring the UI to be open."""
    if not live_fub_available():
        return {
            "mode": "background_sync",
            "status": "not_configured",
            "imported_count": 0,
            "automatic_outcome_count": 0,
            "error_count": 0,
            "evaluation": {"evaluated": 0, "skipped_without_outcomes": 0},
        }

    from services.followupboss import get_calls, get_events, get_person, get_text_messages

    preview_service = FUBSyncPreviewService(
        LEARNING_LEDGER,
        get_calls=get_calls,
        get_text_messages=get_text_messages,
        get_events=get_events,
    )
    activity_result = FUBAutoSyncService(LEARNING_LEDGER, preview_service).sync(limit=50)
    outcome_result = FUBAutoOutcomeService(LEARNING_LEDGER, get_person=get_person).sync(limit=100)
    evaluation_result = LEARNING_EVALUATOR.evaluate_all()
    return {
        **activity_result,
        "automatic_outcomes": outcome_result,
        "automatic_outcome_count": outcome_result.get("imported_count", 0),
        "total_changes": int(activity_result.get("imported_count", 0)) + int(outcome_result.get("imported_count", 0)),
        "evaluation": evaluation_result,
    }


BACKGROUND_SYNC = BackgroundSyncCoordinator(
    LEARNING_LEDGER.database_path,
    _run_background_learning_cycle,
)


DATABASE_BACKUPS = DatabaseBackupCoordinator(
    LEARNING_LEDGER.database_path,
    backup_dir=backup_directory(),
)


@app.on_event("startup")
def _start_background_sync() -> None:
    global STARTUP_VALIDATION_REPORT
    STARTUP_VALIDATION_REPORT = validate_startup(ROOT, LEARNING_LEDGER.database_path).to_dict()
    BACKGROUND_SYNC.start()
    DATABASE_BACKUPS.start()


@app.on_event("shutdown")
def _stop_background_sync() -> None:
    DATABASE_BACKUPS.stop()
    BACKGROUND_SYNC.stop()


@app.get("/ready")
def readiness() -> JSONResponse:
    status = STARTUP_VALIDATION_REPORT.get("status", "starting")
    ready = status in {"healthy", "degraded"}
    return JSONResponse(
        {"ready": ready, "startup": STARTUP_VALIDATION_REPORT},
        status_code=200 if ready else 503,
    )


class AdvisorRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class ExecutionPromptRequest(BaseModel):
    opportunity_id: str = Field(min_length=1, max_length=200)
    asset_type: str = Field(min_length=1, max_length=80)


class ExecutionGenerateRequest(ExecutionPromptRequest):
    prompt: str | None = Field(default=None, max_length=20000)


class RecommendationDecisionRequest(BaseModel):
    status: str = Field(min_length=4, max_length=20)
    selected_action: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=4000)
    decided_by: str = Field(default="Moody", min_length=1, max_length=200)


class RecommendationExecutionRequest(BaseModel):
    action_type: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=4, max_length=20)
    notes: str | None = Field(default=None, max_length=4000)
    external_system: str | None = Field(default=None, max_length=200)
    external_reference: str | None = Field(default=None, max_length=500)
    performed_by: str = Field(default="Moody", min_length=1, max_length=200)


class FUBSyncReviewRequest(BaseModel):
    status: str = Field(min_length=8, max_length=8)
    import_outcome: bool = False
    reason: str | None = Field(default=None, max_length=4000)
    reviewed_by: str = Field(default="Moody", min_length=1, max_length=200)


class RecommendationOutcomeRequest(BaseModel):
    outcome_type: str = Field(min_length=3, max_length=50)
    outcome_value: float | None = None
    source: str = Field(default="manual", min_length=1, max_length=200)
    attribution_confidence: float = Field(default=1.0, ge=0, le=1)
    notes: str | None = Field(default=None, max_length=4000)


DEMO_LEADS = [
    {
        "id": 1002,
        "name": "Kelsie Livingston",
        "stage": "Consultation Canceled",
        "source": "Website",
        "temperature": "HOT",
        "score": 100,
        "lastActivity": "7 website visits",
        "recommendedAction": "Send a personal text, then call with a specific offer to help.",
    },
    {
        "id": 364385,
        "name": "Crystal Rymer",
        "stage": "Sourcing Cash Offers",
        "source": "Orchard - Seller Intake",
        "temperature": "HOT",
        "score": 85,
        "lastActivity": "Recent seller-intake activity",
        "recommendedAction": "Call today and confirm timing, property condition, and desired outcome.",
    },
    {
        "id": 1003,
        "name": "Deborah Viramontes",
        "stage": "Active Buyer",
        "source": "Organic Search",
        "temperature": "WARM",
        "score": 72,
        "lastActivity": "Returned to listing pages",
        "recommendedAction": "Send three matched homes and ask what changed in her search.",
    },
]

DEMO_OPPORTUNITIES = [
    {
        "opportunity_id": "bsw-physician-relocation-demand",
        "title": "BSW Physician Relocation Demand",
        "category": "Relocation",
        "opportunity_score": 96,
        "confidence": 0.91,
        "confidence_percent": 91,
        "confidence_level": "Very High",
        "urgency": "High",
        "executive_summary": "Search demand and existing content performance point to a high-value opportunity to capture Baylor Scott & White physician relocation clients before competing agents strengthen their coverage.",
        "why_now": "Demand is already visible in physician housing and Temple-versus-Austin searches, while several high-intent content gaps remain open.",
        "expected_outcome": "A coordinated content and follow-up campaign should increase qualified physician relocation conversations over the next 30–60 days.",
        "evidence": [
            {"statement": "Physician relocation and BSW housing searches are consistently appearing in Search Console.", "source": "Google Search Console", "metric": "Search demand", "value": "Active"},
            {"statement": "Existing BSW relocation pages are already earning impressions and clicks.", "source": "Website analytics", "metric": "Content traction", "value": "Established"},
            {"statement": "The content backlog includes high-intent neighborhood and cost-of-living topics.", "source": "Content backlog", "metric": "Opportunity gap", "value": "Open"},
        ],
        "reasoning": [
            "Multiple independent signals point to the same audience and decision window.",
            "Physician relocations typically require fast, high-trust guidance across housing, commute, and community fit.",
            "Moody already has local knowledge and relevant content assets, reducing execution time.",
        ],
        "actions": [
            {"title": "Publish the BSW neighborhood guide", "description": "Complete the highest-priority neighborhood comparison page and link it from existing physician content.", "timeframe": "Today", "priority": 1, "owner": "Moody", "expected_result": "Capture additional high-intent organic traffic.", "completed": False},
            {"title": "Create a physician relocation follow-up sequence", "description": "Prepare a concise email and text sequence for BSW prospects and referral partners.", "timeframe": "This Week", "priority": 2, "owner": "Moody", "expected_result": "Convert interest into consultations.", "completed": False},
        ],
        "risks": ["Search demand may not convert without consistent follow-up and a clear consultation offer."],
        "revenue": {"low": 0, "high": 0, "currency": "USD", "transaction_low": 0, "transaction_high": 0, "basis": "Insufficient closed-transaction data for a defensible estimate."},
        "time_horizon": "30–60 days",
        "affected_audience": "BSW physicians, residents, fellows, and relocating medical families",
        "source_signals": ["Search Console", "Content backlog", "Local market knowledge"],
        "tags": ["bsw", "physician", "relocation", "seo"],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    },
    {
        "opportunity_id": "high-intent-lead-follow-up",
        "title": "High-Intent Lead Follow-Up",
        "category": "Lead",
        "opportunity_score": 94,
        "confidence": 0.88,
        "confidence_percent": 88,
        "confidence_level": "High",
        "urgency": "Immediate",
        "executive_summary": "Several leads show recent activity, canceled consultations, or seller-intake behavior that justify immediate personal follow-up.",
        "why_now": "Lead intent decays quickly. The highest-value action available today is direct outreach while recent behavior is still relevant.",
        "expected_outcome": "Personalized follow-up should produce renewed conversations and clarify which leads are ready to move now.",
        "evidence": [
            {"statement": "A canceled consultation is paired with repeated website activity.", "source": "Follow Up Boss", "metric": "Website visits", "value": "7"},
            {"statement": "Seller-intake leads remain active in sourcing and cash-offer stages.", "source": "Follow Up Boss", "metric": "Lead stage", "value": "Active"},
        ],
        "reasoning": [
            "Recent behavioral activity is a stronger predictor of near-term conversion than static lead age.",
            "A personal call and text can resolve stalled intent faster than another automated drip campaign.",
        ],
        "actions": [
            {"title": "Contact the top three leads", "description": "Send a personal text and follow with a call using the lead-specific reason for outreach.", "timeframe": "Today", "priority": 1, "owner": "Moody", "expected_result": "Create at least one live client conversation.", "completed": False},
            {"title": "Record outcomes in Follow Up Boss", "description": "Update stage, timing, motivation, and next step after every conversation.", "timeframe": "Today", "priority": 2, "owner": "Moody", "expected_result": "Improve future prioritization accuracy.", "completed": False},
        ],
        "risks": ["Lead activity can indicate curiosity rather than readiness; outreach must quickly qualify motivation and timing."],
        "revenue": {"low": 0, "high": 0, "currency": "USD", "transaction_low": 0, "transaction_high": 0, "basis": "Insufficient lead-to-close data for a defensible estimate."},
        "time_horizon": "Today–14 days",
        "affected_audience": "Active buyers and sellers in the CRM",
        "source_signals": ["Follow Up Boss"],
        "tags": ["crm", "lead", "follow-up"],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    },
    {
        "opportunity_id": "fort-cavazos-pcs-content-gap",
        "title": "Fort Cavazos PCS Content Gap",
        "category": "Content",
        "opportunity_score": 85,
        "confidence": 0.76,
        "confidence_percent": 76,
        "confidence_level": "High",
        "urgency": "Medium",
        "executive_summary": "A complete Fort Cavazos PCS housing guide can establish early authority in a seasonal relocation niche that currently has little owned content coverage.",
        "why_now": "PCS demand is seasonal and content takes time to rank. Building the asset before the strongest demand window improves the chance of capturing traffic when moves accelerate.",
        "expected_outcome": "The guide should create a reusable lead-capture asset for military families moving into Bell County.",
        "evidence": [
            {"statement": "Fort Cavazos PCS is listed as a high-priority content opportunity.", "source": "Content backlog", "metric": "Priority score", "value": "85"},
            {"statement": "Current site coverage is materially weaker than the BSW relocation content cluster.", "source": "Content inventory", "metric": "Coverage", "value": "Limited"},
        ],
        "reasoning": [
            "PCS clients have clear timing, geography, and housing questions that can be addressed in one decision-focused guide.",
            "The content can support SEO, social posts, email follow-up, and referral outreach from a single core asset.",
        ],
        "actions": [
            {"title": "Build the PCS guide outline", "description": "Define sections for commute, neighborhoods, schools, VA financing, rental options, and move timelines.", "timeframe": "This Week", "priority": 1, "owner": "Moody", "expected_result": "Create a production-ready content brief.", "completed": False},
            {"title": "Create the lead-capture offer", "description": "Add a relocation checklist and consultation CTA to the planned guide.", "timeframe": "This Week", "priority": 2, "owner": "Moody", "expected_result": "Turn future traffic into identifiable prospects.", "completed": False},
        ],
        "risks": ["The guide will not generate immediate leads if it is published too late or lacks distribution."],
        "revenue": {"low": 0, "high": 0, "currency": "USD", "transaction_low": 0, "transaction_high": 0, "basis": "Insufficient historical PCS conversion data for a defensible estimate."},
        "time_horizon": "60–120 days",
        "affected_audience": "Military families receiving PCS orders to Fort Cavazos",
        "source_signals": ["Content backlog", "Seasonal relocation pattern"],
        "tags": ["fort-cavazos", "pcs", "relocation", "content"],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    },
]


def live_fub_available() -> bool:
    return bool(os.getenv("FOLLOWUPBOSS_API_KEY"))


def live_openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def load_opportunities() -> tuple[str, list[dict[str, Any]]]:
    path = ROOT / "data" / "opportunities" / "latest_opportunities.json"
    if not path.exists():
        return "demo", DEMO_OPPORTUNITIES

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("opportunities", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list) or not items:
            raise ValueError("Opportunity file is empty")

        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            confidence = float(item.get("confidence", 0) or 0)
            if confidence > 1:
                confidence /= 100
            item["confidence"] = max(0.0, min(1.0, confidence))
            item["confidence_percent"] = int(round(item["confidence"] * 100))
            item.setdefault("confidence_level", confidence_label(item["confidence"]))
            item.setdefault("evidence", [])
            item.setdefault("reasoning", [])
            item.setdefault("actions", [])
            item.setdefault("risks", [])
            item.setdefault("revenue", {})
            item.setdefault("source_signals", [])
            item.setdefault("tags", [])
            normalized.append(item)

        if not normalized:
            raise ValueError("No valid opportunities")

        normalized.sort(
            key=lambda item: (int(item.get("opportunity_score", 0) or 0), float(item.get("confidence", 0) or 0)),
            reverse=True,
        )
        return "live", normalized
    except Exception:
        return "demo", DEMO_OPPORTUNITIES


def confidence_label(value: float) -> str:
    if value >= 0.9:
        return "Very High"
    if value >= 0.75:
        return "High"
    if value >= 0.55:
        return "Moderate"
    if value >= 0.35:
        return "Low"
    return "Very Low"


def normalize_lead(person: dict[str, Any]) -> dict[str, Any]:
    return normalize_and_record_lead(
        person,
        recommendation_service=RECOMMENDATION_SERVICE,
        source_mode="live",
        policy_registry=POLICY_REGISTRY,
    )


ASSET_SPECS: dict[str, dict[str, str]] = {
    "blog_article": {
        "label": "Blog Article",
        "instruction": "Write a useful 1,200-1,500 word SEO article with a strong title, clear headings, practical local guidance, and a natural consultation call to action.",
        "demo_format": "article",
    },
    "linkedin_post": {
        "label": "LinkedIn Post",
        "instruction": "Write a professional LinkedIn post of 180-250 words with a strong opening, useful insight, and a concise call to action. Avoid hype and excessive hashtags.",
        "demo_format": "social",
    },
    "facebook_post": {
        "label": "Facebook Post",
        "instruction": "Write a friendly Facebook post of 120-180 words that is useful, local, conversational, and ends with one simple question or call to action.",
        "demo_format": "social",
    },
    "video_script": {
        "label": "Video Script",
        "instruction": "Write a clear 2-3 minute video script with a direct hook, three useful points, natural transitions, and a concise closing call to action.",
        "demo_format": "video",
    },
    "google_ads": {
        "label": "Google Ads",
        "instruction": "Create five Google Search ad concepts. For each, provide a headline set, two descriptions, target intent, and landing-page angle. Keep claims accurate.",
        "demo_format": "ads",
    },
    "text_message": {
        "label": "Client Text",
        "instruction": "Write one concise, personal text message under 90 words. It must sound helpful rather than salesy and end with one easy-to-answer question.",
        "demo_format": "text",
    },
    "followup_email": {
        "label": "Follow-up Email",
        "instruction": "Write a concise follow-up email with a subject line, a helpful opening, specific relevance to the recipient, and one clear next step. Keep the body under 250 words.",
        "demo_format": "email",
    },
    "call_script": {
        "label": "Call Script",
        "instruction": "Write a short phone script with an opening, reason for calling, three discovery questions, a helpful value statement, and a low-pressure next step.",
        "demo_format": "call",
    },
}


def find_opportunity(opportunity_id: str) -> dict[str, Any]:
    _, items = load_opportunities()
    for item in items:
        if str(item.get("opportunity_id")) == opportunity_id:
            return item
    raise HTTPException(status_code=404, detail="Opportunity not found")


def execution_prompt(opportunity: dict[str, Any], asset_type: str) -> str:
    spec = ASSET_SPECS.get(asset_type)
    if not spec:
        raise HTTPException(status_code=400, detail="Unsupported asset type")

    evidence = "\n".join(
        f"- {item.get('statement', '')} (Source: {item.get('source', 'Not specified')})"
        for item in opportunity.get("evidence", [])[:5]
    ) or "- No additional evidence supplied."
    reasoning = "\n".join(f"- {item}" for item in opportunity.get("reasoning", [])[:5]) or "- Use the executive summary as the primary rationale."
    actions = "\n".join(
        f"- {item.get('title', '')}: {item.get('description', '')}"
        for item in opportunity.get("actions", [])[:4]
    ) or "- Recommend one practical next action."

    return f"""You are creating a {spec['label']} for Moody Glasgow, a real estate professional serving Temple, Belton, Salado, Fort Cavazos, and the Baylor Scott & White relocation market.

OPPORTUNITY
Title: {opportunity.get('title', '')}
Category: {opportunity.get('category', '')}
Audience: {opportunity.get('affected_audience', 'Local real estate clients and prospects')}
Urgency: {opportunity.get('urgency', '')}
Time horizon: {opportunity.get('time_horizon', '')}

EXECUTIVE SUMMARY
{opportunity.get('executive_summary', '')}

WHY NOW
{opportunity.get('why_now', '')}

EVIDENCE
{evidence}

AI REASONING
{reasoning}

RECOMMENDED BUSINESS ACTIONS
{actions}

EXPECTED OUTCOME
{opportunity.get('expected_outcome', '')}

TASK
{spec['instruction']}

VOICE AND CONSTRAINTS
- Sound knowledgeable, direct, calm, and human.
- Do not invent statistics, client details, or market facts.
- Use only the evidence supplied above unless general wording is clearly identified as general guidance.
- Avoid exaggerated claims, clichés, and generic AI language.
- Make the output ready to use with minimal editing.
""".strip()


def demo_execution_output(opportunity: dict[str, Any], asset_type: str) -> str:
    title = opportunity.get("title", "this opportunity")
    audience = opportunity.get("affected_audience", "local buyers and sellers")
    why_now = opportunity.get("why_now", "Timing matters because current signals indicate an active decision window.")

    if asset_type == "text_message":
        return f"Hi, this is Moody Glasgow. I wanted to reach out because I’m seeing renewed activity around {title.lower()}. I help {audience.lower()} make sense of the local options without adding pressure. Are you still considering a move, or has your timing changed?"
    if asset_type == "followup_email":
        return f"Subject: A helpful next step for your move\n\nHi,\n\nI’m reaching out because I’m seeing increased activity connected to {title.lower()}. {why_now}\n\nI can help you compare the local options, understand timing, and narrow the choices based on what matters most to you. There is no pressure—just practical local guidance.\n\nWould a brief call this week be useful?\n\nMoody Glasgow"
    if asset_type == "call_script":
        return f"OPENING\nHi, this is Moody Glasgow. I’m calling because I’m seeing increased activity around {title.lower()}, and I wanted to see whether that connects with your plans.\n\nDISCOVERY QUESTIONS\n1. Has your timing changed recently?\n2. What is the biggest question you still need answered?\n3. Are you comparing neighborhoods, price points, or whether to move at all?\n\nVALUE\nI can help you sort through the local options and give you a clear next step without pushing you into a decision.\n\nNEXT STEP\nWould it help to schedule a short planning call?"
    if asset_type == "linkedin_post":
        return f"A business opportunity is only useful when it leads to a clear action.\n\nMoodyAI identified {title} by combining current signals, audience needs, timing, and local market context. The important part is not the score—it is the decision behind it.\n\n{why_now}\n\nThe recommended response is focused: provide useful guidance, address the questions this audience is already asking, and make the next step easy.\n\nThat is the role of practical AI: turn scattered data into a decision a business can act on."
    if asset_type == "facebook_post":
        return f"I’m seeing more questions connected to {title.lower()}. {why_now}\n\nFor {audience.lower()}, the best first step is usually not looking at every available property. It is getting clear on timing, location, commute, budget, and the tradeoffs that matter most.\n\nI’m happy to help you sort through those decisions with straightforward local information. What is the biggest question you have right now?"
    if asset_type == "video_script":
        return f"HOOK\nThere is a real estate opportunity developing around {title.lower()}—but the signal matters only if we understand what to do with it.\n\nPOINT 1: WHAT IS HAPPENING\nMoodyAI identified activity from multiple sources and ranked it as a priority.\n\nPOINT 2: WHY IT MATTERS\n{why_now}\n\nPOINT 3: WHAT TO DO\nThe practical response is to answer the audience’s immediate questions, provide clear local comparisons, and create an easy path to a conversation.\n\nCLOSE\nIf you’re part of this market and need help sorting through the options, reach out. I’m Moody Glasgow, and I help clients make informed real estate decisions in Central Texas."
    if asset_type == "google_ads":
        return f"AD CONCEPT 1 — DECISION SUPPORT\nHeadlines: Local Real Estate Guidance | Compare Your Best Options | Talk With Moody Glasgow\nDescriptions: Get practical help evaluating timing, neighborhoods, and next steps related to {title}. Local guidance without the pressure.\nIntent: High-intent research\nLanding angle: Decision guide and consultation\n\nAD CONCEPT 2 — LOCAL EXPERTISE\nHeadlines: Central Texas Move Planning | Temple & Belton Home Guidance | Make a Clearer Move\nDescriptions: Understand the local tradeoffs before you decide. Get focused help based on your timing and priorities.\nIntent: Relocation planning\nLanding angle: Local comparison page"
    return f"# {title}: What It Means and What to Do Next\n\n## The opportunity\n{opportunity.get('executive_summary', '')}\n\n## Why this matters now\n{why_now}\n\n## What the evidence suggests\n" + "\n".join(f"- {e.get('statement', '')}" for e in opportunity.get('evidence', [])[:4]) + f"\n\n## A practical next step\nFor {audience.lower()}, the right response is clear, useful guidance that addresses timing, location, and the decisions that matter most.\n\n## Need help evaluating your options?\nMoody Glasgow provides straightforward local real estate guidance for Central Texas buyers, sellers, and relocating families."



@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    auth = _auth()
    if auth and auth.verify_token(request.cookies.get(auth.cookie_name)):
        return RedirectResponse("/learning", status_code=303)
    return FileResponse(ROOT / "static" / "login.html")


@app.post("/login", include_in_schema=False)
async def login(request: Request):
    auth = _auth()
    if auth is None:
        raise HTTPException(status_code=503, detail="Authentication is not configured. Run configure_step15.py.")
    body = (await request.body()).decode("utf-8", errors="replace")
    from urllib.parse import parse_qs
    password = parse_qs(body).get("password", [""])[0]
    if not auth.verify_password(password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        auth.cookie_name,
        auth.create_token(),
        max_age=auth.config.session_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=os.getenv("MOODYAI_SECURE_COOKIES", "false").lower() == "true",
        path="/",
    )
    return response


@app.post("/logout", include_in_schema=False)
def logout():
    response = JSONResponse({"authenticated": False})
    response.delete_cookie("moodyai_session", path="/")
    return response


@app.get("/health", include_in_schema=False)
def public_health():
    report = build_health_report(LEARNING_LEDGER.database_path, BACKGROUND_SYNC.status, DATABASE_BACKUPS.status)
    status_code = 503 if report["status"] == "unhealthy" else 200
    return JSONResponse(report, status_code=status_code)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/learning", include_in_schema=False)
def learning_console() -> FileResponse:
    return FileResponse(ROOT / "static" / "learning.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    opportunity_mode, _ = load_opportunities()
    return {
        "application": "MoodyAI",
        "status": "running",
        "version": "1.2.0",
        "timestamp": datetime.now().isoformat(),
        "integrations": {
            "openai": live_openai_available(),
            "follow_up_boss": live_fub_available(),
            "opportunity_engine": opportunity_mode == "live",
        },
    }


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    leads = get_leads()
    opportunity_mode, opportunities = load_opportunities()
    top = opportunities[0]
    immediate_actions = sum(
        1
        for opportunity in opportunities
        for action in opportunity.get("actions", [])
        if str(action.get("timeframe", "")).lower() == "today" and not action.get("completed", False)
    )
    return {
        "mode": "live" if opportunity_mode == "live" or leads["mode"] == "live" else "demo",
        "opportunity_mode": opportunity_mode,
        "metrics": [
            {"label": "Active opportunities", "value": len(opportunities), "detail": "Ranked business opportunities"},
            {"label": "Top opportunity score", "value": top.get("opportunity_score", 0), "detail": top.get("title", "Top opportunity")},
            {"label": "Actions due today", "value": immediate_actions, "detail": "Specific recommended actions"},
            {"label": "Top confidence", "value": f"{top.get('confidence_percent', 0)}%", "detail": top.get("confidence_level", "Confidence")},
        ],
        "top_opportunity": top,
        "system": {
            "Opportunity engine": "Live report" if opportunity_mode == "live" else "Portfolio demo",
            "OpenAI": "Connected" if live_openai_available() else "Demo mode",
            "Follow Up Boss": "Connected" if live_fub_available() else "Demo mode",
            "Knowledge base": "Ready",
        },
    }


@app.get("/api/opportunities")
def opportunities() -> dict[str, Any]:
    mode, items = load_opportunities()
    return {"mode": mode, "count": len(items), "items": items}


@app.get("/api/opportunities/{opportunity_id}")
def opportunity_detail(opportunity_id: str) -> dict[str, Any]:
    mode, items = load_opportunities()
    for item in items:
        if item.get("opportunity_id") == opportunity_id:
            return {"mode": mode, "item": item}
    raise HTTPException(status_code=404, detail="Opportunity not found")


@app.get("/api/leads")
def get_leads() -> dict[str, Any]:
    if live_fub_available():
        try:
            # Import from the top-level services package. Do not import from
            # ``app.*`` because this project also contains an interactive
            # app.py script that prompts for lead information at import time.
            from services.followupboss import get_people

            payload = get_people(limit=25)
            people = payload.get("people", []) if isinstance(payload, dict) else []
            normalized = [normalize_lead(person) for person in people]
            actionable = [item for item in normalized if item.get("needs_attention", True)]
            actionable.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
            return {
                "mode": "live",
                "items": actionable[:8],
                "suppressed_count": len(normalized) - len(actionable),
            }
        except Exception as exc:
            return {"mode": "demo", "items": DEMO_LEADS, "warning": f"Live CRM unavailable: {type(exc).__name__}"}
    return {"mode": "demo", "items": DEMO_LEADS}


@app.post("/api/recommendations/{recommendation_id}/decision")
def record_recommendation_decision(
    recommendation_id: str,
    payload: RecommendationDecisionRequest,
) -> dict[str, Any]:
    try:
        decision = DECISION_SERVICE.record_decision(
            recommendation_id=recommendation_id,
            status=payload.status,
            selected_action=payload.selected_action,
            reason=payload.reason,
            decided_by=payload.decided_by,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "recorded": True,
        "decision": {
            "decision_id": decision.decision_id,
            "recommendation_id": decision.recommendation_id,
            "status": decision.status,
            "selected_action": decision.selected_action,
            "reason": decision.reason,
            "decided_by": decision.decided_by,
            "decided_at": decision.decided_at,
        },
    }


@app.get("/api/recommendations/{recommendation_id}/decisions")
def recommendation_decisions(recommendation_id: str) -> dict[str, Any]:
    if LEARNING_LEDGER.get_recommendation(recommendation_id) is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    items = LEARNING_LEDGER.list_decisions(recommendation_id)
    return {
        "recommendation_id": recommendation_id,
        "count": len(items),
        "items": [
            {
                "decision_id": item.decision_id,
                "status": item.status,
                "selected_action": item.selected_action,
                "reason": item.reason,
                "decided_by": item.decided_by,
                "decided_at": item.decided_at,
            }
            for item in items
        ],
    }


@app.post("/api/recommendations/{recommendation_id}/executions")
def record_recommendation_execution(
    recommendation_id: str,
    payload: RecommendationExecutionRequest,
) -> dict[str, Any]:
    try:
        execution = EXECUTION_SERVICE.record_execution(
            recommendation_id=recommendation_id,
            action_type=payload.action_type,
            status=payload.status,
            notes=payload.notes,
            external_system=payload.external_system,
            external_reference=payload.external_reference,
            performed_by=payload.performed_by,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "recorded": True,
        "execution": {
            "execution_id": execution.execution_id,
            "recommendation_id": execution.recommendation_id,
            "action_type": execution.action_type,
            "status": execution.status,
            "notes": execution.notes,
            "external_system": execution.external_system,
            "external_reference": execution.external_reference,
            "performed_by": execution.performed_by,
            "performed_at": execution.performed_at,
        },
    }


@app.get("/api/recommendations/{recommendation_id}/executions")
def recommendation_executions(recommendation_id: str) -> dict[str, Any]:
    if LEARNING_LEDGER.get_recommendation(recommendation_id) is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    items = LEARNING_LEDGER.list_executions(recommendation_id)
    return {
        "recommendation_id": recommendation_id,
        "count": len(items),
        "items": [
            {
                "execution_id": item.execution_id,
                "action_type": item.action_type,
                "status": item.status,
                "notes": item.notes,
                "external_system": item.external_system,
                "external_reference": item.external_reference,
                "performed_by": item.performed_by,
                "performed_at": item.performed_at,
            }
            for item in items
        ],
    }


@app.post("/api/recommendations/{recommendation_id}/outcomes")
def record_recommendation_outcome(
    recommendation_id: str,
    payload: RecommendationOutcomeRequest,
) -> dict[str, Any]:
    try:
        outcome, inserted = OUTCOME_SERVICE.record_outcome_with_status(
            recommendation_id=recommendation_id,
            outcome_type=payload.outcome_type,
            outcome_value=payload.outcome_value,
            source=payload.source,
            attribution_confidence=payload.attribution_confidence,
            notes=payload.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "recorded": inserted,
        "duplicate": not inserted,
        "outcome": {
            "outcome_id": outcome.outcome_id,
            "recommendation_id": outcome.recommendation_id,
            "outcome_type": outcome.outcome_type,
            "outcome_value": outcome.outcome_value,
            "source": outcome.source,
            "attribution_confidence": outcome.attribution_confidence,
            "notes": outcome.notes,
            "observed_at": outcome.observed_at,
        },
    }


@app.get("/api/recommendations/{recommendation_id}/outcomes")
def recommendation_outcomes(recommendation_id: str) -> dict[str, Any]:
    if LEARNING_LEDGER.get_recommendation(recommendation_id) is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    items = LEARNING_LEDGER.list_outcomes(recommendation_id)
    return {
        "recommendation_id": recommendation_id,
        "count": len(items),
        "items": [
            {
                "outcome_id": item.outcome_id,
                "outcome_type": item.outcome_type,
                "outcome_value": item.outcome_value,
                "source": item.source,
                "attribution_confidence": item.attribution_confidence,
                "notes": item.notes,
                "observed_at": item.observed_at,
            }
            for item in items
        ],
    }




@app.get("/api/learning/backups/status")
def database_backup_status() -> dict[str, Any]:
    return DATABASE_BACKUPS.status()


@app.post("/api/learning/backups/run")
def run_database_backup_now() -> dict[str, Any]:
    return DATABASE_BACKUPS.run_once(force=True)


@app.get("/api/learning/background-sync/status")
def background_sync_status() -> dict[str, Any]:
    return BACKGROUND_SYNC.status()


@app.post("/api/learning/background-sync/run")
def run_background_sync_now() -> dict[str, Any]:
    """Optional diagnostic endpoint; normal operation requires no manual run."""
    return BACKGROUND_SYNC.run_once()


@app.get("/api/learning/fub-sync/preview")
def preview_fub_sync(limit: int = 25) -> dict[str, Any]:
    """Preview FUB activity matches without writing to the learning ledger."""
    if not live_fub_available():
        raise HTTPException(status_code=503, detail="Follow Up Boss is not configured")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    try:
        from services.followupboss import get_calls, get_events, get_text_messages

        service = FUBSyncPreviewService(
            LEARNING_LEDGER,
            get_calls=get_calls,
            get_text_messages=get_text_messages,
            get_events=get_events,
        )
        return service.preview(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc





def _fub_sync_services() -> tuple[FUBSyncPreviewService, FUBSyncImportService]:
    from services.followupboss import get_calls, get_events, get_text_messages

    preview_service = FUBSyncPreviewService(
        LEARNING_LEDGER,
        get_calls=get_calls,
        get_text_messages=get_text_messages,
        get_events=get_events,
    )
    return preview_service, FUBSyncImportService(LEARNING_LEDGER, preview_service)


@app.get("/api/learning/fub-sync/pending")
def list_pending_fub_sync_candidates(limit: int = 25) -> dict[str, Any]:
    if not live_fub_available():
        raise HTTPException(status_code=503, detail="Follow Up Boss is not configured")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    preview_service, import_service = _fub_sync_services()
    preview = preview_service.preview(limit=limit)
    reviewed = import_service.list_reviews(limit=1000)
    reviewed_keys = {
        (item["source_kind"], str(item["external_reference"])) for item in reviewed
    }
    pending = [
        item for item in preview.get("items", [])
        if (item.get("source_kind"), str(item.get("external_reference"))) not in reviewed_keys
    ]
    return {**preview, "candidate_count": len(pending), "items": pending, "reviewed_count": len(reviewed)}


@app.post("/api/learning/fub-sync/auto")
def auto_sync_fub_activity(limit: int = 50) -> dict[str, Any]:
    """Import clear FUB actions automatically; do not require duplicate entry."""
    if not live_fub_available():
        raise HTTPException(status_code=503, detail="Follow Up Boss is not configured")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    try:
        preview_service, _ = _fub_sync_services()
        activity_service = FUBAutoSyncService(LEARNING_LEDGER, preview_service)
        activity_result = activity_service.sync(limit=limit)

        from services.followupboss import get_person
        outcome_service = FUBAutoOutcomeService(LEARNING_LEDGER, get_person=get_person)
        outcome_result = outcome_service.sync(limit=min(limit, 100))

        total_changes = int(activity_result.get("imported_count", 0)) + int(outcome_result.get("imported_count", 0))
        if total_changes:
            LEARNING_EVALUATOR.evaluate_all()
        return {
            **activity_result,
            "automatic_outcomes": outcome_result,
            "automatic_outcome_count": outcome_result.get("imported_count", 0),
            "total_changes": total_changes,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/learning/fub-sync/reviews")
def list_fub_sync_reviews(status: str | None = None, limit: int = 100) -> dict[str, Any]:
    if not live_fub_available():
        raise HTTPException(status_code=503, detail="Follow Up Boss is not configured")
    try:
        _, import_service = _fub_sync_services()
        items = import_service.list_reviews(status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"count": len(items), "items": items}


@app.post("/api/learning/fub-sync/candidates/{candidate_id}/review")
def review_fub_sync_candidate(candidate_id: str, payload: FUBSyncReviewRequest) -> dict[str, Any]:
    if not live_fub_available():
        raise HTTPException(status_code=503, detail="Follow Up Boss is not configured")
    try:
        _, import_service = _fub_sync_services()
        return import_service.review_candidate(
            candidate_id,
            status=payload.status,
            import_outcome=payload.import_outcome,
            reason=payload.reason,
            reviewed_by=payload.reviewed_by,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/learning/evaluate")
def evaluate_learning_records() -> dict[str, Any]:
    result = LEARNING_EVALUATOR.evaluate_all()
    return {
        **result,
        "summary": LEARNING_EVALUATOR.summary(),
    }


@app.get("/api/learning/summary")
def learning_summary() -> dict[str, Any]:
    return LEARNING_EVALUATOR.summary()


@app.get("/api/recommendations/{recommendation_id}/evaluation")
def recommendation_evaluation(recommendation_id: str) -> dict[str, Any]:
    if LEARNING_LEDGER.get_recommendation(recommendation_id) is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    evaluation = LEARNING_LEDGER.get_evaluation_for_recommendation(recommendation_id)
    return {
        "recommendation_id": recommendation_id,
        "evaluation": (
            {
                "evaluation_id": evaluation.evaluation_id,
                "policy_version": evaluation.policy_version,
                "predicted_class": evaluation.predicted_class,
                "score": evaluation.score,
                "highest_outcome": evaluation.highest_outcome,
                "outcome_rank": evaluation.outcome_rank,
                "result_class": evaluation.result_class,
                "prediction_correct": evaluation.prediction_correct,
                "action_effective": evaluation.action_effective,
                "evaluated_at": evaluation.evaluated_at,
            }
            if evaluation
            else None
        ),
    }


class PolicyProposalReviewRequest(BaseModel):
    status: str = Field(..., min_length=7, max_length=8)
    reason: str | None = Field(default=None, max_length=4000)
    reviewed_by: str = Field(default="Moody", min_length=1, max_length=200)


@app.post("/api/learning/proposals/generate")
def generate_policy_proposals() -> dict[str, Any]:
    return POLICY_ADAPTATION_SERVICE.generate_proposals()


@app.get("/api/learning/proposals")
def list_policy_proposals(status: str | None = None) -> dict[str, Any]:
    try:
        items = LEARNING_LEDGER.list_policy_proposals(status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "count": len(items),
        "automatic_activation": False,
        "items": [
            {
                "proposal_id": item.proposal_id,
                "current_policy_version": item.current_policy_version,
                "proposed_policy_version": item.proposed_policy_version,
                "feature_name": item.feature_name,
                "current_weight": item.current_weight,
                "proposed_weight": item.proposed_weight,
                "direction": item.direction,
                "sample_size": item.sample_size,
                "feature_present_sample": item.feature_present_sample,
                "feature_absent_sample": item.feature_absent_sample,
                "feature_positive_rate": item.feature_positive_rate,
                "baseline_positive_rate": item.baseline_positive_rate,
                "effect_size": item.effect_size,
                "minimum_effect": item.minimum_effect,
                "rationale": item.rationale,
                "status": item.status,
                "created_at": item.created_at,
                "reviewed_at": item.reviewed_at,
                "reviewed_by": item.reviewed_by,
                "review_reason": item.review_reason,
            }
            for item in items
        ],
    }


@app.post("/api/learning/proposals/{proposal_id}/review")
def review_policy_proposal(
    proposal_id: str, payload: PolicyProposalReviewRequest
) -> dict[str, Any]:
    try:
        proposal = POLICY_ADAPTATION_SERVICE.review_proposal(
            proposal_id,
            status=payload.status,
            reason=payload.reason,
            reviewed_by=payload.reviewed_by,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "reviewed": True,
        "activated": False,
        "proposal": {
            "proposal_id": proposal.proposal_id,
            "status": proposal.status,
            "current_policy_version": proposal.current_policy_version,
            "proposed_policy_version": proposal.proposed_policy_version,
            "feature_name": proposal.feature_name,
            "current_weight": proposal.current_weight,
            "proposed_weight": proposal.proposed_weight,
            "reviewed_at": proposal.reviewed_at,
            "reviewed_by": proposal.reviewed_by,
            "review_reason": proposal.review_reason,
        },
    }


class PolicyActivationRequest(BaseModel):
    actor: str = Field(default="Moody", min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4000)


@app.get("/api/learning/policies")
def list_scoring_policies() -> dict[str, Any]:
    active = POLICY_REGISTRY.get_active_policy()
    items = POLICY_REGISTRY.list_policies()
    return {
        "active_policy_version": active.version,
        "count": len(items),
        "items": [
            {
                "version": item.version,
                "parent_version": item.parent_version,
                "status": item.status,
                "weights": item.weights,
                "thresholds": item.thresholds,
                "created_from_proposal": item.created_from_proposal,
                "created_at": item.created_at,
                "activated_at": item.activated_at,
                "retired_at": item.retired_at,
            }
            for item in items
        ],
    }


@app.post("/api/learning/proposals/{proposal_id}/candidate")
def create_candidate_policy(proposal_id: str) -> dict[str, Any]:
    try:
        policy = POLICY_REGISTRY.create_candidate_from_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"created": True, "activated": False, "policy": {
        "version": policy.version, "status": policy.status,
        "parent_version": policy.parent_version, "weights": policy.weights,
        "thresholds": policy.thresholds,
    }}


@app.post("/api/learning/policies/{policy_version}/backtest")
def backtest_scoring_policy(policy_version: str) -> dict[str, Any]:
    try:
        return POLICY_REGISTRY.backtest(policy_version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/learning/policies/{policy_version}/activate")
def activate_scoring_policy(policy_version: str, payload: PolicyActivationRequest) -> dict[str, Any]:
    try:
        policy = POLICY_REGISTRY.activate(
            policy_version, actor=payload.actor, reason=payload.reason
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"activated": True, "active_policy_version": policy.version}


@app.post("/api/learning/policies/{policy_version}/rollback")
def rollback_scoring_policy(policy_version: str, payload: PolicyActivationRequest) -> dict[str, Any]:
    try:
        policy = POLICY_REGISTRY.rollback(
            policy_version, actor=payload.actor, reason=payload.reason
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"rolled_back": True, "active_policy_version": policy.version}


@app.post("/api/execution/prompt")
def get_execution_prompt(payload: ExecutionPromptRequest) -> dict[str, Any]:
    opportunity = find_opportunity(payload.opportunity_id)
    spec = ASSET_SPECS.get(payload.asset_type)
    if not spec:
        raise HTTPException(status_code=400, detail="Unsupported asset type")
    prompt = execution_prompt(opportunity, payload.asset_type)
    return {
        "mode": "live" if live_openai_available() else "demo",
        "asset_type": payload.asset_type,
        "label": spec["label"],
        "prompt": prompt,
    }


@app.post("/api/execution/generate")
def generate_execution_asset(payload: ExecutionGenerateRequest) -> dict[str, Any]:
    opportunity = find_opportunity(payload.opportunity_id)
    spec = ASSET_SPECS.get(payload.asset_type)
    if not spec:
        raise HTTPException(status_code=400, detail="Unsupported asset type")

    prompt = (payload.prompt or execution_prompt(opportunity, payload.asset_type)).strip()
    if len(prompt) < 20:
        raise HTTPException(status_code=400, detail="Prompt is too short")

    if live_openai_available():
        try:
            from openai import OpenAI

            output_limits = {
                "text_message": 220,
                "followup_email": 500,
                "call_script": 650,
                "linkedin_post": 500,
                "facebook_post": 400,
                "google_ads": 900,
                "video_script": 1200,
                "blog_article": 2400,
            }
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=40.0)
            response = client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                input=prompt,
                max_output_tokens=output_limits.get(payload.asset_type, 1200),
            )
            return {
                "mode": "live",
                "asset_type": payload.asset_type,
                "label": spec["label"],
                "output": response.output_text.strip(),
                "prompt": prompt,
                "grounding": ["Opportunity audience", "Recorded evidence", "AI reasoning", "Business goal"],
            }
        except Exception as exc:
            return {
                "mode": "demo",
                "asset_type": payload.asset_type,
                "label": spec["label"],
                "output": demo_execution_output(opportunity, payload.asset_type),
                "prompt": prompt,
                "grounding": ["Opportunity audience", "Recorded evidence", "AI reasoning", "Business goal"],
                "warning": f"Live generation unavailable: {type(exc).__name__}",
            }

    return {
        "mode": "demo",
        "asset_type": payload.asset_type,
        "label": spec["label"],
        "output": demo_execution_output(opportunity, payload.asset_type),
        "prompt": prompt,
        "grounding": ["Opportunity audience", "Recorded evidence", "AI reasoning", "Business goal"],
    }


@app.post("/api/advisor")
def advisor(payload: AdvisorRequest) -> dict[str, Any]:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    if live_openai_available():
        try:
            from openai import OpenAI

            knowledge_path = ROOT / "knowledge" / "bell_county.txt"
            knowledge = knowledge_path.read_text(encoding="utf-8") if knowledge_path.exists() else ""
            _, opportunities = load_opportunities()
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                input=(
                    "You are MoodyAI, Moody Glasgow's concise real-estate business intelligence advisor. "
                    "Use the opportunity data and local knowledge when relevant. Give a direct recommendation, "
                    "supporting reasoning, and one next action.\n\n"
                    f"CURRENT OPPORTUNITIES:\n{json.dumps(opportunities[:5], indent=2)[:18000]}\n\n"
                    f"LOCAL KNOWLEDGE:\n{knowledge[:8000]}\n\nQUESTION:\n{question}"
                ),
            )
            return {"mode": "live", "answer": response.output_text}
        except Exception as exc:
            return {"mode": "demo", "answer": demo_advisor_answer(question), "warning": f"Live AI unavailable: {type(exc).__name__}"}

    return {"mode": "demo", "answer": demo_advisor_answer(question)}


def demo_advisor_answer(question: str) -> str:
    lowered = question.lower()
    _, opportunities = load_opportunities()
    top = opportunities[0]
    if "opportun" in lowered or "first" in lowered or "today" in lowered:
        actions = [a for a in top.get("actions", []) if str(a.get("timeframe", "")).lower() == "today"]
        first_action = actions[0].get("title") if actions else "open the top opportunity and complete its first action"
        return f"Prioritize {top.get('title')}. It has the highest combined score and confidence in the current report. Your next action is to {first_action.lower()}."
    if "lead" in lowered or "follow" in lowered:
        return "Prioritize the highest-intent lead with recent activity. Send a personal text, follow with a call, and record timing, motivation, and next step in Follow Up Boss."
    if "content" in lowered or "seo" in lowered or "search" in lowered:
        return "The strongest content opportunity is physician relocation around Baylor Scott & White Temple, especially decision-focused neighborhood and cost comparisons. Publish the highest-priority open page and link it from the existing BSW content cluster."
    return f"The current top opportunity is {top.get('title')}. Its score is {top.get('opportunity_score')}/100 with {top.get('confidence_percent')}% confidence. Open the full analysis and complete the highest-priority action due today."
