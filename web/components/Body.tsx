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

export function Body({ text, links, from }: { text: string; links?: PostLink[]; from: number }) {
  const paras = linkify(paragraphs(text), anchorsFrom(links));
  return (
    <div className="body">
      {paras.map((segs, i) => (
        <p key={i}>
          {segs.map((s, j) =>
            s.href ? (
              <Link key={j} href={s.href} title={s.title} className="term" data-track="link_click" data-from={from} data-to={s.toSeq}>
                {s.text}
              </Link>
            ) : (
              <span key={j}>{s.text}</span>
            ),
          )}
        </p>
      ))}
    </div>
  );
}
