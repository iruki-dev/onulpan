"""글에 대표 이미지를 붙인다. 분야별 순서(rules/image_sources.yaml priority)대로 1순위부터 확인한다.

한 출처 안에서는 (1) 관리 화면에서 등록해 둔 이미지 중 이 소식에 맞는 것, (2) 자동 검색 결과 순으로 본다.
후보마다 사용 전 체크리스트를 돌리고, 모두 통과한 첫 후보를 쓴다. 판단 과정은 decision_log(kind='image')에 남긴다.

승인: 자체 그래픽과 관리자가 등록한 이미지는 바로 실린다. 자동으로 찾은 사진은 images.auto_approve가 켜져 있고
대상이 인물이 아닐 때만 바로 실리고, 나머지는 관리 화면 승인 뒤에 실린다(잘못된 인물 사진을 막기 위해).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx
import psycopg

from ..db import jsonb, log_decision
from ..generate.gateway import LLMClient
from ..generate.models import light_call
from ..generate.prompts import parse_json_output
from ..settings import Settings
from ..timeutil import kst
from . import graphics, policy, providers, store
from .brief import Brief, make_brief

log = logging.getLogger(__name__)
STOCK = ["unsplash", "pexels", "pixabay"]


def http_client(s: Settings) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": s["collect"]["user_agent"]}, timeout=20, follow_redirects=True)


def ensure_sources(conn: psycopg.Connection) -> None:
    if conn.execute("SELECT count(*) AS n FROM image_sources").fetchone()["n"] == 0:
        policy.sync_sources(conn)


def chain(field: str) -> list[str]:
    out: list[str] = []
    for k in policy.registry()["priority"].get(field, policy.registry()["priority"]["society"]):
        out.extend(STOCK if k == "stock" else [k])
    return out


def _status_for(c: policy.Candidate, s: Settings, found_by: str) -> str:
    if found_by in ("admin", "graphic"):
        return "active"
    if s["images"].get("auto_approve") and c.subject != "person" and not c.extra.get("personality"):
        return "active"
    return "pending"


def _existing(conn: psycopg.Connection, c: policy.Candidate) -> dict | None:
    if not c.file_url:
        return None
    return conn.execute("SELECT * FROM images WHERE source_key = %s AND file_url = %s", (c.source_key, c.file_url)).fetchone()


def store_candidate(conn: psycopg.Connection, client: httpx.Client | None, s: Settings, c: policy.Candidate, check: dict,
                    found_by: str, now: datetime, content: tuple[bytes, str] | None = None) -> int:
    """파일을 받아 저장하고 images 행을 만든다. 같은 파일이 이미 있으면 그 행을 쓴다."""
    row = _existing(conn, c)
    if row:
        return row["id"]
    info: dict = {}
    if not c.hotlink:
        if content is None:
            assert client is not None and c.file_url
            content = store.download(client, c.file_url, s["images"]["max_bytes"])
        info = store.save(*content, s["images"]["render_width"], prefer_png=found_by == "graphic")
    width = info.get("width") or c.width
    height = info.get("height") or c.height
    return conn.execute(
        """INSERT INTO images (source_key, origin_url, file_url, hotlink, stored_path, original_path, sha256, mime, width, height,
                               title, alt, author, license, license_url, credit, usage_terms, modifiable, subject, scope_slug,
                               query, checklist, status, found_by, reviewed_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (c.source_key, c.origin_url, c.file_url, c.hotlink, info.get("stored_path"), info.get("original_path"),
         info.get("sha256"), info.get("mime"), width, height, c.title, c.alt, c.author, c.license,
         check.get("license_url"), c.credit, c.usage_terms, check["modifiable"], c.subject, c.scope_slug, c.query,
         jsonb(check), _status_for(c, s, found_by), found_by, now if found_by in ("admin", "graphic") else None),
    ).fetchone()["id"]


