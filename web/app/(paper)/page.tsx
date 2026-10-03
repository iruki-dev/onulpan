import Link from "next/link";
import { EditionView } from "@/components/EditionView";
import { Kakao } from "@/components/Icons";
import { RefreshSoon } from "@/components/RefreshSoon";
import { Tracker } from "@/components/Tracker";
import { advanceCursor, latestEdition, latestFront, requestAssembly } from "@/lib/editions";
import { SECTION_KO } from "@/lib/labels";
import { enabledProviders } from "@/lib/oauth";
import { getPosts } from "@/lib/posts";
import { currentUser } from "@/lib/session";
import { kstDateLabel, kstToday } from "@/lib/time";

export default async function TodayPage() {
  const user = await currentUser();
  const today = kstToday();

  if (user) {
    const ed = await latestEdition(user.id, today);
    if (!ed) {
      await requestAssembly(user.id);
      return (
        <div className="page">
          <RefreshSoon />
          <section className="page-head">
            <div className="date">{kstDateLabel(today)}</div>
            <h1 className="page-title">오늘의 조간을 짜고 있어요</h1>
            <p className="page-sub">몇 초면 끝나요.</p>
          </section>
        </div>
      );
    }
    await advanceCursor(user.id, ed.as_of_seq);
    return (
      <>
        <Tracker page="edition" editionId={ed.id} />
        <EditionView date={ed.edition_date} slots={ed.slots} editionId={ed.id} />
      </>
    );
  }

  // 로그인하지 않은 독자: 소개 + 모두에게 같은 오늘 1면
  const front = await latestFront(today);
  const posts = await getPosts(front?.seqs ?? []);
  const kakao = enabledProviders().includes("kakao");
  return (
    <div className="page">
      <Tracker page="landing" />
      <section className="hero">
        <h1>아침마다 한 부,<br />다 읽으면 끝나는 뉴스</h1>
        <p>여러 언론사의 보도를 모아 사실만 정리해 드려요.</p>
      </section>
      {front && posts.size > 0 && (
        <section className="preview" aria-label="오늘 아침 1면">
          {front.seqs.filter((s) => posts.has(s)).map((s, i) => {
            const p = posts.get(s)!;
            return (
              <Link key={s} href={`/p/${s}`}>
                <span className="num tnum">{String(i + 1).padStart(2, "0")}</span>
                <span><strong>{p.title}</strong><small>{SECTION_KO[p.section]} · 언론사 {p.n_outlets}곳</small></span>
              </Link>
            );
          })}
        </section>
      )}
      <section className="values">
        <div><span className="k">10분 · 25분 · 40분</span><strong>고른 만큼만 채워요</strong><span>끝없는 피드 대신, 정한 분량을 다 읽으면 오늘은 끝.</span></div>
        <div><span className="k">출처 공개</span><strong>두 곳 이상 보도한 것만 써요</strong><span>모든 글에 참고한 기사와 원문 링크가 붙어요.</span></div>
        <div><span className="k">쟁점 정리</span><strong>입장은 나란히 보여드려요</strong><span>누가 무엇을 근거로 주장하는지, 판단은 직접.</span></div>
      </section>
      <section className="cta">
        {kakao && <a href="/auth/kakao" className="btn kakao block"><Kakao />카카오로 시작하기</a>}
        <Link href="/login" className={`btn block${kakao ? " secondary" : ""}`}>이메일로 시작하기</Link>
        <small>무료 · 광고 없음</small>
      </section>
    </div>
  );
}
