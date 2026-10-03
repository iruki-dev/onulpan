import Link from "next/link";
import { type Anchor, linkify, paragraphs } from "@/lib/linkify";
import type { Link as PostLink } from "@/lib/posts";

export function anchorsFrom(links: PostLink[] | undefined): Anchor[] {
  return (links ?? [])
    .filter((l) => l.anchor_text)
    .map((l) => ({
      anchor: l.anchor_text!,
      href: l.slug ? `/w/${encodeURIComponent(l.slug)}` : `/p/${l.to_seq}`,
      title: l.to_title,
      toSeq: l.to_seq,
    }));
}

/** 본문 문단. 용어 링크는 글 전체 기준으로 처음 한 번만 걸고, start~end 문단만 그린다. */
export function Paragraphs({ text, links, from, start = 0, end }: {
  text: string; links?: PostLink[]; from: number; start?: number; end?: number;
}) {
  const paras = linkify(paragraphs(text), anchorsFrom(links)).slice(start, end);
  return (
    <>
      {paras.map((segs, i) => (
        <p key={start + i}>
          {segs.map((s, j) =>
            s.href ? (
              <Link key={j} href={s.href} className="term" data-track="link_click" data-from={from} data-to={s.toSeq}>{s.text}</Link>
            ) : (
              <span key={j}>{s.text}</span>
            ),
          )}
        </p>
      ))}
    </>
  );
}

export function paragraphCount(text: string): number {
  return paragraphs(text).length;
}
