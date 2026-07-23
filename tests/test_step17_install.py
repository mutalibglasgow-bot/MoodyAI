from pathlib import Path
import unittest

class Step17InstallTests(unittest.TestCase):
    def test_main_has_request_logging_and_readiness(self):
        text = Path("main.py").read_text()
        self.assertIn("RequestLogMiddleware", text)
        self.assertIn('@app.get("/ready")', text)
        self.assertIn("validate_startup", text)

    def test_production_runner_is_single_worker(self):
        text = Path("run_production.py").read_text()
        self.assertIn("workers=1", text)
        self.assertNotIn("reload=True", text)
