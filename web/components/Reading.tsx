"use client";
import { useCallback, useEffect, useState } from "react";
import { Check, Chevron } from "./Icons";

// 조간 읽기 진행: 펼쳐 읽었거나 글 페이지를 연 기사를 ‘읽음’으로 센다 (이 기기에만 저장)
const KEY = "op_read_seqs";

function load(): Set<number> {
  try {
    return new Set(JSON.parse(localStorage.getItem(KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}
function save(s: Set<number>) {
  try {
    localStorage.setItem(KEY, JSON.stringify([...s].slice(-500)));
  } catch {}
}
export function markRead(seq: number) {
  const s = load();
  if (!s.has(seq)) {
    s.add(seq);
    save(s);
    window.dispatchEvent(new CustomEvent("op:read"));
  }
}

export function useReadSet() {
  const [read, setRead] = useState<Set<number>>(new Set());
  useEffect(() => {
    const sync = () => setRead(load());
    sync();
    window.addEventListener("op:read", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("op:read", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return read;
}

/** 조간 머리의 진행 막대: n칸, 남은 분 */
export function EditionProgress({ items }: { items: { seq: number; minutes: number }[] }) {
  const read = useReadSet();
  const done = items.filter((i) => read.has(i.seq));
  const left = items.filter((i) => !read.has(i.seq)).reduce((a, i) => a + i.minutes, 0);
  return (
    <div className="progress" aria-label={`${items.length}편 중 ${done.length}편 읽음`}>
      <div className="segs" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
        {items.map((i) => <span key={i.seq} className={`seg${read.has(i.seq) ? " on" : ""}`} />)}
      </div>
      <span className="label tnum">{done.length === items.length ? "다 읽었어요" : `${done.length}/${items.length} · ${left}분 남음`}</span>
    </div>
  );
}

/** 기사 머리의 ‘읽음’ 표시 */
export function ReadMark({ seq }: { seq: number }) {
  const read = useReadSet();
  if (!read.has(seq)) return null;
  return <span className="read" style={{ display: "inline-flex" }}><Check />읽음</span>;
}

/** 첫 문단 + ‘이어 읽기’: 지면 안에서 펼쳐 끝까지 읽는다 */
export function StoryBody({ seq, minutes, first, rest, extra, meta, href }: {
  seq: number; minutes: number; first: React.ReactNode; rest?: React.ReactNode; extra?: React.ReactNode;
  meta: React.ReactNode; href: string;
}) {
  const [open, setOpen] = useState(false);
  const toggle = useCallback(() => {
    setOpen((o) => !o);
    markRead(seq);
  }, [seq]);
  return (
    <>
      <div className="prose">{first}{open && rest}</div>
      {extra}
      <div className="story-meta">
        {meta}
        {rest ? (
          <button type="button" className="more-btn" aria-expanded={open} onClick={toggle}>
            {open ? "접기" : `이어 읽기 · ${minutes}분`}<Chevron />
          </button>
        ) : (
          <a href={href} className="more-btn">글 보기<Chevron /></a>
        )}
      </div>
    </>
  );
}

/** 글 페이지: 연 글은 읽음으로, 상단 막대에 읽은 만큼 표시 */
export function ArticleReading({ seq }: { seq: number }) {
  const [p, setP] = useState(0);
  useEffect(() => {
    markRead(seq);
    const onScroll = () => {
      const h = document.documentElement.scrollHeight - window.innerHeight;
      setP(h > 0 ? Math.min(1, window.scrollY / h) : 1);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [seq]);
  return <div className="read-bar" aria-hidden="true"><i style={{ width: `${p * 100}%` }} /></div>;
}

/** 가 버튼: 본문 글자 크기 15~20px 순환 */
export function TextSizeButton() {
  const cycle = () => {
    const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--body-size")) || 17;
    const next = cur >= 20 ? 15 : cur + 1;
    document.documentElement.style.setProperty("--body-size", `${next}px`);
    try {
      localStorage.setItem("op_body_size", String(next));
    } catch {}
  };
  return <button type="button" className="icon-btn" aria-label="글자 크기" onClick={cycle} style={{ fontSize: 17, fontWeight: 600 }}>가</button>;
}
