import Link from "next/link";
import { frontScores, type Slot } from "@/lib/editions";
import { leadImages } from "@/lib/images";
import { NOTICE_KO, SECTION_KO } from "@/lib/labels";
import { conflictsOf, correctedSeqs, getOutgoingLinks, getPosts, getSources, minutesOf, type Post } from "@/lib/posts";
import { kstDateLabel } from "@/lib/time";
import { Check, Chevron } from "./Icons";
import { EditionProgress } from "./Reading";
import { BriefCell, IssueBlock, MoreCell, Story } from "./Story";

const SECTION_ORDER = ["politics", "economy", "society", "world", "scitech", "culture", "none"];
const BRIEF_MIN = 1;

export async function EditionView({ date, slots }: { date: string; slots: Slot[]; editionId?: number }) {
  const seqs = slots.filter((s) => s.seq).map((s) => s.seq!);
  const leadSeq = slots.find((s) => s.slot === "front" && s.seq)?.seq;
  const [posts, links, sources, corrected, scores, images] = await Promise.all([
    getPosts(seqs), getOutgoingLinks(seqs), getSources(seqs), correctedSeqs(seqs), frontScores(date),
    leadImages(leadSeq ? [leadSeq] : []),
  ]);
  const of = (slot: string) => slots.filter((s) => s.slot === slot && s.seq && posts.has(s.seq)).map((s) => posts.get(s.seq!)!);
  const catchup = of("catchup"), front = of("front"), issue = of("issue"), briefs = of("brief");
  const background = of("background"), culture = of("culture");
  const sectionSlots = slots.filter((s) => s.slot === "section" && s.seq && posts.has(s.seq));
  const nicheSeqs = new Set(sectionSlots.filter((s) => s.niche).map((s) => s.seq!));
  const bySection = SECTION_ORDER.map((sec) => ({
    sec, items: sectionSlots.filter((s) => (s.section ?? posts.get(s.seq!)!.section) === sec).map((s) => posts.get(s.seq!)!),
  })).filter((g) => g.items.length);

  // 진행에 세는 글: 한 줄 단신을 뺀 모든 글
  const counted = [...catchup, ...front, ...issue, ...bySection.flatMap((g) => g.items), ...background, ...culture];
  const progressItems = counted.map((p) => ({ seq: p.seq, minutes: minutesOf(p.char_count) }));
  const totalMinutes = progressItems.reduce((a, i) => a + i.minutes, 0) + Math.ceil(briefs.length * 130 / 550);
  const notices = slots.filter((s) => s.slot === "notice").map((s) => NOTICE_KO[s.code ?? ""] ?? s.code);

  const story = (p: Post, num?: number, lead?: boolean, inSection?: boolean) => (
    <Story key={p.seq} post={p} num={num} lead={lead} inSection={inSection} image={lead ? images.get(p.seq) : undefined} links={links.get(p.seq)} conflicts={conflictsOf(p, sources.get(p.seq))}
      corrected={corrected.has(p.seq)} niche={nicheSeqs.has(p.seq)} />
  );

  const toc = [
    catchup.length && { id: "catchup", label: "그동안의 흐름", n: catchup.length },
    front.length && { id: "front", label: "1면", n: front.length },
    issue.length && { id: "issue", label: "쟁점", n: issue.length },
    ...bySection.map((g) => ({ id: g.sec, label: SECTION_KO[g.sec], n: g.items.length })),
    briefs.length && { id: "briefs", label: "단신", n: briefs.length },
    (background.length || culture.length) && { id: "more", label: "더 읽기", n: background.length + culture.length },
  ].filter(Boolean) as { id: string; label: string; n: number }[];

  const moreCells = (
    <>
      {background.map((p) => <MoreCell key={p.seq} post={p} label="오늘의 배경" />)}
      {culture.map((p) => <MoreCell key={p.seq} post={p} label={`교양 · ${minutesOf(p.char_count)}분`} />)}
    </>
  );

  return (
    <div className="edition-grid">
      <aside className="toc" aria-label="목차">
        <div><div className="date">{kstDateLabel(date)}</div><div className="title">오늘의 조간</div></div>
        <EditionProgress items={progressItems} />
        <nav>{toc.map((t) => <a key={t.id} href={`#${t.id}`}><span>{t.label}</span><span className="tnum">{t.n}</span></a>)}</nav>
      </aside>

      <div className="page">
        <section className="page-head">
          <div className="date">{kstDateLabel(date)}</div>
          <h1 className="page-title">오늘의 조간</h1>
          <div style={{ marginTop: 20 }}><EditionProgress items={progressItems} /></div>
          {notices.map((n, i) => <p key={i} className="notice-line">{n}</p>)}
        </section>
        <nav className="chips" aria-label="지면">
          {toc.map((t, i) => <a key={t.id} href={`#${t.id}`} className="chip" aria-current={i === 0 ? "true" : undefined}>{t.label}</a>)}
        </nav>

        {catchup.length > 0 && (
          <>
            <div className="band" />
            <section id="catchup" className="section">
              <h2 className="section-title">그동안의 흐름</h2>
              {catchup.map((p) => story(p))}
            </section>
          </>
        )}

        {front.length > 0 && (
          <>
            <div className="band" />
            <section id="front" className="section">
              <div className="section-head">
                <h2 className="section-title">1면</h2>
                <Link href={`/front/${date}`} className="section-link">선정 기준<Chevron /></Link>
              </div>
              {story(front[0], 1, true)}
              {front.length > 1 && <div className="front-rest">{front.slice(1).map((p, i) => story(p, i + 2))}</div>}
            </section>
          </>
        )}

        {issue.length > 0 && (
          <>
            <div className="band" />
            <section id="issue" className="section" style={{ paddingBottom: 24 }}>
              <h2 className="section-title">오늘의 쟁점</h2>
              {issue.map((p) => <IssueBlock key={p.seq} post={p} />)}
            </section>
          </>
        )}

        {bySection.map((g) => (
          <div key={g.sec}>
            <div className="band" />
            <section id={g.sec} className="section">
              <h2 className="section-title">{SECTION_KO[g.sec]}</h2>
              {g.items.map((p) => story(p, undefined, false, true))}
            </section>
          </div>
        ))}

        {briefs.length >= BRIEF_MIN && (
          <>
            <div className="band" />
            <section id="briefs" className="section">
              <h2 className="section-title">단신</h2>
              {briefs.map((p) => <BriefCell key={p.seq} post={p} />)}
            </section>
          </>
        )}

        {(background.length > 0 || culture.length > 0) && (
          <div className="only-mobile">
            <div className="band" />
            <section id="more" className="section">
              <h2 className="section-title">더 읽기</h2>
              {moreCells}
            </section>
          </div>
        )}

        <div className="band" />
        <section className="done" id="edition-end">
          <span className="check"><Check size={24} /></span>
          <strong>오늘 조간은 여기까지</strong>
          <span>내일 아침 새 지면이 옵니다</span>
          <span className="small muted">약 {totalMinutes}분 · {counted.length + briefs.length}편</span>
        </section>
      </div>

      <aside className="rail" aria-label="1면 선정과 더 읽기">
        {scores.length > 0 && (
          <section>
            <div className="section-head" style={{ minHeight: 0 }}>
              <h2>1면 선정 점수</h2>
              <Link href={`/front/${date}`} className="section-link">전체</Link>
            </div>
            {scores.map((s) => (
              <div key={s.seq} className={`score${s.picked ? " picked" : ""}`}>
                <div className="top"><span>{s.title}</span><span className="tnum">{s.score.toFixed(2)}</span></div>
                <div className="bar"><i style={{ width: `${Math.round((100 * s.score) / (scores[0].score || 1))}%` }} /></div>
              </div>
            ))}
          </section>
        )}
        {(background.length > 0 || culture.length > 0) && (
          <section><h2>더 읽기</h2>{moreCells}</section>
        )}
      </aside>
    </div>
  );
}

