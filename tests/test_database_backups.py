from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from moodyai_learning.backups import DatabaseBackupCoordinator


class DatabaseBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "moodyai.db"
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE example(id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO example(value) VALUES ('preserved')")
            connection.commit()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_creates_verified_backup(self) -> None:
        coordinator = DatabaseBackupCoordinator(
            self.database,
            backup_dir=self.root / "backups",
            enabled=True,
            retention_count=3,
            minimum_age_seconds=0,
        )
        result = coordinator.run_once(force=True)
        self.assertEqual(result["status"], "success")
        backup = Path(result["backup_path"])
        self.assertTrue(backup.exists())
        self.assertTrue(coordinator.verify_backup(backup)["valid"])
        with sqlite3.connect(backup) as connection:
            value = connection.execute("SELECT value FROM example").fetchone()[0]
        self.assertEqual(value, "preserved")

    def test_skips_recent_backup(self) -> None:
        coordinator = DatabaseBackupCoordinator(
            self.database,
            backup_dir=self.root / "backups",
            enabled=True,
            minimum_age_seconds=3600,
        )
        first = coordinator.run_once(force=True)
        second = coordinator.run_once()
        self.assertEqual(first["status"], "success")
        self.assertEqual(second["status"], "recent_backup_exists")
        self.assertFalse(second["ran"])

    def test_retention_removes_old_backups(self) -> None:
        coordinator = DatabaseBackupCoordinator(
            self.database,
            backup_dir=self.root / "backups",
            enabled=True,
            retention_count=3,
            minimum_age_seconds=0,
        )
        for index in range(5):
            # Ensure unique filenames while keeping the test fast.
            coordinator.run_once(force=True)
            import time
            time.sleep(0.01)
        files = list((self.root / "backups").glob("moodyai_*.db"))
        self.assertLessEqual(len(files), 3)

    def test_corrupt_file_fails_verification(self) -> None:
        path = self.root / "corrupt.db"
        path.write_bytes(b"not sqlite")
        result = DatabaseBackupCoordinator.verify_backup(path)
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
