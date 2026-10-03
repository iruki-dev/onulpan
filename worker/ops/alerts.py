"""알림 네 가지뿐: 수집 1시간 연속 0건 / 06:30 조립 실패 또는 1면 후보 3편 미만 / LLM 예산 80% / DB 백업 실패.

텔레그램 봇(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) 또는 이메일(ALERT_EMAIL). 같은 알림은 key로 한 번만 보낸다.
"""
from __future__ import annotations

import logging
import os

import httpx
import psycopg

log = logging.getLogger(__name__)

KINDS = {"collect_zero", "assemble_failed", "front_short", "budget_80", "backup_failed"}


def _deliver(text: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                           json={"chat_id": chat, "text": text}, timeout=10)
            return r.status_code == 200
        except httpx.HTTPError as e:
            log.error("telegram alert failed: %s", e)
    to = os.environ.get("ALERT_EMAIL")
    if to:
        from ..mail.render import RenderedEmail
        from ..mail.sender import get_sender
        from ..settings import settings

        try:
            get_sender(settings()["email"]["from"]).send(
                to, RenderedEmail(subject=f"[오늘판 알림] {text[:60]}", html=f"<p>{text}</p>", text=text, unsubscribe_url=""))
            return True
        except Exception as e:  # noqa: BLE001
            log.error("email alert failed: %s", e)
    log.warning("ALERT: %s", text)
    return False


def alert(conn: psycopg.Connection, kind: str, key: str, text: str) -> bool:
    """key가 처음일 때만 보낸다 (예: budget_80:2026-10)."""
    assert kind in KINDS, kind
    row = conn.execute(
        "INSERT INTO alerts_sent (key) VALUES (%s) ON CONFLICT DO NOTHING RETURNING key", (f"{kind}:{key}",)
    ).fetchone()
    conn.commit()
    if row is None:
        return False
    _deliver(f"[오늘판] {text}")
    return True
