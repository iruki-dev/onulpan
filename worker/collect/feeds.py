"""1단계 수집: 15분마다 피드·API를 조회해 raw_articles에 넣는다.

URL 정규화(추적 파라미터 제거) 후 UNIQUE로 중복 차단. 본문은 본문 추출 라이브러리로 한 번만 가져온다.
유료 기사 영역은 건너뛴다. robots.txt를 확인하고, 같은 도메인 요청 간격은 1초 이상, User-Agent에 연락처.
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import httpx
import psycopg
import yaml

from ..settings import RULES_DIR, Settings
from ..timeutil import now as utcnow
from .fetch import fetch_article
from .policy_api import fetch_policy_news
from .robots import Politeness
from .urls import normalize_url

log = logging.getLogger(__name__)


@dataclass
class FeedItem:
    url: str
    title: str
    published_at: datetime
    summary: str = ""


def load_outlets_yaml() -> list[dict]:
    return yaml.safe_load((RULES_DIR / "outlets.yaml").read_text(encoding="utf-8"))["outlets"]


def sync_outlets(conn: psycopg.Connection) -> int:
    """rules/outlets.yaml → outlets. 매체 요청으로 제외된 매체(excluded_at)는 다시 켜지 않는다."""
    n = 0
    for o in load_outlets_yaml():
        active = bool(o.get("active", True)) and bool(o.get("feed_url"))
        conn.execute(
            """INSERT INTO outlets (name, domain, feed_url, feed_type, grp, active)
               VALUES (%(name)s, %(domain)s, %(feed_url)s, %(feed_type)s, %(grp)s, %(active)s)
               ON CONFLICT (domain) DO UPDATE SET
                 name = EXCLUDED.name, feed_url = EXCLUDED.feed_url, feed_type = EXCLUDED.feed_type,
                 grp = EXCLUDED.grp, active = EXCLUDED.active AND outlets.excluded_at IS NULL""",
            {"name": o["name"], "domain": o["domain"], "feed_url": o.get("feed_url"),
             "feed_type": o.get("feed_type", "rss"), "grp": o["grp"], "active": active},
        )
        n += 1
    return n


def parse_feed(content: bytes | str) -> list[FeedItem]:
    parsed = feedparser.parse(content)
    items = []
    for e in parsed.entries:
        link = e.get("link")
        title = (e.get("title") or "").strip()
        if not link or not title:
            continue
        t = e.get("published_parsed") or e.get("updated_parsed")
        published = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc) if t else utcnow()
        items.append(FeedItem(url=link, title=title, published_at=published, summary=e.get("summary", "")))
    return items


class Collector:
    def __init__(self, conn: psycopg.Connection, s: Settings, ingest, client: httpx.Client | None = None):
        """ingest(outlet_id, url, title, body, published_at) → article_id | None"""
        self.conn, self.s, self.ingest = conn, s, ingest
        c = s["collect"]
        self.client = client or httpx.Client(headers={"User-Agent": c["user_agent"]}, follow_redirects=True)
        self.polite = Politeness(self.client, c["user_agent"], c["min_request_interval_s"])

    def run(self) -> dict:
        stats = {"outlets": 0, "items": 0, "new": 0, "skipped": 0, "errors": 0}
        outlets = self.conn.execute(
            "SELECT * FROM outlets WHERE active AND excluded_at IS NULL AND feed_url IS NOT NULL ORDER BY id"
        ).fetchall()
        for o in outlets:
            stats["outlets"] += 1
            try:
                if o["feed_type"] == "api":
                    self._collect_policy(o, stats)
                else:
                    self._collect_rss(o, stats)
                self.conn.commit()
            except Exception as e:  # 매체 하나의 실패가 다른 매체를 막지 않는다
                self.conn.rollback()
                stats["errors"] += 1
                log.warning("collect %s failed: %s", o["domain"], e)
        return stats

    def _known(self, url: str) -> bool:
        return self.conn.execute("SELECT 1 FROM raw_articles WHERE url = %s", (normalize_url(url),)).fetchone() is not None

    def _collect_rss(self, o: dict, stats: dict) -> None:
        self.polite.wait(o["feed_url"])
        r = self.client.get(o["feed_url"], timeout=20)
        r.raise_for_status()
        cutoff = utcnow() - timedelta(hours=48)
        c = self.s["collect"]
        for item in parse_feed(r.content):
            stats["items"] += 1
            if item.published_at < cutoff or self._known(item.url):
                continue
            if not self.polite.allowed(item.url):
                stats["skipped"] += 1
                continue
            self.polite.wait(item.url)
            try:
                body = fetch_article(self.client, item.url, c["min_body_chars"], c["body_max_chars"])
            except httpx.HTTPError:
                body = None
            if not body:
                stats["skipped"] += 1  # 유료·로그인 영역 또는 추출 실패
                continue
            if self.ingest(outlet_id=o["id"], url=item.url, title=item.title, body=body,
                           published_at=item.published_at):
                stats["new"] += 1
            self.conn.commit()

    def _collect_policy(self, o: dict, stats: dict) -> None:
        for item in fetch_policy_news(self.client, o["feed_url"]):
            stats["items"] += 1
            if self._known(item.url):
                continue
            if self.ingest(outlet_id=o["id"], url=item.url, title=item.title, body=item.body,
                           published_at=item.published_at):
                stats["new"] += 1
            self.conn.commit()
