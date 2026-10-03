"""8단계 후속 트리거. 만들어진 작업은 5단계로 되돌아간다.

- 종합: 같은 slug에 마지막 종합 이후 사실 글 3편 이상, 또는 7일 경과 + 1편 이상. slug당 하루 1편 상한.
- 해설: 14일 안에 서로 다른 글 3편 이상에 등장했고 해설 slug가 없는 용어. 하루 상한 베타 3편, 출시 10편.
- 쟁점 정리: 생성 출력의 disputed: true + 매체군 3개 이상. 하루 1편, 중요도 최고 묶음에만.
- 교양: 트리거가 아니라 편집 캘린더. 매주 일요일에 7편을 한 번에 배치 생성한다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import psycopg
import yaml

from ..db import jsonb, log_decision
from ..settings import RULES_DIR, Settings
from ..timeutil import kst_day_bounds, kst_today
from .links import normalize_slug


def _today_count(conn: psycopg.Connection, kind: str, now: datetime, extra: str = "", args: tuple = ()) -> int:
    start, end = kst_day_bounds(kst_today(now))
    return conn.execute(
        f"""SELECT count(*) AS n FROM generation_requests
            WHERE kind = %s AND attempt = 1 AND status <> 'expired' AND created_at >= %s AND created_at < %s {extra}""",
        (kind, start, end, *args),
    ).fetchone()["n"]


def maybe_synthesis(conn: psycopg.Connection, slug: str, now: datetime, s: Settings) -> int | None:
    t = s["triggers"]
    if _today_count(conn, "synthesis", now, "AND slug = %s", (slug,)) > 0:
        return None
    if conn.execute(
        "SELECT 1 FROM generation_requests WHERE kind='synthesis' AND slug=%s AND status IN ('pending','submitted','received','retry')",
        (slug,),
    ).fetchone():
        return None
    last = conn.execute(
        "SELECT seq, created_at FROM posts WHERE slug = %s AND kind = 'synthesis' ORDER BY seq DESC LIMIT 1", (slug,)
    ).fetchone()
    since_seq = last["seq"] if last else 0
    row = conn.execute(
        """SELECT count(*) AS n, min(created_at) AS first, max(importance) AS imp FROM posts
           WHERE slug = %s AND kind = 'fact' AND seq > %s""",
        (slug, since_seq),
    ).fetchone()
    n = row["n"]
    if n == 0:
        return None
    ref_time = last["created_at"] if last else row["first"]
    stale = (now - ref_time) >= timedelta(days=t["synthesis_stale_days"])
    if n >= t["synthesis_min_facts"] or (stale and n >= 1):
        rid = conn.execute(
            "INSERT INTO generation_requests (kind, slug, priority, mode, created_at) VALUES ('synthesis', %s, %s, 'batch', %s) RETURNING id",
            (slug, float(row["imp"] or 0), now),
        ).fetchone()["id"]
        log_decision(conn, "synthesis_trigger", f"slug:{slug}", {"request_id": rid, "facts_since": n, "stale": stale})
        return rid
    return None


def scan_explainers(conn: psycopg.Connection, now: datetime, s: Settings) -> list[int]:
    t = s["triggers"]
    remaining = t["explainer_daily_cap"] - _today_count(conn, "explainer", now)
    if remaining <= 0:
        return []
    rows = conn.execute(
        """SELECT tm.term, count(DISTINCT tm.post_seq) AS n
           FROM term_mentions tm JOIN posts p ON p.seq = tm.post_seq
           WHERE p.created_at >= %s
           GROUP BY tm.term HAVING count(DISTINCT tm.post_seq) >= %s
           ORDER BY count(DISTINCT tm.post_seq) DESC, tm.term""",
        (now - timedelta(days=t["explainer_window_days"]), t["explainer_min_posts"]),
    ).fetchall()
    created = []
    for r in rows:
        if len(created) >= remaining:
            break
        term = r["term"]
        slug = normalize_slug(term)
        has = conn.execute(
            """SELECT 1 FROM posts p WHERE p.kind = 'explainer' AND (p.slug = %s OR p.slug IN
                 (SELECT slug FROM slug_aliases WHERE alias = %s))""",
            (slug, term),
        ).fetchone()
        if has or conn.execute(
            "SELECT 1 FROM generation_requests WHERE kind='explainer' AND term=%s AND status NOT IN ('expired','failed','discarded')",
            (term,),
        ).fetchone():
            continue
        rid = conn.execute(
            "INSERT INTO generation_requests (kind, term, priority, mode, created_at) VALUES ('explainer', %s, %s, 'immediate', %s) RETURNING id",
            (term, float(r["n"]), now),
        ).fetchone()["id"]
        log_decision(conn, "explainer_trigger", f"term:{term}", {"request_id": rid, "mentions": r["n"]})
        created.append(rid)
    return created


def select_issue(conn: psycopg.Connection, now: datetime, s: Settings) -> int | None:
    t = s["triggers"]
    if _today_count(conn, "issue", now) >= t["issue_daily_cap"]:
        return None
    row = conn.execute(
        """SELECT p.cluster_id, max(p.importance) AS imp FROM posts p JOIN clusters c ON c.id = p.cluster_id
           WHERE p.kind = 'fact' AND (p.meta->>'disputed')::boolean
             AND p.created_at >= %s AND c.n_groups >= %s
             AND NOT EXISTS (SELECT 1 FROM generation_requests g WHERE g.kind = 'issue' AND g.cluster_id = p.cluster_id)
           GROUP BY p.cluster_id ORDER BY max(p.importance) DESC, p.cluster_id LIMIT 1""",
        (now - timedelta(hours=24), t["issue_min_groups"]),
    ).fetchone()
    if not row:
        return None
    rid = conn.execute(
        "INSERT INTO generation_requests (kind, cluster_id, priority, mode, created_at) VALUES ('issue', %s, %s, 'immediate', %s) RETURNING id",
        (row["cluster_id"], float(row["imp"]), now),
    ).fetchone()["id"]
    log_decision(conn, "issue_trigger", f"cluster:{row['cluster_id']}", {"request_id": rid, "importance": float(row["imp"])})
    return rid


def culture_topics(start: date, n: int) -> list[dict]:
    cal = yaml.safe_load((RULES_DIR / "culture_calendar.yaml").read_text(encoding="utf-8"))
    dated = {str(d["date"]): d for d in cal.get("dated", [])}
    rotation = cal.get("rotation", [])
    out = []
    for i in range(n):
        d = start + timedelta(days=i)
        if str(d) in dated:
            item = dict(dated[str(d)])
        else:
            # 회전 목록은 날짜로 결정한다 (같은 날짜면 언제 돌려도 같은 주제)
            item = dict(rotation[d.toordinal() % len(rotation)])
        item["date"] = str(d)
        out.append(item)
    return out


def schedule_culture_week(conn: psycopg.Connection, now: datetime, s: Settings) -> list[int]:
    start = kst_today(now) + timedelta(days=1)  # 일요일 밤 → 월요일부터 7일
    created = []
    for topic in culture_topics(start, s["triggers"]["culture_weekly"]):
        exists = conn.execute(
            "SELECT 1 FROM generation_requests WHERE kind='culture' AND topic->>'date' = %s AND status NOT IN ('expired','failed','discarded')",
            (topic["date"],),
        ).fetchone()
        if exists:
            continue
        created.append(conn.execute(
            "INSERT INTO generation_requests (kind, topic, mode, created_at) VALUES ('culture', %s, 'batch', %s) RETURNING id",
            (jsonb(topic), now),
        ).fetchone()["id"])
    return created


def after_publish(conn: psycopg.Connection, seq: int, now: datetime, s: Settings) -> list[int]:
    post = conn.execute("SELECT kind::text AS kind, slug FROM posts WHERE seq = %s", (seq,)).fetchone()
    out = []
    if post["kind"] in ("fact", "correction") and post["slug"]:
        rid = maybe_synthesis(conn, post["slug"], now, s)
        if rid:
            out.append(rid)
    return out
