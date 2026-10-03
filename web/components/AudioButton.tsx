"use client";
import { useState } from "react";

// ‘오디오로 듣기’ 수요 측정 버튼. 클릭만 기록한다.
export function AudioButton({ seq }: { seq?: number }) {
  const [clicked, setClicked] = useState(false);
  return (
    <button
      type="button"
      className="ghost"
      data-track="audio_interest"
      data-to={seq}
      onClick={() => setClicked(true)}
      disabled={clicked}
    >
      {clicked ? "관심 표시 고맙습니다. 준비되면 알려드릴게요." : "🔈 오디오로 듣기"}
    </button>
  );
}
