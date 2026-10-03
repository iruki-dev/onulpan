import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AudioButton } from "@/components/AudioButton";
import { PostArticle } from "@/components/PostArticle";
import { ReportForm } from "@/components/ReportForm";
import { ShareButton } from "@/components/ShareButton";
import { Tracker } from "@/components/Tracker";
import { GROUP_KO, KIND_KO } from "@/lib/labels";
import { getLater, getOutgoingLinks, getPost, getSources } from "@/lib/posts";
import { kstDateTime } from "@/lib/time";

type Props = { params: Promise<{ seq: string }> };

async function load(seqStr: string) {
  const seq = Number(seqStr);
  return Number.isInteger(seq) && seq > 0 ? getPost(seq) : null;
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
  const [links, sources, later] = await Promise.all([
    getOutgoingLinks([post.seq]), getSources([post.seq]), getLater(post.seq, post.slug),
  ]);
  const out = links.get(post.seq) ?? [];
  const src = sources.get(post.seq) ?? [];
  const related = out.filter((l) => l.rel !== "corrects");
  const corrects = out.find((l) => l.rel === "corrects");
  const report = post.verify_report as { rules?: { id: string; ok: boolean; skipped?: boolean }[]; manual?: boolean };

  return (
    <>
      <Tracker page="post" />
      {later.corrections.map((c) => (
        <p key={c.seq} className="banner banner-correction">
          이 글에는 이후 정정이 있습니다: <Link href={`/p/${c.seq}`}>{c.title}</Link>
        </p>
      ))}
      {later.newer.length > 0 && (
        <p className="banner">
          이 주제의 새 글이 있습니다: <Link href={`/p/${later.newer[0].seq}`}>{later.newer[0].title}</Link>
          {post.slug && <> · <Link href={`/w/${encodeURIComponent(post.slug)}`}>주제 전체 보기</Link></>}
        </p>
      )}
      {corrects && (
        <p className="banner banner-correction">
          이 글은 <Link href={`/p/${corrects.to_seq}`}>{corrects.to_title}</Link>의 정정입니다.
        </p>
      )}
      <PostArticle post={post} links={out} headingLevel={2} />
      <p className="meta-list">
        {KIND_KO[post.kind]} · 발행 {kstDateTime(post.created_at)} · 글 번호 {post.seq}
        {post.slug && <> · 주제 <Link href={`/w/${encodeURIComponent(post.slug)}`}>{post.slug.replaceAll("-", " ")}</Link></>}
      </p>
      <div className="actions">
        <ShareButton url={`/p/${post.seq}`} title={post.title} />
        {post.kind === "issue" && <a className="button ghost" href={`/card/${post.seq}`} target="_blank">카드 이미지</a>}
        <AudioButton seq={post.seq} />
      </div>

      {post.meta.conflicts?.length > 0 && (
        <section>
          <h3 className="section-head">언론사마다 다른 내용</h3>
          <ul>
            {post.meta.conflicts.map((c: { field: string; values: { value: string; source_id: string }[] }, i: number) => (
              <li key={i}>{c.field}: {c.values.map((v) => v.value).join(" / ")}</li>
            ))}
          </ul>
        </section>
      )}

      <section id="sources">
        <h3 className="section-head">참고한 기사 {src.length}건</h3>
        {src.length === 0 ? (
          <p className="muted small">이 글은 언론 보도를 입력으로 쓰지 않았습니다.</p>
        ) : (
          <ol className="sources">
            {src.map((s, i) => (
              <li key={i}>
                <strong>{s.outlet}</strong> <span className="muted small">({GROUP_KO[s.grp]})</span>{" "}
                <a href={s.url} rel="noopener nofollow" target="_blank">{s.title}</a>
              </li>
            ))}
          </ol>
        )}
      </section>

      {related.length > 0 && (
        <section>
          <h3 className="section-head">이어지는 글</h3>
          <ul>
            {related.map((l) => (
              <li key={`${l.to_seq}-${l.rel}`}>
                {l.slug ? <Link href={`/w/${encodeURIComponent(l.slug)}`}>{l.anchor_text ?? l.to_title}</Link> : l.to_title}{" "}
                <span className="muted small">
                  ({l.rel === "follows" ? "이전 글" : l.rel === "summarizes" ? "종합한 글" : KIND_KO[l.to_kind]} ·{" "}
                  <Link href={`/p/${l.to_seq}`}>이 글이 쓰일 당시의 버전</Link>)
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="section-head">어떻게 썼나</h3>
        <p className="small muted">
          {report.manual
            ? "편집자가 직접 썼습니다."
            : `모델 ${post.model}, 지침 ${post.prompt_version}. 게시 전 자동 검증 ${report.rules?.filter((r) => !r.skipped).length ?? 0}개 규칙을 모두 통과했습니다.`}
          {post.meta.review === "approved" && " 편집자가 게시 전에 검토했습니다."}{" "}
          <Link href="/principles">편집 원칙</Link>
        </p>
        <ReportForm seq={post.seq} />
      </section>
    </>
  );
}
