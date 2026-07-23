from __future__ import annotations

import unittest
from pathlib import Path


class BackgroundConsoleTests(unittest.TestCase):
    def test_console_uses_background_status_not_manual_sync(self) -> None:
        html = Path("static/learning.html").read_text()
        self.assertIn("/api/learning/background-sync/status", html)
        self.assertNotIn("api('/api/learning/fub-sync/auto',{method:'POST'})", html)
        self.assertIn("Watching Follow Up Boss automatically", html)

    def test_main_registers_background_routes(self) -> None:
        text = Path("main.py").read_text()
        self.assertIn('/api/learning/background-sync/status', text)
        self.assertIn('BACKGROUND_SYNC.start()', text)
        self.assertIn('BACKGROUND_SYNC.stop()', text)
