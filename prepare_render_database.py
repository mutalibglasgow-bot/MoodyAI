from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def verify(path: Path) -> dict[str, object]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": digest,
        "integrity": integrity,
        "table_count": int(tables),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a verified MoodyAI database seed for Render.")
    parser.add_argument("--source", default="data/learning/moodyai.db")
    parser.add_argument("--output", default="render_seed/moodyai.db")
    args = parser.parse_args()
    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Source database not found: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".db.tmp")
    temp.unlink(missing_ok=True)
    with sqlite3.connect(source, timeout=30) as src, sqlite3.connect(temp, timeout=30) as dst:
        src.backup(dst)
    report = verify(temp)
    if str(report["integrity"]).lower() != "ok":
        temp.unlink(missing_ok=True)
        raise SystemExit(f"Seed integrity failed: {report['integrity']}")
    temp.replace(output)
    report = verify(output)
    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"created": True, "database": str(output), "manifest": str(manifest), **report}, indent=2))


if __name__ == "__main__":
    main()
