"use client";
import { useState } from "react";
import { Share } from "./Icons";

export function ShareButton({ url, title, variant = "icon", label = "공유하기", className = "btn" }: {
  url: string; title: string; variant?: "icon" | "button"; label?: string; className?: string;
}) {
  const [toast, setToast] = useState(false);
  const share = async () => {
    const full = new URL(url, location.origin).toString();
    if (navigator.share) {
      await navigator.share({ url: full, title }).catch(() => {});
      return;
    }
    await navigator.clipboard?.writeText(full);
    setToast(true);
    setTimeout(() => setToast(false), 1800);
  };
  return (
    <>
      {variant === "icon" ? (
        <button type="button" className="icon-btn" aria-label="공유" data-track="share" onClick={share}><Share /></button>
      ) : (
        <button type="button" className={className} data-track="share" onClick={share}>{label}</button>
      )}
      {toast && <div className="toast" role="status">링크를 복사했어요</div>}
    </>
  );
}
