import { NextResponse } from "next/server";
import { one } from "@/lib/db";

// 본문 용어 미리보기: 링크된 글의 주제(slug)에서 지금의 해설·종합 글을 돌려준다
export async function GET(_req: Request, ctx: { params: Promise<{ seq: string }> }) {
  const seq = Number((await ctx.params).seq);
  if (!Number.isInteger(seq)) return NextResponse.json({}, { status: 400 });
  const linked = await one<{ slug: string | null }>("SELECT slug FROM posts WHERE seq = $1", [seq]);
  if (!linked) return NextResponse.json({}, { status: 404 });
  const post = linked.slug
    ? await one<{ seq: number; kind: string; title: string; summary: string; slug: string }>(
        `SELECT seq, kind::text AS kind, title, summary, slug FROM posts WHERE slug = $1
         ORDER BY (kind = 'explainer') DESC, (kind = 'synthesis') DESC, seq DESC LIMIT 1`,
        [linked.slug],
      )
    : await one<{ seq: number; kind: string; title: string; summary: string; slug: null }>(
        "SELECT seq, kind::text AS kind, title, summary, slug FROM posts WHERE seq = $1", [seq],
      );
  const name = linked.slug
    ? (await one<{ display_name: string }>("SELECT display_name FROM slugs WHERE slug = $1", [linked.slug]))?.display_name
    : null;
  return NextResponse.json(
    {
      kind: post!.kind,
      name: name ?? post!.title,
      summary: post!.summary,
      href: post!.slug ? `/w/${encodeURIComponent(post!.slug)}` : `/p/${post!.seq}`,
    },
    { headers: { "cache-control": "public, max-age=300" } },
  );
}
