import { test } from "node:test";
import assert from "node:assert/strict";
import { cardSvg, wrap } from "./card.ts";

test("wrap keeps words and truncates with ellipsis", () => {
  const lines = wrap("가 나다 라마바 사아자차 카타파하 가나다라마바사", 6, 2);
  assert.equal(lines.length, 2);
  assert.ok(lines[1].endsWith("…"));
});

test("card escapes text", () => {
  const svg = cardSvg({ title: "<a & b>", question: "q", positions: [{ holder: "A", claim: "c" }], date: "2026-10-06", url: "x" });
  assert.ok(svg.includes("&lt;a &amp; b&gt;"));
  assert.ok(svg.startsWith("<svg"));
});
