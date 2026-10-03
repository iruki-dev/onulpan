import Link from "next/link";
import { Check, Chevron } from "@/components/Icons";
import { one } from "@/lib/db";
import { SECTION_KO, SECTIONS } from "@/lib/labels";
import { requireUser } from "@/lib/session";
import { deleteAccount, logout, savePrefs } from "./actions";

export const metadata = { title: "설정" };

type Prefs = { preset: string; section_weights: Record<string, number>; niche_topics: string[]; delivery_hour: number; email_enabled: boolean };

const PRESETS = [
  { k: "short", min: "10분", label: "짧게", desc: "1면과 분야별 핵심만" },
  { k: "standard", min: "25분", label: "기본", desc: "쟁점 정리, 배경, 교양까지" },
  { k: "long", min: "40분", label: "길게", desc: "분야별 기사를 두 배로" },
];

function level(w: number | undefined): string {
  return w === undefined || w === 1 ? "normal" : w > 1 ? "more" : "less";
}

export default async function SettingsPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const user = await requireUser("/settings");
  const prefs = (await one<Prefs>("SELECT * FROM user_prefs WHERE user_id = $1", [user.id])) ?? {
    preset: "standard", section_weights: {}, niche_topics: [], delivery_hour: 7, email_enabled: true,
  };
  const marketing = await one<{ marketing_opt_in: boolean }>("SELECT marketing_opt_in FROM users WHERE id = $1", [user.id]);
  return (
    <div className="page">
      <form action={savePrefs}>
        <div className="page-head">
          <h1 className="page-title">하루에 얼마나<br />읽을까요?</h1>
          {sp.saved && <p className="notice-line">저장했어요. 오늘 조간도 새 설정으로 바꿨어요.</p>}
        </div>
        <div role="radiogroup" aria-label="읽을 분량">
          {PRESETS.map((p) => (
            <label key={p.k} className="choice">
              <input type="radio" name="preset" value={p.k} defaultChecked={prefs.preset === p.k} />
              <span className="txt">
                <span className="t1">{p.min} <small>{p.label}</small></span>
                <span className="t2">{p.desc}</span>
              </span>
              <span className="radio" aria-hidden><Check size={14} /></span>
            </label>
          ))}
        </div>

        <div className="band" style={{ marginTop: 28 }} />
        <section className="section">
          <h2 className="section-title">분야별 비중</h2>
          <p className="page-sub" style={{ margin: "2px 0 8px" }}>1면은 바뀌지 않아요</p>
          {SECTIONS.map((sec) => (
            <div key={sec} className="seg-row">
              <span className="name">{SECTION_KO[sec]}</span>
              <fieldset className="segmented" aria-label={SECTION_KO[sec]}>
                {[["less", "덜"], ["normal", "보통"], ["more", "더"]].map(([v, l]) => (
                  <label key={v}>
                    <input type="radio" name={`w_${sec}`} value={v} defaultChecked={level(prefs.section_weights[sec]) === v} />
                    {l}
                  </label>
                ))}
              </fieldset>
            </div>
          ))}
        </section>

        <div className="band" style={{ marginTop: 20 }} />
        <section className="section">
          <h2 className="section-title" style={{ marginBottom: 12 }}>받는 시각</h2>
          <fieldset className="pills" aria-label="받는 시각">
            {[7, 8, 9, 10].map((h) => (
              <label key={h}>
                <input type="radio" name="delivery_hour" value={h} defaultChecked={prefs.delivery_hour === h} />
                {h}시
              </label>
            ))}
          </fieldset>
          <label className="switch-row" style={{ marginTop: 8 }}>
            이메일로도 받기
            <input type="checkbox" role="switch" name="email_enabled" defaultChecked={prefs.email_enabled} />
            <span className="switch" aria-hidden />
          </label>
          <label className="switch-row">
            새 기능 소식 받기
            <input type="checkbox" role="switch" name="marketing_opt_in" defaultChecked={marketing?.marketing_opt_in} />
            <span className="switch" aria-hidden />
          </label>
        </section>

        <div className="band" style={{ marginTop: 20 }} />
        <section className="section">
          <h2 className="section-title" style={{ marginBottom: 12 }}>관심 주제</h2>
          {user.plan === "free" ? (
            <Link href="/founding" className="cell">
              <span className="body">
                <span className="main plain">관심 주제를 먼저 실어 드려요</span>
                <span className="under">창립 멤버 기능</span>
              </span>
              <Chevron className="chev" />
            </Link>
          ) : (
            <label className="field">
              <span className="sr-only">관심 주제</span>
              <input className="input" name="niche_topics" defaultValue={prefs.niche_topics.join(", ")} placeholder="반도체-수출규제, 기준금리" />
              <span className="small muted">쉼표로 나눠 5개까지</span>
            </label>
          )}
        </section>

        <div style={{ padding: "16px 0 8px" }}>
          <button type="submit" className="btn block">저장</button>
        </div>
      </form>

      <div className="band" style={{ marginTop: 28 }} />
      <section className="section">
        <div className="cell">
          <span className="body">
            <span className="over">계정</span>
            <span className="main plain">{user.email}</span>
          </span>
          <span className="small muted">{user.plan === "free" ? "무료" : user.plan === "founding" ? "창립 멤버" : "프리미엄"}</span>
        </div>
        <form action={logout}>
          <button type="submit" className="cell cell-btn">
            <span className="body"><span className="main plain">로그아웃</span></span>
          </button>
        </form>
        <details className="cell-details">
          <summary className="cell">
            <span className="body"><span className="main plain muted">탈퇴하기</span></span>
            <Chevron className="chev" />
          </summary>
          <form action={deleteAccount} style={{ padding: "4px 0 16px" }}>
            <p className="small muted" style={{ margin: "0 0 12px", lineHeight: 1.6 }}>
              이메일 주소와 설정, 읽기 기록이 지워지고 되돌릴 수 없어요. 계속하려면 ‘탈퇴’라고 입력하세요.
            </p>
            {sp.delete === "confirm" && <p className="error small">‘탈퇴’를 정확히 입력해 주세요.</p>}
            <input className="input" name="confirm" autoComplete="off" aria-label="확인 문구" />
            <button type="submit" className="btn secondary small" style={{ marginTop: 8 }}>탈퇴</button>
          </form>
        </details>
      </section>
    </div>
  );
}
