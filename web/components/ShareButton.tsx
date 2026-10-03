"use client";
import { useState } from "react";

export function ShareButton({ url, title }: { url: string; title: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="ghost"
      data-track="share"
      onClick={async () => {
        const full = new URL(url, location.origin).toString();
        if (navigator.share) await navigator.share({ url: full, title }).catch(() => {});
        else await navigator.clipboard?.writeText(full);
        setDone(true);
      }}
    >
      {done ? "링크를 복사했습니다" : "공유하기"}
    </button>
  );
}
