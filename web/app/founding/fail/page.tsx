import { Message } from "@/components/Message";

export default async function FailPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  return <Message title="결제를 마치지 못했어요" sub={sp.message ?? "결제가 취소됐어요."} action={{ href: "/founding", label: "다시 시도하기" }} />;
}
