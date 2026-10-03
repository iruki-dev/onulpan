"""이미지 출처 등록부와 사용 전 체크리스트. 기준: docs/images.md

체크리스트 (가이드 그대로):
  1. 출처가 자유 이용 출처 또는 보도용 제공 출처 목록에 있는지 확인한다.
  2. 개별 이미지의 라이선스와 이용 조건을 확인한다.
  3. 원본 형태를 유지한다. 변형은 변경 허용 라이선스에서만 한다.
  4. 지정 크레딧을 이미지 바로 아래에 표기한다.
여기에 보도용 제공 이미지의 범위(해당 소식을 다루는 글에서만)를 더해 다섯 가지를 검사한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import psycopg
import yaml

from ..settings import RULES_DIR

REGISTRY_PATH = RULES_DIR / "image_sources.yaml"


@lru_cache(maxsize=1)
def registry(path: Path = REGISTRY_PATH) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["by_key"] = {s["key"]: s for s in data["sources"]}
    return data


def source(key: str) -> dict | None:
    return registry()["by_key"].get(key)


def license_info(code: str) -> dict | None:
    return registry()["licenses"].get(code)


def sync_sources(conn: psycopg.Connection) -> int:
    """rules/image_sources.yaml → image_sources. 목록에서 빠진 출처는 지우지 않고 끈다(기존 이미지 기록 보존)."""
    reg = registry()
    keys = []
    for i, s in enumerate(reg["sources"]):
        keys.append(s["key"])
        conn.execute(
            """INSERT INTO image_sources (key, name, tier, url, examples, conditions, licenses, scope_required, auto, ord, active)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)
               ON CONFLICT (key) DO UPDATE SET name=EXCLUDED.name, tier=EXCLUDED.tier, url=EXCLUDED.url,
                 examples=EXCLUDED.examples, conditions=EXCLUDED.conditions, licenses=EXCLUDED.licenses,
                 scope_required=EXCLUDED.scope_required, auto=EXCLUDED.auto, ord=EXCLUDED.ord, active=true""",
            (s["key"], s["name"], s["tier"], s.get("url"), s.get("examples", ""), s["conditions"], s["licenses"],
             bool(s.get("scope_required")), bool(s.get("auto")), i),
        )
    conn.execute("UPDATE image_sources SET active = false WHERE NOT (key = ANY(%s))", (keys,))
    return len(keys)


# ── 라이선스 이름 정규화 (Commons 등 외부 표기 → 등록부 코드) ──

def normalize_license(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().lower().replace("_", " ")
    n = re.sub(r"\s+", " ", n)
    if n in ("cc0", "cc0 1.0", "cc-zero", "cc zero") or n.startswith("cc0"):
        return "CC0"
    if n.startswith("public domain") or n in ("pd", "pdm", "public domain mark"):
        return "PD"
    if "pd-usgov" in n or "pd usgov" in n or "pd-nasa" in n:
        return "PD-USGov"
    m = re.match(r"cc[ -]by[ -]sa[ -]?(\d\.\d)([ -]igo)?", n)
    if m:
        code = f"CC-BY-SA-{m.group(1)}" + ("-IGO" if m.group(2) else "")
        return code if license_info(code) else None
    m = re.match(r"cc[ -]by[ -]?(\d\.\d)$", n)
    if m:
        code = f"CC-BY-{m.group(1)}"
        return code if license_info(code) else None
    if "공공누리" in name or n.startswith("kogl"):
        if "0" in n and "1" not in n:
            return "KOGL-0"
        if "1" in n:
            return "KOGL-1"
    return None


def license_label(code: str) -> str:
    info = license_info(code) or {}
    return info.get("label", code)


def license_url(code: str) -> str | None:
    return (license_info(code) or {}).get("url")


def modifiable(code: str) -> bool:
    return bool((license_info(code) or {}).get("modify"))


def make_credit(source_key: str, *, author: str | None = None, provider: str | None = None, license: str | None = None,
                data: str | None = None, designated: str | None = None) -> str:
    """출처가 지정한 크레딧(designated)이 있으면 그대로 쓴다. 없으면 등록부의 틀을 채운다."""
    if designated and designated.strip():
        return designated.strip()
    tpl = (source(source_key) or {}).get("credit", "사진: {provider}")
    lic = license_label(license) if license else ""
    out = tpl.format(author=(author or "").strip() or (provider or ""), provider=(provider or author or "").strip(),
                     license=lic, data=(data or "").strip())
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r",\s*$", "", out.strip()).replace("/,", ",").replace("//", "/")
    return re.sub(r"\s{2,}", " ", out).strip()


# ── 체크리스트 ──

@dataclass
class Candidate:
    """출처에서 찾은(또는 관리 화면에서 등록한) 이미지 한 장의 표기 그대로."""
    source_key: str
    origin_url: str
    file_url: str | None
    alt: str
    license: str | None                      # 등록부 코드로 정규화한 값. 확인하지 못했으면 None
    credit: str
    author: str | None = None
    title: str | None = None
    usage_terms: str | None = None
    license_url: str | None = None
    width: int | None = None
    height: int | None = None
    hotlink: bool = False
    subject: str | None = None
    scope_slug: str | None = None
    query: str | None = None
    restricted: str | None = None             # 이용 조건상 쓸 수 없는 이유 (예: 제3자 저작권 표기)
    extra: dict = field(default_factory=dict)


def checklist(c: Candidate, post_slug: str | None = None, min_width: int = 0) -> dict:
    """다섯 항목의 결과와 근거. 모두 ok여야 쓴다."""
    src = source(c.source_key)
    items: list[dict] = []

    ok1 = src is not None
    items.append({"id": "source", "ok": ok1,
                  "label": "출처가 목록에 있음",
                  "note": f"{src['name']} ({'보도용 제공' if src['tier'] == 'press' else '자체 제작' if src['tier'] == 'own' else '자유 이용'})"
                  if src else f"등록부에 없는 출처: {c.source_key}"})

    lic_ok = bool(src and c.license and c.license in src["licenses"] and not c.restricted)
    if c.restricted:
        note = c.restricted
    elif not c.license:
        note = "개별 이미지의 라이선스를 확인하지 못함"
    elif src and c.license not in src["licenses"]:
        note = f"{license_label(c.license)}는 이 출처에서 받지 않는 라이선스"
    else:
        note = license_label(c.license) + (f" · {c.usage_terms}" if c.usage_terms else "")
    if lic_ok and min_width and c.width and c.width < min_width and c.source_key != "own":
        lic_ok, note = False, f"해상도 부족 ({c.width}px)"
    items.append({"id": "license", "ok": lic_ok, "label": "개별 이미지의 라이선스·이용 조건 확인", "note": note})

    mod = modifiable(c.license) if c.license else False
    items.append({"id": "original", "ok": True, "label": "원본 형태 유지",
                  "note": "변경 허용 라이선스: 비율 맞춤 가능" if mod else "변경 불가: 자르지 않고 원본 비율로 표시"})

    credit_ok = bool(c.credit and c.credit.strip())
    needs_link = bool(c.license and (license_info(c.license) or {}).get("link_required"))
    link = c.license_url or (license_url(c.license) if c.license else None)
    if needs_link and not link:
        credit_ok = False
    items.append({"id": "credit", "ok": credit_ok, "label": "지정 크레딧을 이미지 바로 아래 표기",
                  "note": (c.credit or "크레딧 없음") + (" · 라이선스 링크 포함" if needs_link and link else "")})

    if src and src.get("scope_required"):
        scope_ok = bool(c.scope_slug) and (post_slug is None or c.scope_slug == post_slug)
        note = (f"이 소식(slug: {c.scope_slug})을 다루는 글에서만" if c.scope_slug else "다루는 소식이 지정되지 않음")
        if c.scope_slug and post_slug and c.scope_slug != post_slug:
            note = f"다른 소식의 보도용 이미지 ({c.scope_slug})"
        items.append({"id": "scope", "ok": scope_ok, "label": "해당 소식을 다루는 글에서만", "note": note})

    return {"ok": all(i["ok"] for i in items), "items": items, "modifiable": mod,
            "license_url": link, "tier": src["tier"] if src else None}
