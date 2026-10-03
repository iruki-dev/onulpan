import Link from "next/link";
import { KIND_KO, SECTION_KO } from "@/lib/labels";
import type { Conflict, Later, Link as PostLink, Post } from "@/lib/posts";
import { kstDateTime } from "@/lib/time";
import { Paragraphs } from "./Body";
import { Chevron } from "./Icons";
import { IssueView, type IssueSections } from "./IssueView";
import { ConflictCell } from "./Story";

/** 글 머리(분야, 정정·후속 링크, 제목, 작성자 줄)와 본문 */
export function ArticleView({ post, links, conflicts, later, outletOf }: {
  post: Post; links?: PostLink[]; conflicts?: Conflict[];
  later?: { corrections: Later[]; newer: Later[] }; outletOf?: Map<string, string>;
}) {
  const sec = post.kind === "issue" ? (post.meta.sections as IssueSections | undefined) : undefined;
  const kicker = post.kind === "fact" ? SECTION_KO[post.section]
    : [KIND_KO[post.kind], post.section !== "none" && post.kind !== "culture" ? SECTION_KO[post.section] : null].filter(Boolean).join(" · ");
  const correctsLink = (links ?? []).find((l) => l.rel === "corrects");
  return (
    <article style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 20 }}>
      {later?.corrections.map((c) => (
        <Link key={c.seq} href={`/p/${c.seq}`} className="text-link ink">이 글에는 정정이 있어요<Chevron size={15} /></Link>
      ))}
      {later && later.newer.length > 0 && (
        <Link href={`/p/${later.newer[0].seq}`} className="text-link">이 주제의 새 글이 있어요<Chevron size={15} /></Link>
      )}
      {correctsLink && (
        <Link href={`/p/${correctsLink.to_seq}`} className="text-link ink">정정한 글: {correctsLink.to_title}<Chevron size={15} /></Link>
      )}
      <span style={{ fontSize: 14, fontWeight: 600, color: "var(--accent)" }}>{kicker}</span>
      <h1 className="article-title">{sec?.question || post.title}</h1>
      <div className="byline">
        <span className="mark">오</span>
        <span style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <span className="who">
            {post.kind === "correction" ? "오늘판 편집자" : <>오늘판 · {post.n_sources ? <a href="#sources">보도 {post.n_sources}건 종합</a> : "AI 작성"}</>}
          </span>
          <span className="when">{kstDateTime(post.created_at)}</span>
        </span>
      </div>
      {sec ? (
        <IssueView sections={sec} outletOf={outletOf} />
      ) : (
        <div className="prose article" style={{ paddingTop: 6, gap: 20 }}>
          <Paragraphs text={post.body_md} links={links} from={post.seq} />
        </div>
      )}
      {conflicts && conflicts.length > 0 && <ConflictCell conflicts={conflicts} />}
    </article>
  );
}
