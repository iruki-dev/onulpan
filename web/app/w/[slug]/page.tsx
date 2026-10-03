import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArticleView } from "@/components/ArticleView";
import { Chevron } from "@/components/Icons";
import { Tracker } from "@/components/Tracker";
import { q } from "@/lib/db";
import { KIND_KO } from "@/lib/labels";
import { leadImages } from "@/lib/images";
import { getOutgoingLinks, getPost, slugInfo } from "@/lib/posts";
import { kstDateTime } from "@/lib/time";

type Props = { params: Promise<{ slug: string }> };

async function load(raw: string) {
  const slug = decodeURIComponent(raw);
  const info = await slugInfo(slug);
  if (!info) return null;
  // 주제의 지금 글: 해설·종합의 최신, 없으면 가장 최근 글
  const current = await q<{ seq: number }>(
    "SELECT seq FROM posts WHERE slug = $1 ORDER BY (kind IN ('synthesis','explainer')) DESC, seq DESC LIMIT 1", [slug],
  );
  const history = await q<{ seq: number; kind: string; title: string; created_at: Date }>(
    "SELECT seq, kind::text AS kind, title, created_at FROM posts WHERE slug = $1 ORDER BY seq DESC LIMIT 100", [slug],
  );
  const backlinks = await q<{ seq: number; title: string }>(
    `SELECT DISTINCT p.seq, p.title FROM post_links l JOIN posts t ON t.seq = l.to_seq JOIN posts p ON p.seq = l.from_seq
     WHERE t.slug = $1 AND p.slug IS DISTINCT FROM $1 ORDER BY p.seq DESC LIMIT 20`, [slug],
  );
  const post = current[0] ? await getPost(current[0].seq) : null;
  return { info, post, history, backlinks };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const d = await load((await params).slug);
  if (!d) return {};
  return { title: d.info.display_name, description: d.post?.summary, alternates: { canonical: `/w/${encodeURIComponent(d.info.slug)}` } };
}

export default async function WikiPage({ params }: Props) {
  const d = await load((await params).slug);
  if (!d) notFound();
  const links = d.post ? await getOutgoingLinks([d.post.seq]) : new Map();
  const images = d.post ? await leadImages([d.post.seq]) : new Map();
  return (
    <div className="page">
      <Tracker page="wiki" />
      <section className="page-head" style={{ paddingBottom: 0 }}>
        <div className="date">주제</div>
        <h1 className="page-title">{d.info.display_name}</h1>
      </section>
      {d.post && <ArticleView post={d.post} links={links.get(d.post.seq)} image={images.get(d.post.seq)} />}
      <div className="band" style={{ marginTop: 36 }} />
      <section className="section">
        <h2 className="section-title">이 주제의 글 {d.history.length}</h2>
        {d.history.map((h) => (
          <Link key={h.seq} href={`/p/${h.seq}`} className="cell">
            <span className="body"><span className="main plain">{h.title}</span><span className="over">{KIND_KO[h.kind]} · {kstDateTime(h.created_at)}</span></span>
            <Chevron size={18} className="chev" />
          </Link>
        ))}
      </section>
      {d.backlinks.length > 0 && (
        <>
          <div className="band" />
          <section className="section" style={{ paddingBottom: 32 }}>
            <h2 className="section-title">이 주제를 언급한 글</h2>
            {d.backlinks.map((b) => (
              <Link key={b.seq} href={`/p/${b.seq}`} className="cell">
                <span className="body"><span className="main plain">{b.title}</span></span><Chevron size={18} className="chev" />
              </Link>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
