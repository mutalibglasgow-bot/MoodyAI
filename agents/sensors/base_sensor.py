from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
import os


@dataclass
class Signal:
    signal_name: str
    source: str
    signal_type: str
    summary: str
    why_it_matters: str
    affected_opportunities: List[str]
    likely_client_types: List[str]
    future_questions_people_will_ask: List[str]
    time_horizon: str
    confidence: float
    business_value_score: int
    generated_at: str = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseSensor:
    name = "Base Sensor"

    def collect(self) -> List[Signal]:
        raise NotImplementedError("Each sensor must implement collect().")

    def read_file(self, path: str) -> str:
        if not os.path.exists(path):
            return ""
        with open(path, "r") as file:
            return file.read()

    def read_recent_text_files(self, folder: str, limit: int = 5) -> str:
        if not os.path.exists(folder):
            return ""

        files = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.endswith(".txt") or f.endswith(".md") or f.endswith(".json")
        ]

        files.sort(reverse=True)

        output = []

        for path in files[:limit]:
            output.append(f"\n\n--- FILE: {path} ---\n")
            output.append(self.read_file(path))

        return "\n".join(output)

    def clean_json_text(self, text: str) -> str:
        cleaned = text.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned.replace("```json", "", 1).strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```", "", 1).strip()

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        return cleaned

    def parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self.clean_json_text(text))
        except json.JSONDecodeError:
            return None