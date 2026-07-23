from __future__ import annotations

import unittest
from pathlib import Path

from moodyai_learning.today_brief import build_today_brief


class TodayBriefTests(unittest.TestCase):
    def test_prioritizes_and_limits_actionable_items(self) -> None:
        payload = {
            "mode": "live",
            "suppressed_count": 4,
            "items": [
                {"name": "Low", "score": 25, "needs_attention": True, "workflow_state": "action_needed"},
                {"name": "High", "score": 95, "needs_attention": True, "workflow_state": "action_needed", "temperature": "HOT"},
                {"name": "Done", "score": 100, "needs_attention": False, "workflow_state": "resolved"},
            ],
        }
        brief = build_today_brief(payload, max_items=1)
        self.assertEqual(brief["items"][0]["name"], "High")
        self.assertEqual(brief["counts"]["shown"], 1)
        self.assertEqual(brief["counts"]["suppressed"], 4)

    def test_empty_brief_creates_no_noise(self) -> None:
        brief = build_today_brief({"mode": "live", "items": []})
        self.assertEqual(brief["counts"]["shown"], 0)
        self.assertIn("Nothing needs", brief["headline"])

    def test_today_page_uses_today_endpoint_and_plain_language(self) -> None:
        html = (Path(__file__).resolve().parents[1] / "static" / "today.html").read_text(encoding="utf-8")
        self.assertIn("/api/today", html)
        self.assertIn("Only the work that genuinely needs your attention", html)
        self.assertIn("Nothing needs action right now", html)

    def test_main_exposes_protected_today_routes(self) -> None:
        main = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn('"/today"', main)
        self.assertIn('"/api/today"', main)
        self.assertIn("build_today_brief", main)


if __name__ == "__main__":
    unittest.main()
