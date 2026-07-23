from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def build_health_report(
    database_path: Path,
    background_status: Callable[[], dict[str, Any]],
    backup_status: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    try:
        with sqlite3.connect(database_path, timeout=5) as connection:
            connection.execute("SELECT 1").fetchone()
        checks["database"] = {"status": "healthy", "path": str(database_path)}
    except Exception as exc:
        checks["database"] = {"status": "unhealthy", "error": type(exc).__name__}

    fub_configured = bool(os.getenv("FOLLOWUPBOSS_API_KEY", "").strip())
    checks["follow_up_boss"] = {
        "status": "configured" if fub_configured else "not_configured",
        "configured": fub_configured,
    }

    try:
        bg = background_status()
        running = bool(bg.get("running"))
        last = bg.get("last_run") or {}
        last_status = last.get("status")
        healthy = running and last_status not in {"failed", "error"}
        checks["background_sync"] = {
            "status": "healthy" if healthy else "degraded",
            "running": running,
            "last_run_status": last_status,
            "last_completed_at": last.get("completed_at"),
            "next_run_at": bg.get("next_run_at"),
        }
    except Exception as exc:
        checks["background_sync"] = {"status": "unhealthy", "error": type(exc).__name__}

    if backup_status is not None:
        try:
            backups = backup_status()
            last = backups.get("last_run") or {}
            last_status = last.get("status")
            backup_count = int(backups.get("backup_count", 0) or 0)
            healthy = bool(backups.get("enabled")) and backup_count > 0 and last_status != "failed"
            checks["database_backups"] = {
                "status": "healthy" if healthy else "degraded",
                "enabled": bool(backups.get("enabled")),
                "backup_count": backup_count,
                "last_run_status": last_status,
                "last_completed_at": last.get("completed_at"),
                "next_run_at": backups.get("next_run_at"),
            }
        except Exception as exc:
            checks["database_backups"] = {"status": "unhealthy", "error": type(exc).__name__}

    auth_configured = bool(
        os.getenv("MOODYAI_ADMIN_PASSWORD", "").strip()
        and os.getenv("MOODYAI_SESSION_SECRET", "").strip()
    )
    checks["authentication"] = {
        "status": "healthy" if auth_configured else "not_configured",
        "configured": auth_configured,
    }

    unhealthy = any(v.get("status") == "unhealthy" for v in checks.values())
    degraded = any(v.get("status") in {"degraded", "not_configured"} for v in checks.values())
    status = "unhealthy" if unhealthy else "degraded" if degraded else "healthy"
    return {
        "application": "MoodyAI",
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
