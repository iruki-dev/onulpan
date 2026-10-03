[글 종류: 종합]
이 주제(slug: {slug})가 지금 어디까지 왔는지, 처음 보는 사람도 알 수 있게 정리한다.
입력은 이전 종합 글과 그 이후의 사실 글들이다. 입력 글에 있는 사실만 쓴다.
시간 순서를 지키고, 날짜는 입력에 적힌 그대로 쓴다.
본문은 800~1,200자. 문단은 빈 줄로 구분하고 제목·목록·굵게를 쓰지 않는다.
facts의 source_ids에는 입력 글의 id(p_로 시작)를 쓴다.

출력 JSON 형식은 사실 글과 같고 "kind"는 "synthesis", "slug_suggestion"은 "{slug}"로 한다.
{
  "kind": "synthesis", "section": "...", "title": "...", "summary": "...", "body_md": "...",
  "slug_suggestion": "{slug}",
  "facts": [{"text": "...", "source_ids": ["p_4411"]}],
  "quotes": [], "terms": [], "disputed": false, "conflicts": []
}
