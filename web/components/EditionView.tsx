import Link from "next/link";
import type { Slot } from "@/lib/editions";
import { NOTICE_KO, SECTION_KO } from "@/lib/labels";
import { correctedSeqs, getOutgoingLinks, getPosts } from "@/lib/posts";
import { kstDateLabel } from "@/lib/time";
import { AudioButton } from "./AudioButton";
import { PostArticle } from "./PostArticle";

const SECTION_ORDER = ["politics", "economy", "society", "world", "scitech", "culture", "none"];

export async function EditionView({ date, slots, editionId }: { date: string; slots: Slot[]; editionId?: number }) {
  const seqs = slots.filter((s) => s.seq).map((s) => s.seq!);
  const [posts, links, corrected] = await Promise.all([getPosts(seqs), getOutgoingLinks(seqs), correctedSeqs(seqs)]);
  const of = (slot: string) => slots.filter((s) => s.slot === slot && s.seq && posts.has(s.seq)).map((s) => posts.get(s.seq!)!);
  const sectionSlots = slots.filter((s) => s.slot === "section" && s.seq && posts.has(s.seq));
  const minutes = Math.max(1, Math.round(
    [...posts.values()].reduce((a, p) => a + (of("brief").includes(p) ? 130 : p.char_count), 0) / 550,
  ));

  const block = (label: string, items: ReturnType<typeof of>, cls = "", mode: "full" | "summary" = "full") =>
    items.length > 0 && (
      <section className={cls}>
        <h2 className="section-head">{label}</h2>
        {items.map((p) => (
          <PostArticle key={p.seq} post={p} links={links.get(p.seq)} corrected={corrected.has(p.seq)} mode={mode} />
        ))}
      </section>
    );

  return (
    <div className="edition">
      <p className="dateline">{kstDateLabel(date)} · 약 {minutes}분 분량</p>
      {slots.filter((s) => s.slot === "notice").map((s, i) => (
        <p key={i} className="notice">{NOTICE_KO[s.code ?? ""] ?? s.code}</p>
      ))}
      {block("그동안의 주요 흐름", of("catchup"))}
      {block("1면", of("front"), "front")}
      {block("오늘의 쟁점", of("issue"))}
      {SECTION_ORDER.map((sec) => {
        const items = sectionSlots.filter((s) => (s.section ?? posts.get(s.seq!)!.section) === sec);
        if (!items.length) return null;
        return (
          <section key={sec}>
            <h2 className="section-head">{SECTION_KO[sec]}</h2>
            {items.map((s) => {
              const p = posts.get(s.seq!)!;
              return (
                <div key={p.seq}>
                  {s.niche && <p className="pill">관심 주제</p>}
                  <PostArticle post={p} links={links.get(p.seq)} corrected={corrected.has(p.seq)} />
                </div>
              );
            })}
          </section>
        );
      })}
      {of("brief").length > 0 && (
        <section>
          <h2 className="section-head">단신</h2>
          <ul className="briefs">
            {of("brief").map((p) => (
              <li key={p.seq}>
                <Link href={`/p/${p.seq}`}>{p.title}</Link>
                <span>{p.summary}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {block("오늘의 배경", of("background"), "", "summary")}
      {block("교양", of("culture"))}
      <div className="actions" id="edition-end">
        <Link href={`/front/${date}`} className="button ghost">1면은 이렇게 골랐습니다</Link>
        <AudioButton />
      </div>
      <p className="muted small">
        모든 글은 AI가 여러 언론 보도를 종합해 썼습니다. 클릭 수·체류 시간·공유 수는 지면을 고르는 데 쓰지 않습니다.
        {editionId ? ` · 지면 번호 ${editionId}` : ""}
      </p>
    </div>
  );
}
