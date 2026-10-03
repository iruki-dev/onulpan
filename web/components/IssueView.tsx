// 쟁점 정리는 고정 틀로 렌더링한다 (카드 이미지 자동 생성과 같은 틀).
type Position = { holder: string; claim: string; grounds: string; source_ids?: string[] };
export type IssueSections = { facts: string[]; question: string; positions: Position[]; unknowns: string[] };

export function IssueView({ sections, outletOf }: { sections: IssueSections; outletOf?: Map<string, string> }) {
  const names = (ids?: string[]) =>
    [...new Set((ids ?? []).map((i) => outletOf?.get(i)).filter(Boolean))].join(" · ");
  return (
    <>
      <nav className="tabs" aria-label="목차">
        <a href="#facts">사실</a><a href="#positions">입장</a><a href="#unknowns">남은 질문</a>
      </nav>
      <section id="facts" className="section" style={{ paddingBottom: 24 }}>
        <h2 className="section-title" style={{ marginBottom: 8 }}>확인된 사실</h2>
        <ul className="dots">{sections.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>
      </section>
      <div className="band" />
      <section id="positions" className="section" style={{ paddingBottom: 28 }}>
        <h2 className="section-title" style={{ marginBottom: 20 }}>입장</h2>
        {sections.positions.map((p, i) => (
          <article key={i} className="position">
            <div className="who"><span className="n tnum">{i + 1}</span>{p.holder}</div>
            <p className="claim">{p.claim}</p>
            <p className="grounds">{p.grounds}</p>
            {names(p.source_ids) && <span className="src">{names(p.source_ids)}</span>}
          </article>
        ))}
      </section>
      <div className="band" />
      <section id="unknowns" className="section" style={{ paddingBottom: 24 }}>
        <h2 className="section-title" style={{ marginBottom: 8 }}>남은 질문</h2>
        <ul className="dots qs">{sections.unknowns.map((f, i) => <li key={i}>{f}</li>)}</ul>
      </section>
    </>
  );
}
