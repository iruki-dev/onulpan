import Link from "next/link";
import { EditionView } from "@/components/EditionView";
import { PostArticle } from "@/components/PostArticle";
import { RefreshSoon } from "@/components/RefreshSoon";
import { Tracker } from "@/components/Tracker";
import { q } from "@/lib/db";
import { advanceCursor, latestEdition, latestFront, requestAssembly } from "@/lib/editions";
import { correctedSeqs, getOutgoingLinks, getPosts } from "@/lib/posts";
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
        <>
          <RefreshSoon />
          <p className="dateline">{kstDateLabel(today)}</p>
          <h1>오늘의 조간을 준비하고 있습니다</h1>
          <p className="muted">설정한 분량과 관심 분야에 맞춰 지면을 짜는 중입니다. 몇 초면 끝납니다.</p>
        </>
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

  // 로그인하지 않은 독자: 모두에게 같은 1면과 오늘의 쟁점
  const front = await latestFront(today);
  const seqs = front ? [...front.seqs, ...(front.issue_seq ? [front.issue_seq] : [])] : [];
  const [posts, links, corrected] = await Promise.all([getPosts(seqs), getOutgoingLinks(seqs), correctedSeqs(seqs)]);
  const recent = await q<{ seq: number; title: string; kind: string; slug: string | null }>(
    `SELECT DISTINCT ON (slug) seq, title, kind::text AS kind, slug FROM posts
     WHERE kind IN ('synthesis','explainer') ORDER BY slug, seq DESC LIMIT 12`,
  );
  return (
    <>
      <Tracker page="public_front" />
      <p className="dateline">{kstDateLabel(front?.edition_date ?? today)} · 모든 독자에게 같은 1면</p>
      {front ? (
        <>
          <section className="front">
            <h2 className="section-head">1면</h2>
            {front.seqs.filter((s) => posts.has(s)).map((s) => (
              <PostArticle key={s} post={posts.get(s)!} links={links.get(s)} corrected={corrected.has(s)} />
            ))}
          </section>
          {front.issue_seq && posts.has(front.issue_seq) && (
            <section>
              <h2 className="section-head">오늘의 쟁점</h2>
              <PostArticle post={posts.get(front.issue_seq)!} links={links.get(front.issue_seq)} />
            </section>
          )}
          <p><Link href={`/front/${front.edition_date}`}>1면은 이렇게 골랐습니다 →</Link></p>
        </>
      ) : (
        <p className="muted">아직 발행된 1면이 없습니다.</p>
      )}
      <div className="cta">
        <h2 style={{ marginTop: 0 }}>나만의 아침 조간</h2>
        <p>10분·25분·40분 중 읽을 분량을 고르면, 1면 뒤로 관심 분야의 소식을 그만큼만 채워 매일 아침 이메일로 보내드립니다.</p>
        <Link href="/login" className="button">무료로 받아보기</Link>
      </div>
      {recent.length > 0 && (
        <section>
          <h2 className="section-head">위키: 지금 이 주제는</h2>
          <ul>
            {recent.map((r) => (
              <li key={r.seq}><Link href={r.slug ? `/w/${encodeURIComponent(r.slug)}` : `/p/${r.seq}`}>{r.title}</Link></li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
