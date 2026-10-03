export const metadata = { title: "개인정보 처리방침" };

export default function PrivacyPage() {
  const contact = process.env.FOUNDER_EMAIL ?? "editor@onulpan.kr";
  return (
    <article>
      <h1>개인정보 처리방침</h1>
      <p className="muted small">세부 문구는 법무 검토를 거쳐 확정합니다. 아래는 서비스가 실제로 처리하는 항목입니다.</p>
      <h2 className="section-head">수집하는 항목과 목적</h2>
      <ul>
        <li>이메일 주소, 로그인 방식(카카오·구글·이메일): 로그인과 조간 발송</li>
        <li>설정(분량, 분야별 비중, 관심 주제, 발송 시각): 개인 지면 구성</li>
        <li>가입 경로(초대 코드, 광고 유입 정보): 어떤 경로로 독자가 오는지 측정</li>
        <li>이용 기록(조간 열람·완독, 링크 클릭): 서비스 개선. 지면을 고르는 데는 쓰지 않습니다.</li>
        <li>결제 기록(창립 멤버): 결제·환불 처리. 카드 정보는 결제대행사가 처리하며 오늘판은 저장하지 않습니다.</li>
      </ul>
      <h2 className="section-head">보관 기간</h2>
      <ul>
        <li>회원 정보와 설정: 탈퇴 시 즉시 파기</li>
        <li>이용 기록: 13개월 뒤 월별 통계만 남기고 삭제</li>
        <li>결제 기록: 전자상거래법에 따른 기간 동안 보관</li>
      </ul>
      <h2 className="section-head">처리 위탁</h2>
      <ul>
        <li>Amazon Web Services(이메일 발송, SES)</li>
        <li>Cloudflare(웹 전송, 백업 저장)</li>
        <li>Anthropic(글 생성. 언론 보도만 보내며 독자 정보는 보내지 않습니다)</li>
        <li>토스페이먼츠(결제)</li>
      </ul>
      <h2 className="section-head">문의</h2>
      <p>{contact}</p>
    </article>
  );
}
