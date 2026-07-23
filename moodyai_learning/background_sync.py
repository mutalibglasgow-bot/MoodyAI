from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS background_sync_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    activity_imported INTEGER NOT NULL DEFAULT 0,
    outcomes_imported INTEGER NOT NULL DEFAULT 0,
    evaluated INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_background_sync_runs_started
ON background_sync_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS background_sync_lock (
    lock_name TEXT PRIMARY KEY,
    owner_token TEXT NOT NULL,
    lease_until_epoch REAL NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


class BackgroundSyncCoordinator:
    """Runs the existing FUB learning cycle without requiring the UI to be open.

    The coordinator is deliberately conservative:
    - a SQLite lease prevents overlapping runs;
    - every run is persisted for visibility;
    - failures are recorded and the next cycle still runs;
    - the worker is a daemon thread so application shutdown is not blocked.
    """

    def __init__(
        self,
        database_path: str | Path,
        cycle: Callable[[], dict[str, Any]],
        *,
        enabled: bool | None = None,
        interval_seconds: int | None = None,
        initial_delay_seconds: int | None = None,
        lease_seconds: int = 240,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.cycle = cycle
        self.enabled = _env_bool("MOODYAI_BACKGROUND_SYNC_ENABLED", True) if enabled is None else enabled
        configured_interval = int(os.getenv("MOODYAI_BACKGROUND_SYNC_INTERVAL_SECONDS", "300")) if interval_seconds is None else interval_seconds
        self.interval_seconds = max(60, int(configured_interval))
        configured_delay = int(os.getenv("MOODYAI_BACKGROUND_SYNC_INITIAL_DELAY_SECONDS", "15")) if initial_delay_seconds is None else initial_delay_seconds
        self.initial_delay_seconds = max(0, int(configured_delay))
        self.lease_seconds = max(30, int(lease_seconds))
        self.owner_token = f"{os.getpid()}:{uuid.uuid4().hex}"
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._local_lock = threading.Lock()
        self._next_run_epoch: float | None = None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            connection.commit()

    def _acquire_lease(self) -> bool:
        now = time.time()
        lease_until = now + self.lease_seconds
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT owner_token, lease_until_epoch FROM background_sync_lock WHERE lock_name='fub_learning_cycle'"
            ).fetchone()
            if row is not None and float(row["lease_until_epoch"]) > now and row["owner_token"] != self.owner_token:
                connection.rollback()
                return False
            connection.execute(
                """
                INSERT INTO background_sync_lock(lock_name, owner_token, lease_until_epoch)
                VALUES ('fub_learning_cycle', ?, ?)
                ON CONFLICT(lock_name) DO UPDATE SET
                    owner_token=excluded.owner_token,
                    lease_until_epoch=excluded.lease_until_epoch
                """,
                (self.owner_token, lease_until),
            )
            connection.commit()
        return True

    def _release_lease(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM background_sync_lock WHERE lock_name='fub_learning_cycle' AND owner_token=?",
                (self.owner_token,),
            )
            connection.commit()

    def _save_run(
        self,
        *,
        run_id: str,
        started_at: str,
        completed_at: str,
        status: str,
        result: dict[str, Any],
        error_message: str | None = None,
    ) -> None:
        activity_imported = int(result.get("imported_count", 0) or 0)
        outcomes_imported = int(result.get("automatic_outcome_count", 0) or 0)
        evaluation = result.get("evaluation") or {}
        evaluated = int(evaluation.get("evaluated", 0) or 0)
        error_count = int(result.get("error_count", 0) or 0)
        automatic = result.get("automatic_outcomes") or {}
        error_count += int(automatic.get("error_count", 0) or 0)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO background_sync_runs(
                    run_id, started_at, completed_at, status,
                    activity_imported, outcomes_imported, evaluated,
                    error_count, error_message, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    started_at,
                    completed_at,
                    status,
                    activity_imported,
                    outcomes_imported,
                    evaluated,
                    error_count,
                    error_message,
                    json.dumps(result, sort_keys=True, default=str),
                ),
            )
            connection.commit()

    def run_once(self) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "ran": False}
        if not self._local_lock.acquire(blocking=False):
            return {"status": "already_running", "ran": False}
        try:
            if not self._acquire_lease():
                return {"status": "lease_held", "ran": False}
            run_id = f"sync_{uuid.uuid4().hex[:20]}"
            started_at = _now_iso()
            try:
                result = self.cycle()
                status = "success" if not result.get("error_count") else "partial"
                completed_at = _now_iso()
                self._save_run(
                    run_id=run_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    status=status,
                    result=result,
                )
                return {"run_id": run_id, "ran": True, "status": status, **result}
            except Exception as exc:
                completed_at = _now_iso()
                error_result = {"error_count": 1, "errors": [{"error": type(exc).__name__, "message": str(exc)}]}
                self._save_run(
                    run_id=run_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="failed",
                    result=error_result,
                    error_message=str(exc),
                )
                return {
                    "run_id": run_id,
                    "ran": True,
                    "status": "failed",
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
            finally:
                self._release_lease()
        finally:
            self._local_lock.release()

    def _worker(self) -> None:
        if self._stop_event.wait(self.initial_delay_seconds):
            return
        while not self._stop_event.is_set():
            self._next_run_epoch = None
            self.run_once()
            self._next_run_epoch = time.time() + self.interval_seconds
            if self._stop_event.wait(self.interval_seconds):
                break

    def start(self) -> None:
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop_event.clear()
        self._next_run_epoch = time.time() + self.initial_delay_seconds
        self._thread = threading.Thread(target=self._worker, name="moodyai-background-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def status(self, *, recent_limit: int = 5) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM background_sync_runs ORDER BY started_at DESC LIMIT ?",
                (max(1, min(recent_limit, 20)),),
            ).fetchall()
        recent = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json"))
            except Exception:
                item["details"] = {}
                item.pop("details_json", None)
            recent.append(item)
        return {
            "enabled": self.enabled,
            "running": bool(self._thread and self._thread.is_alive()),
            "interval_seconds": self.interval_seconds,
            "initial_delay_seconds": self.initial_delay_seconds,
            "next_run_at": datetime.fromtimestamp(self._next_run_epoch, tz=timezone.utc).isoformat() if self._next_run_epoch else None,
            "last_run": recent[0] if recent else None,
            "recent_runs": recent,
            "manual_refresh_required": False,
        }
