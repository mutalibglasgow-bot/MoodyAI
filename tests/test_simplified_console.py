from pathlib import Path
import unittest

class SimplifiedConsoleTests(unittest.TestCase):
    def test_console_uses_plain_language(self):
        html = (Path(__file__).resolve().parents[1] / "static" / "learning_simple.html").read_text()
        self.assertIn("Recommended next step", html)
        self.assertIn("What MoodyAI detected", html)
        self.assertIn("Current result", html)
        self.assertNotIn("Human decision", html)
        self.assertNotIn("Approve execution", html)
        self.assertNotIn("FUB activity review", html)

if __name__ == "__main__": unittest.main()
