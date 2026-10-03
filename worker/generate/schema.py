"""출력 JSON 스키마. structured_output을 켜면 output_config.format으로 넘기고, 끄면 V1이 같은 구조를 검사한다."""
from __future__ import annotations

SECTIONS = ["politics", "economy", "society", "world", "scitech", "culture"]

_fact_item = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "source_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["text", "source_ids"],
    "additionalProperties": False,
}
_quote = {
    "type": "object",
    "properties": {"speaker": {"type": "string"}, "text": {"type": "string"}, "source_id": {"type": "string"}},
    "required": ["speaker", "text", "source_id"],
    "additionalProperties": False,
}
_conflict = {
    "type": "object",
    "properties": {
        "field": {"type": "string"},
        "values": {"type": "array", "items": {
            "type": "object",
            "properties": {"value": {"type": "string"}, "source_id": {"type": "string"}},
            "required": ["value", "source_id"], "additionalProperties": False}},
    },
    "required": ["field", "values"],
    "additionalProperties": False,
}

_common = {
    "kind": {"type": "string"},
    "section": {"type": "string", "enum": SECTIONS},
    "title": {"type": "string"},
    "summary": {"type": "string"},
    "slug_suggestion": {"type": "string"},
    "facts": {"type": "array", "items": _fact_item},
    "quotes": {"type": "array", "items": _quote},
    "terms": {"type": "array", "items": {"type": "string"}},
    "disputed": {"type": "boolean"},
    "conflicts": {"type": "array", "items": _conflict},
}

_issue_sections = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {"type": "string"}},
        "question": {"type": "string"},
        "positions": {"type": "array", "items": {
            "type": "object",
            "properties": {"holder": {"type": "string"}, "claim": {"type": "string"}, "grounds": {"type": "string"},
                           "source_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["holder", "claim", "grounds", "source_ids"], "additionalProperties": False}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["facts", "question", "positions", "unknowns"],
    "additionalProperties": False,
}


def json_schema_for(kind: str) -> dict:
    props = dict(_common)
    if kind == "issue":
        props["sections"] = _issue_sections
    else:
        props["body_md"] = {"type": "string"}
    return {"type": "object", "properties": props, "required": sorted(props), "additionalProperties": False}


REQUIRED_FIELDS = {
    k: sorted(json_schema_for(k)["required"]) for k in ("fact", "synthesis", "issue", "explainer", "culture")
}


def render_issue_body(sections: dict) -> str:
    """쟁점 정리는 웹이 고정 틀로 렌더링한다. posts.body_md에는 같은 틀의 텍스트판을 저장한다(검색·분량·검증용)."""
    parts = ["확인된 사실", *sections.get("facts", []), "", "쟁점", sections.get("question", ""), "", "입장"]
    for p in sections.get("positions", []):
        parts.append(f"{p.get('holder','')}: {p.get('claim','')} 근거: {p.get('grounds','')}")
    parts += ["", "아직 모르는 것", *sections.get("unknowns", [])]
    return "\n\n".join(x for x in parts if x is not None).strip()
