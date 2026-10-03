import Link from "next/link";
import { q } from "@/lib/db";
import { kstDateTime } from "@/lib/time";
import { answerReport, publishCorrection } from "../actions";

export default async function AdminReports({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const reports = await q<{ id: number; post_seq: number; title: string; body: string; contact: string | null; status: string; created_at: Date; answer: string | null; correction_seq: number | null }>(
    `SELECT r.*, p.title FROM error_reports r JOIN posts p ON p.seq = r.post_seq ORDER BY (r.status = 'open') DESC, r.id DESC LIMIT 100`,
  );
  return (
    <>
      <h1>제보·정정</h1>
      {sp.queued && <p className="notice">정정 글 발행을 요청했습니다. 몇 초 뒤 게시됩니다.</p>}
      {sp.error && <p className="error">정정 글의 대상 글 번호, 제목, 본문(20자 이상)을 확인해 주세요.</p>}
      <p className="muted small">48시간 안에 확인하고 답합니다. 틀린 것이 확인되면 정정 글을 새로 씁니다 (원래 글은 고치지 않습니다).</p>
      {reports.map((r) => {
        const late = r.status === "open" && Date.now() - new Date(r.created_at).getTime() > 48 * 36e5;
        return (
          <div key={r.id} className="card" style={{ marginBottom: 14 }}>
            <p className="small">
              #{r.id} · <Link href={`/p/${r.post_seq}`}>{r.title}</Link> · {kstDateTime(r.created_at)} ·{" "}
              <strong className={late ? "error" : ""}>{r.status}{late ? " (48시간 경과)" : ""}</strong> {r.contact && `· ${r.contact}`}
            </p>
            <p>{r.body}</p>
            {r.correction_seq && <p className="small">정정 글: <Link href={`/p/${r.correction_seq}`}>#{r.correction_seq}</Link></p>}
            {r.status === "open" && (
              <>
                <form action={answerReport} className="row">
                  <input type="hidden" name="id" value={r.id} />
                  <input name="answer" placeholder="답변 (확인 결과)" style={{ flex: 1 }} />
                  <select name="status" style={{ width: "auto" }}><option value="rejected">사실과 다르지 않음</option><option value="confirmed">오류 확인</option></select>
                  <button type="submit" className="ghost">답변</button>
                </form>
                <details>
                  <summary className="small">정정 글 쓰기</summary>
                  <CorrectionForm target={r.post_seq} reportId={r.id} />
                </details>
              </>
            )}
          </div>
        );
      })}
      <h2 className="section-head">제보 없이 정정 글 쓰기</h2>
      <CorrectionForm />
    </>
  );
}

function CorrectionForm({ target, reportId }: { target?: number; reportId?: number }) {
  return (
    <form action={publishCorrection}>
      {reportId && <input type="hidden" name="report_id" value={reportId} />}
      <label>정정할 글 번호<input name="target_seq" type="number" defaultValue={target} required /></label>
      <label>제목 (36자 이내)<input name="title" maxLength={36} defaultValue="정정: " required /></label>
      <label>요약 (80자 이내)<input name="summary" maxLength={80} /></label>
      <label>본문: 무엇이 틀렸고 무엇이 맞는지<textarea name="body" rows={6} required /></label>
      <button type="submit">정정 글 발행</button>
    </form>
  );
}
