"""robots.txt 확인과 도메인별 요청 간격(1초 이상)."""
from __future__ import annotations

import threading
import time
import urllib.robotparser
from urllib.parse import urlsplit

import httpx


class Politeness:
    def __init__(self, client: httpx.Client, user_agent: str, min_interval_s: float = 1.0, ttl_s: float = 6 * 3600):
        self.client = client
        self.user_agent = user_agent
        self.min_interval_s = min_interval_s
        self.ttl_s = ttl_s
        self._robots: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None]] = {}
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def _parser(self, base: str) -> urllib.robotparser.RobotFileParser | None:
        cached = self._robots.get(base)
        if cached and time.monotonic() - cached[0] < self.ttl_s:
            return cached[1]
        rp: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
        try:
            self.wait(base)
            r = self.client.get(base + "/robots.txt", timeout=10)
            if r.status_code >= 500:
                rp = None  # 서버 오류: 이번에는 가져오지 않는다
            elif r.status_code >= 400:
                rp.parse([])  # robots.txt 없음 → 허용
            else:
                rp.parse(r.text.splitlines())
        except httpx.HTTPError:
            rp = None
        self._robots[base] = (time.monotonic(), rp)
        return rp

    def allowed(self, url: str) -> bool:
        p = urlsplit(url)
        rp = self._parser(f"{p.scheme}://{p.netloc}")
        return bool(rp and rp.can_fetch(self.user_agent, url))

    def wait(self, url_or_base: str) -> None:
        host = urlsplit(url_or_base).netloc
        with self._lock:
            last = self._last.get(host, 0.0)
            delay = self.min_interval_s - (time.monotonic() - last)
            if delay > 0:
                time.sleep(delay)
            self._last[host] = time.monotonic()
