// 모든 날짜는 KST 기준이다.
export function kstToday(d: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

export function kstDateLabel(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${y}년 ${m}월 ${d}일 ${"일월화수목금토"[wd]}요일`;
}

export function kstDateTime(t: Date | string): string {
  const d = typeof t === "string" ? new Date(t) : t;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(d);
}

export function isIsoDate(s: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(s);
}
