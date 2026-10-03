import Link from "next/link";

export const metadata = { title: "수신 거부" };

export default async function Unsubscribed({ searchParams }: { searchParams: Promise<{ ok?: string }> }) {
  const { ok } = await searchParams;
  return ok === "1" ? (
    <>
      <h1>이메일 조간을 더 보내지 않습니다</h1>
      <p>웹에서는 계속 읽을 수 있습니다. 다시 받으려면 <Link href="/settings">설정</Link>에서 켜 주세요.</p>
    </>
  ) : (
    <>
      <h1>링크를 확인하지 못했습니다</h1>
      <p>로그인한 뒤 <Link href="/settings">설정</Link>에서 이메일 수신을 끌 수 있습니다.</p>
    </>
  );
}
