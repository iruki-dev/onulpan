[글 종류: 교양]
편집 캘린더의 주제 ‘{title}’(분야: {area})에 대해 뉴스와 무관하게 읽을 만한 글을 쓴다.
저작권이 만료된 작품, 역사, 과학만 다룬다. 현대 작품을 인용하지 않는다.
확실히 알려진 사실만 쓰고, 연도와 인물은 널리 확인된 것만 쓴다. 불확실하면 쓰지 않는다.
평가 형용사와 의견 문장을 쓰지 않는다.
본문은 1,000~1,200자. 문단은 빈 줄로 구분하고 제목·목록·굵게를 쓰지 않는다.
이 글에는 입력 기사가 없으므로 facts의 source_ids는 빈 배열로 둔다.

출력 JSON 형식:
{
  "kind": "culture", "section": "culture", "title": "...", "summary": "...", "body_md": "...",
  "slug_suggestion": "교양-주제-이름",
  "facts": [{"text": "...", "source_ids": []}],
  "quotes": [], "terms": [], "disputed": false, "conflicts": []
}
