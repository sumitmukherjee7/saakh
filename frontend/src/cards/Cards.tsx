import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { ShieldCheck, Lock, Clock, FileCheck2, Upload, Store, Sparkles, AlertTriangle, TrendingUp, Landmark, CheckCircle2, Info, Wand2 } from "lucide-react";
import { BandChip, CiteChip, ProofTree, SimBadge, StatusPill, VerBadge } from "../components/common";
import { inr, kb, mlabel, MONTHS, pct, sname, t, UI, useLang } from "../util";
import { appStatus, consentStatus, factLabel, factValue, providerName, useFactReg, viaName } from "../facts";

type Ctx = { upload: (doc: string, f: File) => void; uploadStatement: (f: File, consent: boolean, otp?: string) => void; demo: boolean };
type P = { card: any; c: any; act: (ev: any) => void; active: boolean; ctx?: Ctx };

export function CardView(p: P) {
  const m: any = { consent: ConsentCard, question: QuestionCard, insights: InsightsCard, schemes: SchemesCard, action: ActionCard,
    offers: OffersCard, not_now: NotNowCard, documents: DocumentsCard, approval: ApprovalCard, submitted: SubmittedCard,
    explanation: ExplanationCard, plan: PlanCard, suggestion: SuggestionCard, fallback_statement: FallbackCard, lender: LenderCard,
    reasons: ReasonsCard };
  const C = m[p.card.type];
  return C ? <C {...p} /> : null;
}

function Shell({ children, tone = "white" }: { children: any; tone?: string }) {
  return <div className={`mt-2 rounded-2xl border p-3 ${tone === "white" ? "bg-white border-slate-200" : tone}`}>{children}</div>;
}

function SuggestionCard({ card, act, active }: P) {
  const { lang } = useLang();
  if (!active) return null;
  return (
    <Shell tone="bg-brand-50 border-brand-200">
      <div className="label mb-1">{lang === "hi" ? "उदाहरण (टैप करें)" : "Example (tap to use)"}</div>
      <button className="text-left text-sm text-brand-900" onClick={() => act({ type: "message", text: t(card.text, lang) })}>
        “{t(card.text, lang)}”
      </button>
    </Shell>
  );
}

function PlanCard({ card }: P) {
  const { lang } = useLang();
  const reg = useFactReg();
  const ex = card.extracted || {};
  const keys = Object.keys(ex);
  if (!keys.length) return null;
  return (
    <Shell>
      <div className="label mb-1">{lang === "hi" ? "आपकी बात से समझा" : "Understood from your words"}</div>
      <div className="flex flex-wrap gap-1.5">
        {keys.map((k) => <span key={k} className="pill bg-slate-100 text-ink-700">{factLabel(reg, k, lang)}: {typeof ex[k] === "number" ? inr(ex[k]) : factValue(reg, k, ex[k], lang)}</span>)}
      </div>
    </Shell>
  );
}

function ConsentCard({ card, act, active, c }: P) {
  const { lang } = useLang();
  const [sel, setSel] = useState<Record<string, boolean>>(() => Object.fromEntries(card.consents.map((x: any) => [x.consentId, !!x.required])));
  const [otp, setOtp] = useState("");
  const live = Object.fromEntries((c.consents || []).map((x: any) => [x.consentId, x.status]));
  return (
    <Shell>
      <div className="flex items-center gap-2 mb-2"><ShieldCheck size={16} className="text-brand-600" />
        <span className="font-semibold text-sm">{lang === "hi" ? "आपकी अनुमति" : "Your permission"}</span><SimBadge /></div>
      <div className="space-y-2">
        {card.consents.map((x: any) => (
          <label key={x.consentId} className={`flex gap-3 rounded-xl border p-2.5 ${sel[x.consentId] ? "border-brand-200 bg-brand-50/40" : "border-slate-200"}`}>
            <input type="checkbox" className="mt-1 accent-brand-600" disabled={!active || x.required}
              checked={!!sel[x.consentId]} onChange={(e) => setSel({ ...sel, [x.consentId]: e.target.checked })} />
            <span className="flex-1 text-[13px]">
              <span className="font-semibold text-ink-900">{t(x.title, lang)}</span>
              {x.required && <span className="pill bg-slate-100 text-ink-500 ml-1">{lang === "hi" ? "ज़रूरी" : "needed"}</span>}
              <span className="block text-ink-500">{t(x.data, lang)}</span>
              <span className="block text-ink-400 text-[11px] mt-0.5">
                {lang === "hi" ? "उद्देश्य" : "Purpose"}: {t(x.purpose.text, lang)} · {providerName(x.provider, lang)} · {lang === "hi" ? `अवधि ${x.dataLife.value} महीने` : `valid ${x.dataLife.value} ${x.dataLife.unit.toLowerCase()}(s)`}
                {!active && live[x.consentId] && <span className="ml-1 font-semibold">· {consentStatus(live[x.consentId], lang)}</span>}
              </span>
            </span>
          </label>
        ))}
      </div>
      {active && (
        <div className="mt-3 flex items-center gap-2">
          {card.otp_required && (
            <input value={otp} onChange={(e) => setOtp(e.target.value)} placeholder={lang === "hi" ? "उद्यमी का OTP" : "Entrepreneur's OTP"}
              inputMode="numeric" className="w-40 rounded-xl border border-slate-200 px-3 py-2 text-sm" />)}
          <button className="btn-primary flex-1" onClick={() => act({ type: "consent", decisions: sel, otp })}>
            <Lock size={14} />{t(UI.approveSelected, lang)}</button>
        </div>
      )}
    </Shell>
  );
}

