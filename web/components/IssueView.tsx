// 쟁점 정리는 고정 틀로 렌더링한다. 틀이 고정이어야 카드 이미지 자동 생성이 가능하다.
type Position = { holder: string; claim: string; grounds: string; source_ids?: string[] };
export type IssueSections = { facts: string[]; question: string; positions: Position[]; unknowns: string[] };

export function IssueView({ sections }: { sections: IssueSections }) {
  return (
    <div className="issue">
      <section>
        <h4>확인된 사실</h4>
        <ul>{sections.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>
      </section>
      <section className="issue-question">
        <h4>쟁점</h4>
        <p>{sections.question}</p>
      </section>
      <section>
        <h4>입장</h4>
        <div className="positions">
          {sections.positions.map((p, i) => (
            <div key={i} className="position">
              <p className="holder">{p.holder}</p>
              <p className="claim">{p.claim}</p>
              <p className="grounds"><span>근거</span> {p.grounds}</p>
            </div>
          ))}
        </div>
        <p className="muted small">입장은 기사에 나온 순서대로 싣습니다. 어느 쪽이 옳은지 판단하지 않습니다.</p>
      </section>
      <section>
        <h4>아직 모르는 것</h4>
        <ul>{sections.unknowns.map((f, i) => <li key={i}>{f}</li>)}</ul>
      </section>
    </div>
  );
}
