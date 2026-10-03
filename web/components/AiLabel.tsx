import Link from "next/link";

export function AiLabel({ seq, nSources, model, promptVersion, kind }: {
  seq: number; nSources: number; model: string; promptVersion: string; kind: string;
}) {
  if (kind === "correction") {
    return <p className="ai-label">편집자가 직접 쓴 정정 글 · <Link href={`/p/${seq}#sources`}>원래 출처 {nSources}건</Link></p>;
  }
  if (kind === "culture") {
    return <p className="ai-label">AI({model})가 편집 캘린더 주제로 쓴 교양 글 · 지침 {promptVersion}</p>;
  }
  return (
    <p className="ai-label">
      AI가 언론 보도 <Link href={`/p/${seq}#sources`}>{nSources}건</Link>을 종합해 씀 · {model} · 지침 {promptVersion}
    </p>
  );
}
