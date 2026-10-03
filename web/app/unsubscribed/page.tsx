import { Message } from "@/components/Message";

export const metadata = { title: "수신 거부" };

export default async function Unsubscribed({ searchParams }: { searchParams: Promise<{ ok?: string }> }) {
  const { ok } = await searchParams;
  return ok === "1" ? (
    <Message title="이메일을 더 보내지 않을게요" sub="웹에서는 계속 읽을 수 있어요." action={{ href: "/settings", label: "설정에서 다시 켜기" }} />
  ) : (
    <Message title="링크를 확인하지 못했어요" sub="로그인한 뒤 설정에서 이메일 수신을 끌 수 있어요." action={{ href: "/settings", label: "설정으로" }} />
  );
}