def attach(conn: psycopg.Connection, post_seq: int, image_id: int, now: datetime) -> None:
    conn.execute("UPDATE post_images SET status='removed', removed_at=%s, removed_reason='replaced' "
                 "WHERE post_seq=%s AND role='lead' AND status='active'", (now, post_seq))
    conn.execute("INSERT INTO post_images (post_seq, image_id, created_at) VALUES (%s,%s,%s)", (post_seq, image_id, now))


def _row_candidate(row: dict) -> policy.Candidate:
    return policy.Candidate(
        source_key=row["source_key"], origin_url=row["origin_url"], file_url=row["file_url"], alt=row["alt"],
        license=row["license"], credit=row["credit"], author=row["author"], title=row["title"],
        usage_terms=row["usage_terms"], license_url=row["license_url"], width=row["width"], height=row["height"],
        hotlink=row["hotlink"], subject=row["subject"], scope_slug=row["scope_slug"])


def library(conn: psycopg.Connection, key: str, post: dict, exclude: set[int]) -> list[dict]:
    """관리 화면에서 등록해 둔 이미지 중 이 글의 소식(slug)에 맞는 것."""
    if not post.get("slug"):
        return []
    return conn.execute(
        """SELECT * FROM images WHERE source_key = %s AND status = 'active' AND scope_slug = %s AND NOT (id = ANY(%s))
           ORDER BY id DESC LIMIT 3""",
        (key, post["slug"], list(exclude)),
    ).fetchall()


def vision_ok(conn: psycopg.Connection, llm: LLMClient, s: Settings, c: policy.Candidate, brief: Brief, post: dict) -> bool:
    """출시 모드: 사진이 기사 대상과 맞는지 Claude가 한 번 본다. 판정 실패는 통과로 보지 않는다."""
    if not c.file_url:
        return False
    system = ("너는 신문 사진부 담당자다. 사진이 기사에 실을 대표 이미지로 맞는지 판정한다. "
              "다른 인물·다른 장소이거나 기사와 관계없으면 match는 false. 출력은 JSON 하나뿐이다: "
              '{"match": true, "reason": "한 문장"}')
    content = [{"type": "image", "source": {"type": "url", "url": c.file_url}},
               {"type": "text", "text": f"기사 제목: {post['title']}\n찾던 대상: {brief.query_ko} ({brief.subject})"}]
    res = light_call(conn, llm, s, "image_vision", system, content, 200)
    if res is None or not res.ok:
        return False
    try:
        return bool(parse_json_output(res.text).get("match"))
    except (ValueError, json.JSONDecodeError):
        return False


