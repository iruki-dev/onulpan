"""본문 추출. 본문은 한 번만 가져온다. 유료·로그인 영역은 건너뛴다."""
from __future__ import annotations

import re

import httpx

PAYWALL_MARKERS = (
    "유료 회원", "유료회원", "구독자 전용", "구독 후 이용", "로그인 후 이용", "로그인이 필요",
    "프리미엄 기사", "멤버십 전용", "결제 후", "paywall",
)


def extract_body(html: str, url: str | None = None) -> str | None:
    try:
        import trafilatura

        text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False, favor_precision=True)
    except Exception:  # pragma: no cover
        text = None
    if not text:
        # 최후 수단: <p> 태그 텍스트
        paras = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.S | re.I)
        text = "\n".join(re.sub(r"<[^>]+>", "", p).strip() for p in paras)
    return text.strip() or None


def is_paywalled(html: str, body: str | None, min_chars: int) -> bool:
    if body is None or len(body) < min_chars:
        return True
    head = html[:200_000]
    return any(m in head for m in PAYWALL_MARKERS) and len(body) < min_chars * 3


def fetch_article(client: httpx.Client, url: str, min_chars: int, max_chars: int) -> str | None:
    r = client.get(url, timeout=20, follow_redirects=True)
    if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
        return None
    body = extract_body(r.text, url)
    if is_paywalled(r.text, body, min_chars):
        return None
    return body[:max_chars] if body else None
