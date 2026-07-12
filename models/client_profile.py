from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import os


@dataclass
class Identity:
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    preferred_contact: Optional[str] = None
    source: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Opportunity:
    category: Optional[str] = None
    subcategory: Optional[str] = None
    confidence: int = 0
    priority: int = 0


@dataclass
class Household:
    adults: Optional[int] = None
    children: Optional[int] = None
    pets: List[str] = field(default_factory=list)
    schools_matter: Optional[bool] = None
    special_notes: Optional[str] = None


@dataclass
class Employment:
    employer: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    start_date: Optional[str] = None
    commute_importance: Optional[str] = None


@dataclass
class Financial:
    budget: Optional[int] = None
    buy_or_rent: Optional[str] = None
    financing_type: Optional[str] = None


@dataclass
class Timeline:
    move_timeline: Optional[str] = None
    urgency: Optional[str] = None
    long_term_intent: Optional[bool] = None


@dataclass
class Lifestyle:
    privacy: int = 0
    lake_access: int = 0
    luxury: int = 0
    small_town: int = 0
    walkability: int = 0
    new_construction: int = 0
    land: int = 0
    investment: int = 0


@dataclass
class Relationship:
    trust_score: int = 0
    stage: str = "Discovery"
    last_contact: Optional[str] = None
    next_action: Optional[str] = None


@dataclass
class Revenue:
    expected_commission: Optional[int] = None
    expected_relationship_value: Optional[int] = None
    referral_potential: Optional[str] = None
    roi_priority: Optional[str] = None


@dataclass
class CommunityMatch:
    recommended_areas: Dict[str, int] = field(default_factory=dict)
    best_fit: Optional[str] = None
    reasoning: Optional[str] = None


@dataclass
class ContentPlan:
    recommended_content: List[str] = field(default_factory=list)
    recommended_videos: List[str] = field(default_factory=list)
    sent_content: List[str] = field(default_factory=list)


@dataclass
class CRM:
    fub_person_id: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ClientProfile:
    profile_id: str
    identity: Identity = field(default_factory=Identity)
    opportunity: Opportunity = field(default_factory=Opportunity)
    persona: Optional[str] = None
    household: Household = field(default_factory=Household)
    employment: Employment = field(default_factory=Employment)
    financial: Financial = field(default_factory=Financial)
    timeline: Timeline = field(default_factory=Timeline)
    lifestyle: Lifestyle = field(default_factory=Lifestyle)
    priorities: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)
    community_match: CommunityMatch = field(default_factory=CommunityMatch)
    relationship: Relationship = field(default_factory=Relationship)
    revenue: Revenue = field(default_factory=Revenue)
    content_plan: ContentPlan = field(default_factory=ContentPlan)
    crm: CRM = field(default_factory=CRM)
    raw_conversation: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def save(self, folder: str = "data/client_profiles") -> str:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{self.profile_id}.json")

        with open(path, "w") as file:
            file.write(self.to_json())

        return path

    @staticmethod
    def load(path: str) -> "ClientProfile":
        with open(path, "r") as file:
            data = json.load(file)

        return client_profile_from_dict(data)


def client_profile_from_dict(data: Dict[str, Any]) -> ClientProfile:
    profile = ClientProfile(profile_id=data["profile_id"])

    profile.identity = Identity(**data.get("identity", {}))
    profile.opportunity = Opportunity(**data.get("opportunity", {}))
    profile.persona = data.get("persona")
    profile.household = Household(**data.get("household", {}))
    profile.employment = Employment(**data.get("employment", {}))
    profile.financial = Financial(**data.get("financial", {}))
    profile.timeline = Timeline(**data.get("timeline", {}))
    profile.lifestyle = Lifestyle(**data.get("lifestyle", {}))
    profile.priorities = data.get("priorities", [])
    profile.concerns = data.get("concerns", [])
    profile.community_match = CommunityMatch(**data.get("community_match", {}))
    profile.relationship = Relationship(**data.get("relationship", {}))
    profile.revenue = Revenue(**data.get("revenue", {}))
    profile.content_plan = ContentPlan(**data.get("content_plan", {}))
    profile.crm = CRM(**data.get("crm", {}))
    profile.raw_conversation = data.get("raw_conversation", [])

    return profile