def find_for_post(conn: psycopg.Connection, s: Settings, post: dict, now: datetime, *, client: httpx.Client | None = None,
                  llm: LLMClient | None = None, exclude: set[int] | None = None) -> dict:
    """한 편에 대표 이미지를 찾아 붙인다. 결과 요약을 돌려준다(호출자가 커밋)."""
    ensure_sources(conn)
    exclude = set(exclude or ())
    cfg = s["images"]
    brief = make_brief(conn, s, post, llm)
    tried: list[dict] = []
    chosen: dict | None = None
    own_client = client is None
    client = client or http_client(s)
    try:
        for key in chain(brief.field):
            src = policy.source(key)
            if not src:
                continue
            entry: dict = {"source": key, "library": 0, "found": 0, "rejected": []}
            tried.append(entry)
            # (1) 등록해 둔 이미지
            for row in library(conn, key, post, exclude):
                entry["library"] += 1
                check = policy.checklist(_row_candidate(row), post.get("slug"))
                if check["ok"]:
                    attach(conn, post["seq"], row["id"], now)
                    chosen = {"image_id": row["id"], "source": key, "from": "library"}
                    break
                entry["rejected"].append({"image_id": row["id"], "why": [i["id"] for i in check["items"] if not i["ok"]]})
            if chosen:
                break
            # (2) 자동 검색 / 자체 그래픽
            cands: list[policy.Candidate] = []
            graphic_png: bytes | None = None
            if key == "own":
                g = graphics.timeline_for_slug(conn, post["slug"], post["seq"]) if post.get("slug") else None
                if g:
                    graphic_png = g["png"]
                    cands = [policy.Candidate(
                        source_key="own", origin_url=f"/w/{post['slug']}", file_url=f"own:timeline:{post['seq']}",
                        alt=g["alt"], license="own", credit=policy.make_credit("own", data=g["data"]), author="오늘판",
                        title=g["title"], subject="data", query="timeline", width=1200)]
            elif key in providers.PROVIDERS and src.get("auto"):
                try:
                    cands = providers.PROVIDERS[key](client, brief, cfg["candidates_per_source"])
                except (httpx.HTTPError, ValueError) as e:
                    entry["error"] = str(e)[:200]
                    continue
            entry["found"] = len(cands)
            for c in cands:
                prev = _existing(conn, c)
                if prev and (prev["status"] in ("rejected", "taken_down", "failed") or prev["id"] in exclude):
                    entry["rejected"].append({"file": c.file_url, "why": [f"이전 판정: {prev['status']}"]})
                    continue
                check = policy.checklist(c, post.get("slug"), cfg.get("min_width", 0))
                if not check["ok"]:
                    entry["rejected"].append({"file": c.file_url, "why": [i["note"] for i in check["items"] if not i["ok"]]})
                    continue
                if key != "own" and cfg.get("vision_check") and llm is not None and not vision_ok(conn, llm, s, c, brief, post):
                    entry["rejected"].append({"file": c.file_url, "why": ["사진이 기사 대상과 맞지 않음(판정)"]})
                    continue
                try:
                    content = (graphic_png, "image/png") if graphic_png else None
                    iid = store_candidate(conn, client, s, c, check, "graphic" if key == "own" else "auto", now, content)
                except (store.ImageError, httpx.HTTPError) as e:
                    entry["rejected"].append({"file": c.file_url, "why": [str(e)[:120]]})
                    continue
                providers.after_select(client, c)
                attach(conn, post["seq"], iid, now)
                chosen = {"image_id": iid, "source": key, "from": "graphic" if key == "own" else "search"}
                break
            if chosen:
                break
    finally:
        if own_client:
            client.close()

    outcome = "attached" if chosen else "none"
    conn.execute(
        """INSERT INTO image_searches (post_seq, attempts, last_at, outcome, brief) VALUES (%s, 1, %s, %s, %s)
           ON CONFLICT (post_seq) DO UPDATE SET attempts = image_searches.attempts + 1, last_at = EXCLUDED.last_at,
             outcome = EXCLUDED.outcome, brief = EXCLUDED.brief""",
        (post["seq"], now, outcome, jsonb(brief.to_json())),
    )
    log_decision(conn, "image", f"post:{post['seq']}", {"brief": brief.to_json(), "tried": tried, "chosen": chosen})
    return {"seq": post["seq"], "outcome": outcome, "chosen": chosen, "field": brief.field}


def posts_needing_images(conn: psycopg.Connection, s: Settings, now: datetime) -> list[dict]:
    cfg = s["images"]
    return conn.execute(
        """SELECT p.seq, p.kind::text AS kind, p.section::text AS section, p.slug, p.title, p.summary, p.body_md
           FROM posts p LEFT JOIN image_searches q ON q.post_seq = p.seq
           WHERE p.created_at > %s AND p.kind::text = ANY(%s)
             AND NOT EXISTS (SELECT 1 FROM post_images pi JOIN images i ON i.id = pi.image_id
                             WHERE pi.post_seq = p.seq AND pi.status = 'active' AND i.status IN ('active','pending'))
             AND (q.post_seq IS NULL OR (q.attempts < %s AND q.last_at < %s))
           ORDER BY p.importance DESC, p.seq DESC LIMIT %s""",
        (now - timedelta(hours=cfg["lookback_hours"]), cfg["kinds"], cfg["max_attempts"],
         now - timedelta(hours=cfg["retry_hours"]), cfg["per_run"]),
    ).fetchall()


