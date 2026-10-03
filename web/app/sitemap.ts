import type { MetadataRoute } from "next";
import { q } from "@/lib/db";

export const dynamic = "force-dynamic";

// 공개 해설·종합 페이지 SEO: 위키 주제와 글 페이지
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = (process.env.SITE_URL ?? "http://localhost:3000").replace(/\/$/, "");
  const wiki = await q<{ slug: string; at: Date }>(
    `SELECT slug, max(created_at) AS at FROM posts WHERE slug IS NOT NULL AND kind IN ('synthesis','explainer','issue')
     GROUP BY slug ORDER BY max(created_at) DESC LIMIT 5000`,
  );
  const posts = await q<{ seq: number; created_at: Date }>(
    "SELECT seq, created_at FROM posts ORDER BY seq DESC LIMIT 20000",
  );
  return [
    { url: `${base}/`, changeFrequency: "daily", priority: 1 },
    { url: `${base}/principles`, changeFrequency: "monthly" },
    { url: `${base}/issues/weekly`, changeFrequency: "daily" },
    ...wiki.map((w) => ({ url: `${base}/w/${encodeURIComponent(w.slug)}`, lastModified: w.at, changeFrequency: "daily" as const, priority: 0.8 })),
    ...posts.map((p) => ({ url: `${base}/p/${p.seq}`, lastModified: p.created_at, changeFrequency: "never" as const, priority: 0.5 })),
  ];
}
