import Link from "next/link";
import { Check } from "@/components/Icons";
import { imageById } from "@/lib/images";
import { RELATION_KO } from "@/lib/labels";
import { submitImageRequest } from "./actions";

export const metadata = { title: "이미지 내리기 요청", robots: { index: false } };

const ERRORS: Record<string, string> = {
  contact: "이름과 이메일 주소를 확인해 주세요.",
  relation: "이미지와의 관계를 골라 주세요.",
  body: "요청 내용을 적어 주세요.",
  image: "이미지를 찾지 못했어요. 이미지 아래 ⓘ에서 다시 들어와 주세요.",
};

export default async function ImageRequestPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const id = Number(sp.id);
  const img = Number.isInteger(id) && id > 0 ? await imageById(id) : null;
  const contact = process.env.FOUNDER_EMAIL ?? "editor@onulpan.kr";

  if (sp.sent) {
    return (
      <div className="page narrow">
        <div className="done" style={{ paddingTop: 72 }}>
          <span className="check"><Check size={22} /></span>
          <strong>이미지를 내렸어요</strong>
          <span>출처와 이용 조건을 확인해<br />3일 안에 이메일로 답을 드릴게요.</span>
        </div>
        <Link href="/" className="btn secondary block" style={{ marginBottom: 48 }}>오늘판으로</Link>
      </div>
    );
  }

  return (
    <div className="page narrow">
      <div className="page-head" style={{ paddingTop: 32 }}>
        <h1 className="page-title">이미지 내리기 요청</h1>
        <p className="page-sub">요청을 받으면 바로 내리고, 확인한 뒤 답을 드려요.</p>
      </div>

      {img ? (
        <div className="req-image">
          {img.status === "active" ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={img.src} alt={img.alt} />
          ) : (
            <span className="ph" aria-hidden />
          )}
          <span className="body">
            <span className="main">{img.credit}</span>
            <span className="under">{img.status === "taken_down" ? "이미 내린 이미지예요" : `${img.sourceName} · ${img.licenseLabel}`}</span>
          </span>
        </div>
      ) : (
        <p className="notice">어떤 이미지인지 알려 주시려면 기사 속 이미지 아래 ⓘ를 눌러 들어와 주세요. 이메일({contact})로도 받아요.</p>
      )}

      {sp.error && <p className="notice error">{ERRORS[sp.error] ?? "요청을 받지 못했어요."}</p>}

      {img && (
        <form action={submitImageRequest} style={{ paddingTop: 20 }}>
          <input type="hidden" name="image_id" value={img.id} />
          <fieldset className="field" style={{ border: 0, padding: 0, margin: "0 0 20px" }}>
            <legend style={{ marginBottom: 10, fontSize: 15, fontWeight: 500 }}>이미지와의 관계</legend>
            <div className="pills two">
              {Object.entries(RELATION_KO).map(([k, v]) => (
                <label key={k}><input type="radio" name="relation" value={k} required defaultChecked={k === "owner"} />{v}</label>
              ))}
            </div>
          </fieldset>
          <label className="field">
            이름 또는 기관명
            <input className="input" name="name" required maxLength={80} autoComplete="name" />
          </label>
          <label className="field">
            답을 받을 이메일
            <input className="input" type="email" name="email" required autoComplete="email" />
          </label>
          <label className="field">
            요청 내용
            <textarea className="input" name="body" required maxLength={4000}
              placeholder="권리 관계와 원하시는 조치를 적어 주세요. 예: 제가 찍은 사진이며 이용을 허락한 적이 없습니다." />
          </label>
          <button type="submit" className="btn block">요청하고 바로 내리기</button>
          <p className="small muted" style={{ margin: "14px 0 48px", lineHeight: 1.6, textAlign: "center" }}>
            적어 주신 이름과 이메일은 이 요청에 답하는 데만 써요.
          </p>
        </form>
      )}
    </div>
  );
}
