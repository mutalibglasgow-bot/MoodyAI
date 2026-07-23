from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moodyai_learning.production import JsonFormatter, StartupValidationError, validate_startup


class ProductionReadinessTests(unittest.TestCase):
    def _root(self, temp: str) -> Path:
        root = Path(temp)
        (root / "static").mkdir()
        (root / "static" / "learning.html").write_text("ok")
        (root / "static" / "login.html").write_text("ok")
        return root

    def test_development_allows_missing_optional_configuration(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MOODYAI_ENV": "development"}, clear=True):
            root = self._root(temp)
            report = validate_startup(root, root / "data" / "learning" / "moodyai.db")
            self.assertEqual(report.environment, "development")
            self.assertIn(report.status, {"healthy", "degraded"})

    def test_production_rejects_missing_authentication(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MOODYAI_ENV": "production"}, clear=True):
            root = self._root(temp)
            with self.assertRaises(StartupValidationError):
                validate_startup(root, root / "data" / "learning" / "moodyai.db")

    def test_production_accepts_required_configuration(self):
        env = {
            "MOODYAI_ENV": "production",
            "MOODYAI_AUTH_PASSWORD": "a-long-secure-password",
            "MOODYAI_SESSION_SECRET": "x" * 48,
        }
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, env, clear=True):
            root = self._root(temp)
            report = validate_startup(root, root / "data" / "learning" / "moodyai.db")
            self.assertNotEqual(report.status, "unhealthy")

    def test_json_formatter_emits_machine_readable_log(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)
        record.request_id = "abc"
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["message"], "hello")
        self.assertEqual(payload["request_id"], "abc")
