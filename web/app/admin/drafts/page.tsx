import { DraftCard } from "@/components/DraftCard";
import { pendingDrafts } from "@/lib/admin";
import { q } from "@/lib/db";
import { REJECT_REASONS } from "@/lib/labels";

export default async function AdminDrafts() {
  const pending = await pendingDrafts(500);
  const recent = await q<{ id: number; status: string; reject_reason: string | null; reject_note: string | null; title: string; decided_at: Date }>(
    `SELECT id, status, reject_reason, reject_note, payload->>'title' AS title, decided_at FROM drafts
     WHERE status <> 'pending' ORDER BY decided_at DESC NULLS LAST LIMIT 50`,
  );
  const weekly = await q<{ week: string; reviewed: number; rejected: number; auto_published: number; reject_pct: number | null }>(
    "SELECT * FROM v_review_weekly ORDER BY week DESC LIMIT 6",
  );
  return (
    <>
      <h1>초안</h1>
      <p className="muted small">사람 반려율이 4주 연속 1% 미만이면 사람 검토를 해제할 수 있습니다 (config: review.enabled).</p>
      <table>
        <thead><tr><th>주</th><th>검토</th><th>반려</th><th>자동 게시</th><th>반려율</th></tr></thead>
        <tbody>{weekly.map((w) => <tr key={w.week}><td>{w.week}</td><td>{w.reviewed}</td><td>{w.rejected}</td><td>{w.auto_published}</td><td>{w.reject_pct ?? 0}%</td></tr>)}</tbody>
      </table>
      <h2 className="section-head">대기 ({pending.length})</h2>
      {pending.map((d) => <DraftCard key={d.id} d={d} />)}
      <h2 className="section-head">최근 결정</h2>
      <table>
        <tbody>
          {recent.map((r) => (
            <tr key={r.id}><td>#{r.id}</td><td>{r.title}</td><td>{r.status}</td>
              <td>{r.reject_reason ? REJECT_REASONS[r.reject_reason] : ""} {r.reject_note}</td></tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
