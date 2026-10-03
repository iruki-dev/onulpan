import { cardSvg } from "@/lib/card";
import { getPost } from "@/lib/posts";
import { siteUrl } from "@/lib/session";
import { kstToday } from "@/lib/time";

// 쟁점 카드 이미지: 서버 렌더링 SVG → PNG (resvg). ?format=svg면 SVG 그대로.
export async function GET(req: Request, ctx: { params: Promise<{ seq: string }> }) {
  const seq = Number((await ctx.params).seq);
  const post = Number.isInteger(seq) ? await getPost(seq) : null;
  if (!post || post.kind !== "issue" || !post.meta.sections) return new Response("not found", { status: 404 });
  const svg = cardSvg({
    title: post.title,
    question: post.meta.sections.question,
    positions: post.meta.sections.positions,
    date: kstToday(new Date(post.created_at)),
    url: `${siteUrl().replace(/^https?:\/\//, "")}/p/${post.seq}`,
  });
  const headers = { "cache-control": "public, max-age=86400, immutable" };
  if (new URL(req.url).searchParams.get("format") === "svg") {
    return new Response(svg, { headers: { ...headers, "content-type": "image/svg+xml; charset=utf-8" } });
  }
  try {
    const { Resvg } = await import("@resvg/resvg-js");
    const png = new Resvg(svg, { font: { loadSystemFonts: true, defaultFontFamily: "Noto Sans CJK KR" } }).render().asPng();
    return new Response(new Uint8Array(png), { headers: { ...headers, "content-type": "image/png" } });
  } catch {
    return new Response(svg, { headers: { ...headers, "content-type": "image/svg+xml; charset=utf-8" } });
  }
}
