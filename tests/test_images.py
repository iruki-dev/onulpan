"""뉴스 이미지: docs/images.md의 원칙이 코드로 지켜지는지."""
from __future__ import annotations

import io
import json
from datetime import timedelta

import httpx
import pytest

from worker.dev.fake import FakeLLM
from worker.images import graphics, picker, policy, providers
from worker.images.brief import Brief, classify_field
from worker.jobs import tasks
from worker.mail.render import render_edition

from helpers import full_day


@pytest.fixture(autouse=True)
def image_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_DIR", str(tmp_path / "images"))
    return tmp_path / "images"


def png(w=2000, h=1200, color=(40, 90, 140)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG")
    return buf.getvalue()


NASA_JSON = {"collection": {"items": [
    {"data": [{"nasa_id": "x1", "title": "Moon from orbit", "description": "Image © Someone Else Photography",
               "photographer": "Someone Else", "keywords": ["moon"]}]},
    {"data": [{"nasa_id": "logo1", "title": "NASA Insignia", "description": "The NASA logo", "keywords": ["logo"]}]},
    {"data": [{"nasa_id": "art001", "title": "Artemis rollout", "description": "The rocket rolls out at Kennedy.",
               "photographer": "NASA/Joel Kowsky", "keywords": ["Artemis"]}]},
]}}

COMMONS_JSON = {"query": {"pages": {
    "1": {"index": 1, "title": "File:NC.jpg", "imageinfo": [{
        "thumburl": "https://upload.wikimedia.org/nc.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:NC.jpg",
        "thumbwidth": 1600, "thumbheight": 1000,
        "extmetadata": {"LicenseShortName": {"value": "CC BY-NC 4.0"}, "Artist": {"value": "<a href='x'>Kim</a>"}}}]},
    "2": {"index": 2, "title": "File:Bridge.jpg", "imageinfo": [{
        "thumburl": "https://upload.wikimedia.org/bridge.jpg",
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Bridge.jpg", "thumbwidth": 1600, "thumbheight": 1067,
        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                        "Artist": {"value": "<a href='https://commons.wikimedia.org/wiki/User:Lee'>Lee Minho</a>"}}}]},
}}}


