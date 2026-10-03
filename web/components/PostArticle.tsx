import Link from "next/link";
import { SECTION_KO, KIND_KO } from "@/lib/labels";
import type { Link as PostLink, Post } from "@/lib/posts";
import { AiLabel } from "./AiLabel";
import { Body } from "./Body";
import { IssueView, type IssueSections } from "./IssueView";

export function PostArticle({ post, links, corrected, mode = "full", headingLevel = 3 }: {
  post: Post;
  links?: PostLink[];
  corrected?: boolean;
  mode?: "full" | "summary";
  headingLevel?: 2 | 3;
}) {
  const H = headingLevel === 2 ? "h2" : "h3";
  return (
    <article className={`post post-${post.kind}`} id={`p${post.seq}`}>
      {corrected && (
        <p className="banner banner-correction">
          이 글에는 이후 정정이 있습니다. <Link href={`/p/${post.seq}`}>정정 보기</Link>
        </p>
      )}
      <p className="kicker">
        {post.section !== "none" && <span>{SECTION_KO[post.section]}</span>}
        {post.kind !== "fact" && <span>{KIND_KO[post.kind]}</span>}
      </p>
      <H className="post-title">
        <Link href={`/p/${post.seq}`}>{post.title}</Link>
      </H>
      {mode === "summary" ? (
        <p className="summary">{post.summary}</p>
      ) : post.kind === "issue" && post.meta.sections ? (
        <IssueView sections={post.meta.sections as IssueSections} />
      ) : (
        <Body text={post.body_md} links={links} from={post.seq} />
      )}
      <AiLabel seq={post.seq} nSources={post.n_sources ?? 0} model={post.model} promptVersion={post.prompt_version} kind={post.kind} />
    </article>
  );
}
