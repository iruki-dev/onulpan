import Link from "next/link";
import { Checkout } from "@/components/Checkout";
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
    <>
      <h1>창립 멤버가 되어 주세요</h1>
      <p>오늘판은 광고와 정치 후원을 받지 않습니다. 독자의 구독료로만 운영하려고 합니다. 정식 출시 전에 먼저 믿고 결제해 주시는 분들을 창립 멤버로 모십니다.</p>
      <div className="card">
        <p className="stat">{price}원 <span className="muted small">/ {FOUNDING.months}개월</span></p>
        <ul>
          <li>관심 주제 최대 5개: 그 주제의 새 글을 섹션보다 먼저 실어 드립니다.</li>
          <li>정식 출시 후 {FOUNDING.months}개월 동안 유료 기능 전부</li>
          <li>편집 원칙 개정 때 의견을 먼저 여쭙습니다.</li>
        </ul>
      </div>
      <h2 className="section-head">환불 조건</h2>
      <ul>
        <li>결제 후 14일 안에는 이유를 묻지 않고 전액 환불합니다.</li>
        <li>정식 출시 전에 서비스를 접게 되면 결제 금액 전액을 환불합니다.</li>
        <li>정식 출시 후에는 남은 기간만큼 일할 계산해 환불합니다.</li>
        <li>환불 요청: {process.env.FOUNDER_EMAIL ?? "editor@onulpan.kr"}</li>
      </ul>
      {paid ? (
        <p className="notice">창립 멤버로 함께해 주셔서 고맙습니다.</p>
      ) : !user ? (
        <Link href="/login?next=/founding" className="button">로그인하고 결제하기</Link>
      ) : tossEnabled() ? (
        <Checkout clientKey={process.env.TOSS_CLIENT_KEY!} createOrder={createOrder} />
      ) : (
        <p className="muted">결제 준비 중입니다. 곧 열립니다.</p>
      )}
    </>
  );
}
