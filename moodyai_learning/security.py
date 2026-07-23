from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthConfig:
    password: str
    secret: str
    session_hours: int = 12

    @classmethod
    def from_environment(cls) -> "AuthConfig | None":
        password = os.getenv("MOODYAI_ADMIN_PASSWORD", "").strip()
        secret = os.getenv("MOODYAI_SESSION_SECRET", "").strip()
        if not password or not secret:
            return None
        hours_raw = os.getenv("MOODYAI_SESSION_HOURS", "12")
        try:
            hours = max(1, min(int(hours_raw), 168))
        except ValueError:
            hours = 12
        return cls(password=password, secret=secret, session_hours=hours)


class SessionAuth:
    cookie_name = "moodyai_session"

    def __init__(self, config: AuthConfig):
        self.config = config

    def verify_password(self, submitted: str) -> bool:
        return hmac.compare_digest(submitted.encode(), self.config.password.encode())

    def create_token(self, username: str = "Moody") -> str:
        expires = int(time.time()) + self.config.session_hours * 3600
        nonce = secrets.token_hex(8)
        payload = f"{username}|{expires}|{nonce}"
        signature = hmac.new(self.config.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}|{signature}"

    def verify_token(self, token: str | None) -> bool:
        if not token:
            return False
        parts = token.split("|")
        if len(parts) != 4:
            return False
        username, expires_raw, nonce, signature = parts
        payload = f"{username}|{expires_raw}|{nonce}"
        expected = hmac.new(self.config.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        try:
            return int(expires_raw) >= int(time.time())
        except ValueError:
            return False
