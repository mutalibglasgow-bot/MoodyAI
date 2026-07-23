from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS database_backup_runs (
    backup_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    backup_path TEXT,
    size_bytes INTEGER,
    integrity_status TEXT,
    retained_count INTEGER NOT NULL DEFAULT 0,
    deleted_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_database_backup_runs_started
ON database_backup_runs(started_at DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


class DatabaseBackupCoordinator:
    """Creates verified SQLite backups without interrupting normal reads/writes."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        backup_dir: str | Path | None = None,
        enabled: bool | None = None,
        interval_seconds: int | None = None,
        initial_delay_seconds: int | None = None,
        retention_count: int | None = None,
        minimum_age_seconds: int | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.backup_dir = Path(backup_dir or os.getenv("MOODYAI_BACKUP_DIR", self.database_path.parent / "backups"))
        self.enabled = _env_bool("MOODYAI_BACKUPS_ENABLED", True) if enabled is None else enabled
        configured_interval = int(os.getenv("MOODYAI_BACKUP_INTERVAL_SECONDS", "86400")) if interval_seconds is None else interval_seconds
        self.interval_seconds = max(300, int(configured_interval))
        configured_delay = int(os.getenv("MOODYAI_BACKUP_INITIAL_DELAY_SECONDS", "30")) if initial_delay_seconds is None else initial_delay_seconds
        self.initial_delay_seconds = max(0, int(configured_delay))
        configured_retention = int(os.getenv("MOODYAI_BACKUP_RETENTION_COUNT", "14")) if retention_count is None else retention_count
        self.retention_count = max(3, int(configured_retention))
        configured_minimum = int(os.getenv("MOODYAI_BACKUP_MINIMUM_AGE_SECONDS", "72000")) if minimum_age_seconds is None else minimum_age_seconds
        self.minimum_age_seconds = max(0, int(configured_minimum))
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._run_lock = threading.Lock()
        self._next_run_epoch: float | None = None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            connection.commit()

    def _last_success_epoch(self) -> float | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT completed_at FROM database_backup_runs WHERE status='success' ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
        if row is None or not row["completed_at"]:
            return None
        try:
            return datetime.fromisoformat(row["completed_at"]).timestamp()
        except ValueError:
            return None

    @staticmethod
    def verify_backup(path: str | Path) -> dict[str, Any]:
        backup_path = Path(path)
        if not backup_path.exists():
            return {"valid": False, "integrity_status": "missing", "size_bytes": 0}
        try:
            with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True, timeout=10) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
                table_count = connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
            integrity = str(result[0]) if result else "unknown"
            return {
                "valid": integrity.lower() == "ok",
                "integrity_status": integrity,
                "size_bytes": backup_path.stat().st_size,
                "table_count": int(table_count),
            }
        except Exception as exc:
            return {
                "valid": False,
                "integrity_status": "error",
                "size_bytes": backup_path.stat().st_size if backup_path.exists() else 0,
                "error": type(exc).__name__,
            }

    def _prune(self) -> tuple[int, int]:
        files = sorted(self.backup_dir.glob("moodyai_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        retained = files[: self.retention_count]
        deleted = 0
        for path in files[self.retention_count :]:
            path.unlink(missing_ok=True)
            deleted += 1
        return len(retained), deleted

    def _record_run(self, **values: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO database_backup_runs(
                    backup_id, started_at, completed_at, status, backup_path,
                    size_bytes, integrity_status, retained_count, deleted_count,
                    error_message, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["backup_id"], values["started_at"], values.get("completed_at"), values["status"],
                    values.get("backup_path"), values.get("size_bytes"), values.get("integrity_status"),
                    values.get("retained_count", 0), values.get("deleted_count", 0), values.get("error_message"),
                    json.dumps(values.get("details", {}), sort_keys=True, default=str),
                ),
            )
            connection.commit()

    def run_once(self, *, force: bool = False) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "ran": False}
        if not self._run_lock.acquire(blocking=False):
            return {"status": "already_running", "ran": False}
        try:
            last_success = self._last_success_epoch()
            if not force and last_success and time.time() - last_success < self.minimum_age_seconds:
                return {"status": "recent_backup_exists", "ran": False}

            backup_id = f"backup_{uuid.uuid4().hex[:20]}"
            started_at = _now_iso()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            final_path = self.backup_dir / f"moodyai_{timestamp}_{backup_id[-8:]}.db"
            temp_path = final_path.with_suffix(".db.tmp")
            try:
                with sqlite3.connect(self.database_path, timeout=30) as source:
                    with sqlite3.connect(temp_path, timeout=30) as destination:
                        source.backup(destination)
                verification = self.verify_backup(temp_path)
                if not verification["valid"]:
                    raise RuntimeError(f"Backup integrity check failed: {verification.get('integrity_status')}")
                temp_path.replace(final_path)
                retained, deleted = self._prune()
                completed_at = _now_iso()
                self._record_run(
                    backup_id=backup_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="success",
                    backup_path=str(final_path),
                    size_bytes=final_path.stat().st_size,
                    integrity_status=verification["integrity_status"],
                    retained_count=retained,
                    deleted_count=deleted,
                    details=verification,
                )
                return {
                    "backup_id": backup_id,
                    "ran": True,
                    "status": "success",
                    "backup_path": str(final_path),
                    "size_bytes": final_path.stat().st_size,
                    "integrity_status": verification["integrity_status"],
                    "retained_count": retained,
                    "deleted_count": deleted,
                    "completed_at": completed_at,
                }
            except Exception as exc:
                temp_path.unlink(missing_ok=True)
                completed_at = _now_iso()
                self._record_run(
                    backup_id=backup_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="failed",
                    error_message=str(exc),
                    integrity_status="failed",
                    details={"error": type(exc).__name__},
                )
                return {
                    "backup_id": backup_id,
                    "ran": True,
                    "status": "failed",
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
        finally:
            self._run_lock.release()

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
        self._thread = threading.Thread(target=self._worker, name="moodyai-database-backups", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

    def status(self, *, recent_limit: int = 5) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM database_backup_runs ORDER BY started_at DESC LIMIT ?",
                (max(1, min(recent_limit, 20)),),
            ).fetchall()
        recent: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json"))
            except Exception:
                item["details"] = {}
                item.pop("details_json", None)
            recent.append(item)
        files = sorted(self.backup_dir.glob("moodyai_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        return {
            "enabled": self.enabled,
            "running": bool(self._thread and self._thread.is_alive()),
            "interval_seconds": self.interval_seconds,
            "retention_count": self.retention_count,
            "backup_dir": str(self.backup_dir),
            "backup_count": len(files),
            "newest_backup": str(files[0]) if files else None,
            "next_run_at": datetime.fromtimestamp(self._next_run_epoch, tz=timezone.utc).isoformat() if self._next_run_epoch else None,
            "last_run": recent[0] if recent else None,
            "recent_runs": recent,
        }
