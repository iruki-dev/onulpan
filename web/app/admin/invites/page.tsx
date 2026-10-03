import { q } from "@/lib/db";
import { siteUrl } from "@/lib/session";
import { createInvite } from "../actions";

export default async function AdminInvites() {
  const rows = await q<{ code: string; channel: string; created_at: Date; visits: number; signups: number; paid: number }>(
    `SELECT i.code, i.channel, i.created_at,
            (SELECT count(*) FROM events e WHERE e.name = 'invite_visit' AND e.props->>'code' = i.code)::int AS visits,
            (SELECT count(*) FROM users u WHERE u.invite_code = i.code)::int AS signups,
            (SELECT count(DISTINCT p.user_id) FROM payments p JOIN users u ON u.id = p.user_id WHERE u.invite_code = i.code AND p.status = 'paid')::int AS paid
     FROM invites i ORDER BY i.created_at DESC`,
  );
  return (
    <>
      <h1>초대 코드</h1>
      <p className="muted small">채널마다 코드를 따로 만들어 가입 경로를 잽니다 (예: evertime-w1). 링크: {siteUrl()}/invite/코드</p>
      <form action={createInvite} className="row">
        <input name="code" placeholder="코드" required style={{ width: 180 }} />
        <input name="channel" placeholder="채널 (예: 에브리타임)" required style={{ width: 200 }} />
        <button type="submit">만들기</button>
      </form>
      <div className="table-wrap" style={{ marginTop: 16 }}>
        <table>
          <thead><tr><th>코드</th><th>채널</th><th>방문</th><th>가입</th><th>선결제</th><th>전환율</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code}><td>{r.code}</td><td>{r.channel}</td><td>{r.visits}</td><td>{r.signups}</td><td>{r.paid}</td>
                <td>{r.visits ? `${Math.round((100 * r.signups) / r.visits)}%` : "–"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
