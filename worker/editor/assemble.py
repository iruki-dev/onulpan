"""조간 편집: assemble_edition(user, as_of_seq). 웹 조간과 이메일 조간은 이 함수 하나로 만든다.

1면은 모든 사용자에게 같고, 나머지 지면만 사람마다 다르다. 개인화는 섹션 가중치와 관심 주제로만 하고,
분량 예산 안에서 탐욕 알고리즘으로 채운다. LLM은 쓰지 않는다.

결정성: 같은 사용자·같은 as_of_seq·같은 editor_version이면 항상 같은 지면. 동점은 seq로 가르고, 무작위를 쓰지 않는다.
편집 규칙을 바꾸면 config의 editor.version을 올린다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import psycopg

from ..db import jsonb
from ..settings import Settings
from ..timeutil import kst_today
from .front_page import get_or_select_front

MAIN_SECTIONS = ("politics", "economy", "society", "world", "scitech")


@dataclass(frozen=True)
class Preset:
    name: str
    minutes: int
    budget_chars: int
    front: int
    sections_max: int
    issue: bool
    briefs: int
    background: int
    culture: bool


PRESETS = {
    "short": Preset("short", 10, 5_500, 2, 5, False, 5, 0, False),
    "standard": Preset("standard", 25, 13_400, 3, 14, True, 8, 1, True),
    "long": Preset("long", 40, 22_000, 3, 24, True, 10, 2, True),
}

POST_COLS = "seq, kind::text AS kind, section::text AS section, slug, title, summary, char_count, importance, created_at, meta"


@dataclass
class Edition:
    user_id: str
    edition_date: date
    as_of_seq: int
    preset: str
    editor_version: str
    notices: list[str] = field(default_factory=list)
    catchup: list[dict] = field(default_factory=list)
    front: list[dict] = field(default_factory=list)
    issue: list[dict] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    briefs: list[dict] = field(default_factory=list)
    background: list[dict] = field(default_factory=list)
    culture: list[dict] = field(default_factory=list)
    niche_seqs: set[int] = field(default_factory=set)

    def all_posts(self) -> list[dict]:
        return self.catchup + self.front + self.issue + self.sections

    def slots(self) -> list[dict]:
        out: list[dict] = [{"slot": "notice", "code": c} for c in self.notices]
        out += [{"slot": "catchup", "seq": p["seq"]} for p in self.catchup]
        out += [{"slot": "front", "seq": p["seq"]} for p in self.front]
        out += [{"slot": "issue", "seq": p["seq"]} for p in self.issue]
        for p in self.sections:
            item = {"slot": "section", "seq": p["seq"], "section": p["section"]}
            if p["seq"] in self.niche_seqs:
                item["niche"] = True
            out.append(item)
        out += [{"slot": "brief", "seq": p["seq"]} for p in self.briefs]
        out += [{"slot": "background", "seq": p["seq"]} for p in self.background]
        out += [{"slot": "culture", "seq": p["seq"]} for p in self.culture]
        return out


# ── 입력 ──────────────────────────────────────────────

def load_user(conn: psycopg.Connection, user_id: str) -> dict:
    row = conn.execute(
        """SELECT u.id, u.plan, COALESCE(p.preset, 'standard') AS preset,
                  COALESCE(p.section_weights, '{}'::jsonb) AS section_weights,
                  COALESCE(p.niche_topics, '{}') AS niche_topics
           FROM users u LEFT JOIN user_prefs p ON p.user_id = u.id WHERE u.id = %s""",
        (user_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"user {user_id} not found")
    return row


def effective_cursor(conn: psycopg.Connection, user_id: str, before: date) -> tuple[int, datetime | None]:
    """마지막으로 연 조간(웹) 또는 받은 조간(이메일)의 as_of_seq."""
    c = conn.execute("SELECT last_seq, updated_at FROM reading_cursors WHERE user_id = %s", (user_id,)).fetchone()
    e = conn.execute(
        """SELECT e.as_of_seq, s.sent_at FROM email_sends s JOIN editions e ON e.id = s.edition_id
           WHERE s.user_id = %s AND s.status = 'sent' AND s.edition_date < %s
           ORDER BY s.edition_date DESC LIMIT 1""",
        (user_id, before),
    ).fetchone()
    best = (0, None)
    if c:
        best = (c["last_seq"], c["updated_at"])
    if e and e["as_of_seq"] > best[0]:
        best = (e["as_of_seq"], e["sent_at"])
    return best


def weight(user: dict, section: str, s: Settings) -> float:
    w = (user["section_weights"] or {}).get(section, 1.0)
    if isinstance(w, str):
        w = s["editor"]["weights"].get(w, 1.0)
    return float(w)


def recent_slugs(conn: psycopg.Connection, user_id: str, d: date, days: int) -> set[str]:
    rows = conn.execute(
        """SELECT DISTINCT p.slug FROM (
             SELECT DISTINCT ON (edition_date) slots FROM editions
             WHERE user_id = %s AND edition_date < %s AND edition_date >= %s
             ORDER BY edition_date, id DESC) e
           CROSS JOIN LATERAL jsonb_array_elements(e.slots) x
           JOIN posts p ON p.seq = (x->>'seq')::bigint
           WHERE x ? 'seq' AND x->>'slot' IN ('front','section','issue','catchup')""",
        (user_id, d, d - timedelta(days=days)),
    ).fetchall()
    return {r["slug"] for r in rows if r["slug"]}


def _fetch(conn: psycopg.Connection, seqs: list[int]) -> list[dict]:
    if not seqs:
        return []
    rows = {r["seq"]: r for r in conn.execute(f"SELECT {POST_COLS} FROM posts WHERE seq = ANY(%s)", (seqs,)).fetchall()}
    return [rows[s] for s in seqs if s in rows]


# ── 조립 ──────────────────────────────────────────────

def assemble_edition(conn: psycopg.Connection, user_id: str, as_of_seq: int, now: datetime, s: Settings,
                     edition_date: date | None = None) -> Edition:
    e = s["editor"]
    d = edition_date or kst_today(now)
    user = load_user(conn, user_id)
    budget = PRESETS[user["preset"]]
    ed = Edition(user_id=str(user_id), edition_date=d, as_of_seq=as_of_seq, preset=budget.name,
                 editor_version=e["version"])

    last_seq, cursor_at = effective_cursor(conn, user_id, d)
    window = timedelta(hours=e["window_hours"])
    pool = conn.execute(
        f"""SELECT {POST_COLS} FROM posts
            WHERE seq > %s AND seq <= %s AND created_at >= %s
            ORDER BY seq""",
        (last_seq, as_of_seq, now - window),
    ).fetchall()

    # 폴백 1: 새 글이 없어도 조간은 나간다 (수집 정지 → 창을 72시간으로)
    recent_any = conn.execute(
        "SELECT 1 FROM posts WHERE seq <= %s AND created_at >= %s LIMIT 1", (as_of_seq, now - window)
    ).fetchone()
    if not recent_any:
        ed.notices.append("collection_delayed")
        pool = conn.execute(
            f"SELECT {POST_COLS} FROM posts WHERE seq <= %s AND created_at >= %s ORDER BY seq",
            (as_of_seq, now - timedelta(hours=e["fallback_window_hours"])),
        ).fetchall()

    used_slugs: set[str] = set()
    used_seqs: set[int] = set()

    # 0. 며칠 안 읽은 경우: 그동안 갱신된 종합 글 최대 3편을 ‘그동안의 주요 흐름’으로 맨 앞에
    if cursor_at is not None and now - cursor_at > window:
        rows = conn.execute(
            f"""SELECT {POST_COLS} FROM posts WHERE kind = 'synthesis' AND seq > %s AND seq <= %s
                ORDER BY importance DESC, seq LIMIT %s""",
            (last_seq, as_of_seq, e["catchup_max"]),
        ).fetchall()
        ed.catchup = rows
        for p in rows:
            used_slugs.add(p["slug"])
            used_seqs.add(p["seq"])

    # 1. 1면: 전 사용자 공통
    front = get_or_select_front(conn, d, now, s)
    if front["fallback"]:
        ed.notices.append("front_fallback")
    ed.front = [p for p in _fetch(conn, [x for x in front["seqs"] if x <= as_of_seq]) if p["seq"] not in used_seqs][: budget.front]
    for p in ed.front:
        used_slugs.add(p["slug"])
        used_seqs.add(p["seq"])

    # 2. 쟁점 정리 1편: 오늘 생성된 issue 중 importance 최대 (전 사용자 공통)
    if budget.issue and front["issue_seq"] and front["issue_seq"] <= as_of_seq:
        ed.issue = _fetch(conn, [front["issue_seq"]])
        for p in ed.issue:
            used_seqs.add(p["seq"])
            used_slugs.add(p["slug"])

    fixed_chars = sum(p["char_count"] for p in ed.catchup + ed.front + ed.issue)
    fixed_chars += budget.briefs * e["brief_chars"]
    background_est = 900 * budget.background
    culture_est = 1100 if budget.culture else 0
    sections_chars = max(0, budget.budget_chars - fixed_chars - background_est - culture_est)

    # 3. 관심 주제 (유료): niche_topics slug의 새 글 최대 2편을 섹션보다 먼저
    niche: list[dict] = []
    if user["plan"] in ("founding", "premium") and user["niche_topics"]:
        topics = set(user["niche_topics"])
        niche = [p for p in sorted(pool, key=lambda p: (-p["importance"], p["seq"]))
                 if p["slug"] in topics and p["slug"] not in used_slugs and p["kind"] in ("fact", "synthesis")][:2]
        ed.niche_seqs = {p["seq"] for p in niche}

    # 4. 섹션: 개인 점수 내림차순 탐욕 배치
    seen = recent_slugs(conn, user_id, d, e["novelty_days"])

    def score(p: dict) -> float:
        novelty = e["novelty_factor"] if p["slug"] in seen else 1.0
        return float(p["importance"]) * weight(user, p["section"], s) * novelty

    facts = sorted((p for p in pool if p["kind"] in ("fact", "synthesis") and p["slug"] not in used_slugs
                    and p["seq"] not in used_seqs),
                   key=lambda p: (-score(p), p["seq"]))
    chars = 0
    sec_chars: dict[str, int] = {}
    for p in niche + facts:
        if len(ed.sections) >= budget.sections_max:
            break
        if p["slug"] in used_slugs or p["seq"] in used_seqs:
            continue  # slug당 1편, 나머지는 관련 링크로
        if chars + p["char_count"] > sections_chars:
            continue
        share = (sec_chars.get(p["section"], 0) + p["char_count"]) / sections_chars if sections_chars else 1.0
        if share > e["section_cap"] and p["seq"] not in ed.niche_seqs:
            continue  # 한 섹션이 40% 초과 금지
        ed.sections.append(p)
        used_slugs.add(p["slug"])
        used_seqs.add(p["seq"])
        chars += p["char_count"]
        sec_chars[p["section"]] = sec_chars.get(p["section"], 0) + p["char_count"]
    _ensure_floor(ed, facts, used_slugs, used_seqs, score)

    # 5. 단신: 지면에 오르지 못한 사실 글의 summary
    ed.briefs = [p for p in facts if p["kind"] == "fact" and p["seq"] not in used_seqs
                 and p["slug"] not in used_slugs][: budget.briefs]

    # 6. 오늘의 배경: 오늘 지면 글들이 가장 많이 링크한 explainer
    if budget.background:
        ed.background = most_linked_explainer(conn, [p["seq"] for p in ed.all_posts()], budget.background, as_of_seq)

    # 7. 교양: 편집 캘린더의 오늘 글
    if budget.culture:
        ed.culture = conn.execute(
            f"""SELECT {POST_COLS} FROM posts WHERE kind = 'culture' AND meta->>'calendar_date' = %s AND seq <= %s
                ORDER BY seq DESC LIMIT 1""",
            (str(d), as_of_seq),
        ).fetchall()
    return ed


def _ensure_floor(ed: Edition, facts: list[dict], used_slugs: set, used_seqs: set, score) -> None:
    """후보가 있으면 5개 섹션 각 1편 보장. 예산을 넘으면 가장 많은 섹션의 가장 낮은 점수 글을 뺀다."""
    for sec in MAIN_SECTIONS:
        if any(p["section"] == sec for p in ed.sections + ed.front):
            continue
        cand = next((p for p in facts if p["section"] == sec and p["seq"] not in used_seqs
                     and p["slug"] not in used_slugs), None)
        if cand is None:
            continue
        counts: dict[str, int] = {}
        for p in ed.sections:
            counts[p["section"]] = counts.get(p["section"], 0) + 1
        crowded = sorted((c for c in counts.items() if c[1] > 1), key=lambda c: (-c[1], c[0]))
        if crowded:
            victim_sec = crowded[0][0]
            victims = sorted((p for p in ed.sections if p["section"] == victim_sec and p["seq"] not in ed.niche_seqs),
                             key=lambda p: (score(p), -p["seq"]))
            if victims:
                v = victims[0]
                ed.sections.remove(v)
                used_seqs.discard(v["seq"])
                used_slugs.discard(v["slug"])
        ed.sections.append(cand)
        used_seqs.add(cand["seq"])
        used_slugs.add(cand["slug"])


def most_linked_explainer(conn: psycopg.Connection, seqs: list[int], n: int, as_of_seq: int) -> list[dict]:
    if not seqs or n <= 0:
        return []
    rows = conn.execute(
        """SELECT t.slug, count(*) AS links, max(t.seq) AS any_seq
           FROM post_links l JOIN posts t ON t.seq = l.to_seq
           WHERE l.from_seq = ANY(%s) AND t.kind = 'explainer'
           GROUP BY t.slug ORDER BY count(*) DESC, t.slug LIMIT %s""",
        (seqs, n),
    ).fetchall()
    out = []
    for r in rows:
        latest = conn.execute(
            f"SELECT {POST_COLS} FROM posts WHERE slug = %s AND kind = 'explainer' AND seq <= %s ORDER BY seq DESC LIMIT 1",
            (r["slug"], as_of_seq),
        ).fetchone()
        if latest:
            out.append(latest)
    return out


def save_edition(conn: psycopg.Connection, ed: Edition) -> int:
    return conn.execute(
        """INSERT INTO editions (user_id, edition_date, as_of_seq, preset, slots, editor_version)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (ed.user_id, ed.edition_date, ed.as_of_seq, ed.preset, jsonb(ed.slots()), ed.editor_version),
    ).fetchone()["id"]


def current_max_seq(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT COALESCE(max(seq), 0) AS m FROM posts").fetchone()["m"]


def assemble_and_save(conn: psycopg.Connection, user_id: str, now: datetime, s: Settings,
                      as_of_seq: int | None = None) -> int:
    """같은 날 이미 조간이 있으면 그 as_of_seq로 다시 조립한다(설정 변경). 없으면 지금까지의 글로."""
    d = kst_today(now)
    if as_of_seq is None:
        prev = conn.execute(
            "SELECT as_of_seq FROM editions WHERE user_id = %s AND edition_date = %s ORDER BY id DESC LIMIT 1",
            (user_id, d),
        ).fetchone()
        as_of_seq = prev["as_of_seq"] if prev else current_max_seq(conn)
    ed = assemble_edition(conn, user_id, as_of_seq, now, s, d)
    return save_edition(conn, ed)
