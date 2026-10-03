"""정책브리핑 정책뉴스 API (공공데이터포털, 공공누리 제1유형·출처 표시).

정책브리핑 RSS는 제공이 중단되어 API로 받는다. 응답 필드 이름이 바뀌는 일이 있어 여러 표기를 받아들인다.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from ..timeutil import KST


@dataclass
class PolicyItem:
    url: str
    title: str
    body: str
    published_at: datetime


def _text(el: ET.Element, *names: str) -> str:
    for n in names:
        found = el.find(n)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"&nbsp;", " ", s).strip()


def parse_policy_xml(xml_text: str) -> list[PolicyItem]:
    root = ET.fromstring(xml_text)
    items = []
    for el in root.iter():
        if el.tag not in ("NewsItem", "item"):
            continue
        title = _text(el, "Title", "title")
        url = _text(el, "OriginalUrl", "originalUrl", "link")
        body = _strip_html(_text(el, "DataContents", "dataContents", "description"))
        when = _text(el, "ApproveDate", "approveDate", "pubDate")
        if not (title and url and body):
            continue
        published = None
        for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                published = datetime.strptime(when, fmt)
                break
            except ValueError:
                continue
        if published is None:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=KST)
        items.append(PolicyItem(url=url, title=title, body=body, published_at=published))
    return items


def fetch_policy_news(client: httpx.Client, endpoint: str, day: date | None = None) -> list[PolicyItem]:
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if not key:
        return []
    day = day or datetime.now(KST).date()
    params = {
        "serviceKey": key,
        "startDate": (day - timedelta(days=1)).strftime("%Y%m%d"),
        "endDate": day.strftime("%Y%m%d"),
    }
    r = client.get(endpoint, params=params, timeout=30)
    r.raise_for_status()
    return parse_policy_xml(r.text)
