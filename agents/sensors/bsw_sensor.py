import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

from agents.sensors.base_sensor import Signal


class BSWSensor:
    name = "BSW Healthcare Sensor"

    URLS = [
        "https://jobs.bswhealth.com/us/en/temple-kileen",
        "https://jobs.bswhealth.com/us/en/physician",
        "https://bswh.dejobs.org/locations/temple-tx/jobs/",
        "https://employer.practicematch.com/employer/baylor-scott-physician-jobs/",
    ]

    LOCAL_MARKETS = ["temple", "belton", "killeen", "waco", "round rock", "central texas"]

    ROLE_CLASSES = {
        "surgeon": {
            "keywords": ["surgeon", "surgery", "orthopedic", "cardiothoracic", "colorectal"],
            "label": "Surgeon / High-Income Specialist",
            "home_price_min": 700000,
            "home_price_max": 1800000,
            "relocation_probability": 0.85,
            "value_weight": 10,
        },
        "attending_physician": {
            "keywords": [
                "physician", "hospitalist", "cardiologist", "oncologist", "radiologist",
                "psychiatrist", "pulmonary", "gastroenterology", "internal medicine",
                "family medicine", "emergency medicine", "pediatric"
            ],
            "label": "Attending Physician / Specialist",
            "home_price_min": 500000,
            "home_price_max": 1200000,
            "relocation_probability": 0.75,
            "value_weight": 8,
        },
        "executive": {
            "keywords": ["director", "executive", "administrator", "chief", "vp", "president"],
            "label": "Healthcare Executive / Leadership",
            "home_price_min": 650000,
            "home_price_max": 1500000,
            "relocation_probability": 0.7,
            "value_weight": 8,
        },
        "advanced_practice": {
            "keywords": ["nurse practitioner", "physician assistant", "crna", "advanced practice"],
            "label": "Advanced Practice Provider",
            "home_price_min": 300000,
            "home_price_max": 650000,
            "relocation_probability": 0.45,
            "value_weight": 5,
        },
        "nursing": {
            "keywords": ["registered nurse", " rn ", "nurse", "nursing"],
            "label": "Nursing / Clinical Staff",
            "home_price_min": 250000,
            "home_price_max": 500000,
            "relocation_probability": 0.35,
            "value_weight": 3,
        },
        "recruiting": {
            "keywords": ["recruiter", "recruitment", "talent acquisition"],
            "label": "Healthcare Recruiting Signal",
            "home_price_min": 0,
            "home_price_max": 0,
            "relocation_probability": 0.0,
            "value_weight": 4,
        },
    }

    GENERIC_EXCLUDE = [
        "when you join",
        "you’ll be part",
        "you'll be part",
        "serves approximately",
        "largest not-for-profit",
        "each of our physicians",
        "unique contributions",
        "united in the belief",
        "patient is the center",
        "inclusive culture",
        "faith-based system",
        "medicine is driven",
        "as a baylor scott",
        "i am lucky",
        "bswhealth.com",
        "for more information",
        "powered by practicematch",
        "job openings",
        "physicians | baylor",
        "privacy policy",
        "terms of use",
        "equal opportunity",
    ]

    def fetch_page(self, url):
        headers = {"User-Agent": "Mozilla/5.0 RealEstateAI/1.0"}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.text

    def extract_text(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text("\n", strip=True)

    def is_generic_line(self, line):
        lower = line.lower()
        return any(x in lower for x in self.GENERIC_EXCLUDE)

    def classify_role(self, line):
        lower = f" {line.lower()} "

        for role_key, config in self.ROLE_CLASSES.items():
            if any(keyword in lower for keyword in config["keywords"]):
                return role_key, config

        return None, None

    def looks_like_job_posting(self, line):
        line = re.sub(r"\s+", " ", line).strip()
        lower = line.lower()

        if len(line) < 8 or len(line) > 120:
            return False

        if self.is_generic_line(line):
            return False

        role_key, _ = self.classify_role(line)

        if not role_key:
            return False

        word_count = len(line.split())

        has_local_market = any(market in lower for market in self.LOCAL_MARKETS)

        # Local healthcare lines are strong.
        if has_local_market:
            return True

        # Short title-like lines are acceptable.
        if word_count <= 10:
            return True

        return False

    def extract_job_lines(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        jobs = []

        for line in lines:
            clean = re.sub(r"\s+", " ", line).strip()

            if self.looks_like_job_posting(clean):
                role_key, role_config = self.classify_role(clean)
                location = self.extract_location(clean)

                jobs.append({
                    "title": clean,
                    "role_key": role_key,
                    "role_label": role_config["label"],
                    "location": location,
                    "home_price_min": role_config["home_price_min"],
                    "home_price_max": role_config["home_price_max"],
                    "relocation_probability": role_config["relocation_probability"],
                    "value_weight": role_config["value_weight"],
                })

        unique = []
        seen = set()

        for job in jobs:
            key = job["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(job)

        return unique[:50]

    def extract_location(self, line):
        lower = line.lower()

        for market in self.LOCAL_MARKETS:
            if market in lower:
                return market.title()

        return "Unknown"

    def summarize_jobs(self, jobs):
        counts = {}
        estimated_relocations = 0
        estimated_housing_demand_low = 0
        estimated_housing_demand_high = 0
        total_weight = 0
        local_count = 0

        for job in jobs:
            label = job["role_label"]
            counts[label] = counts.get(label, 0) + 1

            relocation_probability = job["relocation_probability"]
            estimated_relocations += relocation_probability

            estimated_housing_demand_low += job["home_price_min"] * relocation_probability
            estimated_housing_demand_high += job["home_price_max"] * relocation_probability

            total_weight += job["value_weight"]

            if job["location"] != "Unknown":
                local_count += 1

        score = 40 + total_weight + (local_count * 5)

        return {
            "counts": counts,
            "estimated_relocations": round(estimated_relocations, 1),
            "estimated_housing_demand_low": int(estimated_housing_demand_low),
            "estimated_housing_demand_high": int(estimated_housing_demand_high),
            "local_count": local_count,
            "business_value_score": min(score, 100),
        }

    def collect(self):
        all_jobs = []

        for url in self.URLS:
            try:
                html = self.fetch_page(url)
                text = self.extract_text(html)
                jobs = self.extract_job_lines(text)
                all_jobs.extend(jobs)
            except Exception as e:
                print(f"  BSW source failed: {url} — {e}")

        unique_jobs = []
        seen = set()

        for job in all_jobs:
            key = job["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            unique_jobs.append(job)

        if not unique_jobs:
            return []

        stats = self.summarize_jobs(unique_jobs)
        examples = [job["title"] for job in unique_jobs[:8]]

        role_summary = "; ".join(
            [f"{label}: {count}" for label, count in stats["counts"].items()]
        )

        housing_range = (
            f"${stats['estimated_housing_demand_low']:,} - "
            f"${stats['estimated_housing_demand_high']:,}"
        )

        summary = (
            f"Detected {len(unique_jobs)} classified BSW healthcare hiring signals. "
            f"Role mix: {role_summary}. "
            f"Estimated relocations: {stats['estimated_relocations']}. "
            f"Estimated housing demand range: {housing_range}. "
            f"Examples: {'; '.join(examples)}"
        )

        why = (
            "BSW healthcare hiring is a leading indicator of future relocation demand. "
            "Physicians, specialists, healthcare executives, advanced practice providers, "
            "and clinical staff create housing demand before they begin searching for a Realtor."
        )

        return [
            Signal(
                signal_name="BSW Healthcare Hiring Demand Classified",
                source="BSW Careers / BSW Job Sources",
                signal_type="Healthcare Employment",
                summary=summary,
                why_it_matters=why,
                affected_opportunities=[
                    "BSW Attending Physicians",
                    "BSW Residents & Fellows",
                    "High-Income Healthcare Professionals",
                    "Executive Corporate Relocations",
                    "Luxury Home Buyers",
                    "Move-Up Buyers",
                    "Belton Sellers",
                ],
                likely_client_types=[
                    "Attending physicians",
                    "Surgeons",
                    "Medical specialists",
                    "Healthcare executives",
                    "Advanced practice providers",
                    "Relocating healthcare families",
                ],
                future_questions_people_will_ask=[
                    "Where should I live if I work at BSW Temple?",
                    "Is Belton or Temple better for BSW physicians?",
                    "What neighborhoods are best near BSW?",
                    "Should I buy or rent first?",
                    "What is the commute to BSW?",
                    "What schools and lifestyle options should we consider?",
                    "What physician mortgage options are available?",
                ],
                time_horizon="30-180 days",
                confidence=0.9,
                business_value_score=stats["business_value_score"],
                generated_at=datetime.now().isoformat(),
            )
        ]