function QuestionCard({ card, act, active, c }: P) {
  const { lang } = useLang();
  const f = card.fact;
  const [num, setNum] = useState("");
  const answered = c.facts?.[f.key];
  return (
    <Shell>
      {card.affects?.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 mb-2">
          <span className="label">{lang === "hi" ? "इससे तय होगा" : "This decides"}</span>
          {card.affects.slice(0, 4).map((a: any) => <span key={a.id} className="pill bg-saffron-50 text-saffron-600 border border-saffron-100">{sname(a, lang)}</span>)}
        </div>
      )}
      {active ? (
        f.options?.length ? (
          <div className={`grid gap-2 ${f.options.length > 4 ? "grid-cols-2" : "grid-cols-2"}`}>
            {f.options.map((o: any) => (
              <button key={String(o.value)} className="btn-ghost justify-start text-left !py-3"
                onClick={() => act({ type: "answer", fact: f.key, value: o.value })}>{t(o.label, lang)}</button>
            ))}
          </div>
        ) : (
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (num) act({ type: "answer", fact: f.key, value: Number(num) }); }}>
            <input inputMode="numeric" value={num} onChange={(e) => setNum(e.target.value.replace(/[^0-9]/g, ""))}
              className="flex-1 rounded-xl border border-slate-200 px-3 py-2.5 text-sm" placeholder={f.unit === "INR" ? "₹" : f.unit || ""} />
            <button className="btn-primary">OK</button>
          </form>
        )
      ) : null}
      {(card.why || f.why) && (
        <div className="mt-2 flex gap-1.5 text-[11px] text-ink-500"><Info size={12} className="mt-0.5 shrink-0" />
          <span><b>{t(UI.why, lang)}:</b> {t(card.why || f.why, lang)}{f.sensitive && (lang === "hi" ? " · वैकल्पिक, क्रेडिट स्कोर में उपयोग नहीं" : " · optional, never used in credit scoring")}</span></div>
      )}
      {active && (f.sensitive || f.key === "informal_outstanding") && (
        <button className="mt-2 text-xs text-ink-400 underline" onClick={() => act({ type: "skip", fact: f.key })}>{t(UI.skip, lang)}</button>
      )}
    </Shell>
  );
}

