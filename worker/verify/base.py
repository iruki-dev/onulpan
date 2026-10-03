"""검증 규칙 공통 타입."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..nlp import normalize_quotes, normalize_ws
from ..settings import Settings


@dataclass
class Context:
    kind: str
    draft: dict | None                 # 파싱된 생성 JSON (실패 시 None)
    raw_text: str                      # 모델 원 출력
    docs: dict[str, dict]              # 입력 문서 id → {text, outlet_ids, raw_ids, outlet, published, kind}
    s: Settings
    names: set[str] = field(default_factory=set)   # 허용 고유명사: slug 표시 이름·별칭·매체명
    embed: Callable[[list[str]], Any] | None = None
    embedder_name: str = "hashing"
    semantic_judge: Callable[[list[str], list[str]], list[dict]] | None = None  # V11
    parse_error: str | None = None

    @property
    def body(self) -> str:
        if not self.draft:
            return ""
        if self.kind == "issue":
            from ..generate.schema import render_issue_body

            return render_issue_body(self.draft.get("sections") or {})
        return self.draft.get("body_md") or ""

    @property
    def all_text(self) -> str:
        if not self.draft:
            return ""
        return "\n".join([self.draft.get("title", ""), self.draft.get("summary", ""), self.body])

    @property
    def source_text(self) -> str:
        return "\n".join(d["text"] for d in self.docs.values())

    @property
    def has_raw_sources(self) -> bool:
        return any(d.get("kind") == "raw" for d in self.docs.values())


@dataclass
class RuleResult:
    id: str
    ok: bool
    action: str = "regen"              # regen | discard | none
    messages: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    skipped: bool = False

    def to_json(self) -> dict:
        d = {"id": self.id, "ok": self.ok, "action": self.action, "messages": self.messages[:10]}
        if self.details:
            d["details"] = self.details
        if self.skipped:
            d["skipped"] = True
        return d


def ok(rule_id: str, **details) -> RuleResult:
    return RuleResult(rule_id, True, "none", details=details)


def skip(rule_id: str, reason: str) -> RuleResult:
    return RuleResult(rule_id, True, "none", details={"reason": reason}, skipped=True)


def fail(rule_id: str, messages: list[str], action: str = "regen", **details) -> RuleResult:
    return RuleResult(rule_id, False, action, messages, details)


QUOTE_SPAN_RE = re.compile(r"[\"“]([^\"“”]{2,200})[\"”]|[‘']([^'‘’]{2,200})[’']")


def quote_spans(text: str) -> list[str]:
    return [a or b for a, b in QUOTE_SPAN_RE.findall(text or "")]


def without_quotes(text: str, quotes: list[str]) -> str:
    t = QUOTE_SPAN_RE.sub(" ", text or "")
    for q in quotes:
        if q:
            t = t.replace(q, " ")
    return t


def squash(text: str) -> str:
    return re.sub(r"\s+", "", normalize_quotes(text or ""))


def norm(text: str) -> str:
    return normalize_ws(normalize_quotes(text or ""))
