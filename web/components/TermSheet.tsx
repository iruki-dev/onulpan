"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Chevron } from "./Icons";

type Term = { anchor: string; kind: string; name: string; summary: string; href: string };
const KIND: Record<string, string> = { explainer: "해설", synthesis: "종합", fact: "사실", issue: "쟁점 정리" };

// 본문의 밑줄 용어를 누르면 읽던 자리를 떠나지 않고 시트로 연다 (새 탭·수정키 클릭은 그대로 이동)
export function TermSheet() {
  const [term, setTerm] = useState<Term | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onClick = async (e: MouseEvent) => {
      const a = (e.target as HTMLElement).closest("a.term") as HTMLAnchorElement | null;
      if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      const seq = a.dataset.to;
      if (!seq) return;
      e.preventDefault();
      try {
        const r = await fetch(`/api/term/${seq}`);
        if (!r.ok) throw new Error();
        const data = await r.json();
        setTerm({ anchor: a.textContent ?? "", ...data });
      } catch {
        location.href = a.href;
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  useEffect(() => {
    if (!term) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setTerm(null);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [term]);

  if (!term) return null;
  return (
    <div className="sheet-backdrop" onClick={() => setTerm(null)}>
      <section role="dialog" aria-modal="true" aria-label={term.name} className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="grip" />
        <div className="row" style={{ justifyContent: "space-between", marginTop: 12 }}>
          <span className="kind" style={{ marginTop: 0 }}>{KIND[term.kind] ?? "관련 글"}</span>
          <button ref={closeRef} type="button" className="icon-btn" aria-label="닫기" onClick={() => setTerm(null)}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <h2>{term.anchor || term.name}</h2>
        <p>{term.summary}</p>
        <Link href={term.href} className="cell" style={{ borderTop: "1px solid var(--line)", marginTop: 4 }} onClick={() => setTerm(null)}>
          <span className="body"><span className="main plain">{term.name}</span></span>
          <Chevron className="chev" />
        </Link>
        <Link href={term.href} className="btn block" onClick={() => setTerm(null)}>{term.kind === "explainer" ? "해설 전체 읽기" : "전체 읽기"}</Link>
      </section>
    </div>
  );
}
