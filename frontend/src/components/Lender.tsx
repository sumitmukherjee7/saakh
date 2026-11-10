import { useEffect, useRef, useState } from "react";

// The branch's OWN reasons for a decline. Saakh's scorecard factors are reference only and are never sent as the bank's reasons.
const LENDER_REASONS: [string, string][] = [["repayment_capacity", "Repayment capacity"], ["credit_history", "Credit history"],
  ["documents_incomplete", "Documents incomplete"], ["scheme_conditions", "Scheme conditions not met"],
  ["business_viability", "Business viability"], ["collateral_or_guarantee", "Collateral or guarantee"],
  ["policy_limit", "Bank policy limit"], ["other", "Other"]];
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { FileDown, ShieldCheck, CheckCircle2, HelpCircle, XCircle, RefreshCw, Calculator, Lock, LogOut, Paperclip } from "lucide-react";
import { api, clearLenderKey, downloadAttachment, lenderKey, openPdf, setLenderKey } from "../api";
import { inr, kb, mlabel, pct, t, useLang } from "../util";
import { BandChip, CiteChip, SimBadge, Stat, StatusPill, VerBadge } from "./common";
import { ScheduleChart } from "../cards/Cards";

export default function Lender() {
  const [list, setList] = useState<any[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [view, setView] = useState<"queue" | "economics">("queue");
  const [authed, setAuthed] = useState(!!lenderKey());
  const [keyIn, setKeyIn] = useState("");
  const [demoKeys, setDemoKeys] = useState<{ lender: string; key: string }[]>([]);
  const [lenders, setLenders] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const load = () => api.lenderList().then((l) => { setList(l); setErr(""); if (!sel && l.length) setSel(l.find((x: any) => !x.redacted)?.id || l[0].id); })
    .catch((e: any) => { if (e.status === 401) { setAuthed(false); setErr("Invalid branch key"); } else setErr(e.message); });
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
          <div className="flex items-center gap-2 font-semibold"><Lock size={16} className="text-brand-600" />Branch console sign-in</div>
          <p className="text-[13px] text-ink-500">Each branch has its own key and sees only files the entrepreneur addressed to that branch, and only while their consent to share is active.</p>
          {!!demoKeys.length && (
            <label className="block text-[12px] text-violet-700">Demo build, sign in as a branch (keys are public in demo only):
              <select className="mt-1 w-full rounded-xl border border-violet-200 px-3 py-2 text-sm text-ink-900" value={keyIn} onChange={(e) => setKeyIn(e.target.value)}>
                <option value="">Choose a branch…</option>
                {demoKeys.map((d) => <option key={d.key} value={d.key}>{lenders[d.lender] || d.lender}</option>)}
              </select>
            </label>)}
          <input value={keyIn} onChange={(e) => setKeyIn(e.target.value)} placeholder="Branch key" type="password"
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
          {err && <div className="text-[12px] text-rose-700">{err}</div>}
          <button className="btn-primary w-full" onClick={() => { setLenderKey(keyIn); setAuthed(true); }}>Open console</button>
        </div>
      </div>
    );
  }
  return (
    <div className="max-w-[1500px] mx-auto p-3 md:p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="text-xl font-bold">Branch console</div><SimBadge />
        <span className="text-[12px] text-ink-400">Saakh pre-appraised files · decision support only; the branch decides</span>
        <div className="ml-auto flex gap-1">
          <button className={`tab ${view === "queue" ? "tab-on" : ""}`} onClick={() => setView("queue")}>Applications</button>
          <button className={`tab ${view === "economics" ? "tab-on" : ""}`} onClick={() => setView("economics")}><Calculator size={14} className="inline mr-1" />Cost of incomplete files</button>
          <button className="btn-ghost !py-1.5" onClick={load}><RefreshCw size={14} /></button>
          <button className="btn-ghost !py-1.5" onClick={signOut} title="Sign out / switch branch"><LogOut size={14} />{branch ? (lenders[branch] || branch).split(", ")[0] : "Sign out"}</button>
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
                {a.redacted ? <div className="text-[12px] text-ink-400">{a.id} · withdrawn by the entrepreneur, contents erased</div>
                  : <div className="text-[12px] text-ink-500">{a.scheme} · {inr(a.amount)} · {a.district} · {a.activity?.replace(/_/g, " ")}</div>}
                <div className="flex gap-1 mt-1">
                  {!a.redacted && <span className={`pill ${a.complete ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{a.complete ? "all pre-sanction items in" : `${a.pending_items.length} item(s) pending`}</span>}
                  {a.superseded && <span className="pill bg-rose-100 text-rose-800">changed, awaiting re-approval</span>}
                  <span className="pill bg-slate-100 capitalize">{a.status}</span>
                  {a.schedule_type && <span className="pill bg-slate-100">{a.schedule_type}</span>}
                </div>
              </button>
            ))}
            {!list.length && <div className="p-4 text-ink-400 text-sm">No applications addressed to this branch yet. Submit one from the entrepreneur app.</div>}
          </div>
          {sel && <Detail id={sel} onDecided={load} />}
        </div>
      )}
    </div>
  );
}

function Detail({ id, onDecided }: { id: string; onDecided: () => void }) {
  const { lang } = useLang();
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
  if (!a) return <div className="card p-4 text-ink-400">Loading…</div>;
  const d = a.detail, p = a.package, s = d.score;
  const m = d.monthly;
  const st = p.statement || {};
  const nMonths = m?.months?.length || 0;
  const srcLabel = st.source === "upload" ? "entrepreneur-uploaded CSV" : "Account Aggregator, consented";
  const locked = a.status === "withdrawn" || a.summary.superseded || ["sanctioned", "declined"].includes(a.status);
  const cf = m ? m.months.map((mk: string, i: number) => ({ m: mlabel(mk), income: Math.round(m.biz_in[i]), inputs: Math.round(m.biz_out[i]), emi: Math.round(m.emi_out[i] + m.informal_out[i]) })) : [];
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
  return (
    <div className="space-y-3">
      <div className="card p-4">
        <div className="flex flex-wrap items-start gap-3">
          <div className="flex-1 min-w-[240px]">
            <div className="text-lg font-bold">{a.summary.applicant}</div>
            <div className="text-[13px] text-ink-500">{d.facts.activity?.replace(/_/g, " ")} · {d.facts.district}, {d.facts.state} ({d.facts.area_type}) · {d.facts.years_in_business != null ? `${d.facts.years_in_business} yrs` : "vintage not asked"} · {d.facts.ownership_type}</div>
            <div className="text-[12px] text-ink-400 mt-1">{a.id} · LOS {a.los_ref} · {a.lender.name}</div>
          </div>
          <div className="text-right">
            <div className="label">Recommended</div><div className="text-2xl font-bold">{inr(p.offer.amount)}</div>
            {!!p.offer.provisional?.length && <div className="text-[11px] text-amber-700">scheme match provisional, {p.offer.provisional.map((x: any) => t(x.by, lang)).join(", ")} to verify</div>}
            <div className="text-[12px] text-ink-500">{p.offer.scheme_short} · {(p.offer.rate * 100).toFixed(1)}% · {p.offer.tenure}m · {p.schedule_type}</div>
          </div>
          <div className="text-right"><div className="label">Simulated risk estimate</div><BandChip band={p.risk.band} pd={p.risk.pd} />
            <div className="text-[11px] text-ink-400">range {pct(p.risk.pd_low)}–{pct(p.risk.pd_high)} · score {p.risk.score}</div>
            <div className="text-[10px] text-ink-400 max-w-[220px]">Model trained on synthetic data, not a validated probability of default.</div></div>
        </div>
        {d.offer?.against_advice && <div className="mt-2 text-[12px] rounded-lg bg-rose-50 text-rose-800 p-2">Entrepreneur chose to apply although Saakh advised waiting, see reasons.</div>}
        {a.summary.superseded && <div className="mt-2 text-[12px] rounded-lg bg-rose-50 text-rose-800 p-2">The entrepreneur changed this file after sending it ({a.superseded_reason}). Decisions are locked until they re-approve and re-send it.</div>}
        {!!p.disputes?.length && <div className="mt-2 text-[12px] rounded-lg bg-amber-50 text-amber-900 p-2">
          <b>Entrepreneur disputes {p.disputes.length} sourced value(s)</b>; Saakh kept the sourced value; please check:
          {p.disputes.map((d: any) => <div key={d.fact}>· {d.fact.replace(/_/g, " ")} (from {d.source}): entrepreneur says {String(d.claimed)}{d.reason ? `, "${d.reason}"` : ""}</div>)}</div>}
        {!!a.summary.pending_items?.length && <div className="mt-2 text-[12px] rounded-lg bg-amber-50 text-amber-800 p-2">Pending before sanction: {a.summary.pending_items.join(", ").replace(/_/g, " ")}</div>}
      </div>
      <div className="flex gap-1 flex-wrap">
        {[["overview", "Cash flow"], ["score", "Scorecard"], ["schemes", "Eligibility (cited)"], ["docs", "Documents"], ["integrity", "Consent & integrity"]].map(([k, l]) =>
          <button key={k} className={`tab ${tab === k ? "tab-on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}
        <button className="btn-ghost ml-auto !py-1.5" onClick={() => openPdf(`/api/lender/applications/${id}/memo.pdf`, "lender")}><FileDown size={14} />Credit memo PDF</button>
        <button className="btn-ghost !py-1.5" onClick={() => openPdf(`/api/lender/applications/${id}/dpr.pdf`, "lender")}><FileDown size={14} />DPR</button>
      </div>

      {tab === "overview" && (
        <div className="grid md:grid-cols-2 gap-3">
          <div className="card p-3">
            <div className="label">Monthly cash flow, {nMonths} months ({srcLabel}){st.from ? ` · ${st.from} to ${st.to}` : ""}</div>
            {nMonths < 12 && <div className="text-[11px] text-amber-700">Short history: annual figures are scaled up and a full seasonal cycle is not observed.</div>}
            <div className="h-56 -ml-2 mt-1"><ResponsiveContainer><BarChart data={cf}>
              <CartesianGrid vertical={false} stroke="#eef2f6" /><XAxis dataKey="m" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip formatter={(v: any) => inr(v)} /><Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="income" fill="#14917f" name="Business inflow" /><Bar dataKey="inputs" fill="#94a3b8" name="Inputs & opex" /><Bar dataKey="emi" fill="#ea8f12" name="Debt service" />
            </BarChart></ResponsiveContainer></div>
          </div>
          <div className="card p-3 space-y-2">
            <div className="label">Findings</div>
            {(d.insights || []).map((x: any, i: number) => <div key={i} className="text-[13px]"><b>{t(x.title, lang)}.</b> <span className="text-ink-500">{t(x.detail, lang)}</span></div>)}
            <div className="label pt-2">Bureau</div>
            <div className="text-[13px]">{d.bureau ? `Score ${d.bureau.score ?? "NTC (new to credit)"} · ${d.bureau.loans.length} active loan(s)` : "Not pulled (consent declined)"} <SimBadge /></div>
            {d.offer && <><div className="label pt-2">Proposed schedule</div><ScheduleChart o={d.offer} kind={p.schedule_type} /></>}
          </div>
        </div>
      )}

      {tab === "score" && s && (
        <div className="card p-3">
          <div className="text-[12px] text-ink-400 mb-2">Monotone WoE scorecard, each factor's points come from a published table. Gender, caste, religion and location are never inputs.</div>
          <table className="w-full text-[12.5px]">
            <thead><tr className="text-left text-ink-400"><th className="py-1">Factor</th><th>Applicant</th><th>Bin</th><th className="w-48">Points / max</th></tr></thead>
            <tbody>{s.contributions.map((x: any) => (
              <tr key={x.feature} className="border-t border-slate-100">
                <td className="py-1.5">{t(x.label, lang)}</td><td>{x.display}</td><td className="text-ink-500">{x.bin}</td>
                <td><div className="flex items-center gap-2"><div className="flex-1 h-2 rounded bg-slate-100 overflow-hidden">
                  <div className={`h-2 ${x.gap > 8 ? "bg-rose-400" : x.gap > 2 ? "bg-amber-400" : "bg-emerald-500"}`} style={{ width: `${Math.max(4, (x.points / Math.max(x.max_points, 1)) * 100)}%` }} /></div>
                  <span className="text-[11px] w-14 text-right">{Math.round(x.points)}/{Math.round(x.max_points)}</span></div></td>
              </tr>))}</tbody>
          </table>
          <div className="grid md:grid-cols-2 gap-3 mt-3">
            <div><div className="label">Reason codes (points lost)</div>{s.reason_codes.map((r: any) => <div key={r.feature} className="text-[13px]">• {t(r.label, lang)}, {Math.round(r.points_lost)} pts</div>)}</div>
            <div><div className="label">Strengths</div>{s.strengths.map((r: any) => <div key={r.feature} className="text-[13px]">• {t(r.label, lang)} ({r.display})</div>)}</div>
          </div>
          <div className="text-[11px] text-ink-400 mt-2">Model {s.model_version} · {s.thin_file ? "thin file, interval widened" : `${nMonths}-month history`}</div>
        </div>
      )}

      {tab === "schemes" && (
        <div className="card p-3 space-y-2">
          {d.schemes.map((r: any) => (
            <div key={r.id} className="border-t border-slate-100 pt-2 first:border-0 first:pt-0">
              <div className="flex items-center gap-2 text-[13px]"><b className="flex-1">{r.short}</b><StatusPill s={r.eligibility} provisional={r.provisional} />
                {Object.entries(r.verification || {}).filter(([, n]: any) => n).map(([v, n]: any) => <span key={v} className="text-[10px]">{n}× <VerBadge v={v} /></span>)}</div>
              {r.status_note && <div className="text-[12px] text-rose-800">{t(r.status_note, lang)}</div>}
              {r.failing.map((f: any, i: number) => <div key={i} className="text-[12px] text-ink-500">✗ {t(f.text, lang)}<CiteChip c={f.cite} /></div>)}
              {r.eligibility === "eligible" && <div className="text-[12px] text-emerald-700">✓ {r.citations.length} cited criteria met {r.citations.slice(0, 6).map((c: any, i: number) => <CiteChip key={i} c={c} n={i + 1} />)}</div>}
            </div>))}
        </div>)}

      {tab === "docs" && d.documents && (
        <div className="card p-3">
          <div className="flex gap-3 mb-2"><Stat label="Items" value={d.documents.counts.total} /><Stat label="Auto-fetched" value={d.documents.counts.auto} /><Stat label="Prepared by Saakh" value={d.documents.counts.generated} />
            <Stat label="Pending (pre-sanction)" value={a.summary.pending_items.length} tone={a.summary.pending_items.length ? "text-amber-700" : "text-emerald-700"} /></div>
          {p.documents.map((i: any) => {
            const item = d.documents.items.find((x: any) => x.doc === i.doc);
            return (
              <div key={i.doc} className="text-[13px] py-1.5 border-t border-slate-100 flex items-center gap-2">
                <span className="flex-1">{item ? t(item.label, lang) : i.doc} <span className="text-ink-400 text-[11px]">· {item?.via}</span>
                  {i.attachment && <span className="block text-[10px] font-mono text-ink-400">sha256 {i.attachment.sha256.slice(0, 20)}… · {kb(i.attachment.bytes)} · not read by Saakh</span>}</span>
                <span className={`pill ${i.status === "ready" ? "bg-emerald-100 text-emerald-800" : i.post_sanction ? "bg-slate-100" : "bg-amber-100 text-amber-800"}`}>
                  {i.status === "ready" ? "in file" : i.post_sanction ? "after sanction" : i.scheduled_offline ? "JanAI Café visit pending" : "pending"}</span>
                {i.attachment && <button className="btn-ghost !py-1 !text-xs" onClick={async () => {
                  const e = await downloadAttachment(`/api/lender/applications/${id}/documents/${i.doc}`, i.attachment.sha256, `${id}-${i.doc}`);
                  if (e) setErr(`Attachment ${i.doc}: ${e}`);
                }}><Paperclip size={12} />Download</button>}
              </div>);
          })}
          <div className="text-[11px] text-ink-400 mt-2">Each download is re-verified against the fingerprint the entrepreneur approved and recorded in their audit log.</div>
        </div>
      )}

      {tab === "integrity" && (
        <div className="card p-3 space-y-2 text-[13px]">
          {[["Package hash matches what was approved", a.integrity.package_hash_ok], ["Entrepreneur approval bound to this exact file", a.integrity.approval_bound], ["Audit hash chain intact", a.integrity.audit.ok]].map(([l, ok]: any) =>
            <div key={l} className="flex items-center gap-2">{ok ? <CheckCircle2 size={16} className="text-emerald-600" /> : <XCircle size={16} className="text-rose-600" />}{l}</div>)}
          <div className="text-[11px] font-mono text-ink-400 break-all">file {a.hash}<br />audit head {a.integrity.audit.head}</div>
          <div className="label pt-2">Active consents shared with this branch</div>
          {a.consents.map((x: any) => <div key={x.consentId} className="text-[12.5px]"><ShieldCheck size={13} className="inline text-brand-600 mr-1" />{t(x.title, lang)}, {t(x.purpose.text, lang)}</div>)}
          <div className="text-[11px] text-ink-400">If the entrepreneur revokes the sharing consent, this file becomes unavailable here.</div>
        </div>
      )}

      <div className="card p-3">
        <div className="label mb-2">Branch decision {a.decision && <span className="pill bg-slate-100 ml-1 capitalize">{a.decision.decision} · {a.decision.ts}</span>}</div>
        <div className="flex flex-wrap gap-2 items-center">
          <input type="number" value={amt} onChange={(e) => setAmt(Number(e.target.value))} className="w-36 rounded-xl border border-slate-200 px-3 py-2 text-sm" />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note / query (e.g. shop rent agreement)" className="flex-1 min-w-[200px] rounded-xl border border-slate-200 px-3 py-2 text-sm" />
          <button className="btn-primary" disabled={locked || sending} onClick={() => decide("sanction")}><CheckCircle2 size={14} />Sanction</button>
          <button className="btn-warn" disabled={locked || sending || !note.trim()} title="Write the query in the note" onClick={() => decide("query")}><HelpCircle size={14} />Query</button>
          <button className="btn-ghost text-rose-700" disabled={locked || sending || !reasons.length} title="Pick the branch's reason(s) first" onClick={() => decide("decline")}><XCircle size={14} />Decline</button>
        </div>
        {!locked && <div className="mt-2 text-[12px]">
          <div className="label">Branch's reasons (required to decline; the entrepreneur sees these)</div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">{LENDER_REASONS.map(([code, label]) => (
            <label key={code} className="flex items-center gap-1"><input type="checkbox" className="accent-rose-600" checked={reasons.includes(code)}
              onChange={(e) => setReasons(e.target.checked ? [...reasons, code] : reasons.filter((r) => r !== code))} />{label}</label>))}</div>
          <div className="text-[11px] text-ink-400 mt-1">Saakh's scorecard factors (Scorecard tab) are reference only and are not sent as the bank's reasons.</div>
        </div>}
      </div>
    </div>
  );
}

