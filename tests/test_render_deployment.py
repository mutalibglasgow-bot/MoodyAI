from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moodyai_learning.paths import backup_directory, database_path
from moodyai_learning.production import validate_startup


class RenderPathTests(unittest.TestCase):
    def test_data_dir_controls_database_and_backups(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"MOODYAI_DATA_DIR": temp}, clear=False):
                self.assertEqual(database_path(), Path(temp).resolve() / "moodyai.db")
                self.assertEqual(backup_directory(), Path(temp).resolve() / "backups")

    def test_explicit_database_path_wins(self):
        with tempfile.TemporaryDirectory() as temp:
            custom = Path(temp) / "custom.db"
            with patch.dict(os.environ, {"MOODYAI_DATABASE_PATH": str(custom)}, clear=False):
                self.assertEqual(database_path(), custom.resolve())


class RenderValidationTests(unittest.TestCase):
    def test_production_accepts_admin_password_name(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            env = {
                "MOODYAI_ENV": "production",
                "MOODYAI_ADMIN_PASSWORD": "long-enough-password",
                "MOODYAI_SESSION_SECRET": "s" * 64,
                "MOODYAI_DATA_DIR": temp,
            }
            with patch.dict(os.environ, env, clear=False):
                report = validate_startup(root, Path(temp) / "moodyai.db")
                self.assertIn(report.status, {"healthy", "degraded"})
                auth = next(c for c in report.checks if c.name == "authentication_password")
                self.assertEqual(auth.status, "healthy")


class RenderFilesTests(unittest.TestCase):
    def test_render_files_exist(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("Dockerfile", ".dockerignore", "render.yaml", "requirements.txt"):
            self.assertTrue((root / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