def run(conn: psycopg.Connection, s: Settings, now: datetime, llm: LLMClient | None = None,
        client: httpx.Client | None = None) -> dict:
    if not s["images"].get("enabled"):
        return {"skipped": "disabled"}
    ensure_sources(conn)
    out = {"attached": 0, "none": 0, "error": 0}
    for post in posts_needing_images(conn, s, now):
        try:
            r = find_for_post(conn, s, post, now, client=client, llm=llm)
            out[r["outcome"]] += 1
            conn.commit()
        except Exception:  # noqa: BLE001 — 한 편의 실패가 다른 글을 막지 않는다
            log.exception("image search failed for %s", post["seq"])
            conn.rollback()
            conn.execute(
                """INSERT INTO image_searches (post_seq, attempts, last_at, outcome) VALUES (%s, 1, %s, 'error')
                   ON CONFLICT (post_seq) DO UPDATE SET attempts = image_searches.attempts + 1, last_at = EXCLUDED.last_at,
                     outcome = 'error'""",
                (post["seq"], now),
            )
            conn.commit()
            out["error"] += 1
    return out


# ── 관리 화면에서 등록한 이미지 ──

def fetch_registered(conn: psycopg.Connection, s: Settings, image_id: int, now: datetime, attach_seq: int | None = None,
                     client: httpx.Client | None = None) -> dict:
    """관리자가 주소와 표기를 입력한 이미지를 받아 저장한다. 체크리스트를 다시 돌려 통과해야 실린다."""
    ensure_sources(conn)
    row = conn.execute("SELECT * FROM images WHERE id = %s", (image_id,)).fetchone()
    if row is None:
        return {"error": "not found"}
    c = _row_candidate(row)
    post_slug = None
    if attach_seq:
        p = conn.execute("SELECT slug FROM posts WHERE seq = %s", (attach_seq,)).fetchone()
        post_slug = p["slug"] if p else None
    check = policy.checklist(c, post_slug)
    own_client = client is None
    client = client or http_client(s)
    try:
        if not check["ok"]:
            note = "; ".join(i["note"] for i in check["items"] if not i["ok"])
            conn.execute("UPDATE images SET status='failed', checklist=%s, note=%s WHERE id=%s", (jsonb(check), note, image_id))
            conn.commit()
            return {"image_id": image_id, "status": "failed", "note": note}
        info: dict = {}
        if not row["hotlink"]:
            try:
                info = store.save(*store.download(client, row["file_url"], s["images"]["max_bytes"]), s["images"]["render_width"])
            except (store.ImageError, httpx.HTTPError) as e:
                conn.execute("UPDATE images SET status='failed', checklist=%s, note=%s WHERE id=%s",
                             (jsonb(check), str(e)[:300], image_id))
                conn.commit()
                return {"image_id": image_id, "status": "failed", "note": str(e)}
        conn.execute(
            """UPDATE images SET stored_path=%s, original_path=%s, sha256=%s, mime=%s, width=COALESCE(%s, width),
                 height=COALESCE(%s, height), license_url=COALESCE(license_url, %s), modifiable=%s, checklist=%s,
                 status='active', reviewed_at=%s WHERE id=%s""",
            (info.get("stored_path"), info.get("original_path"), info.get("sha256"), info.get("mime"), info.get("width"),
             info.get("height"), check.get("license_url"), check["modifiable"], jsonb(check), now, image_id),
        )
        if attach_seq:
            attach(conn, attach_seq, image_id, now)
            log_decision(conn, "image", f"post:{attach_seq}", {"chosen": {"image_id": image_id, "from": "admin"}})
        conn.commit()
        return {"image_id": image_id, "status": "active"}
    finally:
        if own_client:
            client.close()


# ── 권리자 요청 ──

