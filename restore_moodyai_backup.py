from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from moodyai_learning.backups import DatabaseBackupCoordinator


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a verified MoodyAI SQLite backup.")
    parser.add_argument("backup", type=Path, help="Path to a moodyai_*.db backup file")
    parser.add_argument("--database", type=Path, default=Path("data/learning/moodyai.db"))
    parser.add_argument("--confirm", action="store_true", help="Required safety confirmation")
    args = parser.parse_args()

    if not args.confirm:
        raise SystemExit("Restore not performed. Stop Uvicorn, then rerun with --confirm.")
    verification = DatabaseBackupCoordinator.verify_backup(args.backup)
    if not verification.get("valid"):
        raise SystemExit(f"Backup is not valid: {verification}")

    target = args.database
    target.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safety_copy = target.with_name(f"{target.name}.before_restore_{timestamp}.bak")
    if target.exists():
        with sqlite3.connect(target, timeout=30) as source:
            with sqlite3.connect(safety_copy, timeout=30) as destination:
                source.backup(destination)

    temp_target = target.with_suffix(".restore.tmp")
    temp_target.unlink(missing_ok=True)
    with sqlite3.connect(args.backup, timeout=30) as source:
        with sqlite3.connect(temp_target, timeout=30) as destination:
            source.backup(destination)
    restored_verification = DatabaseBackupCoordinator.verify_backup(temp_target)
    if not restored_verification.get("valid"):
        temp_target.unlink(missing_ok=True)
        raise SystemExit(f"Restored copy failed verification: {restored_verification}")
    os.replace(temp_target, target)
    print("Restore completed successfully.")
    print(f"Database: {target}")
    print(f"Safety copy: {safety_copy if safety_copy.exists() else 'not needed'}")
    print(f"Integrity: {restored_verification['integrity_status']}")


if __name__ == "__main__":
    main()
