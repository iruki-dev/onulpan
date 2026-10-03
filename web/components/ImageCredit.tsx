"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Img } from "@/lib/images";
import { Chevron, Close, External, Info } from "./Icons";

const TIER: Record<Img["tier"], { kind: string; about: string }> = {
  free: { kind: "자유 이용 출처", about: "출처를 밝히는 조건으로 누구나 쓸 수 있는 이미지예요." },
  press: { kind: "보도용 제공", about: "이 소식을 다루는 글에서만, 원본 그대로 싣는 보도용 이미지예요." },
  own: { kind: "자체 제작 그래픽", about: "오늘판이 보도 내용을 바탕으로 직접 만든 그래픽이에요." },
};

/** 크레딧 한 줄(이미지 바로 아래) + 누르면 출처·이용 조건 시트 */
export function ImageCredit({ img }: { img: Img }) {
  const [open, setOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  const t = TIER[img.tier];
  const external = /^https?:/.test(img.originUrl);
  return (
    <>
      <figcaption className="figcap">
        <span className="credit">
          {img.credit}
          {img.linkRequired && img.licenseUrl && (
            <> · <a href={img.licenseUrl} target="_blank" rel="noopener license">{img.licenseLabel}</a></>
          )}
        </span>
        <button type="button" className="info" aria-label="이미지 출처와 이용 조건" onClick={() => setOpen(true)}>
          <Info size={16} />
        </button>
      </figcaption>
      {open && (
        <div className="sheet-backdrop" onClick={() => setOpen(false)}>
          <section role="dialog" aria-modal="true" aria-label="이미지 정보" className="sheet" onClick={(e) => e.stopPropagation()}>
            <div className="grip" />
            <div className="sheet-head">
              <span className="kind">{t.kind}</span>
              <button ref={closeRef} type="button" className="icon-btn" aria-label="닫기" onClick={() => setOpen(false)}><Close /></button>
            </div>
            <h2>{img.sourceName}</h2>
            <p>{t.about}</p>
            <dl className="facts">
              <div><dt>크레딧</dt><dd>{img.credit}</dd></div>
              <div>
                <dt>라이선스</dt>
                <dd>{img.licenseUrl ? <a href={img.licenseUrl} target="_blank" rel="noopener license">{img.licenseLabel}</a> : img.licenseLabel}</dd>
              </div>
              {img.usageTerms && <div><dt>이용 조건</dt><dd>{img.usageTerms}</dd></div>}
              <div><dt>원본 형태</dt><dd>{img.modifiable ? "비율만 맞춰 실어요" : "자르거나 고치지 않고 실어요"}</dd></div>
            </dl>
            {external ? (
              <a href={img.originUrl} target="_blank" rel="noopener" className="cell">
                <span className="body"><span className="main plain">원본 보기</span></span>
                <span className="chev"><External /></span>
              </a>
            ) : (
              <Link href={img.originUrl} className="cell" onClick={() => setOpen(false)}>
                <span className="body"><span className="main plain">원자료 보기</span></span>
                <Chevron className="chev" />
              </Link>
            )}
            <Link href={`/images/request?id=${img.id}`} className="sheet-foot" onClick={() => setOpen(false)}>
              권리자이신가요? 이미지 내리기 요청<Chevron size={14} />
            </Link>
          </section>
        </div>
      )}
    </>
  );
}