def handle_request(conn: psycopg.Connection, s: Settings, request_id: int, now: datetime, sender=None,
                   llm: LLMClient | None = None, client: httpx.Client | None = None) -> dict:
    """웹이 접수와 동시에 이미지를 내렸다. 여기서는 (1) 내림을 다시 확인하고 (2) 접수 회신을 보내고
    (3) 창업자에게 알리고 (4) 그 이미지를 쓰던 글의 대체 이미지 후보를 찾아 둔다(승인 대기)."""
    from ..mail.render import RenderedEmail, site_url
    from ..ops import alerts

    req = conn.execute("SELECT * FROM image_requests WHERE id = %s", (request_id,)).fetchone()
    if req is None:
        return {"error": "not found"}
    img = conn.execute("SELECT * FROM images WHERE id = %s", (req["image_id"],)).fetchone()
    conn.execute("UPDATE images SET status='taken_down', taken_down_at=COALESCE(taken_down_at, %s) WHERE id=%s",
                 (req["received_at"], img["id"]))
    conn.commit()

    out: dict = {"request_id": request_id, "image_id": img["id"]}
    if sender is not None and req["acked_at"] is None:
        days = s["images"]["request_reply_days"]
        when = kst(req["received_at"]).strftime("%Y-%m-%d %H:%M")
        body = (f"{req['name']}님, 오늘판입니다.\n\n요청하신 이미지를 {when}에 내렸습니다.\n"
                f"- 이미지: {img['title'] or img['alt']}\n- 표기: {img['credit']}\n\n"
                f"이미지의 출처와 이용 조건을 확인해 {days}일 안에 이 주소로 답을 드리겠습니다. "
                f"이용 근거가 확인되지 않으면 내린 상태를 유지하거나 다른 이미지로 바꿉니다.\n\n오늘판 드림\n{site_url()}")
        mail = RenderedEmail(subject="[오늘판] 이미지 요청을 받았습니다",
                             html="".join(f"<p>{line}</p>" for line in body.replace("\n\n", "\n").split("\n") if line),
                             text=body, unsubscribe_url="")
        out["ack_message_id"] = sender.send(req["email"], mail)
        conn.execute("UPDATE image_requests SET acked_at = %s WHERE id = %s", (now, request_id))
        conn.commit()
    alerts.alert(conn, "image_request", str(request_id),
                 f"이미지 권리자 요청 #{request_id}: {img['credit']} — 이미지는 내려졌습니다. 관리 화면에서 확인해 주세요.")

    # 대체 후보 (자동 승인하지 않는다: 협의 전에 다른 사진을 바로 싣지 않기 위해 승인 대기로)
    posts = conn.execute(
        """SELECT p.seq, p.kind::text AS kind, p.section::text AS section, p.slug, p.title, p.summary, p.body_md
           FROM post_images pi JOIN posts p ON p.seq = pi.post_seq WHERE pi.image_id = %s AND pi.status = 'active'""",
        (img["id"],),
    ).fetchall()
    s2 = type(s)({**s, "images": {**s["images"], "auto_approve": False}})
    out["replacements"] = []
    for p in posts:
        r = find_for_post(conn, s2, p, now, client=client, llm=llm, exclude={img["id"]})
        conn.commit()
        out["replacements"].append(r)
    return out


def send_reply(conn: psycopg.Connection, request_id: int, sender) -> str | None:
    """관리 화면에서 처리 결과(이용 근거 제시, 교체, 삭제 유지)를 적으면 요청자에게 보낸다."""
    from ..mail.render import RenderedEmail

    req = conn.execute("SELECT r.*, i.credit FROM image_requests r JOIN images i ON i.id = r.image_id WHERE r.id = %s",
                       (request_id,)).fetchone()
    if req is None or not req["resolution"]:
        return None
    label = {"restored": "이용 근거를 확인해 다시 게시합니다", "replaced": "다른 이미지로 바꿨습니다",
             "removed": "이미지를 내린 상태로 두었습니다"}.get(req["status"], "처리 결과를 알려 드립니다")
    text = f"{req['name']}님, 오늘판입니다.\n\n요청하신 이미지({req['credit']})에 대해 {label}.\n\n{req['resolution']}\n\n오늘판 드림"
    mail = RenderedEmail(subject="[오늘판] 이미지 요청 처리 결과",
                         html="".join(f"<p>{line}</p>" for line in text.split("\n") if line), text=text, unsubscribe_url="")
    return sender.send(req["email"], mail)
