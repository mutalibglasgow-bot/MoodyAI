from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from moodyai_learning.production import configure_structured_logging, validate_startup
from moodyai_learning.paths import database_path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(ROOT / ".env")
    os.environ.setdefault("MOODYAI_ENV", "production")
    configure_structured_logging()
    validate_startup(ROOT, database_path())
    host = os.getenv("MOODYAI_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("MOODYAI_PORT", "8000")))
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("MOODYAI_FORWARDED_ALLOW_IPS", "*"),
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
