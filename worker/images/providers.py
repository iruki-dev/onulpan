"""자동 검색 출처. 각 출처의 개별 이미지 표기(라이선스, 작가, 이용 제한)를 그대로 읽어 Candidate로 돌려준다.

판단(쓸 수 있는지)은 policy.checklist가 한다. 여기서는 표기를 옮기기만 하고, 출처가 밝힌 제한은 restricted에 적는다.
API 키가 필요한 스톡 출처는 키가 없으면 건너뛴다.
"""
from __future__ import annotations

import html
import logging
import os
import re
from typing import Callable

import httpx

from .brief import Brief
from .policy import Candidate, license_url, make_credit, normalize_license

log = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")


def _text(v: str | None) -> str:
    return html.unescape(_TAG.sub("", v or "")).strip()


def _q(brief: Brief, english: bool) -> str | None:
    return brief.query_en if english else (brief.query_en or brief.query_ko)


# ── NASA: 기관이 직접 제작한 이미지만. 제3자 저작권 표기나 로고·휘장은 제외 ──
_NASA_THIRD_PARTY = re.compile(r"©|copyright|courtesy of (?!nasa)|image credit: (?!nasa)|getty|reuters|associated press|\bAP Photo",
                               re.I)
_NASA_LOGO = re.compile(r"\b(logo|insignia|meatball|emblem|patch)\b", re.I)


def nasa(client: httpx.Client, brief: Brief, n: int) -> list[Candidate]:
    q = _q(brief, english=True)
    if not q:
        return []
    r = client.get("https://images-api.nasa.gov/search", params={"q": q, "media_type": "image", "page_size": n})
    r.raise_for_status()
    out = []
    for item in (r.json().get("collection") or {}).get("items", [])[:n]:
        d = (item.get("data") or [{}])[0]
        nid = d.get("nasa_id")
        if not nid:
            continue
        desc = _text(d.get("description"))
        who = _text(d.get("photographer") or d.get("secondary_creator") or "")
        restricted = None
        if _NASA_THIRD_PARTY.search(desc) or (who and _NASA_THIRD_PARTY.search(who)):
            restricted = "제3자 저작권 표기가 있어 NASA 제작 이미지로 볼 수 없음"
        elif _NASA_LOGO.search(d.get("title") or "") or "logo" in [k.lower() for k in d.get("keywords") or []]:
            restricted = "기관 로고·휘장은 별도 규정 대상"
        if who.upper().startswith("NASA/"):
            credit = f"사진: {who}"                      # NASA 표기 관례 그대로 (예: NASA/Bill Ingalls)
        elif who and "nasa" not in who.lower():
            credit = f"사진: NASA/{who}"
        else:
            credit = "사진: NASA"
        out.append(Candidate(
            source_key="nasa", origin_url=f"https://images.nasa.gov/details/{nid}",
            file_url=f"https://images-assets.nasa.gov/image/{nid}/{nid}~large.jpg",
            alt=brief.alt, license="PD-USGov", credit=credit, author=who or "NASA", title=_text(d.get("title")),
            usage_terms="NASA 미디어 이용 지침: 출처 표시, NASA 보증으로 오해되지 않게", restricted=restricted,
            subject=brief.subject, query=q, extra={"center": d.get("center"), "date": d.get("date_created")},
        ))
    return out


# ── Wikimedia Commons: 파일별 extmetadata의 라이선스·작가 표기를 따른다 ──

