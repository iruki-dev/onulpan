// 쟁점 카드 이미지 (1080×1350 SVG). 고정 틀이라 자동 생성할 수 있다.
export type CardData = { title: string; question: string; positions: { holder: string; claim: string }[]; date: string; url: string };

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** 글자 수 기준 줄바꿈 (한글은 고정폭에 가깝다) */
export function wrap(text: string, perLine: number, maxLines: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > perLine) {
      if (cur) lines.push(cur);
      cur = w;
    } else cur = (cur + " " + w).trim();
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    const cut = lines.slice(0, maxLines);
    cut[maxLines - 1] = cut[maxLines - 1].replace(/.{1,2}$/, "") + "…";
    return cut;
  }
  return lines;
}

export function cardSvg(d: CardData): string {
  const W = 1080, H = 1350;
  const font = `font-family="Noto Sans KR, Noto Sans CJK KR, Apple SD Gothic Neo, sans-serif"`;
  const serif = `font-family="Noto Serif KR, Noto Serif CJK KR, serif"`;
  let y = 150;
  const parts: string[] = [];
  parts.push(`<rect width="${W}" height="${H}" fill="#fbf8f2"/>`);
  parts.push(`<text x="80" y="100" ${serif} font-size="44" font-weight="900" fill="#1d1a16">오늘판</text>`);
  parts.push(`<text x="${W - 80}" y="100" ${font} font-size="26" fill="#6b6257" text-anchor="end">오늘의 쟁점 · ${esc(d.date)}</text>`);
  parts.push(`<rect x="80" y="120" width="${W - 160}" height="4" fill="#1d1a16"/>`);
  y = 210;
  for (const line of wrap(d.title, 20, 2)) {
    parts.push(`<text x="80" y="${y}" ${serif} font-size="58" font-weight="900" fill="#1d1a16">${esc(line)}</text>`);
    y += 74;
  }
  y += 20;
  for (const line of wrap(d.question, 30, 3)) {
    parts.push(`<text x="80" y="${y}" ${font} font-size="36" font-weight="700" fill="#9c2f1c">${esc(line)}</text>`);
    y += 50;
  }
  y += 30;
  const n = Math.min(3, d.positions.length);
  const boxH = Math.floor((H - y - 160) / Math.max(1, n)) - 20;
  d.positions.slice(0, n).forEach((p) => {
    const lines = wrap(p.claim, 28, Math.max(1, Math.floor((boxH - 120) / 46)));
    const h = Math.min(boxH, 110 + lines.length * 46);  // 내용에 맞춘 높이
    parts.push(`<rect x="80" y="${y}" width="${W - 160}" height="${h}" fill="#fffdf8" stroke="#d9cfbd" stroke-width="2"/>`);
    parts.push(`<text x="110" y="${y + 56}" ${font} font-size="34" font-weight="800" fill="#1d1a16">${esc(p.holder)}</text>`);
    let ly = y + 110;
    for (const line of lines) {
      parts.push(`<text x="110" y="${ly}" ${font} font-size="32" fill="#1d1a16">${esc(line)}</text>`);
      ly += 46;
    }
    y += h + 24;
  });
  parts.push(`<text x="80" y="${H - 90}" ${font} font-size="24" fill="#6b6257">어느 쪽이 옳은지 판단하지 않습니다. 근거와 출처는 전문에서.</text>`);
  parts.push(`<text x="80" y="${H - 50}" ${font} font-size="24" fill="#6b6257">${esc(d.url)} · AI가 여러 언론 보도를 종합해 씀</text>`);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${parts.join("")}</svg>`;
}
