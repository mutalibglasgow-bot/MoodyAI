from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moodyai_learning.health import build_health_report
from moodyai_learning.security import AuthConfig, SessionAuth


class SecurityTests(unittest.TestCase):
    def test_session_token_round_trip_and_tamper_rejection(self) -> None:
        auth = SessionAuth(AuthConfig(password="correct horse", secret="a" * 64, session_hours=1))
        token = auth.create_token()
        self.assertTrue(auth.verify_token(token))
        self.assertFalse(auth.verify_token(token + "tampered"))
        self.assertTrue(auth.verify_password("correct horse"))
        self.assertFalse(auth.verify_password("wrong"))

    def test_missing_environment_fails_closed(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(AuthConfig.from_environment())

    def test_health_report_checks_database_background_and_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"FOLLOWUPBOSS_API_KEY": "test", "MOODYAI_ADMIN_PASSWORD": "pw", "MOODYAI_SESSION_SECRET": "s" * 64},
            clear=True,
        ):
            db = Path(tmp) / "health.db"
            import sqlite3
            sqlite3.connect(db).close()
            report = build_health_report(db, lambda: {"running": True, "last_run": {"status": "success"}, "next_run_at": None})
            self.assertEqual(report["status"], "healthy")
            self.assertEqual(report["checks"]["database"]["status"], "healthy")
            self.assertTrue(report["checks"]["authentication"]["configured"])
