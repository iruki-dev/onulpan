"use client";
import { useState } from "react";
import { Chevron } from "./Icons";

export function ReportForm({ seq }: { seq: number }) {
  const [state, setState] = useState<"idle" | "open" | "sent" | "error">("idle");
  if (state === "idle") {
    return (
      <button type="button" className="cell" onClick={() => setState("open")}
        style={{ width: "100%", background: "none", border: 0, padding: "12px 0", cursor: "pointer", textAlign: "left" }}>
        <span className="body"><span className="main plain">오류 제보하기</span></span>
        <span className="chev"><Chevron size={18} /></span>
      </button>
    );
  }
  if (state === "sent") return <p className="notice">제보 고맙습니다. 48시간 안에 확인하고 알려드릴게요.</p>;
  return (
    <form
      style={{ paddingTop: 12 }}
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
      <label className="field">무엇이 사실과 다른가요?<textarea name="body" className="input" required minLength={5} maxLength={2000} /></label>
      <label className="field">답변 받을 이메일 (선택)<input name="contact" type="email" className="input" maxLength={200} /></label>
      <button type="submit" className="btn block">보내기</button>
      {state === "error" && <p className="error small">보내지 못했어요. 잠시 뒤 다시 시도해 주세요.</p>}
    </form>
  );
}
