"use client";
import Script from "next/script";
import { useState } from "react";

type Order = { orderId: string; amount: number; orderName: string; customerKey: string; email: string };
declare global {
  interface Window {
    TossPayments?: (clientKey: string) => {
      payment: (o: { customerKey: string }) => { requestPayment: (p: Record<string, unknown>) => Promise<void> };
    };
  }
}

export function Checkout({ clientKey, createOrder }: { clientKey: string; createOrder: () => Promise<Order> }) {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Script src="https://js.tosspayments.com/v2/standard" onLoad={() => setReady(true)} />
      <button className="btn block"
        type="button"
        disabled={!ready || busy}
        onClick={async () => {
          setBusy(true);
          try {
            const o = await createOrder();
            const payment = window.TossPayments!(clientKey).payment({ customerKey: o.customerKey });
            await payment.requestPayment({
              method: "CARD",
              amount: { currency: "KRW", value: o.amount },
              orderId: o.orderId,
              orderName: o.orderName,
              customerEmail: o.email,
              successUrl: `${location.origin}/founding/success`,
              failUrl: `${location.origin}/founding/fail`,
            });
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "결제 창을 여는 중…" : "창립 멤버 되기"}
      </button>
    </>
  );
}
