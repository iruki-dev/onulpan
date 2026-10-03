import Link from "next/link";
import { one } from "@/lib/db";
import { PRESET_KO, SECTION_KO, SECTIONS } from "@/lib/labels";
import { requireUser } from "@/lib/session";
import { deleteAccount, logout, savePrefs } from "./actions";

export const metadata = { title: "설정" };

type Prefs = { preset: string; section_weights: Record<string, number>; niche_topics: string[]; delivery_hour: number; email_enabled: boolean };

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
    <>
      <h1>설정</h1>
      <p className="muted small">{user.email} · {user.plan === "free" ? "무료" : user.plan === "founding" ? "창립 멤버" : "프리미엄"}</p>
      {sp.saved && <p className="notice">저장했습니다. 오늘 조간을 새 설정으로 다시 짰습니다.</p>}
      <form action={savePrefs}>
        <fieldset>
          <legend>읽을 분량</legend>
          <div className="choices">
            {Object.entries(PRESET_KO).map(([k, v]) => (
              <label key={k}><input type="radio" name="preset" value={k} defaultChecked={prefs.preset === k} /> {v}</label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>분야별 비중</legend>
          <p className="muted small">1면은 모든 독자에게 같습니다. 나머지 지면에서 분야별 비중만 바꿉니다. 다섯 분야는 소식이 있으면 적어도 한 편씩 실립니다.</p>
          {SECTIONS.map((sec) => (
            <div key={sec} className="row">
              <strong style={{ width: 80 }}>{SECTION_KO[sec]}</strong>
              <div className="choices">
                {[["more", "더"], ["normal", "보통"], ["less", "덜"]].map(([v, l]) => (
                  <label key={v}>
                    <input type="radio" name={`w_${sec}`} value={v} defaultChecked={level(prefs.section_weights[sec]) === v} /> {l}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </fieldset>
        <fieldset>
          <legend>관심 주제 {user.plan === "free" && <span className="muted small">(창립 멤버 기능)</span>}</legend>
          {user.plan === "free" ? (
            <p className="muted small">관심 주제를 정해 두면 그 주제의 새 글을 섹션보다 먼저 실어 드립니다. <Link href="/founding">창립 멤버 알아보기</Link></p>
          ) : (
            <label>
              주제 이름표(slug)를 쉼표로, 최대 5개
              <input name="niche_topics" defaultValue={prefs.niche_topics.join(", ")} placeholder="반도체-수출규제, 기준금리" />
            </label>
          )}
        </fieldset>
        <fieldset>
          <legend>이메일 조간</legend>
          <label><input type="checkbox" name="email_enabled" defaultChecked={prefs.email_enabled} /> 매일 아침 이메일로 받기</label>
          <label>
            받는 시각
            <select name="delivery_hour" defaultValue={prefs.delivery_hour}>
              {[7, 8, 9, 10].map((h) => <option key={h} value={h}>오전 {h}시</option>)}
            </select>
          </label>
          <label><input type="checkbox" name="marketing_opt_in" defaultChecked={marketing?.marketing_opt_in} /> 새 기능·이벤트 소식 받기 (선택)</label>
        </fieldset>
        <button type="submit">저장</button>
      </form>

      <form action={logout} style={{ marginTop: 32 }}>
        <button type="submit" className="ghost">로그아웃</button>
      </form>

      <details style={{ marginTop: 32 }}>
        <summary>탈퇴하기</summary>
        <form action={deleteAccount}>
          <p className="small">탈퇴하면 이메일 주소와 설정, 읽기 기록이 지워지고 되돌릴 수 없습니다. 계속하려면 ‘탈퇴’라고 입력하세요.</p>
          {sp.delete === "confirm" && <p className="error small">‘탈퇴’를 정확히 입력해 주세요.</p>}
          <input name="confirm" autoComplete="off" />
          <button type="submit" className="ghost" style={{ marginTop: 8 }}>탈퇴</button>
        </form>
      </details>
    </>
  );
}
