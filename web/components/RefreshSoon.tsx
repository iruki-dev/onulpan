"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

// 워커가 조간을 조립하는 동안(수 초) 기다렸다가 다시 그린다.
export function RefreshSoon({ ms = 2500 }: { ms?: number }) {
  const router = useRouter();
  useEffect(() => {
    const t = setInterval(() => router.refresh(), ms);
    return () => clearInterval(t);
  }, [router, ms]);
  return null;
}
