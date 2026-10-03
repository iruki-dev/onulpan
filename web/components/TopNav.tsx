"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "오늘의 조간" },
  { href: "/archive", label: "지난 조간" },
  { href: "/issues/weekly", label: "쟁점" },
  { href: "/principles", label: "편집 원칙" },
];

export function TopNav() {
  const path = usePathname();
  return (
    <nav className="top-nav" aria-label="주 메뉴">
      {ITEMS.map((i) => (
        <Link key={i.href} href={i.href} aria-current={path === i.href ? "page" : undefined}>{i.label}</Link>
      ))}
    </nav>
  );
}
