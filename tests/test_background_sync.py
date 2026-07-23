from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moodyai_learning.background_sync import BackgroundSyncCoordinator


class BackgroundSyncCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Path(self.temp_dir.name) / "learning.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_persists_successful_cycle(self) -> None:
        runner = BackgroundSyncCoordinator(
            self.db,
            lambda: {
                "imported_count": 2,
                "automatic_outcome_count": 1,
                "error_count": 0,
                "evaluation": {"evaluated": 3},
            },
            enabled=True,
            interval_seconds=60,
            initial_delay_seconds=0,
        )
        result = runner.run_once()
        self.assertTrue(result["ran"])
        self.assertEqual(result["status"], "success")
        status = runner.status()
        self.assertEqual(status["last_run"]["activity_imported"], 2)
        self.assertEqual(status["last_run"]["outcomes_imported"], 1)
        self.assertEqual(status["last_run"]["evaluated"], 3)

    def test_failure_is_recorded_without_raising(self) -> None:
        def fail() -> dict:
            raise RuntimeError("temporary FUB failure")

        runner = BackgroundSyncCoordinator(self.db, fail, enabled=True, interval_seconds=60)
        result = runner.run_once()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(runner.status()["last_run"]["status"], "failed")

    def test_disabled_runner_does_not_run(self) -> None:
        calls = []
        runner = BackgroundSyncCoordinator(self.db, lambda: calls.append(1) or {}, enabled=False)
        result = runner.run_once()
        self.assertFalse(result["ran"])
        self.assertEqual(calls, [])
