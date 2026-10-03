import { q } from "@/lib/db";
import { GROUP_KO } from "@/lib/labels";
import { excludeOutlet } from "../actions";

export default async function AdminOutlets() {
  const rows = await q<{ id: number; name: string; domain: string; grp: string; active: boolean; excluded_at: Date | null; excluded_note: string | null; n_24h: number }>(
    `SELECT o.*, v.n_24h FROM outlets o JOIN v_outlet_collection_24h v ON v.id = o.id ORDER BY o.grp, o.name`,
  );
  return (
    <>
      <h1>매체</h1>
      <p className="muted small">수집 목록은 rules/outlets.yaml에서 관리합니다. 언론사가 제외를 요청하면 24시간 안에 여기서 제외합니다. 이미 쓴 글의 출처 표시는 그대로 둡니다.</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>매체</th><th>형태</th><th>24시간</th><th>상태</th><th></th></tr></thead>
          <tbody>
            {rows.map((o) => (
              <tr key={o.id}>
                <td>{o.name}<br /><span className="muted small">{o.domain}</span></td>
                <td>{GROUP_KO[o.grp]}</td>
                <td>{o.n_24h}</td>
                <td>{o.excluded_at ? `제외됨 (${o.excluded_note ?? ""})` : o.active ? "수집 중" : "비활성"}</td>
                <td>
                  {!o.excluded_at && (
                    <form action={excludeOutlet} className="row">
                      <input type="hidden" name="id" value={o.id} />
                      <input name="note" placeholder="요청 내용" style={{ width: 140 }} required />
                      <button type="submit" className="ghost">제외</button>
                    </form>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
