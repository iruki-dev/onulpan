import { budgetUsd } from "@/lib/admin";
import { q } from "@/lib/db";

export default async function AdminCosts() {
  const daily = await q<{ day: string; purpose: string; model: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number }>(
    "SELECT * FROM v_llm_cost_daily WHERE day > (now() AT TIME ZONE 'Asia/Seoul')::date - 31 ORDER BY day DESC, cost_usd DESC",
  );
  const perPost = await q<{ month: string; cost_usd: number; posts: number; cost_per_post: number | null }>(
    "SELECT * FROM v_cost_per_post_month ORDER BY month DESC LIMIT 12",
  );
  return (
    <>
      <h1>비용</h1>
      <p>월 상한 ${budgetUsd()} (80%에서 알림, 100%에서 생성 제출 중단). 글당 비용 목표: 베타 $0.03, 출시 $0.07 이하.</p>
      <h2 className="section-head">글당 비용</h2>
      <table>
        <thead><tr><th>월</th><th>LLM 비용</th><th>게시 글</th><th>글당</th></tr></thead>
        <tbody>{perPost.map((m) => <tr key={m.month}><td>{m.month.slice(0, 7)}</td><td>${m.cost_usd.toFixed(2)}</td><td>{m.posts}</td><td>{m.cost_per_post != null ? `$${m.cost_per_post}` : "–"}</td></tr>)}</tbody>
      </table>
      <h2 className="section-head">최근 31일</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>날짜</th><th>용도</th><th>모델</th><th>호출</th><th>입력</th><th>출력</th><th>비용</th></tr></thead>
          <tbody>
            {daily.map((d, i) => (
              <tr key={i}><td>{d.day}</td><td>{d.purpose}</td><td>{d.model}</td><td>{d.calls}</td>
                <td>{d.input_tokens.toLocaleString()}</td><td>{d.output_tokens.toLocaleString()}</td><td>${d.cost_usd.toFixed(4)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
