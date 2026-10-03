import { approveDraft, rejectDraft } from "@/app/admin/actions";
import { KIND_KO, REJECT_REASONS, SECTION_KO } from "@/lib/labels";

type Rule = { id: string; ok: boolean; skipped?: boolean; messages: string[]; details?: Record<string, unknown> };
export type Draft = {
  id: number; kind: string; status: string; created_at: Date;
  payload: { title: string; summary: string; section: string; body_md?: string; sections?: { question: string; positions: { holder: string; claim: string }[] };
             facts: { text: string; source_ids: string[] }[]; conflicts: unknown[] };
  verify_report: { rules: Rule[] };
  queued: boolean;
};

export function DraftCard({ d }: { d: Draft }) {
  const notes = d.verify_report.rules.filter((r) => !r.skipped && r.details && Object.keys(r.details).length);
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <p className="kicker">{KIND_KO[d.kind]} · {SECTION_KO[d.payload.section] ?? d.payload.section} · 초안 #{d.id}</p>
      <h3 style={{ margin: "4px 0" }}>{d.payload.title}</h3>
      <p className="muted">{d.payload.summary}</p>
      <details>
        <summary>본문과 사실 목록</summary>
        {d.payload.body_md ? <pre>{d.payload.body_md}</pre> : <pre>{JSON.stringify(d.payload.sections, null, 2)}</pre>}
        <ol className="small">{d.payload.facts.map((f, i) => <li key={i}>{f.text} <span className="muted">[{f.source_ids.join(", ")}]</span></li>)}</ol>
      </details>
      <p>
        {d.verify_report.rules.map((r) => (
          <span key={r.id} className={`pill ${r.skipped ? "" : r.ok ? "ok" : "bad"}`} title={r.messages.join("\n")}>{r.id}{r.skipped ? " –" : ""}</span>
        ))}
      </p>
      {notes.length > 0 && (
        <details>
          <summary className="small">규칙별 세부 (복제율, 최소 유사도 등)</summary>
          <pre>{notes.map((r) => `${r.id}: ${JSON.stringify(r.details)}`).join("\n")}</pre>
        </details>
      )}
      {d.queued ? (
        <p className="muted small">처리 중…</p>
      ) : d.status === "pending" ? (
        <div className="row">
          <form action={approveDraft}><input type="hidden" name="draft_id" value={d.id} /><button type="submit">승인</button></form>
          <form action={rejectDraft} className="row">
            <input type="hidden" name="draft_id" value={d.id} />
            <select name="reason" style={{ width: "auto" }}>
              {Object.entries(REJECT_REASONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input name="note" placeholder="메모 (선택)" style={{ width: 180 }} />
            <button type="submit" className="ghost">반려</button>
          </form>
        </div>
      ) : (
        <p className="small muted">{d.status}</p>
      )}
    </div>
  );
}
