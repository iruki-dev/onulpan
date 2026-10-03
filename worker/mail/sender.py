"""발송: Amazon SES (SMTP 인터페이스). 개발 환경은 outbox 디렉터리에 .eml로 떨어뜨린다.

환경 변수: EMAIL_BACKEND=ses|console, SES_SMTP_HOST, SES_SMTP_PORT(587), SES_SMTP_USER, SES_SMTP_PASS
"""
from __future__ import annotations

import os
import smtplib
import ssl
import uuid
from email import policy
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Protocol

from ..settings import ROOT
from .render import RenderedEmail


class Sender(Protocol):
    def send(self, to: str, mail: RenderedEmail) -> str: ...


def build_message(sender: str, to: str, mail: RenderedEmail) -> EmailMessage:
    # 긴 List-Unsubscribe 주소가 RFC 2047로 인코딩되지 않도록 줄 길이 제한을 SMTP 한도(998)로
    msg = EmailMessage(policy=policy.default.clone(max_line_length=998))
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = mail.subject
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1].rstrip(">"))
    # 원클릭 수신 거부 (RFC 8058)
    if mail.unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{mail.unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(mail.text)
    msg.add_alternative(mail.html, subtype="html")
    return msg


class ConsoleSender:
    def __init__(self, sender: str, outbox: Path | None = None):
        self.sender = sender
        self.outbox = outbox or ROOT / "var" / "outbox"
        self.outbox.mkdir(parents=True, exist_ok=True)

    def send(self, to: str, mail: RenderedEmail) -> str:
        msg = build_message(self.sender, to, mail)
        mid = uuid.uuid4().hex
        (self.outbox / f"{mid}.eml").write_bytes(bytes(msg))
        return mid


class SesSmtpSender:
    def __init__(self, sender: str):
        self.sender = sender
        self.host = os.environ["SES_SMTP_HOST"]
        self.port = int(os.environ.get("SES_SMTP_PORT", "587"))
        self.user = os.environ["SES_SMTP_USER"]
        self.password = os.environ["SES_SMTP_PASS"]
        self._smtp: smtplib.SMTP | None = None

    def _conn(self) -> smtplib.SMTP:
        if self._smtp is None:
            s = smtplib.SMTP(self.host, self.port, timeout=30)
            s.starttls(context=ssl.create_default_context())
            s.login(self.user, self.password)
            self._smtp = s
        return self._smtp

    def send(self, to: str, mail: RenderedEmail) -> str:
        msg = build_message(self.sender, to, mail)
        try:
            self._conn().send_message(msg)
        except smtplib.SMTPServerDisconnected:
            self._smtp = None
            self._conn().send_message(msg)
        return msg["Message-ID"]

    def close(self) -> None:
        if self._smtp is not None:
            try:
                self._smtp.quit()
            finally:
                self._smtp = None


def get_sender(sender_addr: str) -> Sender:
    if os.environ.get("EMAIL_BACKEND", "console") == "ses":
        return SesSmtpSender(sender_addr)
    return ConsoleSender(sender_addr)


def send_login_link(sender: Sender, to: str, url: str) -> str:
    mail = RenderedEmail(
        subject="[오늘판] 로그인 링크",
        html=f'<p>아래 링크를 누르면 오늘판에 로그인합니다. 링크는 15분 동안 유효합니다.</p><p><a href="{url}">로그인하기</a></p>',
        text=f"아래 링크를 누르면 오늘판에 로그인합니다. 링크는 15분 동안 유효합니다.\n{url}",
        unsubscribe_url="",
    )
    return sender.send(to, mail)

