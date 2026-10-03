import { Message } from "@/components/Message";

export default function NotFound() {
  return <Message title="찾는 글이 없어요" sub="주소가 바뀌었거나 지워진 글이에요." action={{ href: "/", label: "오늘의 조간으로" }} />;
}
