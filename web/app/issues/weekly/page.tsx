import Link from "next/link";
import type { IssueSections } from "@/components/IssueView";
import { ShareButton } from "@/components/ShareButton";
import { Tracker } from "@/components/Tracker";
import { q } from "@/lib/db";
import { SECTION_KO } from "@/lib/labels";

export const metadata = {
  title: "이번 주 쟁점 5 — 면접·시사 대비",
  description: "지난 7일 동안 입장이 갈린 사안 다섯 가지. 확인된 사실, 쟁점, 입장별 주장과 근거, 아직 모르는 것.",
};

export default async function WeeklyIssuesPage() {
  const rows = await q<{ seq: number; title: string; section: string; meta: { sections?: IssueSections } }>(
    `SELECT seq, title, section, meta FROM posts
     WHERE kind = 'issue' AND created_at > now() - interval '7 days'
     ORDER BY importance DESC, seq DESC LIMIT 5`,
  );
  return (
    <div className="page">
      <Tracker page="weekly_issues" />
      <div className="page-head">
        <h1 className="page-title">이번 주 쟁점</h1>
        <p className="page-sub">지난 7일, 입장이 갈린 사안 {rows.length}가지</p>
      </div>
      {rows.length === 0 && <p className="muted" style={{ padding: "8px 0 40px" }}>이번 주에는 아직 쟁점 정리가 없어요.</p>}
      {rows.map((r, i) => {
        const sec = r.meta.sections;
        return (
          <div key={r.seq}>
            <div className="band" />
            <section className="section" style={{ paddingBottom: 28, display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="kicker">
                <span className="num tnum">{String(i + 1).padStart(2, "0")}</span>
                <span className="sec">{SECTION_KO[r.section] ?? ""}</span>
              </div>
              <h2 className="issue-title" style={{ margin: 0 }}><Link href={`/p/${r.seq}`}>{sec?.question || r.title}</Link></h2>
              {sec && (
                <div className="split" style={{ gridTemplateColumns: `repeat(${Math.min(sec.positions.length, 3)}, minmax(0, 1fr))` }}>
                  {sec.positions.map((p, j) => <div key={j}><strong>{p.holder}</strong><span>{p.claim}</span></div>)}
                </div>
              )}
              <div className="btn-row">
                <Link href={`/p/${r.seq}`} className="btn secondary small">근거와 남은 질문</Link>
                <ShareButton url={`/p/${r.seq}`} title={r.title} variant="button" label="공유" className="btn small" />
              </div>
            </section>
          </div>
        );
      })}
    </div>
  );
}
