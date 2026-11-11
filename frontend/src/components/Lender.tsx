import { useEffect, useRef, useState } from "react";

// The branch's OWN reasons for a decline. Saakh's scorecard factors are reference only and are never sent as the bank's reasons.
const LENDER_REASONS: [string, string, string][] = [["repayment_capacity", "Repayment capacity", "चुकाने की क्षमता"], ["credit_history", "Credit history", "क्रेडिट इतिहास"],
  ["documents_incomplete", "Documents incomplete", "दस्तावेज़ अधूरे"], ["scheme_conditions", "Scheme conditions not met", "योजना की शर्तें पूरी नहीं"],
  ["business_viability", "Business viability", "व्यवसाय की व्यवहार्यता"], ["collateral_or_guarantee", "Collateral or guarantee", "गिरवी या गारंटी"],
  ["policy_limit", "Bank policy limit", "बैंक नीति की सीमा"], ["other", "Other", "अन्य"]];
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { FileDown, ShieldCheck, CheckCircle2, HelpCircle, XCircle, RefreshCw, Calculator, Lock, LogOut, Paperclip } from "lucide-react";
import { api, clearLenderKey, downloadAttachment, lenderKey, openPdf, setLenderKey } from "../api";
import { inr, kb, mlabel, pct, sname, t, useL, useLang } from "../util";
import { appStatus, factLabel, factValue, useFactReg, viaName } from "../facts";
import { BandChip, CiteChip, SimBadge, Stat, StatusPill, VerBadge } from "./common";
import { ScheduleChart } from "../cards/Cards";

