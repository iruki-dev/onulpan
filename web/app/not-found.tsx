import Link from "next/link";

export default function NotFound() {
  return (
    <>
      <h1>찾는 글이 없습니다</h1>
      <p><Link href="/">오늘의 조간으로</Link></p>
    </>
  );
}
