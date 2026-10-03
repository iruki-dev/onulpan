import Link from "next/link";
import { IssueView, type IssueSections } from "@/components/IssueView";
import { ShareButton } from "@/components/ShareButton";
import { Tracker } from "@/components/Tracker";
import { q } from "@/lib/db";
import { kstDateTime } from "@/lib/time";

export const metadata = {
  title: "이번 주 쟁점 5 — 면접·시사 대비",
  description: "지난 7일 동안 입장이 갈린 사안 다섯 가지. 확인된 사실, 쟁점, 입장별 주장과 근거, 아직 모르는 것.",
};

export default async function WeeklyIssuesPage() {
  const rows = await q<{ seq: number; title: string; summary: string; meta: { sections: IssueSections }; created_at: Date }>(
    `SELECT seq, title, summary, meta, created_at FROM posts
     WHERE kind = 'issue' AND created_at > now() - interval '7 days'
     ORDER BY importance DESC, seq DESC LIMIT 5`,
  );
  return (
    <>
      <Tracker page="weekly_issues" />
      <h1>이번 주 쟁점 5</h1>
      <p className="muted">면접·논술·시사 토론을 준비하는 분들을 위해 지난 7일 동안 입장이 갈린 사안을 모았습니다. 어느 쪽이 옳은지 판단하지 않습니다.</p>
      {rows.length === 0 && <p className="muted">이번 주에는 아직 쟁점 정리 글이 없습니다.</p>}
      {rows.map((r, i) => (
        <article key={r.seq} className="post">
          <p className="kicker">쟁점 {i + 1} · {kstDateTime(r.created_at)}</p>
          <h2 className="post-title"><Link href={`/p/${r.seq}`}>{r.title}</Link></h2>
          {r.meta.sections && <IssueView sections={r.meta.sections} />}
          <div className="actions">
            <ShareButton url={`/p/${r.seq}`} title={r.title} />
            <a className="button ghost" href={`/card/${r.seq}`} target="_blank">카드 이미지</a>
          </div>
        </article>
      ))}
    </>
  );
}
