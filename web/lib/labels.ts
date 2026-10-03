export const SECTION_KO: Record<string, string> = {
  politics: "정치", economy: "경제", society: "사회", world: "국제", scitech: "과학기술", culture: "문화", none: "기타",
};
export const SECTIONS = ["politics", "economy", "society", "world", "scitech"] as const;
export const KIND_KO: Record<string, string> = {
  fact: "사실", synthesis: "종합", issue: "쟁점 정리", explainer: "해설", culture: "교양", correction: "정정",
};
export const GROUP_KO: Record<string, string> = {
  national_daily: "전국 종합일간지", broadcast: "방송", wire: "뉴스통신사", economic: "경제지",
  regional: "지역지", online: "인터넷 언론", public: "정부",
};
export const PRESET_KO: Record<string, string> = { short: "짧게 (10분)", standard: "기본 (25분)", long: "길게 (40분)" };
export const NOTICE_KO: Record<string, string> = {
  collection_delayed: "밤사이 새 소식 수집이 지연되었습니다. 최근 72시간의 글로 지면을 채웠습니다.",
  front_fallback: "오늘은 1면 후보가 부족해 전날 1면 주제의 종합 글로 채웠습니다.",
};
export const REJECT_REASONS: Record<string, string> = {
  fact_error: "사실 오류", interpretation_error: "해석 오류", expression: "표현", duplicate: "중복",
};

/** 이미지 라이선스 표기. rules/image_sources.yaml의 licenses와 같은 값이어야 한다 (tests/test_images.py가 대조). */
export const LICENSES: Record<string, { label: string; url?: string; link?: boolean }> = {
  "KOGL-0": { label: "공공누리 제0유형", url: "https://www.kogl.or.kr/info/license.do" },
  "KOGL-1": { label: "공공누리 제1유형", url: "https://www.kogl.or.kr/info/licenseType1.do" },
  CC0: { label: "CC0", url: "https://creativecommons.org/publicdomain/zero/1.0/deed.ko" },
  PD: { label: "퍼블릭 도메인" },
  "PD-USGov": { label: "미국 연방정부 저작물" },
  "CC-BY-2.0": { label: "CC BY 2.0", url: "https://creativecommons.org/licenses/by/2.0/deed.ko" },
  "CC-BY-3.0": { label: "CC BY 3.0", url: "https://creativecommons.org/licenses/by/3.0/deed.ko" },
  "CC-BY-4.0": { label: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/deed.ko" },
  "CC-BY-SA-2.0": { label: "CC BY-SA 2.0", url: "https://creativecommons.org/licenses/by-sa/2.0/deed.ko", link: true },
  "CC-BY-SA-3.0": { label: "CC BY-SA 3.0", url: "https://creativecommons.org/licenses/by-sa/3.0/deed.ko", link: true },
  "CC-BY-SA-3.0-IGO": { label: "CC BY-SA 3.0 IGO", url: "https://creativecommons.org/licenses/by-sa/3.0/igo/", link: true },
  "CC-BY-SA-4.0": { label: "CC BY-SA 4.0", url: "https://creativecommons.org/licenses/by-sa/4.0/deed.ko", link: true },
  Unsplash: { label: "Unsplash 라이선스", url: "https://unsplash.com/license" },
  Pexels: { label: "Pexels 라이선스", url: "https://www.pexels.com/license/" },
  Pixabay: { label: "Pixabay 라이선스", url: "https://pixabay.com/service/license-summary/" },
  press: { label: "보도용 제공" },
  own: { label: "자체 제작" },
};
export const TIER_KO: Record<string, string> = { free: "자유 이용 출처", press: "보도용 제공 출처", own: "자체 제작 그래픽" };
export const RELATION_KO: Record<string, string> = { owner: "저작권자", agent: "대리인", portrait: "사진 속 인물", other: "기타" };
