[글 종류: 해설]
용어 ‘{term}’을 설명한다. 세 가지를 쓴다.
1. 뜻: 입력 글에서 확인되는 범위에서 이 말이 무엇을 가리키는지.
2. 왜 뉴스에 나오는지.
3. 최근 글에서 어떻게 쓰였는지: 입력 글 3편 이상을 짚는다.
입력은 이 용어가 나온 오늘판의 글들이다. 입력에 없는 정의나 역사는 덧붙이지 않는다.
본문은 700~1,000자. 문단은 빈 줄로 구분하고 제목·목록·굵게를 쓰지 않는다.
facts의 source_ids에는 입력 글의 id(p_로 시작)를 쓴다.

출력 JSON 형식은 사실 글과 같고 "kind"는 "explainer", "slug_suggestion"은 용어를 하이픈으로 이은 이름으로 한다.
{
  "kind": "explainer", "section": "...", "title": "...", "summary": "...", "body_md": "...",
  "slug_suggestion": "...",
  "facts": [{"text": "...", "source_ids": ["p_4411", "p_4420"]}],
  "quotes": [], "terms": [], "disputed": false, "conflicts": []
}
