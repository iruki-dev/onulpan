"use client";
import { useState } from "react";

export function ReportForm({ seq }: { seq: number }) {
  const [state, setState] = useState<"idle" | "open" | "sent" | "error">("idle");
  if (state === "idle") {
    return <button type="button" className="ghost" onClick={() => setState("open")}>사실과 다른 내용이 있나요?</button>;
  }
  if (state === "sent") return <p className="muted">제보 고맙습니다. 48시간 안에 확인하고 결과를 알려드리겠습니다.</p>;
  return (
    <form
      className="report-form"
      onSubmit={async (e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        const r = await fetch("/api/report", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ seq, body: f.get("body"), contact: f.get("contact") }),
        });
        setState(r.ok ? "sent" : "error");
      }}
    >
      <label>무엇이 사실과 다른가요?<textarea name="body" required minLength={5} maxLength={2000} rows={4} /></label>
      <label>답변 받을 이메일 (선택)<input name="contact" type="email" maxLength={200} /></label>
      <button type="submit">제보하기</button>
      {state === "error" && <p className="error">보내지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>}
    </form>
  );
}
