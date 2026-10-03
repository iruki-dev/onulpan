"use client";
import { useState } from "react";
import { Speaker } from "./Icons";

// ‘오디오로 듣기’ 수요 측정. 클릭만 기록한다.
export function AudioButton({ seq }: { seq?: number }) {
  const [toast, setToast] = useState(false);
  return (
    <>
      <button type="button" className="icon-btn" aria-label="듣기" data-track="audio_interest" data-to={seq}
        onClick={() => { setToast(true); setTimeout(() => setToast(false), 2200); }}>
        <Speaker />
      </button>
      {toast && <div className="toast" role="status">듣기 기능을 준비하고 있어요</div>}
    </>
  );
}
