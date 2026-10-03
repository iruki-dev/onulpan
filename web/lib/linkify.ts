// 본문 표기 → 위키 링크. 링크는 워커가 사전 매칭으로 만든 post_links(anchor_text)만 쓴다 (LLM이 링크를 만들지 않는다).
export type Segment = { text: string; href?: string; title?: string; toSeq?: number };
export type Anchor = { anchor: string; href: string; title: string; toSeq: number };

export function paragraphs(body: string): string[] {
  return body.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
}

/** 각 표기는 글 전체에서 처음 한 번만 링크한다. */
export function linkify(paras: string[], anchors: Anchor[]): Segment[][] {
  const pending = [...anchors].filter((a) => a.anchor).sort((a, b) => b.anchor.length - a.anchor.length);
  const used = new Set<string>();
  return paras.map((p) => {
    const segs: Segment[] = [];
    let rest = p;
    for (;;) {
      let best: { idx: number; a: Anchor } | null = null;
      for (const a of pending) {
        if (used.has(a.anchor)) continue;
        const idx = rest.indexOf(a.anchor);
        if (idx >= 0 && (best === null || idx < best.idx)) best = { idx, a };
      }
      if (!best) break;
      if (best.idx > 0) segs.push({ text: rest.slice(0, best.idx) });
      segs.push({ text: best.a.anchor, href: best.a.href, title: best.a.title, toSeq: best.a.toSeq });
      used.add(best.a.anchor);
      rest = rest.slice(best.idx + best.a.anchor.length);
    }
    if (rest) segs.push({ text: rest });
    return segs;
  });
}
