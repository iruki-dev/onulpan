import Link from "next/link";
import { Checkout } from "@/components/Checkout";
import { Check, Chevron } from "@/components/Icons";
import { one } from "@/lib/db";
import { FOUNDING, tossEnabled } from "@/lib/payments";
import { currentUser } from "@/lib/session";
import { createOrder } from "./actions";

export const metadata = { title: "창립 멤버" };

export default async function FoundingPage() {
  const user = await currentUser();
  const paid = user
    ? await one("SELECT 1 FROM payments WHERE user_id = $1 AND status = 'paid'", [user.id])
    : null;
  const price = FOUNDING.amount.toLocaleString("ko-KR");
  return (
    <div className="page">
      <div className="hero" style={{ paddingBottom: 28 }}>
        <h1>광고 없이,<br />독자의 구독료로만</h1>
        <p>정식 출시 전에 먼저 믿어 주시는 분들을 창립 멤버로 모셔요.</p>
      </div>
      <div className="price-card">
        <div className="price"><strong className="tnum">{price}원</strong><span>{FOUNDING.months}개월</span></div>
        <ul className="checks">
          <li><Check />관심 주제 5개를 먼저 실어 드려요</li>
          <li><Check />정식 출시 후 {FOUNDING.months}개월 동안 유료 기능 전부</li>
          <li><Check />편집 원칙을 고칠 때 먼저 의견을 여쭤요</li>
        </ul>
      </div>
      <div style={{ padding: "20px 0 8px" }}>
        {paid ? (
          <p className="notice">창립 멤버로 함께해 주셔서 고맙습니다.</p>
        ) : !user ? (
          <Link href="/login?next=/founding" className="btn block">로그인하고 시작하기</Link>
        ) : tossEnabled() ? (
          <Checkout clientKey={process.env.TOSS_CLIENT_KEY!} createOrder={createOrder} />
        ) : (
          <button type="button" className="btn block" disabled>곧 열려요</button>
        )}
      </div>
      <details className="cell-details" style={{ marginBottom: 40 }}>
        <summary className="cell">
          <span className="body"><span className="main plain">환불 조건</span></span>
          <Chevron className="chev" />
        </summary>
        <ul className="dots" style={{ marginTop: 0 }}>
          <li>결제 후 14일 안에는 이유를 묻지 않고 전액 환불해요.</li>
          <li>정식 출시 전에 서비스를 접으면 전액 환불해요.</li>
          <li>정식 출시 후에는 남은 기간만큼 일할 계산해 환불해요.</li>
          <li>환불 요청: {process.env.FOUNDER_EMAIL ?? "editor@onulpan.kr"}</li>
        </ul>
      </details>
    </div>
  );
}