function InsightsCard({ card }: P) {
  const { lang } = useLang();
  const m = card.monthly;
  const data = m.months.map((mk: string, i: number) => ({ m: mlabel(mk), income: Math.round(m.biz_in[i]),
    costs: Math.round(m.biz_out[i] + m.hh_out[i] - (m.transfers_out?.[i] || 0) + m.emi_out[i] + m.informal_out[i]) }));
  const tone: any = { good: "text-emerald-700", info: "text-ink-700", warn: "text-amber-700", bad: "text-rose-700" };
  return (
    <Shell>
      <div className="flex items-center gap-2"><TrendingUp size={16} className="text-brand-600" />
        <span className="font-semibold text-sm">{card.source === "upload" ? (lang === "hi" ? "आपके अपलोड किए विवरण से" : "From the statement you uploaded")
          : (lang === "hi" ? "आपके खाते से (AA)" : "From your account (AA)")}</span>
        <span className={`pill ${card.months && card.months < 12 ? "bg-amber-100 text-amber-800" : "bg-slate-100"}`}>{card.months ?? m.months.length} {lang === "hi" ? "महीने" : "months"}</span>
        {card.simulated && <SimBadge />}</div>
      <div className="h-36 mt-2 -ml-3">
        <ResponsiveContainer>
          <BarChart data={data}>
            <XAxis dataKey="m" tick={{ fontSize: 9 }} interval={1} />
            <YAxis tick={{ fontSize: 9 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} width={34} />
            <Tooltip formatter={(v: any) => inr(v)} />
            <Bar dataKey="income" fill="#14917f" radius={[3, 3, 0, 0]} name={lang === "hi" ? "व्यावसायिक आय" : "Business income"} />
            <Bar dataKey="costs" fill="#cbd5e1" radius={[3, 3, 0, 0]} name={lang === "hi" ? "खर्च" : "Spending"} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="space-y-1.5 mt-1">
        {card.insights.map((x: any) => (
          <div key={x.id + t(x.title, "en")} className="text-[13px]">
            <span className={`font-semibold ${tone[x.tone]}`}>{t(x.title, lang)}.</span> <span className="text-ink-500">{t(x.detail, lang)}</span>
          </div>
        ))}
      </div>
    </Shell>
  );
}

export function SchemeRow({ r, open, onToggle }: { r: any; open: boolean; onToggle: () => void }) {
  const { lang } = useLang();
  const reg = useFactReg();
  return (
    <div className="rounded-xl border border-slate-200">
      <button className="w-full flex items-center gap-2 p-2.5 text-left" onClick={onToggle}>
        <span className="flex-1">
          <span className="font-semibold text-[13px] text-ink-900">{sname(r, lang)}</span>
          {r.availability === "unconfirmed" && <span className="pill bg-rose-50 text-rose-700 border border-rose-200 ml-1">{lang === "hi" ? "स्थिति अपुष्ट" : "status unconfirmed"}</span>}
          {r.availability === "unavailable" && <span className="pill bg-slate-100 text-slate-600 border border-slate-200 ml-1">{lang === "hi" ? "अभी उपलब्ध नहीं" : "not available now"}</span>}
          <span className="block text-[11px] text-ink-400 line-clamp-1">{t(r.summary, lang)}</span>
        </span>
        <StatusPill s={r.eligibility} kind={r.kind} provisional={r.provisional} />
      </button>
      {open && (
        <div className="px-3 pb-3 border-t border-slate-100">
          {r.status_note && (
            <div className="mt-2 rounded-lg bg-rose-50 p-2 text-[12px] text-rose-800">
              {t(r.status_note, lang)} {(r.status_cites || []).map((c: any, i: number) => <CiteChip key={i} c={c} />)}
            </div>
          )}
          <div className="mt-2"><ProofTree node={r.proof} cites={r.citations} /></div>
          {r.missing_facts?.length > 0 && <div className="text-[11px] text-amber-700 mt-1">{lang === "hi" ? "अभी अज्ञात" : "Still unknown"}: {r.missing_facts.map((k: string) => factLabel(reg, k, lang)).join(", ")}</div>}
          {r.benefits?.length > 0 && (
            <div className="mt-2 space-y-1">
              <div className="label">{lang === "hi" ? "लाभ" : "Benefits"}</div>
              {r.benefits.map((b: any, i: number) => (
                <div key={i} className="text-[12px] text-ink-700">• {t(b.label, lang)}{b.display && <b>: {b.display}</b>}<CiteChip c={b.cite} /></div>
              ))}
            </div>
          )}
          {r.caveats?.length > 0 && r.caveats.map((cv: any, i: number) => (
            <div key={i} className="mt-2 rounded-lg bg-amber-50 p-2 text-[12px] text-amber-800">⚠ {t(cv.text, lang)}<CiteChip c={cv.cite} /></div>))}
          {r.lender_checks?.length > 0 && (
            <div className="mt-2 space-y-1">
              <div className="label">{lang === "hi" ? "बैंक तय करेगा" : "Still decided by the lender"}</div>
              {r.lender_checks.map((lc: any, i: number) => (
                <div key={i} className="text-[12px] text-ink-600">• {t(lc.text, lang)}
                  {lc.status === "T" && <span className="text-emerald-700"> ✓</span>}{lc.status === "F" && <span className="text-rose-700"> ✗</span>}
                  <CiteChip c={lc.cite} /></div>))}
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-1">{Object.entries(r.verification || {}).filter(([, n]: any) => n > 0).map(([k, n]: any) =>
            <span key={k} className="text-[10px] text-ink-400">{n}× <VerBadge v={k} /></span>)}</div>
        </div>
      )}
    </div>
  );
}

function SchemesCard({ c }: P) {
  const { lang } = useLang();
  const [open, setOpen] = useState<string | null>(null);
  const list = c.schemes || [];
  return (
    <Shell>
      <div className="flex items-center gap-2 mb-2"><Landmark size={16} className="text-brand-600" />
        <span className="font-semibold text-sm">{lang === "hi" ? "योजनाएँ, हर दावे का स्रोत" : "Schemes, every claim cites its source"}</span></div>
      <div className="space-y-1.5">
        {list.map((r: any) => <SchemeRow key={r.id} r={r} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} />)}
      </div>
      <div className="text-[11px] text-ink-400 mt-2">{lang === "hi" ? "स्थिति आपके जवाबों के साथ लाइव अपडेट होती है।" : "Status updates live as you answer."}</div>
    </Shell>
  );
}

