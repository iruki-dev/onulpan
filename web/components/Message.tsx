import Link from "next/link";

/** 한 줄 안내 화면(404, 수신 거부, 결제 결과 등). */
export function Message({ title, sub, action }: { title: string; sub?: React.ReactNode; action?: { href: string; label: string } }) {
  return (
    <div className="page narrow message">
      <h1 className="page-title">{title}</h1>
      {sub && <p className="page-sub">{sub}</p>}
      {action && <Link href={action.href} className="btn block" style={{ marginTop: 32 }}>{action.label}</Link>}
    </div>
  );
}
