[글 종류: 사실]
무슨 일이 언제 누구에게 일어났는지 쓴다. 첫 문장에 핵심을 담는다.
배경은 <related_posts>에 있는 것만 한 문장으로 붙인다. 없으면 쓰지 않는다.
본문은 400~700자. 문단은 빈 줄로 구분하고 제목·목록·굵게를 쓰지 않는다.
서로 다른 주체가 상충하는 주장을 펼치면 disputed를 true로 한다.

출력 JSON 형식:
{
  "kind": "fact",
  "section": "politics | economy | society | world | scitech | culture 중 하나",
  "title": "36자 이내, 따옴표·물음표·느낌표 없음",
  "summary": "80자 이내 한 문장",
  "body_md": "본문",
  "slug_suggestion": "기존 slug가 맞으면 그 slug, 없으면 새 이름 (명사구, 하이픈 연결)",
  "facts": [{"text": "본문에 쓴 사실 한 문장", "source_ids": ["r_1832", "r_1840"]}],
  "quotes": [{"speaker": "발언자", "text": "40자 이내", "source_id": "r_1832"}],
  "terms": ["본문에 나온 설명이 필요한 용어"],
  "disputed": false,
  "conflicts": [{"field": "사망자 수", "values": [{"value": "12명", "source_id": "r_1832"}, {"value": "11명", "source_id": "r_1840"}]}]
}
