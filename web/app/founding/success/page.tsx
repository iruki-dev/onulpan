import Link from "next/link";
import { one, q } from "@/lib/db";
import { confirmToss } from "@/lib/payments";
import { requireUser } from "@/lib/session";

export default async function SuccessPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const user = await requireUser("/founding");
  const order = await one<{ id: number; amount: number; status: string }>(
    "SELECT id, amount, status FROM payments WHERE order_id = $1 AND user_id = $2",
    [sp.orderId ?? "", user.id],
  );
  // 금액을 서버 기록과 대조한다 (클라이언트가 바꾼 금액으로 승인하지 않는다)
  if (!order || Number(sp.amount) !== order.amount || !sp.paymentKey) {
    return <><h1>결제를 확인하지 못했습니다</h1><p><Link href="/founding">다시 시도하기</Link></p></>;
  }
  if (order.status !== "paid") {
    const r = await confirmToss(sp.paymentKey, sp.orderId!, order.amount);
    if (!r.ok) {
      await q("UPDATE payments SET status = 'failed', raw = $2 WHERE id = $1", [order.id, JSON.stringify(r.body)]);
      return <><h1>결제가 승인되지 않았습니다</h1><p>{String(r.body.message ?? "")}</p><p><Link href="/founding">다시 시도하기</Link></p></>;
    }
    await q("UPDATE payments SET status = 'paid', payment_key = $2, raw = $3, paid_at = now() WHERE id = $1", [
      order.id, sp.paymentKey, JSON.stringify(r.body),
    ]);
    await q("UPDATE users SET plan = 'founding' WHERE id = $1", [user.id]);
    await q("INSERT INTO events (user_id, name, props) VALUES ($1, 'founding_paid', $2)", [user.id, JSON.stringify({ amount: order.amount })]);
  }
  return (
    <>
      <h1>창립 멤버가 되셨습니다</h1>
      <p>고맙습니다. <Link href="/settings">설정</Link>에서 관심 주제를 정해 보세요.</p>
    </>
  );
}
