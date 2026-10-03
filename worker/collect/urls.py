"""URL 정규화: 추적 파라미터를 지워 같은 기사가 두 번 저장되지 않게 한다 (UNIQUE로 차단)."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "dclid", "yclid", "mc_", "_ga", "igshid", "spm")
TRACKING_KEYS = {
    "ref", "ref_src", "from", "source", "cmpid", "rss", "rssid", "outlink", "fromrss",
    "mobile", "naver", "daum", "kakao", "share", "sns", "plink", "ocid", "lt", "cid",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    host = parts.netloc.lower()
    if host.startswith("m.") and host.count(".") >= 2:
        host = "www." + host[2:]
    if host.endswith(":443") or host.endswith(":80"):
        host = host.rsplit(":", 1)[0]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_KEYS
    ]
    query.sort()
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def domain_of(url: str) -> str:
    host = urlsplit(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host
