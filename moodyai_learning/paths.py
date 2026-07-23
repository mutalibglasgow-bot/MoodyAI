from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    configured = os.getenv("MOODYAI_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / "data" / "learning"


def database_path() -> Path:
    configured = os.getenv("MOODYAI_DATABASE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return data_root() / "moodyai.db"


def backup_directory() -> Path:
    configured = os.getenv("MOODYAI_BACKUP_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return data_root() / "backups"
