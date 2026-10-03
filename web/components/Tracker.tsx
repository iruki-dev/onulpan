"use client";
import { useEffect } from "react";

// 행동 로그: 조간 열람·완독, 링크 클릭, 오디오 수요, 공유. 이벤트 목록은 PRD 참조.
function send(name: string, props: Record<string, unknown> = {}) {
  const body = JSON.stringify({ name, props, path: location.pathname });
  if (navigator.sendBeacon) navigator.sendBeacon("/api/events", new Blob([body], { type: "application/json" }));
  else fetch("/api/events", { method: "POST", body, headers: { "content-type": "application/json" }, keepalive: true });
}

function captureUtm() {
  const p = new URLSearchParams(location.search);
  const utm: Record<string, string> = {};
  for (const k of ["utm_source", "utm_medium", "utm_campaign", "utm_content"]) {
    const v = p.get(k);
    if (v) utm[k] = v.slice(0, 80);
  }
  if (Object.keys(utm).length && !document.cookie.includes("op_utm=")) {
    document.cookie = `op_utm=${encodeURIComponent(JSON.stringify(utm))}; path=/; max-age=${60 * 60 * 24 * 30}; samesite=lax`;
  }
}

export function Tracker({ page, editionId }: { page: string; editionId?: number }) {
  useEffect(() => {
    captureUtm();
    send(editionId ? "edition_open" : "page_view", { page, edition_id: editionId });
    const end = document.getElementById("edition-end");
    let observer: IntersectionObserver | undefined;
    if (end && editionId) {
      observer = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          send("edition_complete", { edition_id: editionId });
          observer?.disconnect();
        }
      });
      observer.observe(end);
    }
    const onClick = (e: MouseEvent) => {
      const el = (e.target as HTMLElement).closest("[data-track]") as HTMLElement | null;
      if (!el) return;
      send(el.dataset.track!, { from: el.dataset.from, to: el.dataset.to, edition_id: editionId });
    };
    document.addEventListener("click", onClick);
    return () => {
      observer?.disconnect();
      document.removeEventListener("click", onClick);
    };
  }, [page, editionId]);
  return null;
}
