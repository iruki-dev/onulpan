import "server-only";

// 창립 멤버 선결제. 금액·기간은 환경 변수로 정한다 (가격 실험).
export const FOUNDING = {
  product: "founding_12m",
  name: "오늘판 창립 멤버 12개월",
  amount: Number(process.env.FOUNDING_PRICE_KRW ?? 39000),
  months: 12,
};

export function tossEnabled(): boolean {
  return Boolean(process.env.TOSS_CLIENT_KEY && process.env.TOSS_SECRET_KEY);
}

/** 토스페이먼츠 결제 승인. 서버에서 금액을 다시 대조한 뒤 호출한다. */
export async function confirmToss(paymentKey: string, orderId: string, amount: number) {
  const auth = Buffer.from(`${process.env.TOSS_SECRET_KEY}:`).toString("base64");
  const r = await fetch("https://api.tosspayments.com/v1/payments/confirm", {
    method: "POST",
    headers: { authorization: `Basic ${auth}`, "content-type": "application/json", "idempotency-key": orderId },
    body: JSON.stringify({ paymentKey, orderId, amount }),
  });
  return { ok: r.ok, body: (await r.json().catch(() => ({}))) as Record<string, unknown> };
}