function ActionCard({ card, act, active }: P) {
  const { lang } = useLang();
  const a = card.action;
  return (
    <Shell tone="bg-saffron-50 border-saffron-100">
      <div className="flex items-center gap-2"><Wand2 size={16} className="text-saffron-600" />
        <span className="font-semibold text-sm">{t(a.label, lang)}</span><SimBadge /></div>
      <div className="text-[12px] text-ink-500 mt-1">{t(a.effort, lang)} · {lang === "hi" ? "इससे पूरी होगी शर्त" : "Unlocks"}: {a.unlocks.map((u: any) => sname(u, lang)).join(", ")}</div>
      {active && (
        <div className="flex gap-2 mt-3">
          <button className="btn-warn flex-1" onClick={() => act({ type: "action", action: a.action, go: true })}>{t(UI.doIt, lang)}</button>
          <button className="btn-ghost" onClick={() => act({ type: "action", action: a.action, go: false })}>{t(UI.later, lang)}</button>
        </div>
      )}
    </Shell>
  );
}

export function ScheduleChart({ o, kind, months = 12 }: { o: any; kind: "seasonal" | "flat"; months?: number }) {
  const { lang } = useLang();
  const inst = (kind === "seasonal" ? o.seasonal.instalments : o.flat.instalments).slice(0, months);
  const start = o.start_month || 12;
  const data = inst.map((v: number, i: number) => ({ m: MONTHS[(start - 1 + i) % 12], emi: v, cap: Math.max(0, o.expected_disposable[i]) }));
  return (
    <div className="h-32 -ml-3">
      <ResponsiveContainer>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f6" />
          <XAxis dataKey="m" tick={{ fontSize: 9 }} />
          <YAxis tick={{ fontSize: 9 }} width={34} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
          <Tooltip formatter={(v: any) => inr(v)} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Bar dataKey="emi" fill={kind === "seasonal" ? "#14917f" : "#94a3b8"} name={lang === "hi" ? "किस्त" : "Instalment"} radius={[3, 3, 0, 0]} />
          <Line dataKey="cap" stroke="#ea8f12" strokeWidth={2} dot={false} name={lang === "hi" ? "बची आय (अनुमान)" : "Spare income (expected)"} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function OfferBox({ o, act, active, score }: { o: any; act: any; active: boolean; score: any }) {
  const { lang } = useLang();
  const [kind, setKind] = useState<"seasonal" | "flat">("seasonal");
  const k = o.kfs;
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[11px] text-ink-400">{sname(o, lang)}</div>
          <div className="text-2xl font-bold text-ink-900">{inr(o.amount)}</div>
          {o.amount < o.requested && <div className="text-[11px] text-ink-500">{lang === "hi" ? "माँगा" : "asked"} {inr(o.requested)}, {t(o.why, lang)}</div>}
          {!!o.provisional?.length && <div className="mt-1 text-[11px] rounded-md bg-amber-50 text-amber-800 px-2 py-1">
            {lang === "hi" ? "अस्थायी: " : "Provisional: "}{o.provisional.map((p: any) => t(p.text, lang)).join("; ")}</div>}
        </div>
        <BandChip band={o.risk.band} pd={o.risk.pd} />
      </div>
      <div className="flex flex-wrap gap-1 mt-2 text-[11px]">
        <span className="pill bg-slate-100 text-ink-700">{(o.rate * 100).toFixed(1)}% · {o.tenure} {lang === "hi" ? "महीने" : "months"}</span>
        {o.subsidy > 0 && <span className="pill bg-emerald-100 text-emerald-800">{lang === "hi" ? "सब्सिडी" : "Subsidy"} {inr(o.subsidy)}</span>}
        {o.grants?.map((g: any, i: number) => <span key={i} className="pill bg-emerald-100 text-emerald-800">{t(g.label, lang)} {g.display}</span>)}
        {o.cgtmse_possible && <span className="pill bg-sky-50 text-sky-800 border border-sky-200" title={lang === "hi" ? "तभी, जब आपका बैंक CGTMSE सदस्य हो और गारंटी लेना चुने" : "Only if your lender is a CGTMSE member and chooses to obtain cover"}>
          {lang === "hi" ? "CGTMSE गारंटी संभव (बैंक तय करेगा)" : "CGTMSE cover possible (lender decides)"}</span>}
      </div>
      <div className="flex gap-1 mt-3">
        {(["seasonal", "flat"] as const).map((x) => (
          <button key={x} onClick={() => setKind(x)} className={`tab ${kind === x ? "tab-on" : ""} !text-xs`}>{t(UI[x], lang)}
            <span className={`ml-1 pill ${(x === "seasonal" ? o.seasonal : o.flat).stress_months ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"}`}>
              {(x === "seasonal" ? o.seasonal : o.flat).stress_months} {lang === "hi" ? "तनाव माह" : "tight mo."}</span>
          </button>
        ))}
      </div>
      <ScheduleChart o={o} kind={kind} />
      {k && (
        <div className="grid grid-cols-3 gap-2 text-center mt-1">
          <div><div className="label">APR</div><div className="font-bold text-sm">{pct(kind === "seasonal" ? k.apr_seasonal : k.apr_flat)}</div></div>
          <div><div className="label">{lang === "hi" ? "कुल ब्याज" : "Interest"}</div><div className="font-bold text-sm">{inr(kind === "seasonal" ? k.total_interest_seasonal : k.total_interest_flat)}</div></div>
          <div><div className="label">{lang === "hi" ? "शुल्क" : "Fees"}</div><div className="font-bold text-sm">{inr(k.processing_fee + k.guarantee_fee_year1)}</div></div>
        </div>
      )}
      {o.refinance && <div className="mt-2 text-[12px] rounded-lg bg-emerald-50 text-emerald-800 p-2">{t(o.refinance.note, lang)}</div>}
      {o.uplift?.projected > 0 && <div className="mt-1 text-[11px] text-ink-400">{lang === "hi" ? "नई संपत्ति से अनुमानित अतिरिक्त आय का केवल 50% गिना गया" : `Counts only 50% of the projected +${Math.round(o.uplift.projected * 100)}% income from the new asset`}.</div>}
      {k && <div className="text-[10px] text-ink-400 mt-1">{t(k.note, lang)}</div>}
      {active && (
        <button className="btn-primary w-full mt-3" onClick={() => act({ type: "choose_offer", index: o.index, schedule: kind })}>
          {o.amount > 0 ? t(UI.choose, lang) : (lang === "hi" ? "फिर भी आवेदन करें" : "Apply anyway")}</button>
      )}
    </div>
  );
}

function ReleaseNotice({ r }: { r: any }) {
  const { lang } = useLang();
  if (!r || r.status === "released") return null;
  return (
    <div className="mb-2 rounded-lg bg-rose-50 text-rose-800 text-[12px] p-2 flex gap-1.5"><AlertTriangle size={14} className="shrink-0 mt-0.5" />
      {lang === "hi" ? "जोखिम मॉडल अपनी निष्पक्षता रिलीज़ जाँच में पास नहीं हुआ (डेमो)। ये राशियाँ केवल प्रदर्शन के लिए हैं, असली उपयोग में मॉडल बंद रहता।"
        : "The risk model has NOT passed its fairness release gate (demo). Amounts are for demonstration only, in production the model stays off."}</div>
  );
}

function OffersCard({ card, act, active }: P) {
  const { lang } = useLang();
  return (
    <Shell>
      <div className="flex items-center gap-2 mb-2"><Sparkles size={16} className="text-brand-600" />
        <span className="font-semibold text-sm">{lang === "hi" ? "आपके विकल्प" : "Your options"}</span></div>
      <ReleaseNotice r={card.model_release} />
      <div className="space-y-2">{card.offers.filter((o: any) => o.amount > 0).map((o: any) =>
        <OfferBox key={o.index} o={o} act={act} active={active} score={card.score} />)}</div>
    </Shell>
  );
}

function NotNowCard({ card, act, active }: P) {
  const { lang } = useLang();
  const s = card.score;
  return (
    <Shell tone="bg-rose-50/40 border-rose-200">
      <div className="flex items-center gap-2"><AlertTriangle size={16} className="text-rose-600" />
        <span className="font-semibold text-sm">{lang === "hi" ? "अभी ऋण से बोझ बढ़ सकता है" : "A loan now would likely strain you"}</span>
        <BandChip band={s.band} pd={s.pd} /></div>
      <div className="mt-2"><ReleaseNotice r={card.model_release} /></div>
      <div className="mt-2 space-y-2">
        {s.reason_codes.map((r: any) => (
          <div key={r.feature} className="text-[13px]">
            <div className="font-semibold text-ink-900">{t(r.label, lang)} <span className="text-ink-400 font-normal">({r.display})</span></div>
            <div className="text-ink-500">{t(r.advice, lang)}{r.better && <span className="text-brand-700"> → {r.better.to_bin} (+{Math.round(r.better.points_gain)} pts)</span>}</div>
          </div>
        ))}
      </div>
      {active && (
        <div className="flex gap-2 mt-3">
          <button className="btn-ghost flex-1" onClick={() => alert(lang === "hi" ? "3 महीने बाद याद दिलाया जाएगा (डेमो)" : "Reminder set for 3 months (demo)")}>
            <Clock size={14} />{lang === "hi" ? "3 महीने बाद याद दिलाएँ" : "Remind me in 3 months"}</button>
          <button className="btn-ghost" onClick={() => act({ type: "choose_offer", index: card.offers[0].index, schedule: "seasonal" })}>
            {lang === "hi" ? "फिर भी आवेदन" : "Apply anyway"}</button>
        </div>
      )}
    </Shell>
  );
}

function ReasonsCard({ card }: P) {
  const { lang } = useLang();
  return <Shell>{card.reasons.map((r: any) => <div key={r.feature} className="text-[13px]"><b>{t(r.label, lang)}</b>, {t(r.advice, lang)}</div>)}</Shell>;
}

function DocumentsCard({ c, act, active, ctx }: P) {
  const { lang } = useLang();
  const d = c.documents;
  if (!d) return null;
  const how: any = { auto: ["bg-emerald-100 text-emerald-800", lang === "hi" ? "अपने आप" : "fetched"], generated: ["bg-sky-100 text-sky-800", lang === "hi" ? "बनाया" : "prepared"],
    done: ["bg-emerald-100 text-emerald-800", lang === "hi" ? "हो गया" : "done"], upload: ["bg-amber-100 text-amber-800", lang === "hi" ? "आप करें" : "you"],
    capture: ["bg-amber-100 text-amber-800", lang === "hi" ? "आप करें" : "you"], offline: ["bg-violet-100 text-violet-800", lang === "hi" ? "JanAI कैफ़े" : "JanAI Café"], paid: ["bg-rose-100 text-rose-800", lang === "hi" ? "शुल्क वाला" : "paid"] };
  const isPending = (i: any) => i.status === "pending" && !i.post_sanction && !c.uploads?.[i.doc] && !c.scheduled?.includes(i.doc);
  return (
    <Shell>
      <div className="flex items-center gap-2"><FileCheck2 size={16} className="text-brand-600" />
        <span className="font-semibold text-sm">{lang === "hi" ? "दस्तावेज़" : "Documents"}</span>
        <span className="ml-auto text-[11px] text-ink-500"><s>{d.traditional.count} {lang === "hi" ? "काग़ज़" : "papers"}</s> → <b>{d.counts.you_do} {lang === "hi" ? "आपके लिए" : "for you"}</b></span></div>
      <div className="mt-2 divide-y divide-slate-100">
        {d.items.map((i: any) => (
          <div key={i.doc} className="py-1.5 flex items-center gap-2 text-[13px]">
            <span className="flex-1">{t(i.label, lang)}<span className="block text-[10px] text-ink-400">{viaName(i.via, lang)} · {i.serves.map((s: any) => t(s.label, lang)).slice(0, 2).join(", ")}{i.post_sanction ? (lang === "hi" ? " · स्वीकृति के बाद" : " · after sanction") : ""}</span></span>
            {c.scheduled?.includes(i.doc) ? <span className="pill bg-violet-100 text-violet-800">{lang === "hi" ? "JanAI कैफ़े" : "JanAI Café"}</span>
              : c.uploads?.[i.doc] ? <span className="pill bg-emerald-100 text-emerald-800" title={t(c.uploads[i.doc].note, lang)}>
                  {lang === "hi" ? "प्राप्त" : "received"} · {c.uploads[i.doc].sha256.slice(0, 8)}{c.uploads[i.doc].demo_sample ? (lang === "hi" ? " · डेमो" : " · demo") : ""}</span>
              : <span className={`pill ${how[i.how]?.[0]}`}>{how[i.how]?.[1]}</span>}
            {active && isPending(i) && (
              <span className="flex gap-1">
                <label className="btn-primary !px-2 !py-1 !text-[11px] cursor-pointer"><Upload size={12} />{t(UI.upload, lang)}
                  <input type="file" accept="application/pdf,image/jpeg,image/png" capture={i.doc === "selfie" ? "user" : undefined} className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) ctx?.upload(i.doc, f); }} /></label>
                <button className="btn-ghost !px-2 !py-1 !text-[11px]" title={t(UI.atCafe, lang)} onClick={() => act({ type: "upload", doc: i.doc, assisted: true })}><Store size={12} /></button>
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="mt-2 text-[11px] text-ink-400">{lang === "hi" ? "फ़ाइल पूर्णता" : "File completeness"}: {pct(d.completeness, 0)} · {t(d.traditional.note, lang)}</div>
      <div className="mt-1 text-[11px] text-ink-400">{lang === "hi" ? "PDF/JPEG/PNG, अधिकतम 5 MB। साख फ़ाइल को जाँचता और फ़िंगरप्रिंट करता है, पढ़ता नहीं, बैंक सत्यापित करता है।"
        : "PDF/JPEG/PNG up to 5 MB. Saakh checks and fingerprints the file but does not read it; the lender verifies it."}</div>
    </Shell>
  );
}

function ApprovalCard({ card, act, active, c }: P) {
  const { lang } = useLang();
  const [ok, setOk] = useState(false);
  const [otp, setOtp] = useState("");
  const o = card.offer;
  return (
    <Shell tone="bg-white border-brand-200 ring-2 ring-brand-100">
      <div className="flex items-center gap-2"><CheckCircle2 size={16} className="text-brand-600" />
        <span className="font-semibold text-sm">{lang === "hi" ? "मंज़ूरी से पहले देखें" : "Review before you approve"}</span></div>
      <div className="grid grid-cols-2 gap-2 mt-2 text-[13px]">
        <div><div className="label">{lang === "hi" ? "योजना" : "Scheme"}</div><b>{sname(o, lang)}</b></div>
        <div><div className="label">{lang === "hi" ? "राशि" : "Amount"}</div><b>{inr(o.amount)}</b></div>
        <div><div className="label">{lang === "hi" ? "ब्याज" : "Rate"}</div>{(o.rate * 100).toFixed(1)}% · {o.tenure}{lang === "hi" ? " माह" : "m"} · {appStatus(o.schedule_type, lang)}</div>
        <div><div className="label">APR</div>{card.kfs ? pct(o.schedule_type === "seasonal" ? card.kfs.apr_seasonal : card.kfs.apr_flat) : "-"}</div>
      </div>
      <div className="mt-2">
        <div className="label">{lang === "hi" ? "किसे भेजा जाएगा" : "Send to"}</div>
        <select disabled={!active} className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={card.lender.id}
          onChange={(e) => act({ type: "set_lender", lender_id: e.target.value })}>
          {card.lenders.map((l: any) => <option key={l.id} value={l.id}>{l.name} ({l.type})</option>)}
        </select>
      </div>
      <div className="mt-2 text-[12px] text-ink-500"><span className="label">{lang === "hi" ? "क्या साझा होगा" : "What will be shared"}</span>
        <div className="mt-0.5">{card.shares.map((s: any) => t(s, lang)).join(" · ")}</div></div>
      {!!card.attachments?.length && <div className="mt-2 text-[11px] text-ink-500"><span className="label">{lang === "hi" ? "संलग्न फ़ाइलें (फ़िंगरप्रिंट)" : "Attached files (fingerprint)"}</span>
        {card.attachments.map((a: any) => <div key={a.doc} className="font-mono">{a.doc} · {kb(a.bytes)} · {a.sha256.slice(0, 16)}…</div>)}</div>}
      {!!card.pending_items?.length && <div className="mt-2 text-[12px] rounded-lg bg-amber-50 text-amber-800 p-2">
        {lang === "hi" ? "अभी बाकी (बैंक इन्हें बाकी के रूप में देखेगा): " : "Still pending (the bank will see these as pending): "}
        {card.pending_items.map((d: string) => { const it = c.documents?.items?.find((x: any) => x.doc === d); return it ? t(it.label, lang) : d.replace(/_/g, " "); }).join(", ")}</div>}
      <div className="mt-2 text-[10px] font-mono text-ink-400 break-all">{lang === "hi" ? "फ़ाइल हैश" : "file hash"} {card.hash}</div>
      {active && (
        <>
          <label className="flex gap-2 mt-3 text-[13px]">
            <input type="checkbox" className="accent-brand-600" checked={ok} onChange={(e) => setOk(e.target.checked)} />
            {lang === "hi" ? "मैंने यह आवेदन देख लिया है और इसे भेजने की मंज़ूरी देता/देती हूँ।" : "I have reviewed this application and approve sending it."}
          </label>
          <div className="flex gap-2 mt-2">
            {card.otp_required && <input value={otp} onChange={(e) => setOtp(e.target.value)} placeholder={lang === "hi" ? "उद्यमी का OTP" : "Entrepreneur's OTP"} inputMode="numeric" className="w-40 rounded-xl border border-slate-200 px-3 py-2 text-sm" />}
            <button disabled={!ok} className="btn-primary flex-1" onClick={() => act({ type: "approve", hash: card.hash, confirm: true, otp })}>{t(UI.approve, lang)}</button>
            <button className="btn-ghost" onClick={() => act({ type: "approve", hash: card.hash, confirm: false })}>{t(UI.notNow, lang)}</button>
          </div>
        </>
      )}
      {!active && c.approval && <div className="mt-2 text-[12px] text-emerald-700">✓ {lang === "hi" ? "मंज़ूरी दी" : "Approved"} {c.approval.ts} · {lang === "hi"
        ? (String(c.approval.method).startsWith("OTP") ? "उद्यमी के फ़ोन पर OTP से (सहायता मोड)" : "ऐप में पुष्टि") : c.approval.method}</div>}
    </Shell>
  );
}

function SubmittedCard({ card }: P) {
  const { lang } = useLang();
  return (
    <Shell tone="bg-emerald-50 border-emerald-200">
      <div className="text-sm font-semibold text-emerald-800">{lang === "hi" ? "जमा हो गया" : "Submitted"} · {card.ref} <SimBadge /></div>
      <div className="text-[12px] text-emerald-900">{card.lender.name}</div>
    </Shell>
  );
}

function LenderCard({ card }: P) {
  const { lang } = useLang();
  const d = card.decision;
  const tone = d.decision === "sanction" ? "bg-emerald-50 border-emerald-200" : d.decision === "query" ? "bg-amber-50 border-amber-200" : "bg-rose-50 border-rose-200";
  return <Shell tone={tone}><div className="text-sm font-semibold capitalize">{lang === "hi" ? `बैंक: ${appStatus(d.decision, lang)}` : d.decision}{d.amount ? ` · ${inr(d.amount)}` : ""}</div>{d.note && <div className="text-[12px]">{d.note}</div>}</Shell>;
}

function ExplanationCard({ card, c }: P) {
  const { lang } = useLang();
  const sents = lang === "hi" && card.sentences_hi ? card.sentences_hi : card.sentences;
  return (
    <Shell>
      {sents.map((s: any, i: number) => (
        <div key={i} className="text-[13px] py-0.5">{lang === "hi" && s.text_hi ? s.text_hi : s.text}{s.cites?.map((ct: any, j: number) => <CiteChip key={j} c={ct} />)}</div>
      ))}
    </Shell>
  );
}

function FallbackCard({ active, c, ctx }: P) {
  const { lang } = useLang();
  const [agree, setAgree] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [otp, setOtp] = useState("");
  const assisted = c.mode === "assisted";
  if (!active) return null;
  return (
    <Shell tone="bg-amber-50 border-amber-200">
      <div className="text-[12px] text-ink-700">{lang === "hi" ? "अपने बैंक से CSV निर्यात (कॉलम: date, narration, debit, credit, balance)।"
        : "A CSV export from your bank (columns: date, narration, debit, credit, balance)."}</div>
      <input type="file" accept=".csv,text/csv" className="mt-2 text-[12px]" onChange={(e) => setFile(e.target.files?.[0] || null)} />
      <label className="flex gap-2 mt-2 text-[12px]">
        <input type="checkbox" className="accent-brand-600" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
        {lang === "hi" ? "मैं साख को इस विवरण का विश्लेषण केवल इस ऋण आवेदन के लिए करने की अनुमति देता/देती हूँ; अनुमति वापस लेने पर इसे मिटा दिया जाएगा।"
          : "I allow Saakh to analyse this statement for this loan application only; it is deleted when I withdraw consent."}
      </label>
      <div className="flex gap-2 mt-2">
        {assisted && <input value={otp} onChange={(e) => setOtp(e.target.value)} inputMode="numeric" className="w-40 rounded-xl border border-slate-200 px-3 py-2 text-sm"
          placeholder={lang === "hi" ? "उद्यमी का OTP" : "Entrepreneur's OTP"} />}
        <button className="btn-primary flex-1" disabled={!file || !agree || (assisted && otp.length < 6)} onClick={() => file && ctx?.uploadStatement(file, agree, otp)}>
          <Upload size={14} />{lang === "hi" ? "विवरण अपलोड करें" : "Upload statement"}</button>
        <button className="btn-ghost" onClick={() => alert(lang === "hi" ? "निकटतम JanAI कैफ़े: ब्लॉक कार्यालय के पास (डेमो)" : "Nearest JanAI Café: near the block office (demo)")}><Store size={14} />JanAI Café</button>
      </div>
      {ctx?.demo && <a className="block mt-2 text-[11px] text-brand-700 underline" href={`/api/demo/sample-statement/${c.persona}.csv`}>
        {lang === "hi" ? "डेमो: इस व्यक्ति का नमूना CSV डाउनलोड करें" : "Demo: download this persona's sample CSV"}</a>}
    </Shell>
  );
}

export function useIsActive(c: any) {
  return useMemo(() => {
    const msgs = c?.messages || [];
    for (let i = msgs.length - 1; i >= 0; i--) if (msgs[i].card && msgs[i].role === "agent") return msgs[i].id;
    return null;
  }, [c]);
}
