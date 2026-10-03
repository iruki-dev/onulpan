import "server-only";
import { one, q } from "./db";

export type Post = {
  seq: number;
  id: string;
  kind: string;
  section: string;
  slug: string | null;
  title: string;
  summary: string;
  body_md: string;
  char_count: number;
  meta: Record<string, any>;
  importance: number;
  model: string;
  prompt_version: string;
  verify_report: Record<string, any>;
  created_at: Date;
  n_sources?: number;
  n_outlets?: number;
};

export type Source = { post_seq: number; raw_article_id: number; outlet: string; grp: string; url: string; title: string };
export type Link = { from_seq: number; to_seq: number; rel: string; anchor_text: string | null; slug: string | null; to_title: string; to_kind: string };

const COLS = `p.seq, p.id, p.kind::text AS kind, p.section::text AS section, p.slug, p.title, p.summary, p.body_md,
  p.char_count, p.meta, p.importance, p.model, p.prompt_version, p.verify_report, p.created_at,
  (SELECT count(*) FROM post_sources s WHERE s.post_seq = p.seq) AS n_sources,
  COALESCE((p.meta->'cluster'->>'n_outlets')::int,
           (SELECT count(DISTINCT outlet_id) FROM post_sources s WHERE s.post_seq = p.seq)) AS n_outlets`;

export async function getPost(seq: number): Promise<Post | null> {
  return one<Post>(`SELECT ${COLS} FROM posts p WHERE p.seq = $1`, [seq]);
}

export async function getPosts(seqs: number[]): Promise<Map<number, Post>> {
  if (!seqs.length) return new Map();
  const rows = await q<Post>(`SELECT ${COLS} FROM posts p WHERE p.seq = ANY($1::bigint[])`, [seqs]);
  return new Map(rows.map((r) => [r.seq, r]));
}

export async function getSources(seqs: number[]): Promise<Map<number, Source[]>> {
  const out = new Map<number, Source[]>();
  if (!seqs.length) return out;
  const rows = await q<Source>(
    `SELECT s.post_seq, s.raw_article_id, o.name AS outlet, o.grp::text AS grp, s.url, s.title
     FROM post_sources s JOIN outlets o ON o.id = s.outlet_id
     WHERE s.post_seq = ANY($1::bigint[]) ORDER BY o.name, s.raw_article_id`,
    [seqs],
  );
  for (const r of rows) out.set(r.post_seq, [...(out.get(r.post_seq) ?? []), r]);
  return out;
}

export async function getOutgoingLinks(seqs: number[]): Promise<Map<number, Link[]>> {
  const out = new Map<number, Link[]>();
  if (!seqs.length) return out;
  const rows = await q<Link>(
    `SELECT l.from_seq, l.to_seq, l.rel::text AS rel, l.anchor_text, t.slug, t.title AS to_title, t.kind::text AS to_kind
     FROM post_links l JOIN posts t ON t.seq = l.to_seq WHERE l.from_seq = ANY($1::bigint[]) ORDER BY l.to_seq`,
    [seqs],
  );
  for (const r of rows) out.set(r.from_seq, [...(out.get(r.from_seq) ?? []), r]);
  return out;
}

export type Later = { seq: number; kind: string; rel: string; title: string; created_at: Date };

/** 이 글 이후에 나온 글 (정정·후속 표시용): 역참조 + 같은 slug의 더 새 글 */
export async function getLater(seq: number, slug: string | null): Promise<{ corrections: Later[]; newer: Later[] }> {
  const corrections = await q<Later>(
    `SELECT p.seq, p.kind::text AS kind, l.rel::text AS rel, p.title, p.created_at
     FROM post_links l JOIN posts p ON p.seq = l.from_seq WHERE l.to_seq = $1 AND l.rel = 'corrects' ORDER BY p.seq`,
    [seq],
  );
  const newer = slug
    ? await q<Later>(
        `SELECT seq, kind::text AS kind, 'newer' AS rel, title, created_at FROM posts
         WHERE slug = $1 AND seq > $2 AND kind <> 'correction' ORDER BY seq DESC LIMIT 5`,
        [slug, seq],
      )
    : [];
  return { corrections, newer };
}

export async function correctedSeqs(seqs: number[]): Promise<Set<number>> {
  if (!seqs.length) return new Set();
  const rows = await q<{ to_seq: number }>(
    "SELECT DISTINCT to_seq FROM post_links WHERE rel = 'corrects' AND to_seq = ANY($1::bigint[])",
    [seqs],
  );
  return new Set(rows.map((r) => r.to_seq));
}

export async function slugInfo(slug: string) {
  return one<{ slug: string; display_name: string; created_at: Date }>("SELECT * FROM slugs WHERE slug = $1", [slug]);
}

/** 읽는 시간(분): 분당 550자 */
export function minutesOf(chars: number): number {
  return Math.max(1, Math.round(chars / 550));
}

export type Conflict = { field: string; rows: { value: string; who: string }[] };

/** 생성 출력의 conflicts(source_id = r_<원문 id>)를 언론사 이름으로 바꾼다 */
export function conflictsOf(post: Post, sources: Source[] | undefined): Conflict[] {
  const outletOf = new Map((sources ?? []).map((s) => [`r_${s.raw_article_id}`, s.outlet]));
  const list = (post.meta.conflicts ?? []) as { field: string; values: { value: string; source_id: string }[] }[];
  return list.map((c) => {
    const byValue = new Map<string, string[]>();
    for (const v of c.values) byValue.set(v.value, [...(byValue.get(v.value) ?? []), outletOf.get(v.source_id) ?? "출처"]);
    return { field: c.field, rows: [...byValue.entries()].map(([value, who]) => ({ value, who: [...new Set(who)].join(" · ") })) };
  });
}

export type FlowItem = { seq: number; kind: string; title: string; created_at: Date };

export async function topicFlow(slug: string | null, limit = 6): Promise<FlowItem[]> {
  if (!slug) return [];
  return q<FlowItem>(
    "SELECT seq, kind::text AS kind, title, created_at FROM posts WHERE slug = $1 ORDER BY seq DESC LIMIT $2",
    [slug, limit],
  );
}