export default function Lender() {
  const L = useL();
  const { lang } = useLang();
  const reg = useFactReg();
  const [list, setList] = useState<any[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [view, setView] = useState<"queue" | "economics">("queue");
  const [authed, setAuthed] = useState(!!lenderKey());
  const [keyIn, setKeyIn] = useState("");
  const [demoKeys, setDemoKeys] = useState<{ lender: string; key: string }[]>([]);
  const [lenders, setLenders] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const load = () => api.lenderList().then((l) => { setList(l); setErr(""); if (!sel && l.length) setSel(l.find((x: any) => !x.redacted)?.id || l[0].id); })
    .catch((e: any) => { if (e.status === 401) { setAuthed(false); setErr(L("Invalid branch key", "शाखा कुंजी सही नहीं है")); } else setErr(e.message); });
  useEffect(() => {
    api.health().then((h: any) => setDemoKeys(h.demo_lender_keys || [])).catch(() => {});
    api.lenders().then((ls) => setLenders(Object.fromEntries(ls.map((l: any) => [l.id, l.name])))).catch(() => {});
  }, []);
  useEffect(() => { if (authed) load(); }, [authed]);
  const signOut = () => { clearLenderKey(); setList([]); setSel(null); setKeyIn(""); setAuthed(false); };
  const branch = demoKeys.find((d) => d.key === lenderKey())?.lender;
  if (!authed) {
    return (
      <div className="max-w-md mx-auto p-6">
        <div className="card p-5 space-y-3">
          <div className="flex items-center gap-2 font-semibold"><Lock size={16} className="text-brand-600" />{L("Branch console sign-in", "बैंक शाखा कंसोल में प्रवेश")}</div>
          <p className="text-[13px] text-ink-500">{L(
            "Each branch has its own key and sees only files the entrepreneur addressed to that branch, and only while their consent to share is active.",
            "हर शाखा की अपनी कुंजी है। शाखा केवल वही फ़ाइलें देखती है जो उद्यमी ने उसी शाखा को भेजी हैं, और तभी तक जब तक साझा करने की सहमति सक्रिय है।")}</p>
          {!!demoKeys.length && (
            <label className="block text-[12px] text-violet-700">{L("Demo build, sign in as a branch (keys are public in demo only):", "डेमो संस्करण: किसी शाखा के रूप में प्रवेश करें (कुंजियाँ केवल डेमो में सार्वजनिक हैं):")}
              <select className="mt-1 w-full rounded-xl border border-violet-200 px-3 py-2 text-sm text-ink-900" value={keyIn} onChange={(e) => setKeyIn(e.target.value)}>
                <option value="">{L("Choose a branch…", "शाखा चुनें…")}</option>
                {demoKeys.map((d) => <option key={d.key} value={d.key}>{lenders[d.lender] || d.lender}</option>)}
              </select>
            </label>)}
          <input value={keyIn} onChange={(e) => setKeyIn(e.target.value)} placeholder={L("Branch key", "शाखा कुंजी")} type="password"
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
          {err && <div className="text-[12px] text-rose-700">{err}</div>}
          <button className="btn-primary w-full" onClick={() => { setLenderKey(keyIn); setAuthed(true); }}>{L("Open console", "कंसोल खोलें")}</button>
        </div>
      </div>
    );
  }
  return (
    <div className="max-w-[1500px] mx-auto p-3 md:p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <div className="text-xl font-bold">{L("Branch console", "बैंक शाखा कंसोल")}</div><SimBadge />
        <span className="text-[12px] text-ink-400">{L("Saakh pre-appraised files · decision support only; the branch decides", "साख से पहले से जाँची फ़ाइलें · केवल निर्णय में मदद; फ़ैसला शाखा का")}</span>
        <div className="ml-auto flex gap-1">
          <button className={`tab ${view === "queue" ? "tab-on" : ""}`} onClick={() => setView("queue")}>{L("Applications", "आवेदन")}</button>
          <button className={`tab ${view === "economics" ? "tab-on" : ""}`} onClick={() => setView("economics")}><Calculator size={14} className="inline mr-1" />{L("Cost of incomplete files", "अधूरी फ़ाइलों की लागत")}</button>
          <button className="btn-ghost !py-1.5" onClick={load} title={L("Refresh", "ताज़ा करें")}><RefreshCw size={14} /></button>
          <button className="btn-ghost !py-1.5" onClick={signOut} title={L("Sign out / switch branch", "बाहर निकलें / शाखा बदलें")}><LogOut size={14} />{branch ? (lenders[branch] || branch).split(", ")[0] : L("Sign out", "बाहर निकलें")}</button>
        </div>
      </div>
      {view === "economics" ? <Economics list={list} /> : (
        <div className="grid lg:grid-cols-[380px_1fr] gap-4">
          <div className="card divide-y divide-slate-100 h-fit">
            {list.map((a) => (
              <button key={a.id} onClick={() => setSel(a.id)} className={`w-full text-left p-3 hover:bg-slate-50 ${sel === a.id ? "bg-brand-50/60" : ""}`}>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-[13px] flex-1 line-clamp-1">{a.applicant}</span>{a.band && <BandChip band={a.band} />}
                </div>
                {a.redacted ? <div className="text-[12px] text-ink-400">{a.id} · {L("withdrawn by the entrepreneur, contents erased", "उद्यमी ने वापस लिया, सामग्री मिटा दी गई")}</div>
                  : <div className="text-[12px] text-ink-500">{lang === "hi" ? (a.scheme_hi || a.scheme) : a.scheme} · {inr(a.amount)} · {a.district} · {factValue(reg, "activity", a.activity, lang)}</div>}
                <div className="flex gap-1 mt-1 flex-wrap">
                  {!a.redacted && <span className={`pill ${a.complete ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{a.complete
                    ? L("all pre-sanction items in", "स्वीकृति से पहले की सब चीज़ें मौजूद") : L(`${a.pending_items.length} item(s) pending`, `${a.pending_items.length} चीज़ें बाकी`)}</span>}
                  {a.superseded && <span className="pill bg-rose-100 text-rose-800">{L("changed, awaiting re-approval", "बदली गई, दोबारा मंज़ूरी बाकी")}</span>}
                  <span className="pill bg-slate-100 capitalize">{appStatus(a.status, lang)}</span>
                  {a.schedule_type && <span className="pill bg-slate-100">{appStatus(a.schedule_type, lang)}</span>}
                </div>
              </button>
            ))}
            {!list.length && <div className="p-4 text-ink-400 text-sm">{L("No applications addressed to this branch yet. Submit one from the entrepreneur app.", "इस शाखा को अभी कोई आवेदन नहीं भेजा गया। उद्यमी ऐप से एक भेजें।")}</div>}
          </div>
          {sel && <Detail id={sel} onDecided={load} />}
        </div>
      )}
    </div>
  );
}

function Detail({ id, onDecided }: { id: string; onDecided: () => void }) {
  const { lang } = useLang();
  const L = useL();
  const reg = useFactReg();
  const [a, setA] = useState<any>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("overview");
  const [amt, setAmt] = useState<number>(0);
  const [note, setNote] = useState("");
  const [reasons, setReasons] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const attempt = useRef<{ key: string; id: string } | null>(null);  // same request, same id: a retry is a replay
  useEffect(() => {
    setA(null); setErr("");
    api.lenderGet(id).then((x: any) => { setA(x); setAmt(x.package.offer.amount || 0); }).catch((e) => setErr(e.message));
  }, [id]);
  if (err) return <div className="card p-4 text-rose-700"><Lock size={16} className="inline mr-1" />{err}</div>;
  if (!a) return <div className="card p-4 text-ink-400">{L("Loading…", "लोड हो रहा है…")}</div>;
  const d = a.detail, p = a.package, s = d.score;
  const m = d.monthly;
  const st = p.statement || {};
  const nMonths = m?.months?.length || 0;
  const srcLabel = st.source === "upload" ? L("entrepreneur-uploaded CSV", "उद्यमी द्वारा अपलोड CSV") : L("Account Aggregator, consented", "अकाउंट एग्रीगेटर, सहमति से");
  const locked = a.status === "withdrawn" || a.summary.superseded || ["sanctioned", "declined"].includes(a.status);
  const cf = m ? m.months.map((mk: string, i: number) => ({ m: mlabel(mk), income: Math.round(m.biz_in[i]), inputs: Math.round(m.biz_out[i]), emi: Math.round(m.emi_out[i] + m.informal_out[i]) })) : [];
  const docLabel = (code: string) => { const it = d.documents?.items?.find((x: any) => x.doc === code); return it ? t(it.label, lang) : code.replace(/_/g, " "); };
  async function decide(decision: string) {
    const body: any = { decision, amount: decision === "sanction" ? amt : null, note: note || null,
      reasons: decision === "decline" ? reasons : null };
    const key = JSON.stringify(body);
    if (!attempt.current || attempt.current.key !== key) {
      attempt.current = { key, id: (crypto as any).randomUUID ? (crypto as any).randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2, 10)}` };
    }
    setSending(true);
    try {
      await api.decide(id, { ...body, request_id: attempt.current.id });
      attempt.current = null;  // recorded: the next action gets a new id
      setReasons([]); setNote("");
      setA(await api.lenderGet(id)); onDecided();
    } catch (e: any) { setErr(e.message); }
    setSending(false);
  }
  const f = d.facts;
  return (
    <div className="space-y-3">
      <div className="card p-4">
        <div className="flex flex-wrap items-start gap-3">
          <div className="flex-1 min-w-[240px]">
            <div className="text-lg font-bold">{a.summary.applicant}</div>
            <div className="text-[13px] text-ink-500">{factValue(reg, "activity", f.activity, lang)} · {f.district}, {f.state} ({factValue(reg, "area_type", f.area_type, lang)}) · {f.years_in_business != null
              ? L(`${f.years_in_business} yrs`, `${f.years_in_business} साल`) : L("vintage not asked", "व्यवसाय की उम्र नहीं पूछी")} · {factValue(reg, "ownership_type", f.ownership_type, lang)}</div>
            <div className="text-[12px] text-ink-400 mt-1">{a.id} · LOS {a.los_ref} · {a.lender.name}</div>
          </div>
          <div className="text-right">
            <div className="label">{L("Recommended", "सुझाई राशि")}</div><div className="text-2xl font-bold">{inr(p.offer.amount)}</div>
            {!!p.offer.provisional?.length && <div className="text-[11px] text-amber-700">{L("scheme match provisional, ", "योजना मिलान अस्थायी, ")}{p.offer.provisional.map((x: any) => t(x.by, lang)).join(", ")}{L(" to verify", " सत्यापित करेगा")}</div>}
            <div className="text-[12px] text-ink-500">{sname(d.schemes?.find((r: any) => r.id === p.offer.scheme_id) || p.offer, lang)} · {(p.offer.rate * 100).toFixed(1)}% · {p.offer.tenure}{L("m", " माह")} · {appStatus(p.schedule_type, lang)}</div>
          </div>
          <div className="text-right"><div className="label">{L("Simulated risk estimate", "सिम्युलेटेड जोखिम अनुमान")}</div><BandChip band={p.risk.band} pd={p.risk.pd} />
            <div className="text-[11px] text-ink-400">{L("range", "दायरा")} {pct(p.risk.pd_low)}–{pct(p.risk.pd_high)} · {L("score", "स्कोर")} {p.risk.score}</div>
            <div className="text-[10px] text-ink-400 max-w-[220px]">{L("Model trained on synthetic data, not a validated probability of default.", "मॉडल कृत्रिम डेटा पर प्रशिक्षित है; यह चूक की सत्यापित संभावना नहीं है।")}</div></div>
        </div>
        {d.offer?.against_advice && <div className="mt-2 text-[12px] rounded-lg bg-rose-50 text-rose-800 p-2">{L("Entrepreneur chose to apply although Saakh advised waiting, see reasons.", "साख ने रुकने की सलाह दी थी, फिर भी उद्यमी ने आवेदन चुना; कारण देखें।")}</div>}
        {a.summary.superseded && <div className="mt-2 text-[12px] rounded-lg bg-rose-50 text-rose-800 p-2">{L(
          `The entrepreneur changed this file after sending it (${a.superseded_reason}). Decisions are locked until they re-approve and re-send it.`,
          `उद्यमी ने भेजने के बाद यह फ़ाइल बदली (${a.superseded_reason})। जब तक वे दोबारा मंज़ूरी देकर फिर न भेजें, फ़ैसले बंद हैं।`)}</div>}
        {!!p.disputes?.length && <div className="mt-2 text-[12px] rounded-lg bg-amber-50 text-amber-900 p-2">
          <b>{L(`Entrepreneur disputes ${p.disputes.length} sourced value(s)`, `उद्यमी ${p.disputes.length} स्रोत वाले मान से असहमत है`)}</b>{L("; Saakh kept the sourced value; please check:", "; साख ने स्रोत वाला मान रखा है; कृपया जाँचें:")}
          {p.disputes.map((x: any) => <div key={x.fact}>· {factLabel(reg, x.fact, lang)} ({L("from", "स्रोत")} {x.source}): {L("entrepreneur says", "उद्यमी के अनुसार")} {factValue(reg, x.fact, x.claimed, lang)}{x.reason ? `, "${x.reason}"` : ""}</div>)}</div>}
        {!!a.summary.pending_items?.length && <div className="mt-2 text-[12px] rounded-lg bg-amber-50 text-amber-800 p-2">{L("Pending before sanction: ", "स्वीकृति से पहले बाकी: ")}{a.summary.pending_items.map(docLabel).join(", ")}</div>}
      </div>
      <div className="flex gap-1 flex-wrap">
        {[["overview", L("Cash flow", "नकदी प्रवाह")], ["score", L("Scorecard", "स्कोरकार्ड")], ["schemes", L("Eligibility (cited)", "पात्रता (स्रोत सहित)")],
          ["docs", L("Documents", "दस्तावेज़")], ["integrity", L("Consent & integrity", "सहमति और अखंडता")]].map(([k, l]) =>
          <button key={k} className={`tab ${tab === k ? "tab-on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}
        <button className="btn-ghost ml-auto !py-1.5" onClick={() => openPdf(`/api/lender/applications/${id}/memo.pdf`, "lender")}><FileDown size={14} />{L("Credit memo PDF", "क्रेडिट मेमो PDF")}</button>
        <button className="btn-ghost !py-1.5" onClick={() => openPdf(`/api/lender/applications/${id}/dpr.pdf`, "lender")}><FileDown size={14} />DPR</button>
      </div>
      {lang === "hi" && <div className="text-[11px] text-ink-400">PDF दस्तावेज़ बैंक के लिए अंग्रेज़ी में रहते हैं।</div>}

      {tab === "overview" && (
        <div className="grid md:grid-cols-2 gap-3">
          <div className="card p-3">
            <div className="label">{L(`Monthly cash flow, ${nMonths} months (${srcLabel})`, `मासिक नकदी प्रवाह, ${nMonths} महीने (${srcLabel})`)}{st.from ? ` · ${st.from} ${L("to", "से")} ${st.to}` : ""}</div>
            {nMonths < 12 && <div className="text-[11px] text-amber-700">{L("Short history: annual figures are scaled up and a full seasonal cycle is not observed.", "छोटा इतिहास: सालाना आँकड़े बढ़ाकर अनुमानित हैं और पूरा मौसमी चक्र नहीं दिखा।")}</div>}
            <div className="h-56 -ml-2 mt-1"><ResponsiveContainer><BarChart data={cf}>
              <CartesianGrid vertical={false} stroke="#eef2f6" /><XAxis dataKey="m" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip formatter={(v: any) => inr(v)} /><Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="income" fill="#14917f" name={L("Business inflow", "व्यवसाय की आय")} /><Bar dataKey="inputs" fill="#94a3b8" name={L("Inputs & opex", "कच्चा माल और खर्च")} /><Bar dataKey="emi" fill="#ea8f12" name={L("Debt service", "कर्ज़ की किस्तें")} />
            </BarChart></ResponsiveContainer></div>
          </div>
          <div className="card p-3 space-y-2">
            <div className="label">{L("Findings", "निष्कर्ष")}</div>
            {(d.insights || []).map((x: any, i: number) => <div key={i} className="text-[13px]"><b>{t(x.title, lang)}.</b> <span className="text-ink-500">{t(x.detail, lang)}</span></div>)}
            <div className="label pt-2">{L("Bureau", "क्रेडिट ब्यूरो")}</div>
            <div className="text-[13px]">{d.bureau
              ? L(`Score ${d.bureau.score ?? "NTC (new to credit)"} · ${d.bureau.loans.length} active loan(s)`, `स्कोर ${d.bureau.score ?? "NTC (पहली बार ऋण)"} · ${d.bureau.loans.length} चालू ऋण`)
              : L("Not pulled (consent declined)", "नहीं देखा गया (सहमति नहीं दी)")} <SimBadge /></div>
            {d.offer && <><div className="label pt-2">{L("Proposed schedule", "प्रस्तावित किस्त योजना")}</div><ScheduleChart o={d.offer} kind={p.schedule_type} /></>}
          </div>
        </div>
      )}

      {tab === "score" && s && (
        <div className="card p-3">
          <div className="text-[12px] text-ink-400 mb-2">{L("Monotone WoE scorecard, each factor's points come from a published table. Gender, caste, religion and location are never inputs.",
            "एक-दिशा WoE स्कोरकार्ड: हर कारक के अंक एक प्रकाशित तालिका से आते हैं। लिंग, जाति, धर्म और स्थान कभी इनपुट नहीं होते।")}</div>
          <table className="w-full text-[12.5px]">
            <thead><tr className="text-left text-ink-400"><th className="py-1">{L("Factor", "कारक")}</th><th>{L("Applicant", "आवेदक")}</th><th>{L("Bin", "श्रेणी")}</th><th className="w-48">{L("Points / max", "अंक / अधिकतम")}</th></tr></thead>
            <tbody>{s.contributions.map((x: any) => (
              <tr key={x.feature} className="border-t border-slate-100">
                <td className="py-1.5">{t(x.label, lang)}</td><td>{x.display}</td><td className="text-ink-500">{x.bin}</td>
                <td><div className="flex items-center gap-2"><div className="flex-1 h-2 rounded bg-slate-100 overflow-hidden">
                  <div className={`h-2 ${x.gap > 8 ? "bg-rose-400" : x.gap > 2 ? "bg-amber-400" : "bg-emerald-500"}`} style={{ width: `${Math.max(4, (x.points / Math.max(x.max_points, 1)) * 100)}%` }} /></div>
                  <span className="text-[11px] w-14 text-right">{Math.round(x.points)}/{Math.round(x.max_points)}</span></div></td>
              </tr>))}</tbody>
          </table>
          <div className="grid md:grid-cols-2 gap-3 mt-3">
            <div><div className="label">{L("Reason codes (points lost)", "कारण कोड (कटे अंक)")}</div>{s.reason_codes.map((r: any) => <div key={r.feature} className="text-[13px]">• {t(r.label, lang)}, {Math.round(r.points_lost)} {L("pts", "अंक")}</div>)}</div>
            <div><div className="label">{L("Strengths", "मज़बूत पक्ष")}</div>{s.strengths.map((r: any) => <div key={r.feature} className="text-[13px]">• {t(r.label, lang)} ({r.display})</div>)}</div>
          </div>
          <div className="text-[11px] text-ink-400 mt-2">{L("Model", "मॉडल")} {s.model_version} · {s.thin_file ? L("thin file, interval widened", "कम इतिहास, दायरा चौड़ा किया") : L(`${nMonths}-month history`, `${nMonths} महीने का इतिहास`)}</div>
        </div>
      )}

      {tab === "schemes" && (
        <div className="card p-3 space-y-2">
          {d.schemes.map((r: any) => (
            <div key={r.id} className="border-t border-slate-100 pt-2 first:border-0 first:pt-0">
              <div className="flex items-center gap-2 text-[13px]"><b className="flex-1">{sname(r, lang)}</b><StatusPill s={r.eligibility} provisional={r.provisional} />
                {Object.entries(r.verification || {}).filter(([, n]: any) => n).map(([v, n]: any) => <span key={v} className="text-[10px]">{n}× <VerBadge v={v} /></span>)}</div>
              {r.status_note && <div className="text-[12px] text-rose-800">{t(r.status_note, lang)}</div>}
              {r.failing.map((x: any, i: number) => <div key={i} className="text-[12px] text-ink-500">✗ {t(x.text, lang)}<CiteChip c={x.cite} /></div>)}
              {r.eligibility === "eligible" && <div className="text-[12px] text-emerald-700">✓ {L(`${r.citations.length} cited criteria met`, `स्रोत सहित ${r.citations.length} शर्तें पूरी`)} {r.citations.slice(0, 6).map((c: any, i: number) => <CiteChip key={i} c={c} n={i + 1} />)}</div>}
            </div>))}
        </div>)}

      {tab === "docs" && d.documents && (
        <div className="card p-3">
          <div className="flex gap-3 mb-2 flex-wrap"><Stat label={L("Items", "कुल")} value={d.documents.counts.total} /><Stat label={L("Auto-fetched", "अपने आप मिले")} value={d.documents.counts.auto} />
            <Stat label={L("Prepared by Saakh", "साख ने बनाए")} value={d.documents.counts.generated} />
            <Stat label={L("Pending (pre-sanction)", "बाकी (स्वीकृति से पहले)")} value={a.summary.pending_items.length} tone={a.summary.pending_items.length ? "text-amber-700" : "text-emerald-700"} /></div>
          {p.documents.map((i: any) => {
            const item = d.documents.items.find((x: any) => x.doc === i.doc);
            return (
              <div key={i.doc} className="text-[13px] py-1.5 border-t border-slate-100 flex items-center gap-2">
                <span className="flex-1">{item ? t(item.label, lang) : i.doc} <span className="text-ink-400 text-[11px]">· {viaName(item?.via, lang)}</span>
                  {i.attachment && <span className="block text-[10px] font-mono text-ink-400">sha256 {i.attachment.sha256.slice(0, 20)}… · {kb(i.attachment.bytes)} · {L("not read by Saakh", "साख ने नहीं पढ़ा")}</span>}</span>
                <span className={`pill ${i.status === "ready" ? "bg-emerald-100 text-emerald-800" : i.post_sanction ? "bg-slate-100" : "bg-amber-100 text-amber-800"}`}>
                  {i.status === "ready" ? L("in file", "फ़ाइल में") : i.post_sanction ? L("after sanction", "स्वीकृति के बाद") : i.scheduled_offline ? L("JanAI Café visit pending", "JanAI कैफ़े जाना बाकी") : L("pending", "बाकी")}</span>
                {i.attachment && <button className="btn-ghost !py-1 !text-xs" onClick={async () => {
                  const e = await downloadAttachment(`/api/lender/applications/${id}/documents/${i.doc}`, i.attachment.sha256, `${id}-${i.doc}`);
                  if (e) setErr(`${L("Attachment", "संलग्न फ़ाइल")} ${i.doc}: ${e}`);
                }}><Paperclip size={12} />{L("Download", "डाउनलोड")}</button>}
              </div>);
          })}
          <div className="text-[11px] text-ink-400 mt-2">{L("Each download is re-verified against the fingerprint the entrepreneur approved and recorded in their audit log.",
            "हर डाउनलोड को उस फ़िंगरप्रिंट से दोबारा मिलाया जाता है जिसे उद्यमी ने मंज़ूर किया और अपने ऑडिट लॉग में दर्ज किया।")}</div>
        </div>
      )}

      {tab === "integrity" && (
        <div className="card p-3 space-y-2 text-[13px]">
          {[[L("Package hash matches what was approved", "फ़ाइल का हैश मंज़ूर फ़ाइल से मेल खाता है"), a.integrity.package_hash_ok],
            [L("Entrepreneur approval bound to this exact file", "उद्यमी की मंज़ूरी इसी फ़ाइल से बँधी है"), a.integrity.approval_bound],
            [L("Audit hash chain intact", "ऑडिट हैश श्रृंखला सही-सलामत"), a.integrity.audit.ok]].map(([l, ok]: any, i: number) =>
            <div key={i} className="flex items-center gap-2">{ok ? <CheckCircle2 size={16} className="text-emerald-600" /> : <XCircle size={16} className="text-rose-600" />}{l}</div>)}
          <div className="text-[11px] font-mono text-ink-400 break-all">file {a.hash}<br />audit head {a.integrity.audit.head}</div>
          <div className="label pt-2">{L("Active consents shared with this branch", "इस शाखा के साथ साझा सक्रिय सहमतियाँ")}</div>
          {a.consents.map((x: any) => <div key={x.consentId} className="text-[12.5px]"><ShieldCheck size={13} className="inline text-brand-600 mr-1" />{t(x.title, lang)}, {t(x.purpose.text, lang)}</div>)}
          <div className="text-[11px] text-ink-400">{L("If the entrepreneur revokes the sharing consent, this file becomes unavailable here.", "अगर उद्यमी साझा करने की सहमति वापस लेता है, तो यह फ़ाइल यहाँ उपलब्ध नहीं रहेगी।")}</div>
        </div>
      )}

      <div className="card p-3">
        <div className="label mb-2">{L("Branch decision", "शाखा का फ़ैसला")} {a.decision && <span className="pill bg-slate-100 ml-1 capitalize">{appStatus(a.decision.decision, lang)} · {a.decision.ts}</span>}</div>
        <div className="flex flex-wrap gap-2 items-center">
          <input type="number" value={amt} onChange={(e) => setAmt(Number(e.target.value))} className="w-36 rounded-xl border border-slate-200 px-3 py-2 text-sm" />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={L("Note / query (e.g. shop rent agreement)", "टिप्पणी / सवाल (जैसे दुकान का किराया अनुबंध)")} className="flex-1 min-w-[200px] rounded-xl border border-slate-200 px-3 py-2 text-sm" />
          <button className="btn-primary" disabled={locked || sending} onClick={() => decide("sanction")}><CheckCircle2 size={14} />{L("Sanction", "स्वीकृत करें")}</button>
          <button className="btn-warn" disabled={locked || sending || !note.trim()} title={L("Write the query in the note", "सवाल टिप्पणी में लिखें")} onClick={() => decide("query")}><HelpCircle size={14} />{L("Query", "सवाल पूछें")}</button>
          <button className="btn-ghost text-rose-700" disabled={locked || sending || !reasons.length} title={L("Pick the branch's reason(s) first", "पहले शाखा के कारण चुनें")} onClick={() => decide("decline")}><XCircle size={14} />{L("Decline", "अस्वीकार करें")}</button>
        </div>
        {!locked && <div className="mt-2 text-[12px]">
          <div className="label">{L("Branch's reasons (required to decline; the entrepreneur sees these)", "शाखा के कारण (अस्वीकार के लिए ज़रूरी; उद्यमी इन्हें देखता है)")}</div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">{LENDER_REASONS.map(([code, en, hi]) => (
            <label key={code} className="flex items-center gap-1"><input type="checkbox" className="accent-rose-600" checked={reasons.includes(code)}
              onChange={(e) => setReasons(e.target.checked ? [...reasons, code] : reasons.filter((r) => r !== code))} />{L(en, hi)}</label>))}</div>
          <div className="text-[11px] text-ink-400 mt-1">{L("Saakh's scorecard factors (Scorecard tab) are reference only and are not sent as the bank's reasons.",
            "साख के स्कोरकार्ड कारक (स्कोरकार्ड टैब) केवल संदर्भ के लिए हैं और बैंक के कारणों के रूप में नहीं भेजे जाते।")}</div>
        </div>}
      </div>
    </div>
  );
}

function Economics({ list }: { list: any[] }) {
  const L = useL();
  const { lang } = useLang();
  const [v, setV] = useState({ files: 60, incompleteNow: 0.45, cycles: 2.2, hours: 1.6, rate: 750, incompleteSaakh: 0.05, travel: 0.25, ticket: 300000, agentFee: 0.12 });
  const set = (k: string) => (e: any) => setV({ ...v, [k]: Number(e.target.value) });
  const reworkNow = v.files * v.incompleteNow * v.cycles * v.hours * (1 + v.travel);
  const reworkSaakh = v.files * v.incompleteSaakh * v.cycles * v.hours * (1 + v.travel);
  const saved = (reworkNow - reworkSaakh) * v.rate;
  const fields: [string, string, number][] = [
    ["files", L("Files / month / branch", "फ़ाइलें / महीना / शाखा"), 1],
    ["incompleteNow", L("Share incomplete today", "आज अधूरी फ़ाइलों का हिस्सा"), 0.01],
    ["cycles", L("Rework cycles per incomplete file", "हर अधूरी फ़ाइल पर दोबारा काम के चक्र"), 0.1],
    ["hours", L("Officer hours per cycle", "हर चक्र में अधिकारी के घंटे"), 0.1],
    ["travel", L("Extra for visits/follow-up (share)", "दौरे / फ़ॉलो-अप का अतिरिक्त हिस्सा"), 0.05],
    ["rate", L("Loaded cost / officer-hour (₹)", "अधिकारी के एक घंटे की कुल लागत (₹)"), 50],
    ["incompleteSaakh", L("Share incomplete with Saakh", "साख के साथ अधूरी फ़ाइलों का हिस्सा"), 0.01],
    ["ticket", L("Average loan (₹)", "औसत ऋण (₹)"), 10000],
    ["agentFee", L("Agent fee avoided (share of loan)", "बचा एजेंट शुल्क (ऋण का हिस्सा)"), 0.01]];
  return (
    <div className="grid lg:grid-cols-[380px_1fr] gap-4">
      <div className="card p-4 space-y-2">
        <div className="font-semibold">{L("Assumptions", "मान्यताएँ")} <span className="text-[11px] text-ink-400 font-normal">{L("- hypotheses to validate in field research", "- फ़ील्ड रिसर्च में जाँचने वाली परिकल्पनाएँ")}</span></div>
        {fields.map(([k, l, step]) => (
          <label key={k} className="flex items-center gap-2 text-[13px]"><span className="flex-1">{l}</span>
            <input type="number" step={step} value={(v as any)[k]} onChange={set(k)} className="w-28 rounded-lg border border-slate-200 px-2 py-1 text-right" /></label>))}
      </div>
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label={L("Officer hours freed / month", "हर महीने बचे अधिकारी-घंटे")} value={Math.round(reworkNow - reworkSaakh)} sub={L("per branch", "प्रति शाखा")} tone="text-brand-700" />
          <Stat label={L("Rework cost avoided / month", "हर महीने बची दोबारा काम की लागत")} value={inr(saved)} sub={L("per branch", "प्रति शाखा")} tone="text-brand-700" />
          <Stat label={L("… per year, 100 branches", "… प्रति वर्ष, 100 शाखाएँ")} value={inr(saved * 12 * 100, true)} />
          <Stat label={L("Agent fees avoided / borrower", "प्रति उधारकर्ता बचा एजेंट शुल्क")} value={inr(v.ticket * v.agentFee)} sub={L("at the stated fee share", "बताए गए शुल्क हिस्से पर")} tone="text-emerald-700" />
        </div>
        <div className="card p-4 text-[13px] text-ink-700 space-y-2">
          <div className="font-semibold">{L("Who pays, business model", "भुगतान कौन करता है: व्यवसाय मॉडल")}</div>
          {lang !== "hi" ? (
            <p>Lenders pay Saakh per <b>complete, consented, pre-appraised file</b> (₹150–400 per file, set below the rework cost avoided above), and a success fee on disbursal. Entrepreneurs pay nothing; that replaces the 10–15% agent cut. DICs and SHG federations use Saakh's cohort screening to meet scheme targets. JanAI Cafés earn an assisted-service fee from lenders.</p>
          ) : (
            <p>बैंक साख को हर <b>पूरी, सहमति वाली, पहले से जाँची फ़ाइल</b> के लिए भुगतान करते हैं (₹150–400 प्रति फ़ाइल, ऊपर दिखी बची लागत से कम), और ऋण बँटने पर सफलता शुल्क। उद्यमी कुछ नहीं देते; इससे 10–15% एजेंट कमीशन ख़त्म होता है। ज़िला उद्योग केंद्र और स्वयं सहायता समूह महासंघ योजना लक्ष्य पूरे करने के लिए साख की सामूहिक जाँच का उपयोग करते हैं। JanAI कैफ़े बैंकों से सहायता शुल्क कमाते हैं।</p>
          )}
          <p className="text-ink-500">{L(`Live portfolio here: ${list.length} file(s), ${list.filter((a) => a.complete).length} complete on first submission.`,
            `यहाँ की लाइव सूची: ${list.length} फ़ाइलें, जिनमें ${list.filter((a) => a.complete).length} पहली बार में ही पूरी।`)}</p>
        </div>
      </div>
    </div>
  );
}