function Economics({ list }: { list: any[] }) {
  const [v, setV] = useState({ files: 60, incompleteNow: 0.45, cycles: 2.2, hours: 1.6, rate: 750, incompleteSaakh: 0.05, travel: 0.25, ticket: 300000, agentFee: 0.12 });
  const set = (k: string) => (e: any) => setV({ ...v, [k]: Number(e.target.value) });
  const reworkNow = v.files * v.incompleteNow * v.cycles * v.hours * (1 + v.travel);
  const reworkSaakh = v.files * v.incompleteSaakh * v.cycles * v.hours * (1 + v.travel);
  const saved = (reworkNow - reworkSaakh) * v.rate;
  const fields: [string, string, number][] = [["files", "Files / month / branch", 1], ["incompleteNow", "Share incomplete today", 0.01], ["cycles", "Rework cycles per incomplete file", 0.1],
    ["hours", "Officer hours per cycle", 0.1], ["travel", "Extra for visits/follow-up (share)", 0.05], ["rate", "Loaded cost / officer-hour (₹)", 50],
    ["incompleteSaakh", "Share incomplete with Saakh", 0.01], ["ticket", "Average loan (₹)", 10000], ["agentFee", "Agent fee avoided (share of loan)", 0.01]];
  return (
    <div className="grid lg:grid-cols-[380px_1fr] gap-4">
      <div className="card p-4 space-y-2">
        <div className="font-semibold">Assumptions <span className="text-[11px] text-ink-400 font-normal">- hypotheses to validate in field research</span></div>
        {fields.map(([k, l, step]) => (
          <label key={k} className="flex items-center gap-2 text-[13px]"><span className="flex-1">{l}</span>
            <input type="number" step={step} value={(v as any)[k]} onChange={set(k)} className="w-28 rounded-lg border border-slate-200 px-2 py-1 text-right" /></label>))}
      </div>
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Officer hours freed / month" value={Math.round(reworkNow - reworkSaakh)} sub="per branch" tone="text-brand-700" />
          <Stat label="Rework cost avoided / month" value={inr(saved)} sub="per branch" tone="text-brand-700" />
          <Stat label="… per year, 100 branches" value={inr(saved * 12 * 100, true)} />
          <Stat label="Agent fees avoided / borrower" value={inr(v.ticket * v.agentFee)} sub="at the stated fee share" tone="text-emerald-700" />
        </div>
        <div className="card p-4 text-[13px] text-ink-700 space-y-2">
          <div className="font-semibold">Who pays, business model</div>
          <p>Lenders pay Saakh per <b>complete, consented, pre-appraised file</b> (₹150–400 per file, set below the rework cost avoided above), and a success fee on disbursal. Entrepreneurs pay nothing; that replaces the 10–15% agent cut. DICs and SHG federations use Saakh's cohort screening to meet scheme targets. JanAI Cafés earn an assisted-service fee from lenders.</p>
          <p className="text-ink-500">Live portfolio here: {list.length} file(s), {list.filter((a) => a.complete).length} complete on first submission.</p>
        </div>
      </div>
    </div>
  );
}
