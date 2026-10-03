"""수신 거부 링크 서명. 웹(web/lib/tokens.ts)과 같은 방식: HMAC-SHA256(ONULPAN_SECRET, "unsub:" + user_id)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os


def _secret() -> bytes:
    return os.environ.get("ONULPAN_SECRET", "dev-secret-change-me").encode()


def sign(purpose: str, value: str) -> str:
    mac = hmac.new(_secret(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()[:32]
    v = base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")
    return f"{v}.{mac}"


def verify(purpose: str, token: str) -> str | None:
    try:
        v, mac = token.split(".", 1)
        value = base64.urlsafe_b64decode(v + "=" * (-len(v) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    return value if hmac.compare_digest(sign(purpose, value).split(".", 1)[1], mac) else None
