import Link from "next/link";
import { SECTION_KO } from "@/lib/labels";
import { type Conflict, type Link as PostLink, type Post, minutesOf } from "@/lib/posts";
import { Paragraphs, paragraphCount } from "./Body";
import { Book, Chevron, Drop } from "./Icons";
import type { IssueSections } from "./IssueView";
import { ReadMark, StoryBody } from "./Reading";

export function ConflictCell({ conflicts }: { conflicts: Conflict[] }) {
  return (
    <>
      {conflicts.map((c, i) => (
        <div key={i} className="conflict">
          <span className="field">보도마다 다른 숫자 · {c.field}</span>
          {c.rows.map((r, j) => (
            <div key={j} className="row"><span className="val">{r.value}</span><span className="who">{r.who}</span></div>
          ))}
        </div>
      ))}
    </>
  );
}

/** 조간 속 기사: 번호·분야, 제목, 첫 문단, (펼치면) 나머지 */
export function Story({ post, num, lead, links, conflicts, corrected, niche, inSection }: {
  post: Post; num?: number; lead?: boolean; links?: PostLink[]; conflicts?: Conflict[]; corrected?: boolean; niche?: boolean;
  /** 분야 머리 아래에서는 분야 이름을 되풀이하지 않는다 */
  inSection?: boolean;
}) {
  const minutes = minutesOf(post.char_count);
  const more = paragraphCount(post.body_md) > 1;
  return (
    <article className="story" id={`p${post.seq}`} data-story={post.seq}>
      <div className="kicker">
        {num !== undefined && <span className="num">{String(num).padStart(2, "0")}</span>}
        {post.section !== "none" && !inSection && <span className="sec">{SECTION_KO[post.section]}</span>}
        {niche && <span className="tag">관심 주제</span>}
        <ReadMark seq={post.seq} />
      </div>
      {corrected && <Link href={`/p/${post.seq}`} className="text-link ink">이 글에는 정정이 있어요<Chevron size={15} /></Link>}
      <h3 className={`story-title${lead ? " lead" : ""}`}><Link href={`/p/${post.seq}`}>{post.title}</Link></h3>
      <StoryBody
        seq={post.seq}
        minutes={minutes}
        href={`/p/${post.seq}`}
        first={<Paragraphs text={post.body_md} links={links} from={post.seq} end={1} />}
        rest={more ? <Paragraphs text={post.body_md} links={links} from={post.seq} start={1} /> : undefined}
        extra={conflicts && conflicts.length > 0 ? <ConflictCell conflicts={conflicts} /> : undefined}
        meta={<><span>언론사 {post.n_outlets}곳</span><span>·</span><span>{minutes}분</span></>}
      />
    </article>
  );
}

/** 조간 속 쟁점: 질문을 제목으로, 입장을 가는 선으로 나란히 */
export function IssueBlock({ post }: { post: Post }) {
  const sec = post.meta.sections as IssueSections | undefined;
  if (!sec) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 8 }}>
      <h3 className="issue-title"><Link href={`/p/${post.seq}`}>{sec.question || post.title}</Link></h3>
      <div className="split" style={{ gridTemplateColumns: `repeat(${Math.min(sec.positions.length, 3)}, minmax(0, 1fr))` }}>
        {sec.positions.map((p, i) => (
          <div key={i}><strong>{p.holder}</strong><span>{p.claim}</span></div>
        ))}
      </div>
      <Link href={`/p/${post.seq}`} className="btn secondary block" style={{ minHeight: 52, fontSize: 16 }}>근거와 남은 질문 보기</Link>
    </div>
  );
}

export function CompactStory({ post }: { post: Post }) {
  return (
    <Link href={`/p/${post.seq}`} className="compact">
      <strong>{post.title}</strong>
      <span className="sum">{post.summary}</span>
      <span className="story-meta">언론사 {post.n_outlets}곳 · {minutesOf(post.char_count)}분</span>
    </Link>
  );
}

export function MoreCell({ post, label }: { post: Post; label: string }) {
  const href = post.slug && post.kind === "explainer" ? `/w/${encodeURIComponent(post.slug)}` : `/p/${post.seq}`;
  return (
    <Link href={href} className="cell">
      <span className="thumb">{post.kind === "culture" ? <Drop /> : <Book />}</span>
      <span className="body"><span className="over">{label}</span><span className="main">{post.title}</span></span>
      <Chevron size={18} className="chev" />
    </Link>
  );
}

export function BriefCell({ post }: { post: Post }) {
  return (
    <Link href={`/p/${post.seq}`} className="cell">
      <span className="body"><span className="main">{post.title}</span><span className="under">{post.summary}</span></span>
      <Chevron size={18} className="chev" />
    </Link>
  );
}
