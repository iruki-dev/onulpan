import Link from "next/link";
import { DraftCard } from "@/components/DraftCard";
import { budgetUsd, pendingDrafts } from "@/lib/admin";
import { one, q } from "@/lib/db";
import { GROUP_KO } from "@/lib/labels";
import { kstDateTime, kstToday } from "@/lib/time";

export const metadata = { title: "오늘" };

export default async function AdminToday() {
  const today = kstToday();
  const yesterday = kstToday(new Date(Date.now() - 864e5));
  const [drafts, pipe, outlets, rules, cost, readers, signups, quality] = await Promise.all([
    pendingDrafts(),
    one<{ last_fetch: Date | null; open_clusters: number; pending_gen: number; submitted_gen: number; posts_24h: number; open_reports: number }>(
      `SELECT (SELECT max(fetched_at) FROM raw_articles) AS last_fetch,
              (SELECT count(*) FROM clusters WHERE state = 'open') AS open_clusters,
              (SELECT count(*) FROM generation_requests WHERE status = 'pending') AS pending_gen,
              (SELECT count(*) FROM generation_requests WHERE status = 'submitted') AS submitted_gen,
              (SELECT count(*) FROM posts WHERE created_at > now() - interval '24 hours') AS posts_24h,
              (SELECT count(*) FROM error_reports WHERE status = 'open') AS open_reports`,
    ),
    q<{ id: number; name: string; grp: string; active: boolean; n_24h: number; last_fetched: Date | null }>(
      "SELECT * FROM v_outlet_collection_24h WHERE active ORDER BY n_24h, name",
    ),
    q<{ rule_id: string; today_pct: number | null; week_pct: number | null; today_failed: number }>(
      `SELECT rule_id,
              max(fail_pct) FILTER (WHERE day = $1) AS today_pct,
              sum(failed) FILTER (WHERE day = $1) AS today_failed,
              round(100.0 * sum(failed) FILTER (WHERE day > $1::date - 7) / NULLIF(sum(checked) FILTER (WHERE day > $1::date - 7), 0), 1) AS week_pct
       FROM v_verify_rule_daily GROUP BY rule_id ORDER BY substring(rule_id from 2)::int`,
      [today],
    ),
    one<{ today: number; month: number }>(
      `SELECT COALESCE((SELECT sum(cost_usd) FROM llm_calls WHERE kst_date(at) = $1), 0) AS today,
              COALESCE((SELECT cost_usd FROM v_llm_cost_month WHERE month = date_trunc('month', $1::date)::date), 0) AS month`,
      [today],
    ),
    one<{ openers: number; completers: number; link_clicks: number; audio_interest: number }>(
      "SELECT * FROM v_reader_daily WHERE day = $1", [yesterday],
    ),
    q<{ channel: string; invite_code: string | null; signups: number }>(
      "SELECT channel, invite_code, sum(signups)::int AS signups FROM v_signups_daily WHERE day >= $1::date - 1 GROUP BY 1, 2 ORDER BY 3 DESC",
      [today],
    ),
    one<{ pass_pct: number | null; discard_pct: number | null; generated: number }>("SELECT * FROM v_quality_daily WHERE day = $1", [today]),
  ]);
  const budget = budgetUsd();
  const ratio = cost ? cost.month / budget : 0;
  const zero = outlets.filter((o) => o.n_24h === 0);

  return (
    <>
      <h1>오늘 {today}</h1>

      <h2 className="section-head">1. 초안 검토 ({drafts.length}) — 06:20까지 손대지 않은 초안은 자동 게시</h2>
      {drafts.length === 0 && <p className="muted">검토할 초안이 없습니다.</p>}
      {drafts.slice(0, 30).map((d) => <DraftCard key={d.id} d={d} />)}
      {drafts.length > 30 && <p><Link href="/admin/drafts">나머지 {drafts.length - 30}편 보기</Link></p>}

      <h2 className="section-head">2. 파이프라인 상태</h2>
      <div className="grid2">
        <div className="card">
          <p>최근 수집: <strong className={!pipe?.last_fetch || Date.now() - new Date(pipe.last_fetch).getTime() > 36e5 ? "error" : ""}>
            {pipe?.last_fetch ? kstDateTime(pipe.last_fetch) : "없음"}</strong></p>
          <p>열린 묶음 {pipe?.open_clusters} · 생성 대기 {pipe?.pending_gen} · 배치 처리 중 {pipe?.submitted_gen}</p>
          <p>최근 24시간 게시 {pipe?.posts_24h}편 · 미처리 제보 <Link href="/admin/reports">{pipe?.open_reports}건</Link></p>
          <p>오늘 첫 생성 통과율 {quality?.pass_pct ?? "–"}% (목표 80% 이상) · 폐기율 {quality?.discard_pct ?? "–"}% (목표 5% 미만)</p>
        </div>
        <div className="card">
          <p><strong>매체별 24시간 수집</strong> {zero.length > 0 && <span className="error">· 0건 {zero.length}곳</span>}</p>
          <div className="table-wrap" style={{ maxHeight: 260, overflowY: "auto" }}>
            <table><tbody>
              {outlets.map((o) => (
                <tr key={o.id} className={o.n_24h === 0 ? "error" : ""}>
                  <td>{o.name}</td><td className="muted small">{GROUP_KO[o.grp]}</td><td>{o.n_24h}</td>
                </tr>
              ))}
            </tbody></table>
          </div>
        </div>
      </div>

      <h2 className="section-head">3. 검증 실패율 (규칙별, 오늘 / 7일 평균)</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>규칙</th><th>오늘 실패</th><th>오늘 %</th><th>7일 %</th></tr></thead>
          <tbody>
            {rules.length === 0 && <tr><td colSpan={4} className="muted">아직 검증 기록이 없습니다.</td></tr>}
            {rules.map((r) => (
              <tr key={r.rule_id}><td>{r.rule_id}</td><td>{r.today_failed ?? 0}</td><td>{r.today_pct ?? "–"}</td><td>{r.week_pct ?? "–"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="section-head">4. 비용</h2>
      <p>오늘 <strong>${cost?.today.toFixed(2)}</strong> · 당월 <strong className={ratio >= 0.8 ? "error" : ""}>${cost?.month.toFixed(2)}</strong> / 상한 ${budget}
        ({Math.round(ratio * 100)}%){ratio >= 1 && <strong className="error"> · 생성 제출 중단됨</strong>} · <Link href="/admin/costs">자세히</Link></p>

      <h2 className="section-head">5. 독자 (어제)</h2>
      <p>조간 연 사람 {readers?.openers ?? 0} · 완독 {readers?.completers ?? 0}
        {readers?.openers ? ` (${Math.round((100 * (readers.completers ?? 0)) / readers.openers)}%)` : ""} · 링크 클릭 {readers?.link_clicks ?? 0}
        · 오디오 관심 {readers?.audio_interest ?? 0}</p>
      <p>신규 가입 (어제·오늘): {signups.length === 0 ? "없음" : signups.map((s) => `${s.channel}${s.invite_code ? `(${s.invite_code})` : ""} ${s.signups}`).join(" · ")}</p>
    </>
  );
}
