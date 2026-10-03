import Link from "next/link";
import { q } from "@/lib/db";
import { imageSources } from "@/lib/images";
import { GROUP_KO } from "@/lib/labels";

export const metadata = {
  title: "편집 원칙",
  description: "오늘판의 인공지능이 무엇을 쓰고 무엇을 쓰지 않는지, 어떤 기준으로 지면을 고르는지 공개하는 약속입니다.",
};

const REVISIONS = [
  { version: "v1", date: process.env.BETA_LAUNCH_DATE ?? "베타 공개일", change: "최초 공개" },
  { version: "v1.1", date: "2026-10-03", change: "이미지 원칙 추가" },
];

export default async function PrinciplesPage() {
  const outlets = await q<{ name: string; grp: string; active: boolean; excluded_at: Date | null }>(
    "SELECT name, grp::text AS grp, active, excluded_at FROM outlets WHERE domain NOT LIKE '%.invalid' ORDER BY grp, name",
  );
  const stats = await q<{ month: string; posts: number; corrections: number; correction_pct: number }>(
    "SELECT * FROM v_correction_monthly ORDER BY month DESC LIMIT 12",
  );
  const imgSources = await imageSources();
  const byGroup = new Map<string, typeof outlets>();
  for (const o of outlets.filter((o) => o.active && !o.excluded_at)) byGroup.set(o.grp, [...(byGroup.get(o.grp) ?? []), o]);
  const founder = process.env.FOUNDER_NAME ?? "창업자";
  const contact = process.env.FOUNDER_EMAIL ?? "editor@onulpan.kr";

  return (
    <article className="page prose-doc principles">
      <h1>오늘판 편집 원칙</h1>
      <p>
        오늘판의 모든 글은 인공지능이 여러 언론 보도를 종합해 씁니다. 이 문서는 그 인공지능이 무엇을 쓰고 무엇을 쓰지 않는지,
        어떤 기준으로 지면을 고르는지 독자에게 공개하는 약속입니다.
      </p>

      <h2 className="section-head">우리가 쓰는 것과 쓰지 않는 것</h2>
      <p><strong>오늘판은 사실을 모아 정리하지만, 무엇이 옳은지 판단하지 않습니다.</strong> 그래서 사설과 칼럼을 쓰지 않습니다.
        입장이 갈리는 사안은 ‘쟁점 정리’로, 누가 무엇을 주장하는지를 나란히 보여드립니다.</p>
      <h3>우리가 쓰는 글 다섯 종류</h3>
      <ul>
        <li><strong>사실:</strong> 오늘 일어난 한 가지 일. 서로 다른 언론사 두 곳 이상이 보도한 내용만 씁니다.</li>
        <li><strong>종합:</strong> 며칠, 몇 주에 걸친 사안이 지금 어디까지 왔는지 정리한 글.</li>
        <li><strong>쟁점 정리:</strong> 확인된 사실, 무엇에 대한 다툼인지, 각 주체의 주장과 근거, 아직 모르는 것.</li>
        <li><strong>해설:</strong> 뉴스에 자주 나오는 말의 뜻과 배경. 본문의 밑줄 링크가 이 글로 연결됩니다.</li>
        <li><strong>교양:</strong> 뉴스와 무관하게 읽을 만한 역사·과학·고전 이야기.</li>
      </ul>
      <h3>우리가 지키는 것</h3>
      <ul>
        <li>모든 주장에는 말한 사람이나 기관을 붙입니다. “논란이 일고 있다”처럼 주어가 없는 문장을 쓰지 않습니다.</li>
        <li>평가하는 형용사를 쓰지 않습니다. 충격적이다, 황당하다 같은 판단은 독자의 몫입니다.</li>
        <li>언론사마다 숫자가 다르면 다르다고 쓰고, 각각 어디서 나왔는지 밝힙니다.</li>
        <li>한 곳만 보도한 소식(단독 보도)은 확인될 때까지 쓰지 않습니다.</li>
        <li>기사의 문장을 옮겨 쓰지 않고, 사실을 뽑아 처음부터 다시 씁니다.</li>
      </ul>
      <h3>우리가 하지 않는 것</h3>
      <ul>
        <li>사설, 칼럼, 전망, 추천을 쓰지 않습니다.</li>
        <li>정치 광고, 선거 광고, 정당·정치 단체의 후원을 받지 않습니다.</li>
        <li>광고주를 위해 글을 쓰거나 지면을 바꾸지 않습니다.</li>
      </ul>

      <h2 className="section-head">어디서 가져오는가</h2>
      <p><strong>우리는 언론사를 골라 담지 않습니다. 주요 언론사를 성향과 관계없이 모두 읽습니다.</strong> 언론사마다 정치 성향을 매겨
        ‘균형’을 맞추는 방식은 그 분류 자체가 논쟁이 됩니다. 대신 범위를 넓게 잡는 것으로 치우침을 줄입니다.</p>
      <ul>
        <li><strong>읽는 곳:</strong> 전국 종합일간지, 지상파·종편·보도 전문 방송, 뉴스통신사, 경제지 가운데 공개 구독 주소(RSS)를 제공하는 곳 전부,
          그리고 정부 정책브리핑. 전체 목록은 <a href="#outlets">이 페이지 하단</a>에 공개하고 바뀔 때마다 갱신합니다.</li>
        <li><strong>읽지 않는 곳:</strong> 유료 구독 전용 기사, 로그인이 필요한 기사.</li>
        <li><strong>출처 표시:</strong> 모든 글 아래에 참고한 기사 전부를 언론사 이름, 제목, 원문 링크로 보여드립니다. 원문을 직접 확인하실 수 있습니다.</li>
        <li><strong>언론사의 제외 요청:</strong> 언론사가 요청하면 24시간 안에 수집 대상에서 뺍니다. 이미 쓴 글의 출처 표시는 그대로 둡니다.</li>
        <li><strong>인공지능:</strong> 글은 Anthropic의 Claude 모델이 씁니다. 각 글 아래에 어떤 모델과 지침 버전으로 썼는지 기록합니다.</li>
      </ul>

      <h2 className="section-head" id="front">1면과 지면은 이렇게 고릅니다</h2>
      <p><strong>1면은 ‘얼마나 많은 언론사가, 얼마나 다양한 형태로 보도했는가’로 고릅니다. 편집자의 취향이 아니라 공개된 공식입니다.</strong>
        이 절이 오늘판의 기사배열 기본방침입니다.</p>
      <h3>1면 (모든 독자에게 같습니다)</h3>
      <p>매일 아침 06시 25분, 직전 24시간 동안 쓴 글에 아래 점수를 매겨 서로 다른 주제 3편을 고릅니다. 같은 분야(정치·경제 등)는 최대 2편까지입니다.</p>
      <p className="card">점수 = log₂(1 + 보도한 언론사 수) × (1 + 0.25 × (언론사 형태 수 − 1)) × 시간 감쇠</p>
      <ul>
        <li><strong>보도한 언론사 수</strong>는 로그로 줄여, 통신사 기사를 여러 곳이 그대로 옮겨 실은 경우가 과대평가되지 않게 합니다.</li>
        <li><strong>언론사 형태 수</strong>는 종합일간지·방송·통신사·경제지·지역지·인터넷 언론·정부 가운데 몇 가지 형태가 보도했는지입니다. 여러 형태가 함께 다룬 사안일수록 점수가 높습니다.</li>
        <li><strong>시간 감쇠</strong>는 마지막 보도 후 시간이 지날수록 점수를 줄입니다(18시간마다 약 63%씩 감소).</li>
        <li>매일 후보 상위 10편의 점수와 탈락 이유를 조간 하단 ‘1면은 이렇게 골랐습니다’에서 볼 수 있습니다.</li>
      </ul>
      <h3>나머지 지면 (독자마다 다릅니다)</h3>
      <ul>
        <li>설정에서 고른 분량(10분·25분·40분)만큼, 1면과 같은 점수에 독자가 정한 분야 가중치(더·보통·덜)를 곱해 높은 순으로 채웁니다.</li>
        <li>한 분야가 지면의 40%를 넘지 않고, 정치·경제·사회·국제·과학기술 다섯 분야는 후보가 있으면 적어도 한 편씩 싣습니다.</li>
        <li>같은 주제는 한 편만 싣고, 최근 사흘 안에 이미 보신 주제는 뒤로 보냅니다.</li>
        <li>쟁점 정리 1편은 모든 독자에게 같습니다. 오늘 입장이 갈린 사안 가운데 점수가 가장 높은 것입니다.</li>
      </ul>
      <p><strong>우리가 쓰지 않는 기준.</strong> 클릭 수, 체류 시간, 공유 수는 1면과 지면을 고르는 데 쓰지 않습니다. 많이 읽히는 글이 아니라 많이 보도된 글이 앞에 옵니다.</p>

      <h2 className="section-head" id="images">이미지는 이렇게 고르고 표기합니다</h2>
      <p><strong>이미지는 이용 조건이 확인된 출처에서만 가져오고, 출처가 지정한 크레딧을 이미지 바로 아래에 그대로 적습니다.</strong>{" "}
        언론사가 찍은 보도사진은 가져오지 않습니다. 같은 사이트 안에서도 이미지마다 조건이 다를 수 있어, 이미지 한 장 한 장의 표기를 기준으로 판단합니다.</p>
      <ul>
        <li><strong>자유 이용 출처를 먼저 찾습니다.</strong> 기업·기관 발표를 다루는 글에는 그 기업·기관이 보도용으로 제공한 이미지를, 그 소식을 다루는 글에서만 씁니다.</li>
        <li><strong>원본 형태를 유지합니다.</strong> 자르거나 글자를 얹는 것은 변경을 허락한 라이선스에서만 합니다. 나머지는 원본 비율 그대로 싣습니다.</li>
        <li><strong>자체 제작 그래픽</strong>에는 원자료의 출처를 함께 적습니다.</li>
        <li><strong>사람이 확인합니다.</strong> 자동으로 찾은 사진은 사람이 확인한 뒤에 싣습니다. 인물 사진은 항상 그렇습니다.</li>
        <li>이미지 아래 ⓘ를 누르면 출처, 라이선스, 이용 조건, 원본을 볼 수 있습니다.</li>
      </ul>
      {(["free", "press"] as const).map((tier) => (
        <div key={tier}>
          <h3>{tier === "free" ? "자유 이용 출처 — 출처 표시만 하면 모든 글에" : "보도용 제공 출처 — 그 소식을 다루는 글에서만, 원본 그대로"}</h3>
          <div className="table-wrap">
            <table>
              <thead><tr><th>출처</th><th>주요 이미지</th><th>사용 조건</th></tr></thead>
              <tbody>
                {imgSources.filter((s) => s.tier === tier).map((s) => (
                  <tr key={s.key}>
                    <td>{s.url ? <a href={s.url} target="_blank" rel="noopener">{s.name}</a> : s.name}</td>
                    <td>{s.examples}</td><td>{s.conditions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      <h3 id="image-requests">권리자 요청</h3>
      <p>이미지의 권리자이시거나 사진 속 인물이시라면 이미지 아래 ⓘ → ‘이미지 내리기 요청’으로 알려 주세요({contact}로도 받습니다).{" "}
        <strong>요청을 받으면 그 자리에서 이미지를 내리고</strong>, 출처와 이용 조건을 확인해 3일 안에 답을 드립니다.{" "}
        이용 근거를 확인하면 근거를 보여 드리고 협의하며, 그렇지 않으면 다른 이미지로 바꾸거나 내린 상태로 둡니다.</p>

      <h2 className="section-head">글은 고치지 않고 덧붙입니다</h2>
      <p><strong>한 번 발행한 글은 수정하거나 지우지 않습니다. 틀린 것이 확인되면 정정 글을 새로 쓰고, 원래 글 위에 그 사실을 표시합니다.</strong>
        조용히 고친 글은 독자가 무엇이 바뀌었는지 알 수 없습니다. 오늘판은 무엇을 언제 잘못 썼는지까지 기록으로 남깁니다.</p>
      <ul>
        <li><strong>정정:</strong> 원래 글 맨 위에 “이 글에는 이후 정정이 있습니다” 띠가 붙고, 정정 글로 연결됩니다. 정정 글에는 무엇이 틀렸고 무엇이 맞는지를 씁니다.</li>
        <li><strong>후속:</strong> 사안에 새 소식이 생기면 새 글을 쓰고, 이전 글 위에 “이 주제의 새 글이 있습니다”를 표시합니다.</li>
        <li><strong>오류 제보:</strong> 모든 글 아래 “사실과 다른 내용이 있나요?”로 알려주세요. 48시간 안에 확인하고 결과를 알려드립니다.</li>
        <li><strong>정정·반론보도 청구:</strong> 법에 따른 청구도 같은 방식으로 새 글을 발행해 처리합니다.</li>
        <li><strong>정정 통계:</strong> 매달 발행한 글 수와 정정 글 수를 이 페이지에 공개합니다.</li>
      </ul>
      <div className="table-wrap">
        <table>
          <thead><tr><th>월</th><th>발행한 글</th><th>정정 글</th><th>정정률</th></tr></thead>
          <tbody>
            {stats.length === 0 && <tr><td colSpan={4} className="muted">아직 집계할 글이 없습니다.</td></tr>}
            {stats.map((s) => (
              <tr key={s.month}><td>{s.month.slice(0, 7)}</td><td>{s.posts}</td><td>{s.corrections}</td><td>{s.correction_pct ?? 0}%</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="section-head" id="contact">책임자와 연락처, 개정 이력</h2>
      <p><strong>편집 원칙을 바꿀 때는 무엇을 왜 바꿨는지 이 페이지에 먼저 공개하고 적용합니다.</strong></p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>역할</th><th>담당</th><th>연락처</th></tr></thead>
          <tbody>
            <tr><td>기사배열책임자</td><td>{founder}</td><td>{contact}</td></tr>
            <tr><td>청소년보호책임자</td><td>{founder}</td><td>{contact}</td></tr>
            <tr><td>오류 제보·정정 요청</td><td>모든 글 하단 제보 버튼</td><td>48시간 안에 답변</td></tr>
            <tr><td>언론사 수집 제외 요청</td><td>이메일</td><td>{contact} · 24시간 안에 처리</td></tr>
          </tbody>
        </table>
      </div>
      <div className="table-wrap" style={{ marginTop: 16 }}>
        <table>
          <thead><tr><th>버전</th><th>날짜</th><th>바뀐 내용</th></tr></thead>
          <tbody>{REVISIONS.map((r) => <tr key={r.version}><td>{r.version}</td><td>{r.date}</td><td>{r.change}</td></tr>)}</tbody>
        </table>
      </div>

      <h2 className="section-head" id="outlets">수집하는 언론사 ({outlets.filter((o) => o.active && !o.excluded_at).length}곳)</h2>
      {[...byGroup.entries()].map(([grp, list]) => (
        <p key={grp}><strong>{GROUP_KO[grp]}</strong>: {list.map((o) => o.name).join(", ")}</p>
      ))}
      {outlets.some((o) => o.excluded_at) && (
        <p className="muted small">요청으로 제외한 곳: {outlets.filter((o) => o.excluded_at).map((o) => o.name).join(", ")}</p>
      )}
      <p className="muted small">공개 구독 주소를 확인하는 대로 목록에 더합니다. 수집 목록은 저장소의 <code>rules/outlets.yaml</code>로 관리되며 변경 이력이 남습니다.
</p>
    </article>
  );
}
