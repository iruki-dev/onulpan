import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PostArticle } from "@/components/PostArticle";
import { Tracker } from "@/components/Tracker";
import { q } from "@/lib/db";
import { KIND_KO } from "@/lib/labels";
import { getOutgoingLinks, getPost, slugInfo } from "@/lib/posts";
import { kstDateTime } from "@/lib/time";

type Props = { params: Promise<{ slug: string }> };

async function load(raw: string) {
  const slug = decodeURIComponent(raw);
  const info = await slugInfo(slug);
  if (!info) return null;
  // slug의 현재 글: 종합·해설의 최신, 없으면 가장 최근 글
  const current = await q<{ seq: number }>(
    `SELECT seq FROM posts WHERE slug = $1 ORDER BY (kind IN ('synthesis','explainer')) DESC, seq DESC LIMIT 1`,
    [slug],
  );
  const history = await q<{ seq: number; kind: string; title: string; created_at: Date }>(
    "SELECT seq, kind::text AS kind, title, created_at FROM posts WHERE slug = $1 ORDER BY seq DESC LIMIT 100",
    [slug],
  );
  const backlinks = await q<{ seq: number; title: string }>(
    `SELECT DISTINCT p.seq, p.title FROM post_links l JOIN posts t ON t.seq = l.to_seq JOIN posts p ON p.seq = l.from_seq
     WHERE t.slug = $1 AND p.slug IS DISTINCT FROM $1 ORDER BY p.seq DESC LIMIT 20`,
    [slug],
  );
  const post = current[0] ? await getPost(current[0].seq) : null;
  return { info, post, history, backlinks };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const d = await load((await params).slug);
  if (!d) return {};
  return {
    title: d.info.display_name,
    description: d.post?.summary,
    alternates: { canonical: `/w/${encodeURIComponent(d.info.slug)}` },
  };
}

export default async function WikiPage({ params }: Props) {
  const d = await load((await params).slug);
  if (!d) notFound();
  const links = d.post ? await getOutgoingLinks([d.post.seq]) : new Map();
  return (
    <>
      <Tracker page="wiki" />
      <p className="dateline">주제</p>
      <h1>{d.info.display_name}</h1>
      {d.post ? (
        <>
          <p className="muted small">지금 이 주제의 최신 글입니다. 오늘판의 글은 고치지 않고, 새 글로 이어 씁니다.</p>
          <PostArticle post={d.post} links={links.get(d.post.seq)} headingLevel={2} />
        </>
      ) : (
        <p className="muted">아직 글이 없습니다.</p>
      )}
      <section>
        <h2 className="section-head">이 주제의 모든 글 ({d.history.length})</h2>
        <ul>
          {d.history.map((h) => (
            <li key={h.seq}>
              <Link href={`/p/${h.seq}`}>{h.title}</Link> <span className="muted small">{KIND_KO[h.kind]} · {kstDateTime(h.created_at)}</span>
            </li>
          ))}
        </ul>
      </section>
      {d.backlinks.length > 0 && (
        <section>
          <h2 className="section-head">이 주제를 언급한 글</h2>
          <ul>{d.backlinks.map((b) => <li key={b.seq}><Link href={`/p/${b.seq}`}>{b.title}</Link></li>)}</ul>
        </section>
      )}
    </>
  );
}
