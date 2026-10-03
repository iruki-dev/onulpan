import { test } from "node:test";
import assert from "node:assert/strict";
import { linkify, paragraphs } from "./linkify.ts";

test("links first occurrence only, longest anchor first", () => {
  const paras = paragraphs("기준금리가 올랐다. 기준금리 인상은\n\n반도체 수출규제와 반도체 이야기");
  const out = linkify(paras, [
    { anchor: "기준금리", href: "/w/기준금리", title: "해설", toSeq: 1 },
    { anchor: "반도체 수출규제", href: "/w/반도체-수출규제", title: "종합", toSeq: 2 },
    { anchor: "반도체", href: "/w/반도체", title: "x", toSeq: 3 },
  ]);
  assert.equal(out[0].filter((s) => s.href).length, 1);
  assert.equal(out[0][0].href, "/w/기준금리");
  const linked = out[1].filter((s) => s.href).map((s) => s.text);
  assert.deepEqual(linked, ["반도체 수출규제", "반도체"]);
  assert.equal(out[1].map((s) => s.text).join(""), "반도체 수출규제와 반도체 이야기");
});

test("no anchors → plain text", () => {
  assert.deepEqual(linkify(["가나다"], []), [[{ text: "가나다" }]]);
});
