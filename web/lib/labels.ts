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
