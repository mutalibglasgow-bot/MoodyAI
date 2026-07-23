from __future__ import annotations

import json
from pathlib import Path
from dotenv import load_dotenv

from moodyai_learning.production import StartupValidationError, configure_structured_logging, validate_startup

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
configure_structured_logging()
try:
    report = validate_startup(ROOT, ROOT / "data" / "learning" / "moodyai.db")
except StartupValidationError as exc:
    print(json.dumps(exc.report.to_dict(), indent=2))
    raise SystemExit(1)
print(json.dumps(report.to_dict(), indent=2))