def mock_client(calls: list | None = None) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(req.url))
        host = req.url.host
        if host == "images-api.nasa.gov":
            return httpx.Response(200, json=NASA_JSON)
        if host == "commons.wikimedia.org":
            return httpx.Response(200, json=COMMONS_JSON)
        if host in ("images-assets.nasa.gov", "upload.wikimedia.org", "www.korea.kr", "press.example.com"):
            return httpx.Response(200, content=png(), headers={"content-type": "image/jpeg"})
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def make_post(conn, title, section="scitech", slug=None, kind="fact", at=None, display=None):
    if slug:
        conn.execute("INSERT INTO slugs (slug, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (slug, display or slug.replace("-", " ")))
    row = conn.execute(
        """INSERT INTO posts (kind, section, slug, title, summary, body_md, char_count, model, prompt_version,
                              verify_report, cost_usd, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,10,'m','v','{}',0,%s) RETURNING seq, kind::text AS kind, section::text AS section,
                  slug, title, summary, body_md""",
        (kind, section, slug, title, title + " 요약", title + " 본문", at),
    ).fetchone()
    conn.commit()
    return row


# ── 등록부와 크레딧 ──

def test_registry_matches_guide():
    reg = policy.registry()
    free = {s["key"] for s in reg["sources"] if s["tier"] == "free"}
    press = {s["key"] for s in reg["sources"] if s["tier"] == "press"}
    assert {"kogl", "gongu", "nasa", "nih", "noaa", "esa_hubble", "commons", "unsplash", "pexels", "pixabay"} <= free
    assert {"newsroom", "eurekalert", "esa", "prwire", "organizer"} <= press
    assert all(policy.source(k)["scope_required"] for k in press)          # 해당 소식을 다루는 글에서만
    for field, keys in reg["priority"].items():                             # 분야별 순서의 모든 출처가 등록부에 있다
        for k in keys:
            assert k == "stock" or policy.source(k), (field, k)
    assert picker.chain("space")[:2] == ["nasa", "esa_hubble"]
    assert picker.chain("economy") == ["newsroom", "prwire", "unsplash", "pexels", "pixabay"]


def test_credit_examples_from_guide():
    assert policy.make_credit("kogl", provider="○○시", license="KOGL-1") == "사진: ○○시 제공 (공공누리 제1유형)"
    assert policy.make_credit("nasa") == "사진: NASA"
    assert policy.make_credit("esa_hubble") == "이미지: ESA/Hubble, CC BY 4.0"
    assert policy.make_credit("esa", author="촬영자") == "이미지: ESA/촬영자"
    assert policy.make_credit("newsroom", designated="사진: Intel Corporation") == "사진: Intel Corporation"
    assert policy.make_credit("unsplash", author="작가명") == "사진: 작가명/Unsplash"
    assert policy.make_credit("own", data="원자료 기관") == "그래픽: 오늘판 · 자료: 원자료 기관"


def test_license_normalization():
    n = policy.normalize_license
    assert n("CC BY-SA 4.0") == "CC-BY-SA-4.0" and n("cc-by-sa-3.0-igo") == "CC-BY-SA-3.0-IGO"
    assert n("CC BY 4.0") == "CC-BY-4.0" and n("CC0") == "CC0" and n("Public domain") == "PD"
    assert n("CC BY-NC 4.0") is None and n("CC BY-ND 4.0") is None and n("All rights reserved") is None


# ── 체크리스트 ──

def _c(**kw):
    base = dict(source_key="commons", origin_url="https://c/x", file_url="https://c/x.jpg", alt="다리",
                license="CC-BY-4.0", credit="사진: Kim/Wikimedia Commons, CC BY 4.0", width=1600)
    base.update(kw)
    return policy.Candidate(**base)


def test_checklist_items():
    ok = policy.checklist(_c())
    assert ok["ok"] and [i["id"] for i in ok["items"]] == ["source", "license", "original", "credit"]
    assert ok["modifiable"] is True
    assert not policy.checklist(_c(source_key="getty"))["ok"]                       # 1. 목록에 없는 출처
    assert not policy.checklist(_c(license=None))["ok"]                             # 2. 라이선스 미확인
    assert not policy.checklist(_c(source_key="nasa", license="CC-BY-4.0"))["ok"]   # 2. 출처가 받지 않는 라이선스
    assert not policy.checklist(_c(restricted="제3자 저작권"))["ok"]
    sa = policy.checklist(_c(license="CC-BY-SA-4.0", license_url=None))
    assert sa["ok"] and sa["modifiable"] is False                                   # 3. SA는 변형하지 않는다
    assert sa["license_url"]                                                        # 4. 라이선스 링크 포함
    assert not policy.checklist(_c(credit=""))["ok"]                                # 4. 크레딧 없음
    assert not policy.checklist(_c(width=500), min_width=800)["ok"]


def test_press_scope():
    press = _c(source_key="newsroom", license="press", credit="사진: 누리전자", scope_slug="누리전자-실적")
    assert policy.checklist(press, "누리전자-실적")["ok"]
    assert not policy.checklist(press, "다른-소식")["ok"]
    assert not policy.checklist(_c(source_key="newsroom", license="press", credit="사진: X"))["ok"]
    assert policy.checklist(press)["modifiable"] is False                           # 보도용은 원본 유지


# ── 출처별 표기 읽기 ──

def test_nasa_excludes_third_party_and_logos():
    b = Brief(field="space", subject="object", query_ko="로켓", query_en="Artemis rocket", alt="로켓이 발사대로 옮겨지는 모습")
    with mock_client() as c:
        cands = providers.nasa(c, b, 5)
    by_id = {x.origin_url.rsplit("/", 1)[-1]: x for x in cands}
    assert by_id["x1"].restricted and by_id["logo1"].restricted
    good = by_id["art001"]
    assert good.restricted is None and good.license == "PD-USGov" and good.credit == "사진: NASA/Joel Kowsky"
    assert good.file_url.endswith("art001~large.jpg")


def test_commons_reads_per_file_license():
    b = Brief(field="world", subject="place", query_ko="다리", query_en="bridge", alt="강 위의 다리")
    with mock_client() as c:
        cands = providers.commons(c, b, 5)
    assert cands[0].license is None                                              # NC는 받지 않는다
    assert not policy.checklist(cands[0])["ok"]
    sa = cands[1]
    assert sa.license == "CC-BY-SA-4.0" and sa.author == "Lee Minho"
    assert sa.credit == "사진: Lee Minho/Wikimedia Commons, CC BY-SA 4.0"
    assert policy.checklist(sa)["ok"]


def test_stock_skipped_without_keys(monkeypatch):
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    b = Brief(field="economy", subject="concept", query_ko="반도체", query_en="semiconductor", alt="반도체 웨이퍼")
    with mock_client() as c:
        assert providers.unsplash(c, b, 3) == []


def test_field_classification():
    assert classify_field("scitech", "누리호 위성 발사 성공") == "space"
    assert classify_field("scitech", "전고체 배터리 수명 늘린 소재") == "tech"
    assert classify_field("scitech", "연구팀이 새 효소를 발견") == "science"
    assert classify_field("politics", "예산안") == "politics"


# ── 찾기와 붙이기 ──

def test_find_space_image_beta_pending(conn, s, now, image_dir):
    post = make_post(conn, "누리호 위성 발사 준비", at=now)
    with mock_client() as c:
        r = picker.find_for_post(conn, s, post, now, client=c, llm=FakeLLM([]))
    conn.commit()
    assert r["outcome"] == "attached" and r["chosen"]["source"] == "nasa"
    img = conn.execute("SELECT * FROM images WHERE id = %s", (r["chosen"]["image_id"],)).fetchone()
    assert img["status"] == "pending"                                           # 베타: 관리 화면 승인 뒤 실린다
    assert img["credit"] == "사진: NASA/Joel Kowsky" and img["license"] == "PD-USGov"
    assert img["checklist"]["ok"] and img["width"] == s["images"]["render_width"] and img["height"] == 960  # 비율 유지
    assert (image_dir / img["stored_path"]).exists() and (image_dir / img["original_path"]).exists()
    log = conn.execute("SELECT payload FROM decision_log WHERE kind='image'").fetchone()["payload"]
    assert log["tried"][0]["source"] == "nasa" and len(log["tried"][0]["rejected"]) == 2


def test_launch_auto_approves_but_not_people(conn, s_launch, now):
    s_launch["images"]["vision_check"] = False
    post = make_post(conn, "누리호 위성 발사 준비", at=now)
    with mock_client() as c:
        r = picker.find_for_post(conn, s_launch, post, now, client=c, llm=FakeLLM([]))
    assert conn.execute("SELECT status FROM images WHERE id=%s", (r["chosen"]["image_id"],)).fetchone()["status"] == "active"
    c2 = policy.Candidate(source_key="commons", origin_url="o", file_url="f", alt="a", license="CC0", credit="c",
                          subject="person")
    assert picker._status_for(c2, s_launch, "auto") == "pending"


def test_vision_check_rejects_mismatch(conn, s_launch, now):
    post = make_post(conn, "누리호 위성 발사 준비", at=now)

    class NoMatch(FakeLLM):
        def create(self, params):
            if isinstance(params["messages"][0]["content"], list):
                from worker.generate.gateway import LLMResult, Usage
                return LLMResult(text='{"match": false}', model="m", usage=Usage(1, 1))
            return super().create(params)
    with mock_client() as c:
        r = picker.find_for_post(conn, s_launch, post, now, client=c, llm=NoMatch([]))
    assert r["outcome"] in ("none", "attached")
    assert r["chosen"] is None or r["chosen"]["source"] != "nasa"


def test_press_library_only_for_same_story(conn, s, now):
    picker.ensure_sources(conn)
    a = make_post(conn, "누리전자 신제품 공개", section="economy", slug="누리전자-신제품", at=now)
    b = make_post(conn, "다른 회사 실적", section="economy", slug="다른-회사", at=now)
    check = policy.checklist(_c(source_key="newsroom", license="press", credit="사진: 누리전자", scope_slug="누리전자-신제품"))
    iid = conn.execute(
        """INSERT INTO images (source_key, origin_url, file_url, stored_path, alt, license, credit, modifiable, scope_slug,
                               checklist, status, found_by)
           VALUES ('newsroom','https://press.example.com/kit','https://press.example.com/a.jpg','r/x.jpg','신제품',
                   'press','사진: 누리전자',false,'누리전자-신제품',%s,'active','admin') RETURNING id""",
        (json.dumps(check),),
    ).fetchone()["id"]
    conn.commit()
    with mock_client() as c:
        ra = picker.find_for_post(conn, s, a, now, client=c)
        rb = picker.find_for_post(conn, s, b, now, client=c)
    assert ra["chosen"] == {"image_id": iid, "source": "newsroom", "from": "library"}
    assert rb["chosen"] is None or rb["chosen"]["image_id"] != iid


@pytest.mark.skipif(graphics.font_path() is None, reason="한글 글꼴 없음")
def test_own_timeline_graphic(conn, s, now, image_dir):
    full_day(conn, s, now)
    slug = "예산-심사"
    make_post(conn, "예산안 국회 제출", section="politics", slug=slug, at=now - timedelta(days=3), display="내년도 예산안")
    make_post(conn, "예결위 심사 시작", section="politics", slug=slug, at=now - timedelta(days=1))
    post = make_post(conn, "가람당 증액, 새벽당 감액 요구", section="politics", slug=slug, at=now)
    with mock_client() as c:
        r = picker.find_for_post(conn, s, post, now, client=c)
    assert r["chosen"]["source"] == "own"
    img = conn.execute("SELECT * FROM images WHERE id=%s", (r["chosen"]["image_id"],)).fetchone()
    assert img["status"] == "active" and img["credit"].startswith("그래픽: 오늘판 · 자료:")
    assert img["mime"] == "image/png" and (image_dir / img["stored_path"]).exists()


def test_run_task_marks_attempts(conn, s, now):
    full_day(conn, s, now)
    out = picker.run(conn, s, now, client=mock_client())
    n = conn.execute("SELECT count(*) AS n FROM image_searches").fetchone()["n"]
    assert n == sum(out.values()) and n > 0
    assert picker.run(conn, s, now, client=mock_client())["none"] == 0          # 같은 시각에 다시 찾지 않는다


# ── 관리 화면 등록, 권리자 요청 ──

def _register(conn, **kw):
    picker.ensure_sources(conn)
    v = dict(source_key="kogl", origin_url="https://www.korea.kr/photo/1", file_url="https://www.korea.kr/1.jpg",
             alt="정부세종청사 전경", license="KOGL-1", credit="사진: 행정안전부 제공 (공공누리 제1유형)", scope_slug=None)
    v.update(kw)
    iid = conn.execute(
        """INSERT INTO images (source_key, origin_url, file_url, alt, license, credit, scope_slug, status, found_by)
           VALUES (%(source_key)s,%(origin_url)s,%(file_url)s,%(alt)s,%(license)s,%(credit)s,%(scope_slug)s,'fetching','admin')
           RETURNING id""", v).fetchone()["id"]
    conn.commit()
    return iid


def test_admin_registered_image(conn, s, now, image_dir):
    post = make_post(conn, "세종청사 이전 계획", section="politics", slug="청사-이전", at=now)
    iid = _register(conn)
    r = picker.fetch_registered(conn, s, iid, now, attach_seq=post["seq"], client=mock_client())
    assert r["status"] == "active"
    row = conn.execute("SELECT * FROM images WHERE id=%s", (iid,)).fetchone()
    assert row["modifiable"] is True and (image_dir / row["stored_path"]).exists()
    assert conn.execute("SELECT count(*) AS n FROM post_images WHERE post_seq=%s AND status='active'",
                        (post["seq"],)).fetchone()["n"] == 1
    bad = _register(conn, source_key="newsroom", license="press", file_url="https://press.example.com/b.jpg",
                    credit="사진: X")                                            # 보도용인데 다루는 소식이 없다
    assert picker.fetch_registered(conn, s, bad, now, client=mock_client())["status"] == "failed"


class Outbox:
    def __init__(self):
        self.sent = []

    def send(self, to, mail):
        self.sent.append((to, mail))
        return f"m{len(self.sent)}"


def test_rights_request_takes_down_and_replies(conn, s, now, monkeypatch):
    post = make_post(conn, "누리호 위성 발사 준비", at=now)
    with mock_client() as c:
        r = picker.find_for_post(conn, s, post, now, client=c, llm=FakeLLM([]))
    iid = r["chosen"]["image_id"]
    conn.execute("UPDATE images SET status='active' WHERE id=%s", (iid,))
    # 웹이 하는 일: 접수와 동시에 내린다
    rid = conn.execute(
        """INSERT INTO image_requests (image_id, name, email, relation, body) VALUES (%s,'홍길동','h@x.kr','owner','제 사진입니다')
           RETURNING id""", (iid,)).fetchone()["id"]
    conn.execute("UPDATE images SET status='taken_down', taken_down_at=now() WHERE id=%s", (iid,))
    conn.commit()
    delivered = []
    monkeypatch.setattr("worker.ops.alerts._deliver", lambda text: delivered.append(text) or True)
    box = Outbox()
    out = picker.handle_request(conn, s, rid, now, sender=box, llm=FakeLLM([]), client=mock_client())
    assert box.sent[0][0] == "h@x.kr" and "내렸습니다" in box.sent[0][1].text
    assert delivered and "#%d" % rid in delivered[0]
    assert conn.execute("SELECT acked_at FROM image_requests WHERE id=%s", (rid,)).fetchone()["acked_at"]
    # 대체 후보는 내린 이미지를 빼고 찾고, 승인 대기로 둔다
    rep = out["replacements"][0]
    if rep["chosen"]:
        assert rep["chosen"]["image_id"] != iid
        assert conn.execute("SELECT status FROM images WHERE id=%s", (rep["chosen"]["image_id"],)).fetchone()["status"] == "pending"
    # 처리 결과 회신
    conn.execute("UPDATE image_requests SET status='removed', resolution='출처 표기를 확인하지 못해 내린 상태로 둡니다.' WHERE id=%s",
                 (rid,))
    conn.commit()
    assert picker.send_reply(conn, rid, box) and "내린 상태로" in box.sent[-1][1].text


def test_email_shows_lead_image_with_credit(conn, s, now):
    full_day(conn, s, now)
    uid = conn.execute("INSERT INTO users (email, provider) VALUES ('r@x.kr','email') RETURNING id").fetchone()["id"]
    conn.commit()
    tasks.front(conn, s, now)
    tasks.assemble_morning(conn, s, now)
    eid = conn.execute("SELECT id, slots FROM editions WHERE user_id=%s", (uid,)).fetchone()
    lead = next(x["seq"] for x in eid["slots"] if x["slot"] == "front")
    iid = _register(conn, file_url="https://www.korea.kr/lead.jpg")
    picker.fetch_registered(conn, s, iid, now, attach_seq=lead, client=mock_client())
    mail = render_edition(conn, eid["id"])
    assert f"/img/{iid}" in mail.html and "사진: 행정안전부 제공 (공공누리 제1유형)" in mail.html
    conn.execute("UPDATE images SET status='taken_down' WHERE id=%s", (iid,))
    conn.commit()
    assert f"/img/{iid}" not in render_edition(conn, eid["id"]).html            # 내린 이미지는 바로 빠진다


def test_web_license_labels_match_registry():
    """웹(lib/labels.ts LICENSES)과 등록부의 라이선스 표기가 같아야 한다."""
    import re
    from pathlib import Path

    ts = (Path(__file__).resolve().parent.parent / "web" / "lib" / "labels.ts").read_text(encoding="utf-8")
    block = ts[ts.index("export const LICENSES"):ts.index("export const TIER_KO")]
    web = {m.group(1) or m.group(2): m.group(3) for m in re.finditer(r'(?:"([A-Za-z0-9.-]+)"|([A-Za-z0-9]+)): \{ label: "([^"]+)"', block)}
    reg = {k: v["label"] for k, v in policy.registry()["licenses"].items()}
    assert web == reg
    for k, v in policy.registry()["licenses"].items():
        if v.get("link_required"):
            assert re.search(rf'"{re.escape(k)}": \{{[^}}]*link: true', block), k
