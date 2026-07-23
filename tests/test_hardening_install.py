from __future__ import annotations

import unittest
from pathlib import Path


class HardeningInstallTests(unittest.TestCase):
    def test_main_contains_auth_and_public_health_routes(self) -> None:
        text = Path("main.py").read_text()
        self.assertIn('app.middleware("http")', text)
        self.assertIn('@app.get("/login"', text)
        self.assertIn('@app.get("/health"', text)
        self.assertIn('AuthConfig.from_environment()', text)

    def test_login_page_exists(self) -> None:
        text = Path("static/login.html").read_text()
        self.assertIn("Sign in", text)
        self.assertIn("/login", text)