def commons(client: httpx.Client, brief: Brief, n: int) -> list[Candidate]:
    q = _q(brief, english=False)
    if not q:
        return []
    r = client.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:bitmap {q}",
        "gsrnamespace": 6, "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 1600,
    })
    r.raise_for_status()
    pages = sorted(((r.json().get("query") or {}).get("pages") or {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        get = lambda k: (md.get(k) or {}).get("value")  # noqa: E731
        lic = normalize_license(get("LicenseShortName"))
        author = _text(get("Artist")) or _text(get("Credit")) or None
        restricted = None
        restr = (get("Restrictions") or "").lower()
        if "trademark" in restr or "insignia" in restr:
            restricted = f"이용 제한 표기: {get('Restrictions')}"
        if lic and lic not in ("CC0", "PD", "PD-USGov") and not author:
            restricted = "저작자 표기가 필요한 라이선스인데 작가 정보가 없음"
        out.append(Candidate(
            source_key="commons", origin_url=ii.get("descriptionurl") or "", file_url=ii.get("thumburl") or ii.get("url"),
            alt=brief.alt, license=lic, credit=make_credit("commons", author=author, license=lic) if lic else "",
            author=author, title=_text(get("ObjectName")) or p.get("title"),
            usage_terms=_text(get("UsageTerms")) or None, license_url=get("LicenseUrl") or (license_url(lic) if lic else None),
            width=ii.get("thumbwidth") or ii.get("width"), height=ii.get("thumbheight") or ii.get("height"),
            restricted=restricted, subject=brief.subject, query=q,
            extra={"license_raw": get("LicenseShortName"), "personality": "personality" in restr},
        ))
    return out


# ── 스톡: 개념·일반 삽화. 항상 작가와 출처를 표시한다 ──

def unsplash(client: httpx.Client, brief: Brief, n: int) -> list[Candidate]:
    key, q = os.environ.get("UNSPLASH_ACCESS_KEY"), _q(brief, english=True)
    if not key or not q:
        return []
    r = client.get("https://api.unsplash.com/search/photos", headers={"Authorization": f"Client-ID {key}"},
                   params={"query": q, "per_page": n, "orientation": "landscape", "content_filter": "high"})
    r.raise_for_status()
    out = []
    for ph in r.json().get("results", [])[:n]:
        name = (ph.get("user") or {}).get("name") or "Unsplash"
        raw = (ph.get("urls") or {}).get("raw")
        w, h = ph.get("width"), ph.get("height")
        out.append(Candidate(
            source_key="unsplash", origin_url=(ph.get("links") or {}).get("html") or "",
            # Unsplash API 지침: 원본 주소로 불러온다(hotlink), 고를 때 download_location을 한 번 부른다
            file_url=f"{raw}&w=1600&q=80&fm=jpg" if raw else None, hotlink=True,
            alt=brief.alt, license="Unsplash", credit=make_credit("unsplash", author=name), author=name,
            width=1600 if w else None, height=round(h * 1600 / w) if w and h else None, subject=brief.subject, query=q,
            extra={"download_location": (ph.get("links") or {}).get("download_location")},
        ))
    return out


def pexels(client: httpx.Client, brief: Brief, n: int) -> list[Candidate]:
    key, q = os.environ.get("PEXELS_API_KEY"), _q(brief, english=True)
    if not key or not q:
        return []
    r = client.get("https://api.pexels.com/v1/search", headers={"Authorization": key},
                   params={"query": q, "per_page": n, "orientation": "landscape"})
    r.raise_for_status()
    return [Candidate(
        source_key="pexels", origin_url=ph.get("url") or "", file_url=(ph.get("src") or {}).get("large2x"),
        alt=ph.get("alt") or brief.alt, license="Pexels", credit=make_credit("pexels", author=ph.get("photographer")),
        author=ph.get("photographer"), width=ph.get("width"), height=ph.get("height"), subject=brief.subject, query=q,
    ) for ph in r.json().get("photos", [])[:n]]


def pixabay(client: httpx.Client, brief: Brief, n: int) -> list[Candidate]:
    key, q = os.environ.get("PIXABAY_API_KEY"), _q(brief, english=True)
    if not key or not q:
        return []
    r = client.get("https://pixabay.com/api/", params={"key": key, "q": q, "image_type": "photo",
                                                       "orientation": "horizontal", "per_page": max(3, n), "safesearch": "true"})
    r.raise_for_status()
    return [Candidate(
        source_key="pixabay", origin_url=hit.get("pageURL") or "", file_url=hit.get("largeImageURL"),
        alt=brief.alt, license="Pixabay", credit=make_credit("pixabay", author=hit.get("user")), author=hit.get("user"),
        width=hit.get("imageWidth"), height=hit.get("imageHeight"), subject=brief.subject, query=q,
    ) for hit in r.json().get("hits", [])[:n]]


PROVIDERS: dict[str, Callable[[httpx.Client, Brief, int], list[Candidate]]] = {
    "nasa": nasa, "commons": commons, "unsplash": unsplash, "pexels": pexels, "pixabay": pixabay,
}


def after_select(client: httpx.Client, c: Candidate) -> None:
    """출처 약관이 요구하는 선택 후 호출 (Unsplash 다운로드 집계)."""
    loc = c.extra.get("download_location")
    if c.source_key == "unsplash" and loc and os.environ.get("UNSPLASH_ACCESS_KEY"):
        try:
            client.get(loc, headers={"Authorization": f"Client-ID {os.environ['UNSPLASH_ACCESS_KEY']}"})
        except httpx.HTTPError as e:  # pragma: no cover
            log.warning("unsplash download ping failed: %s", e)
