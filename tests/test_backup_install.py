from __future__ import annotations

import unittest
from pathlib import Path


class BackupInstallTests(unittest.TestCase):
    def test_main_contains_backup_coordinator(self) -> None:
        text = Path("main.py").read_text()
        self.assertIn("DatabaseBackupCoordinator", text)
        self.assertIn("DATABASE_BACKUPS.start()", text)
        self.assertIn("/api/learning/backups/status", text)

    def test_restore_script_exists(self) -> None:
        self.assertTrue(Path("restore_moodyai_backup.py").exists())


if __name__ == "__main__":
    unittest.main()
