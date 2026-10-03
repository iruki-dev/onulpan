import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArticleView } from "@/components/ArticleView";
import { AudioButton } from "@/components/AudioButton";
import { Back, Chevron, External } from "@/components/Icons";
import { ArticleReading, TextSizeButton } from "@/components/Reading";
import { ReportForm } from "@/components/ReportForm";
import { ShareButton } from "@/components/ShareButton";
import { Tracker } from "@/components/Tracker";
import { GROUP_KO, KIND_KO } from "@/lib/labels";
import { leadImages } from "@/lib/images";
import { conflictsOf, getLater, getOutgoingLinks, getPost, getSources, topicFlow } from "@/lib/posts";

type Props = { params: Promise<{ seq: string }> };
const GROUPS = 7;

async function load(seqStr: string) {
  const seq = Number(seqStr);
  return Number.isInteger(seq) && seq > 0 ? getPost(seq) : null;
}

function shortDate(d: Date): string {
  const k = new Date(new Date(d).toLocaleString("en-US", { timeZone: "Asia/Seoul" }));
  return `${String(k.getMonth() + 1).padStart(2, "0")}.${String(k.getDate()).padStart(2, "0")}`;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const post = await load((await params).seq);
  if (!post) return {};
  return {
    title: post.title,
    description: post.summary,
    alternates: { canonical: `/p/${post.seq}` },
    openGraph: { title: post.title, description: post.summary, type: "article",
                 images: post.kind === "issue" ? [`/card/${post.seq}`] : undefined },
  };
}

export default async function PostPage({ params }: Props) {
  const post = await load((await params).seq);
  if (!post) notFound();
  const [links, sources, later, flow, images] = await Promise.all([
    getOutgoingLinks([post.seq]), getSources([post.seq]), getLater(post.seq, post.slug), topicFlow(post.slug), leadImages([post.seq]),
  ]);
  const src = sources.get(post.seq) ?? [];
  const groups = new Set(src.map((s) => s.grp));
  const outletOf = new Map(src.map((s) => [`r_${s.raw_article_id}`, s.outlet]));
  const merged = Math.max(0, (post.n_outlets ?? 0) - new Set(src.map((s) => s.outlet)).size);
  const report = post.verify_report as { rules?: { id: string; ok: boolean; skipped?: boolean }[]; manual?: boolean };
  const checked = report.rules?.filter((r) => !r.skipped).length ?? 0;

  return (
    <>
      <Tracker page="post" />
      <div className="page" style={{ display: "flex", justifyContent: "space-between", padding: "0 4px" }}>
        <Link href="/" className="icon-btn" aria-label="오늘의 조간"><Back /></Link>
        <div style={{ display: "flex" }}>
          <TextSizeButton />
          <AudioButton seq={post.seq} />
          <ShareButton url={`/p/${post.seq}`} title={post.title} />
        </div>
      </div>
      <ArticleReading seq={post.seq} />

      <div className="page">
        <ArticleView post={post} links={links.get(post.seq)} conflicts={conflictsOf(post, src)} later={later} outletOf={outletOf}
          image={images.get(post.seq)} />
        {post.kind === "issue" && (
          <div className="btn-row" style={{ padding: "24px 0 8px" }}>
            <a href={`/card/${post.seq}`} className="btn secondary" target="_blank" data-track="card_view">카드로 저장</a>
            <ShareButton url={`/p/${post.seq}`} title={post.title} variant="button" />
          </div>
        )}

        <div className="band" style={{ marginTop: 36 }} />
        <section id="sources" className="section">
          <div className="section-head">
            <h2 className="section-title">참고한 기사 {src.length}</h2>
            {src.length > 0 && (
              <span className="form-meter" aria-label={`언론 형태 ${GROUPS}개 중 ${groups.size}개`}>
                언론 형태 {groups.size}/{GROUPS}
                <span>{Array.from({ length: GROUPS }, (_, i) => <i key={i} className={i < groups.size ? "on" : ""} />)}</span>
              </span>
            )}
          </div>
          {src.length === 0 && <p className="footnote">언론 보도를 입력으로 쓰지 않은 글입니다.</p>}
          {src.map((s, i) => (
            <a key={i} href={s.url} rel="noopener nofollow" target="_blank" className="cell">
              <span className="thumb">{s.outlet.slice(0, 1)}</span>
              <span className="body"><span className="over">{s.outlet} · {GROUP_KO[s.grp]}</span><span className="main" style={{ fontSize: 15, fontWeight: 500 }}>{s.title}</span></span>
              <span className="chev"><External /></span>
            </a>
          ))}
          {merged > 0 && <p className="footnote">같은 기사를 옮겨 실은 {merged}곳은 하나로 셌습니다.</p>}
        </section>

        {flow.length > 1 && (
          <>
            <div className="band" style={{ marginTop: 20 }} />
            <section className="section timeline">
              <div className="section-head">
                <h2 className="section-title">이 주제의 흐름</h2>
                {post.slug && <Link href={`/w/${encodeURIComponent(post.slug)}`} className="section-link">전체<Chevron /></Link>}
              </div>
              {flow.map((f) => (
                <Link key={f.seq} href={`/p/${f.seq}`} className="cell" aria-current={f.seq === post.seq ? "page" : undefined}>
                  <span className="date tnum">{shortDate(f.created_at)}</span>
                  <span className="body">
                    <span className={`main${f.seq === post.seq ? "" : " plain"}`} style={{ fontSize: 15 }}>{f.title}</span>
                    <span className="over">{f.seq === post.seq ? "지금 읽는 글" : KIND_KO[f.kind]}</span>
                  </span>
                </Link>
              ))}
            </section>
          </>
        )}

        <div className="band" style={{ marginTop: 12 }} />
        <section style={{ padding: "8px 0 40px" }}>
          <details className="cell-details">
            <summary className="cell"><span className="body"><span className="main plain">작성 방식과 검증</span></span><span className="chev"><Chevron size={18} /></span></summary>
            <div className="kv">
              {report.manual ? (
                <div><span>작성</span><b>편집자</b></div>
              ) : (
                <>
                  <div><span>모델</span><b>{post.model}</b></div>
                  <div><span>지침</span><b>{post.prompt_version}</b></div>
                  <div><span>자동 검증</span><b>{checked}개 규칙 통과</b></div>
                  {post.meta.review === "approved" && <div><span>편집자 검토</span><b>게시 전 확인</b></div>}
                </>
              )}
              <div><span>발행 뒤 수정</span><b>하지 않음 · 정정은 새 글로</b></div>
              <Link href="/principles" className="text-link" style={{ marginTop: 4 }}>편집 원칙<Chevron size={15} /></Link>
            </div>
          </details>
          <ReportForm seq={post.seq} />
        </section>
      </div>
    </>
  );
}
