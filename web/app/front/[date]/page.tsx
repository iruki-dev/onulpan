import Link from "next/link";
import { notFound } from "next/navigation";
import { one } from "@/lib/db";
import { SECTION_KO } from "@/lib/labels";
import { isIsoDate, kstDateLabel } from "@/lib/time";

export const metadata = { title: "1면은 이렇게 골랐어요" };

type Row = {
  rank: number; seq: number; title: string; section: string; kind: string; score: number; picked: boolean; reason: string | null;
  explain: { n_outlets?: number; n_groups?: number; hours_since_last?: number };
};

export default async function FrontHowPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  if (!isIsoDate(date)) notFound();
  const log = await one<{ payload: { top: Row[]; fallback: boolean; n_candidates: number } }>(
    "SELECT payload FROM decision_log WHERE kind = 'select' AND ref = $1 ORDER BY id DESC LIMIT 1",
    [`front:${date}`],
  );
  const max = Math.max(...(log?.payload.top.map((r) => r.score) ?? [1]), 0.001);
  return (
    <div className="page">
      <div className="page-head">
        <div className="date">{kstDateLabel(date)}</div>
        <h1 className="page-title">1면은 이렇게 골랐어요</h1>
        <p className="page-sub">보도한 언론사 수와 형태, 시간만으로 점수를 매겨요. 클릭 수는 쓰지 않아요.</p>
      </div>
      <div className="box formula">
        log₂(1 + 언론사 수) × (1 + 0.25 × (형태 수 − 1)) × 시간 감쇠
      </div>
      {!log ? (
        <p className="muted" style={{ padding: "24px 0 40px" }}>이날의 선정 기록이 없어요.</p>
      ) : (
        <section className="section">
          <div className="section-head">
            <h2 className="section-title">
              {log.payload.n_candidates > log.payload.top.length ? `후보 ${log.payload.n_candidates}편 중 상위 ${log.payload.top.length}편` : `후보 ${log.payload.n_candidates}편`}
            </h2>
          </div>
          {log.payload.fallback && <p className="notice-line" style={{ marginTop: 0 }}>후보가 모자라 전날 1면 주제의 종합 글로 채웠어요.</p>}
          {log.payload.top.map((r) => (
            <Link key={r.seq} href={`/p/${r.seq}`} className={`score-row${r.picked ? " picked" : ""}`}>
              <span className="rank tnum">{r.rank}</span>
              <span className="body">
                <span className="t">{r.title}</span>
                <span className="m">
                  {SECTION_KO[r.section]} · 언론사 {r.explain.n_outlets ?? "—"}곳 · 형태 {r.explain.n_groups ?? "—"}
                  {r.explain.hours_since_last != null && ` · ${r.explain.hours_since_last}시간 전`}
                  {!r.picked && r.reason && ` · ${r.reason}`}
                </span>
                <span className="bar"><i style={{ width: `${(r.score / max) * 100}%` }} /></span>
              </span>
              <span className="v tnum">{r.score.toFixed(2)}</span>
            </Link>
          ))}
        </section>
      )}
      <div style={{ padding: "8px 0 40px" }}>
        <Link href="/principles#front" className="text-link ink">편집 원칙 전문 보기</Link>
      </div>
    </div>
  );
}
