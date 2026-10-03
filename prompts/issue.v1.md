[글 종류: 쟁점 정리]
입장이 갈린 사안을 네 부분으로 정리한다.
1. 확인된 사실: 여러 매체가 공통으로 보도한 사실.
2. 쟁점: 무엇에 대한 다툼인지 한 문장.
3. 입장: 주장하는 주체(holder)별로 주장(claim)과 근거(grounds). 입장 수는 입력에 있는 만큼, 순서는 입력에 등장한 순서.
4. 아직 모르는 것: 입력 기사에서 확인되지 않았거나 서로 다른 내용.
어느 입장이 옳은지 판단하지 않는다. 각 입장의 분량을 비슷하게 맞춘다.
전체 분량(사실+쟁점+입장+모르는 것)은 1,000~1,400자.

출력 JSON 형식:
{
  "kind": "issue",
  "section": "politics | economy | society | world | scitech | culture 중 하나",
  "title": "36자 이내, 따옴표·물음표·느낌표 없음",
  "summary": "80자 이내 한 문장",
  "slug_suggestion": "기존 slug가 맞으면 그 slug, 없으면 새 이름",
  "sections": {
    "facts": ["확인된 사실 문장"],
    "question": "무엇에 대한 다툼인지 한 문장",
    "positions": [{"holder": "주체", "claim": "주장", "grounds": "근거", "source_ids": ["r_1832"]}],
    "unknowns": ["아직 모르는 것"]
  },
  "facts": [{"text": "위 sections에 쓴 사실·주장 문장 하나", "source_ids": ["r_1832"]}],
  "quotes": [{"speaker": "발언자", "text": "40자 이내", "source_id": "r_1832"}],
  "terms": [],
  "disputed": true,
  "conflicts": []
}
