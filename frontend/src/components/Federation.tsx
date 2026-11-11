import { useState } from "react";
import { Users } from "lucide-react";
import { api } from "../api";
import { inr, useL, useLang } from "../util";
import { factValue, useFactReg } from "../facts";
import { Stat } from "./common";


export default function Federation() {
  const L = useL();
  const { lang } = useLang();
  const reg = useFactReg();
  const [r, setR] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  async function run() { setBusy(true); setR(await api.screen(40)); setBusy(false); }
  const byScheme = r ? (lang === "hi" && r.by_scheme_hi ? r.by_scheme_hi : r.by_scheme) : {};
  return (
    <div className="max-w-[1200px] mx-auto p-3 md:p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Users className="text-brand-600" /><div className="text-xl font-bold">{L("SHG federation / Bank Mitra, cohort screening", "स्वयं सहायता समूह महासंघ / बैंक मित्र: सामूहिक जाँच")}</div>
      </div>
      <div className="text-[13px] text-ink-500 max-w-3xl">{L(
        "A federation officer or business correspondent screens a whole member list against every scheme in seconds, using profile facts only (no financial data, so no consent pull). Members with a match are invited to start their own consented Saakh journey.",
        "महासंघ अधिकारी या बैंक मित्र पूरी सदस्य सूची को हर योजना से कुछ ही सेकंड में जाँचते हैं, केवल प्रोफ़ाइल जानकारी से (कोई वित्तीय डेटा नहीं, इसलिए सहमति की ज़रूरत नहीं)। जिनका मिलान होता है, उन्हें अपनी सहमति से साख की पूरी प्रक्रिया शुरू करने के लिए बुलाया जाता है।")}</div>
      <button className="btn-primary" disabled={busy} onClick={run}>{busy ? L("Screening…", "जाँच हो रही है…") : L("Screen 40 members (synthetic list)", "40 सदस्यों की जाँच करें (कृत्रिम सूची)")}</button>
      {r && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label={L("Members screened", "जाँचे गए सदस्य")} value={r.n} />
            <Stat label={L("With ≥1 eligible scheme", "कम से कम 1 योजना के पात्र")} value={r.with_any} tone="text-brand-700" />
            <Stat label={L("Est. annual benefit unlocked", "अनुमानित सालाना लाभ")} value={inr(r.est_annual_value, true)}
              sub={L("vs borrowing informally at 30%", "30% पर अनौपचारिक उधार की तुलना में")} tone="text-emerald-700" />
            <Stat label={L("Need Udyam first", "पहले उद्यम पंजीकरण चाहिए")} value={r.members.filter((m: any) => m.unlock).length}
              sub={L("one free registration unlocks CGTMSE", "एक मुफ़्त पंजीकरण से सीजीटीएमएसई की शर्त पूरी")} />
          </div>
          <div className="card p-3">
            <div className="flex flex-wrap gap-2 mb-2">{Object.entries(byScheme).map(([k, v]: any) => <span key={k} className="pill bg-brand-50 text-brand-700">{k}: {v}</span>)}</div>
            <table className="w-full text-[12.5px]">
              <thead><tr className="text-left text-ink-400"><th className="py-1">{L("Member", "सदस्य")}</th><th>{L("Activity", "गतिविधि")}</th><th>{L("Need", "ज़रूरत")}</th>
                <th>{L("Eligible now", "अभी पात्र")}</th><th>{L("Next action", "अगला कदम")}</th></tr></thead>
              <tbody>{r.members.map((m: any) => (
                <tr key={m.id} className="border-t border-slate-100"><td className="py-1">{m.id} · {m.name}</td>
                  <td className="capitalize">{factValue(reg, "activity", m.activity, lang)}</td><td>{inr(m.need)}</td>
                  <td>{((lang === "hi" && m.eligible_hi) ? m.eligible_hi : m.eligible).join(", ") || <span className="text-ink-400">-</span>}</td>
                  <td>{m.unlock ? <span className="pill bg-saffron-50 text-saffron-600">{L("Register Udyam", "उद्यम पंजीकरण करें")}</span> : ""}</td></tr>))}</tbody>
            </table>
            <div className="text-[11px] text-ink-400 mt-2">{lang === "hi" && r.note_hi ? r.note_hi : r.note}</div>
          </div>
        </>
      )}
    </div>
  );
}
