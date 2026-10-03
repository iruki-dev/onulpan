import type { Img } from "@/lib/images";
import { ImageCredit } from "./ImageCredit";

/**
 * 이미지 + 바로 아래 크레딧. 원본 형태 유지 원칙:
 * - 변경 허용 라이선스(modifiable)만 대표 이미지 틀(3:2)에 맞춰 자른다.
 * - 나머지는 원본 비율 그대로. 너무 길거나 세로인 사진은 자르지 않고 틀 안에 여백을 둔다.
 */
export function Figure({ img, lead = false, priority = false }: { img: Img; lead?: boolean; priority?: boolean }) {
  const ratio = img.width && img.height ? img.width / img.height : 1.5;
  let mode: "crop" | "natural" | "fit";
  if (lead && img.modifiable && img.tier !== "own") mode = "crop";
  else if (ratio >= 1.2 && ratio <= 2.4) mode = "natural";
  else mode = "fit";
  const aspect = mode === "natural" ? `${img.width} / ${img.height}` : "3 / 2";
  return (
    <figure className="figure">
      <div className={`frame ${mode}`} style={{ aspectRatio: aspect }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={img.src} alt={img.alt} width={img.width ?? undefined} height={img.height ?? undefined}
          loading={priority ? "eager" : "lazy"} decoding="async" fetchPriority={priority ? "high" : undefined}
          referrerPolicy="no-referrer" />
      </div>
      <ImageCredit img={img} />
    </figure>
  );
}
