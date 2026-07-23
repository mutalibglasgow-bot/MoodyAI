from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_PATH = ROOT / "static" / "learning.html"


class LearningConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = CONSOLE_PATH.read_text(encoding="utf-8")

    def test_console_file_exists(self) -> None:
        self.assertTrue(CONSOLE_PATH.exists())

    def test_console_uses_simplified_next_action_language(self) -> None:
        for text in (
            "Priority leads",
            "Next action",
            "Recommended next step",
            "What MoodyAI detected",
            "Current result",
        ):
            with self.subTest(text=text):
                self.assertIn(text, self.html)

    def test_console_reads_required_automatic_workflow_endpoints(self) -> None:
        for endpoint in (
            "/api/leads",
            "/api/learning/summary",
            "/api/learning/background-sync/status",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, self.html)

    def test_console_can_record_uncertain_outcomes(self) -> None:
        self.assertIn("/api/recommendations/${rid}/outcomes", self.html)

        for outcome in (
            "replied",
            "appointment_booked",
            "no_response",
            "not_interested",
        ):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, self.html)

    def test_console_does_not_restore_removed_manual_workflow(self) -> None:
        # Calls and texts are detected from FUB automatically.
        self.assertNotIn("<option>accepted</option>", self.html)
        self.assertNotIn("Save decision", self.html)
        self.assertNotIn("Record execution", self.html)
        self.assertNotIn("Approve execution", self.html)

    def test_console_explains_automatic_fub_monitoring(self) -> None:
        self.assertIn("watches Follow Up Boss automatically", self.html)
        self.assertIn("You only need to answer", self.html)


if __name__ == "__main__":
    unittest.main()
