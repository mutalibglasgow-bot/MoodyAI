import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

from agents.sensors.base_sensor import Signal


class TEDCSensor:
    name = "Temple EDC / Growth Sensor"

    URLS = [
        "https://templeedc.com/",
        "https://templeedc.com/news-press/",
        "https://templeedc.com/news-press/news/",
        "https://www.templetx.gov/community/data_center_development.php",
    ]

    GROWTH_KEYWORDS = [
        "data center", "investment", "jobs", "acres", "land",
        "industrial", "distribution", "manufacturing", "expansion",
        "incentive", "tax abatement", "infrastructure", "business park",
        "development", "site", "facility", "warehouse", "employer",
    ]

    HIGH_VALUE_KEYWORDS = [
        "data center", "million", "billion", "acres", "jobs",
        "investment", "industrial", "distribution", "manufacturing",
        "expansion", "business park",
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

    def extract_growth_lines(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        matches = []

        for line in lines:
            clean = re.sub(r"\s+", " ", line).strip()
            lower = clean.lower()

            if len(clean) < 20 or len(clean) > 220:
                continue

            if any(keyword in lower for keyword in self.GROWTH_KEYWORDS):
                matches.append(clean)

        unique = []
        seen = set()

        for line in matches:
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(line)

        return unique[:40]

    def classify_growth(self, lines):
        data_center_count = 0
        jobs_mentions = 0
        investment_mentions = 0
        acreage_mentions = 0
        industrial_mentions = 0

        for line in lines:
            lower = line.lower()

            if "data center" in lower:
                data_center_count += 1

            if "jobs" in lower or "employees" in lower:
                jobs_mentions += 1

            if "million" in lower or "billion" in lower or "investment" in lower:
                investment_mentions += 1

            if "acre" in lower or "land" in lower:
                acreage_mentions += 1

            if "industrial" in lower or "distribution" in lower or "manufacturing" in lower:
                industrial_mentions += 1

        score = 40
        score += data_center_count * 12
        score += investment_mentions * 8
        score += acreage_mentions * 8
        score += jobs_mentions * 6
        score += industrial_mentions * 8

        return {
            "data_center_count": data_center_count,
            "jobs_mentions": jobs_mentions,
            "investment_mentions": investment_mentions,
            "acreage_mentions": acreage_mentions,
            "industrial_mentions": industrial_mentions,
            "business_value_score": min(score, 100),
        }

    def collect(self):
        all_lines = []

        for url in self.URLS:
            try:
                html = self.fetch_page(url)
                text = self.extract_text(html)
                lines = self.extract_growth_lines(text)
                all_lines.extend(lines)
            except Exception as e:
                print(f"  TEDC source failed: {url} — {e}")

        unique_lines = []
        seen = set()

        for line in all_lines:
            key = line.lower()
            if key not in seen:
                seen.add(key)
                unique_lines.append(line)

        if not unique_lines:
            return []

        stats = self.classify_growth(unique_lines)
        examples = unique_lines[:8]

        summary = (
            f"Detected {len(unique_lines)} Temple growth and economic-development signals. "
            f"Data center mentions: {stats['data_center_count']}. "
            f"Investment mentions: {stats['investment_mentions']}. "
            f"Acreage/land mentions: {stats['acreage_mentions']}. "
            f"Jobs/employment mentions: {stats['jobs_mentions']}. "
            f"Industrial/distribution/manufacturing mentions: {stats['industrial_mentions']}. "
            f"Examples: {'; '.join(examples)}"
        )

        why = (
            "Temple economic-development activity is a leading indicator of future housing demand. "
            "Major employers, industrial projects, data centers, land purchases, and infrastructure "
            "investment can create future buyers, sellers, investors, builders, renters, and relocation clients."
        )

        return [
            Signal(
                signal_name="Temple Growth / Economic Development Activity Detected",
                source="Temple EDC / City of Temple Growth Sources",
                signal_type="Economic Development",
                summary=summary,
                why_it_matters=why,
                affected_opportunities=[
                    "High-Equity Homeowners",
                    "Local Home Sellers",
                    "Residential Investors",
                    "Executive Corporate Relocations",
                    "New Construction Buyers",
                    "Move-Up Buyers",
                    "Remote Workers & Digital Professionals",
                    "Acreage & Ranch Buyers",
                ],
                likely_client_types=[
                    "Investors",
                    "Builders",
                    "High-equity homeowners",
                    "Corporate relocation buyers",
                    "Move-up buyers",
                    "Local sellers near growth corridors",
                    "Employees relocating for new jobs",
                ],
                future_questions_people_will_ask=[
                    "What is being built in Temple?",
                    "Will this development affect home values?",
                    "Should I buy before prices rise?",
                    "Which neighborhoods will benefit from growth?",
                    "Is East or South Temple becoming a growth corridor?",
                    "Should investors buy near new development?",
                    "Will data centers affect Temple real estate?",
                ],
                time_horizon="6-36 months",
                confidence=0.8,
                business_value_score=stats["business_value_score"],
                generated_at=datetime.now().isoformat(),
            )
        ]