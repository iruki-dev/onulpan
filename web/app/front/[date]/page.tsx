import Link from "next/link";
import { notFound } from "next/navigation";
import { one } from "@/lib/db";
import { SECTION_KO } from "@/lib/labels";
import { isIsoDate, kstDateLabel } from "@/lib/time";

export const metadata = { title: "1면은 이렇게 골랐습니다" };

type Row = {
  rank: number; seq: number; title: string; section: string; kind: string; score: number; picked: boolean; reason: string | null;
  explain: { n_outlets?: number; n_groups?: number; hours_since_last?: number; outlet_term?: number; group_term?: number; decay_term?: number; stored_importance?: number };
};

export default async function FrontHowPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  if (!isIsoDate(date)) notFound();
  const log = await one<{ payload: { top: Row[]; fallback: boolean; n_candidates: number; at: string; formula: string } }>(
    "SELECT payload FROM decision_log WHERE kind = 'select' AND ref = $1 ORDER BY id DESC LIMIT 1",
    [`front:${date}`],
  );
  return (
    <>
      <p className="dateline">{kstDateLabel(date)}</p>
      <h1>1면은 이렇게 골랐습니다</h1>
      <p>
        1면은 편집자의 취향이 아니라 공개된 공식으로 고릅니다. 매일 아침 06시 25분, 직전 24시간 동안 쓴 사실·종합 글에 점수를 매겨
        서로 다른 주제 3편을 고릅니다. 같은 분야는 최대 2편입니다. 클릭 수, 체류 시간, 공유 수는 쓰지 않습니다.
      </p>
      <p className="card">
        점수 = log₂(1 + 보도한 언론사 수) × (1 + 0.25 × (언론사 형태 수 − 1)) × 시간 감쇠(18시간마다 약 63% 감소)
      </p>
      {!log ? (
        <p className="muted">이날의 선정 기록이 없습니다.</p>
      ) : (
        <>
          <p className="muted small">후보 {log.payload.n_candidates}편 가운데 상위 {log.payload.top.length}편의 점수와 결과입니다.
            {log.payload.fallback && " 이날은 후보가 3편보다 적어 전날 1면 주제의 종합 글로 채웠습니다."}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>순위</th><th>글</th><th>분야</th><th>언론사</th><th>형태</th><th>경과</th><th>점수</th><th>결과</th></tr>
              </thead>
              <tbody>
                {log.payload.top.map((r) => (
                  <tr key={r.seq}>
                    <td>{r.rank}</td>
                    <td><Link href={`/p/${r.seq}`}>{r.title}</Link></td>
                    <td>{SECTION_KO[r.section]}</td>
                    <td>{r.explain.n_outlets ?? "—"}</td>
                    <td>{r.explain.n_groups ?? "—"}</td>
                    <td>{r.explain.hours_since_last != null ? `${r.explain.hours_since_last}시간` : "—"}</td>
                    <td>{r.score.toFixed(3)}</td>
                    <td>{r.picked ? <strong>1면</strong> : <span className="muted">{r.reason}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p><Link href="/principles#front">편집 원칙: 1면과 지면은 이렇게 고릅니다</Link></p>
    </>
  );
}
