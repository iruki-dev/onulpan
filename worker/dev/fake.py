"""개발·테스트용 가짜 부품: 고정 초안을 돌려주는 LLM, 사건 키워드로 묶이는 임베더, 가상 하루치 픽스처.

운영 코드 경로는 그대로 두고 바깥 부품만 바꿔 끼운다. API 키 없이 파이프라인 전체를 돌려 볼 수 있다.
"""
from __future__ import annotations

import copy
import itertools
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import yaml

from ..generate.gateway import LLMResult, Usage
from ..nlp import sentences
from ..process.embed import DIM, HashingEmbedder
from ..settings import ROOT
from ..timeutil import kst

FIXTURE = ROOT / "tests" / "fixtures" / "demo_day.yaml"


def load_fixture(path: Path = FIXTURE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def fill_dates(obj, base_day: datetime):
    """{M}, {D} 자리표시자를 기준 날짜로 채운다 (재귀)."""
    m, d = str(base_day.month), str(base_day.day)
    if isinstance(obj, str):
        return obj.replace("{M}", m).replace("{D}", d)
    if isinstance(obj, list):
        return [fill_dates(x, base_day) for x in obj]
    if isinstance(obj, dict):
        return {k: fill_dates(v, base_day) for k, v in obj.items()}
    return obj


class KeywordEmbedder:
    """사건 키워드 축 + 약한 해시 성분. 같은 사건 기사끼리 코사인 0.9 이상이 나오게 한다."""

    name = "keyword"

    def __init__(self, keys: list[str], noise: float = 0.35):
        self.keys = keys
        self.noise = noise
        self.hashing = HashingEmbedder()

    def embed(self, texts: list[str]) -> np.ndarray:
        out = []
        base = self.hashing.embed(texts)
        for t, h in zip(texts, base):
            v = h * self.noise
            for i, k in enumerate(self.keys):
                if k in t:
                    v[(i * 37 + 11) % DIM] += 1.0
            n = float(np.linalg.norm(v))
            out.append(v / n if n else v)
        return np.stack(out) if out else np.zeros((0, DIM), dtype=np.float32)


_ARTICLE_RE = re.compile(r'<article id="(r_\d+)" outlet="([^"]*)"')
_POST_RE = re.compile(r'<post id="(p_\d+)" kind="([^"]*)"[^>]*>\n(.*?)\n</post>', re.S)


def _subst(obj, mapping: dict[str, str]):
    if isinstance(obj, str):
        for k, v in mapping.items():
            obj = obj.replace("{" + k + "}", v)
        return obj
    if isinstance(obj, list):
        return [_subst(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: _subst(v, mapping) for k, v in obj.items()}
    return obj


class FakeLLM:
    """프롬프트에서 사건 키워드를 찾아 픽스처의 초안을 돌려준다. 키워드가 없으면 입력 글로 추출식 초안을 만든다.

    mutate(kind, draft, attempt) 훅으로 테스트가 틀린 초안을 주입할 수 있다.
    """

    def __init__(self, events: list[dict], mutate: Callable[[str, dict, int], dict] | None = None):
        self.events = events
        self.mutate = mutate
        self.calls: list[dict] = []
        self._batches: dict[str, list[tuple[str, dict]]] = {}
        self._ids = itertools.count(1)

    # ── 초안 만들기 ──
    def _kind(self, user: str) -> str:
        m = re.search(r"\[글 종류: (사실|종합|쟁점 정리|해설|교양)\]", user)
        return {"사실": "fact", "종합": "synthesis", "쟁점 정리": "issue", "해설": "explainer", "교양": "culture"}[m.group(1)]

    def _draft(self, params: dict) -> dict:
        user = params["messages"][0]["content"]
        kind = self._kind(user)
        attempt = 2 if len(params["messages"]) > 1 else 1
        draft = None
        if kind in ("fact", "issue"):
            mapping = {outlet: rid for rid, outlet in _ARTICLE_RE.findall(user)}
            for ev in self.events:
                if ev["key"] in user and kind in ev.get("drafts", {}):
                    draft = _subst(copy.deepcopy(ev["drafts"][kind]), mapping)
                    break
        if draft is None:
            draft = self._extractive(kind, user)
        if self.mutate:
            draft = self.mutate(kind, draft, attempt)
        return draft

    def _extractive(self, kind: str, user: str) -> dict:
        """종합·해설: 입력 글의 문장을 모아 분량을 맞춘다 (우리 글이 입력이라 복제율 규칙 대상이 아니다)."""
        if kind == "culture":
            title = re.search(r"주제 ‘(.+?)’", user).group(1)
            body = CULTURE_BODY.replace("{title}", title)
            facts = [{"text": s, "source_ids": []} for s in sentences(body.replace("\n\n", " "))]
            return {"kind": "culture", "section": "culture", "title": title[:36], "summary": f"{title}에 대한 교양 읽을거리다."[:80],
                    "body_md": body, "slug_suggestion": "교양-" + re.sub(r"[^가-힣A-Za-z0-9]+", "-", title).strip("-")[:40],
                    "facts": facts, "quotes": [], "terms": [], "disputed": False, "conflicts": []}
        posts = _POST_RE.findall(user)
        lo = {"synthesis": 820, "explainer": 720}[kind]
        hi = {"synthesis": 1150, "explainer": 950}[kind]
        paras: list[str] = []
        facts: list[dict] = []
        total = 0
        title = ""
        section = "economy"
        for pid, _k, text in posts:
            body = text.split("본문: ", 1)[-1]
            if not title:
                title = text.split("\n", 1)[0].replace("제목: ", "")
            for s in sentences(body.replace("\n\n", " ")):
                if total + len(s) > hi:
                    break
                if any(f["text"] == s for f in facts):
                    continue
                facts.append({"text": s, "source_ids": [pid]})
                paras.append(s)
                total += len(s) + 1
            if total >= lo:
                break
        body_md = "\n\n".join(" ".join(paras[i:i + 3]) for i in range(0, len(paras), 3))
        term = re.search(r"용어 ‘(.+?)’", user)
        return {"kind": kind, "section": section, "title": (("해설: " + term.group(1)) if term else ("종합: " + title))[:36],
                "summary": (paras[0] if paras else title)[:80], "body_md": body_md,
                "slug_suggestion": term.group(1) if term else "종합", "facts": facts, "quotes": [], "terms": [],
                "disputed": False, "conflicts": []}

    # ── LLMClient ──
    def create(self, params: dict) -> LLMResult:
        self.calls.append(params)
        model = params["model"]
        if "semantic" in str(params.get("system")) or "사실 확인 담당자" in str(params.get("system")):
            return LLMResult(text='{"unsupported": []}', model=model, usage=Usage(800, 20))
        if "사진부" in str(params.get("system")):
            content = params["messages"][0]["content"]
            if isinstance(content, list):          # 사진 대조
                return LLMResult(text='{"match": true, "reason": "기사 대상과 같은 장면"}', model=model, usage=Usage(1200, 20))
            title = re.search(r"제목: (.+)", content).group(1)
            field = "space" if re.search(r"우주|위성|NASA|발사", content) else "society"
            brief = {"field": field, "subject": "concept", "query_en": "news", "query_ko": title[:12],
                     "alt": f"{title[:20]} 관련 사진"}
            return LLMResult(text=json.dumps(brief, ensure_ascii=False), model=model, usage=Usage(400, 60))
        if "같은 사건" in str(params.get("system")):
            return LLMResult(text='{"same_event": false}', model=model, usage=Usage(300, 10))
        draft = self._draft(params)
        text = json.dumps(draft, ensure_ascii=False)
        return LLMResult(text=text, model=model, usage=Usage(7000, 1200), stop_reason="end_turn")

    def batch_create(self, requests: list[tuple[str, dict]]) -> str:
        bid = f"fakebatch_{next(self._ids)}"
        self._batches[bid] = requests
        return bid

    def batch_status(self, batch_id: str) -> str:
        return "ended"

    def batch_results(self, batch_id: str) -> Iterable[tuple[str, LLMResult]]:
        for cid, params in self._batches.get(batch_id, []):
            yield cid, self.create(params)

    def batch_cancel(self, batch_id: str) -> None:
        self._batches.pop(batch_id, None)


CULTURE_BODY = (
    "이 글은 {title}을 주제로 한 오늘판 교양 지면의 견본 글이다. 실제 운영에서는 편집 캘린더의 주제에 맞춰 Claude가 본문을 쓴다. "
    "이 견본은 API 키 없이 지면 구성을 확인하려고 넣은 자리 채움 글이다.\n\n"
    "교양 지면은 뉴스와 무관하게 읽을 만한 역사, 과학, 고전 이야기를 싣는다. 저작권이 끝난 작품만 인용한다. "
    "현대 작품은 인용하지 않는다. 평가하는 형용사와 의견 문장을 쓰지 않는다는 원칙은 다른 지면과 같다.\n\n"
    "교양 글은 매주 일요일 밤에 다음 일주일 치 일곱 편을 한 번에 만든다. 한 편의 분량은 1000자에서 1200자 사이다. "
    "만들어진 글은 날짜별로 조간 맨 끝에 한 편씩 실린다. 기본 분량과 길게 읽기 설정에서만 보인다. "
    "짧게 읽기 설정에서는 교양 지면을 싣지 않는다.\n\n"
    "교양 글도 다른 글처럼 한 번 발행하면 고치지 않는다. 틀린 내용이 확인되면 정정 글을 새로 쓴다. "
    "원래 글 위에는 정정이 있다는 표시가 붙는다. 독자는 정정 글로 바로 이동할 수 있다. "
    "이 원칙은 오늘판의 모든 글에 똑같이 적용된다.\n\n"
    "편집 캘린더는 저장소의 규칙 파일로 관리한다. 주제를 바꾸려면 파일에 한 줄을 고치고 커밋한다. "
    "변경 이력은 그대로 남는다. 날짜가 정해진 주제가 먼저 들어가고, 나머지 날은 순환 목록에서 차례로 고른다. "
    "같은 날짜에는 언제 돌려도 같은 주제가 나온다. 순환 목록에는 과학과 고전 주제가 번갈아 들어 있다. "
    "새 주제를 넣을 때는 저작권이 끝났는지 먼저 확인한다.\n\n"
    "교양 글은 검증 규칙도 다른 글과 같이 거친다. 상대 날짜를 쓰지 않고, 금지 표현 목록에 걸리는 말을 쓰지 않는다. "
    "다만 교양 글은 언론 보도를 입력으로 쓰지 않으므로 출처 수 규칙은 적용하지 않는다. "
    "대신 널리 확인된 사실만 쓰고, 불확실한 연도나 인물은 쓰지 않는다는 지시를 따른다. "
    "사람 검토 기간에는 교양 글도 창업자가 아침마다 훑어본 뒤에 게시된다. "
    "독자가 오류를 제보하면 48시간 안에 확인하고 결과를 알린다."
)


def build_events(base: datetime) -> list[dict]:
    return fill_dates(load_fixture()["events"], kst(base))


def article_times(now: datetime, hours_ago: float) -> datetime:
    return now - timedelta(hours=hours_ago)
