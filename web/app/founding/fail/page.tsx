import Link from "next/link";

export default async function FailPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  return (
    <>
      <h1>결제를 마치지 못했습니다</h1>
      <p className="muted">{sp.message ?? "결제가 취소되었습니다."}</p>
      <p><Link href="/founding">다시 시도하기</Link></p>
    </>
  );
}
