import { useEffect, useState } from "react";
import { Bot, Wrench, RefreshCw, ShieldAlert, Brain, UserCheck, LifeBuoy, EyeOff, ListChecks, Link2, Fingerprint } from "lucide-react";
import { api, sendEvent } from "../api";
import { inr, sname, t, useL, useLang } from "../util";
import { consentStatus, evidenceText, factLabel, factValue, pendingName, sourceName, useFactReg } from "../facts";
import { BandChip, SimBadge } from "./common";
import { SchemeRow } from "../cards/Cards";

const KIND: any = {
  plan: [<ListChecks size={14} />, "text-brand-700", "plan"], tool: [<Wrench size={14} />, "text-ink-700", "tool"],
  retry: [<RefreshCw size={14} />, "text-saffron-600", "retry"], guard: [<ShieldAlert size={14} />, "text-rose-600", "guard"],
  decision: [<Brain size={14} />, "text-violet-700", "decision"], human: [<UserCheck size={14} />, "text-emerald-700", "human"],
  fallback: [<LifeBuoy size={14} />, "text-saffron-600", "fallback"], privacy: [<EyeOff size={14} />, "text-sky-700", "privacy"],
};

export default function AgentPanel({ c, onCase }: { c: any; onCase: (x: any) => void }) {
  const { lang } = useLang();
  const L = useL();
  const reg = useFactReg();
  const [tab, setTab] = useState("trace");
  const [audit, setAudit] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { if (tab === "audit") api.audit(c.id).then(setAudit); }, [tab, c]);
  const VERIFIED = ["ekyc", "bureau", "udyam", "udyam_portal", "aa", "aa-inferred", "statement_upload", "statement_upload-inferred"];
  async function correct(k: string, v: any) {
    const sourced = VERIFIED.includes(c.fact_meta?.[k]?.source);
    const name = factLabel(reg, k, lang), src = sourceName(c.fact_meta?.[k]?.source, lang);
    const nv = window.prompt(sourced
      ? L(`"${name}" came from ${src}. Your correction is recorded as a dispute the bank will see; the sourced value stays in use until it is fixed at the source. Value you believe is right:`,
        `"${name}" ${src} से आया है। आपका सुधार एक आपत्ति के रूप में दर्ज होगा जिसे बैंक देखेगा; स्रोत में ठीक होने तक स्रोत वाला मान ही इस्तेमाल होगा। आपके अनुसार सही मान:`)
      : L(`New value for "${name}" (now: ${String(v)}):`, `"${name}" का नया मान (अभी: ${String(v)}):`), String(v ?? ""));
    if (nv === null || nv.trim() === "") return;
    const reason = window.prompt(L("Reason (optional):", "कारण (वैकल्पिक):"), "") || null;
    const val = nv.trim() === "true" ? true : nv.trim() === "false" ? false : nv.trim();
    try { const r = await sendEvent(c.id, { type: "correct", fact: k, value: val, reason }); if (r) onCase(r); }
    catch (e: any) { alert(e.message); }
  }

  const tabs = [["trace", L("Agent trace", "एजेंट के कदम")], ["schemes", L("Schemes & proofs", "योजनाएँ और प्रमाण")], ["facts", L("Facts & provenance", "जानकारी और स्रोत")],
    ["consents", L("Consents", "सहमतियाँ")], ["audit", L("Audit chain", "ऑडिट श्रृंखला")]];
  const eligible = (c.schemes || []).filter((r: any) => r.eligibility === "eligible")
    .map((r: any) => sname(r, lang) + (r.provisional?.length ? L(" (provisional)", " (अस्थायी)") : "")).join(", ");
  return (
    <div className="space-y-3">
      <div className="card p-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Bot size={18} className="text-brand-600" />
          <div className="font-semibold">{L("Saakh agent", "साख एजेंट")}</div>
          <span className="text-[12px] text-ink-400">{L("goal: right credit · fair terms · complete file · your approval", "लक्ष्य: सही ऋण · उचित शर्तें · पूरी फ़ाइल · आपकी मंज़ूरी")}</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-[12px]">
          <div><div className="label">{L("Waiting on", "किसका इंतज़ार")}</div><div className="font-semibold">{pendingName(c.pending?.type, lang) || (c.submission ? L("lender", "बैंक") : "-")}</div></div>
          <div><div className="label">{L("Schemes eligible", "पात्र योजनाएँ")}</div><div className="font-semibold">{eligible || "-"}</div></div>
          <div><div className="label">{L("Simulated risk", "सिम्युलेटेड जोखिम")}</div>{c.score ? <BandChip band={c.score.band} pd={c.score.pd} /> : "-"}</div>
          <div><div className="label">{L("Selected", "चुना गया")}</div><div className="font-semibold">{c.selected_offer ? `${sname(c.selected_offer, lang)} ${inr(c.selected_offer.amount)}` : "-"}</div></div>
        </div>
      </div>
      <div className="flex gap-1 flex-wrap">{tabs.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`tab ${tab === k ? "tab-on" : ""}`}>{l}</button>)}</div>

      {tab === "trace" && (
        <div className="card p-3">
          <div className="text-[12px] text-ink-400 mb-2">{L("Every step the agent took, tool calls pass a code-level guard (consent, approval hash) before running.",
            "एजेंट का हर कदम। हर टूल चलने से पहले कोड-स्तर की जाँच (सहमति, मंज़ूरी हैश) से गुज़रता है। तकनीकी नाम अंग्रेज़ी में रखे गए हैं।")}</div>
          <div className="space-y-1">
            {[...c.trace].reverse().map((x: any, i: number) => {
              const k = KIND[x.kind] || KIND.tool;
              return (
                <div key={i} className="flex gap-2 text-[12.5px] py-1 border-b border-slate-50">
                  <span className={`mt-0.5 ${k[1]}`}>{k[0]}</span>
                  <span className="flex-1">
                    <span className="font-mono text-[12px] font-semibold">{x.name}</span>
                    {x.simulated && <span className="ml-1"><SimBadge /></span>}
                    {x.status && x.status !== "ok" && <span className={`pill ml-1 ${x.status === "blocked" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}`}>{x.status}</span>}
                    {x.summary && <span className="block text-ink-500">{x.summary}</span>}
                    {x.guard?.length > 0 && <span className="block text-[10.5px] text-emerald-700">guard ✓ {x.guard.join(" · ")}</span>}
                    {x.error && <span className="block text-[11px] text-rose-600">{x.error}</span>}
                  </span>
                  <span className="text-[10px] text-ink-400 whitespace-nowrap">{x.ms != null ? `${x.ms}ms` : ""}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tab === "schemes" && (
        <div className="space-y-1.5">
          {(c.unlocks || []).length > 0 && <div className="card p-3 text-[13px]"><b>{L("Unlock actions:", "शर्त पूरी करने वाले कदम:")}</b> {c.unlocks.map((u: any) => `${t(u.label, lang)} → ${u.unlocks.map((x: any) => sname(x, lang)).join(", ")}`).join("; ")}</div>}
          {(c.schemes || []).map((r: any) => <SchemeRow key={r.id} r={r} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} />)}
          {!c.schemes?.length && <div className="card p-3 text-ink-400 text-sm">{L("Schemes appear after consent and data fetch.", "सहमति और डेटा मिलने के बाद योजनाएँ दिखेंगी।")}</div>}
        </div>
      )}

      {tab === "facts" && (
        <div className="card p-3 overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead><tr className="text-left text-ink-400"><th className="py-1">{L("Fact", "जानकारी")}</th><th>{L("Value", "मान")}</th><th>{L("Source", "स्रोत")}</th><th>{L("Evidence", "सबूत")}</th><th></th></tr></thead>
            <tbody>
              {Object.entries(c.facts || {}).map(([k, v]: any) => (
                <tr key={k} className="border-t border-slate-100">
                  <td className="py-1">{factLabel(reg, k, lang)}<span className="block font-mono text-[10px] text-ink-400">{k}</span></td>
                  <td>{factValue(reg, k, v, lang)}</td>
                  <td><span className="pill bg-slate-100">{sourceName(c.fact_meta?.[k]?.source, lang)}</span></td>
                  <td className="text-ink-400 text-[11px]">{evidenceText(c.fact_meta?.[k]?.evidence, lang)}
                    {c.fact_meta?.[k]?.dispute && <span className="block text-amber-700">{L(`disputed: you say ${String(c.fact_meta[k].dispute.claimed)}, open`, `आपत्ति: आपके अनुसार ${factValue(reg, k, c.fact_meta[k].dispute.claimed, lang)}, खुली है`)}</span>}
                    {c.fact_meta?.[k]?.corrected_from && <span className="block">{L(`corrected (was ${String(c.fact_meta[k].corrected_from.value)})`, `सुधारा गया (पहले ${factValue(reg, k, c.fact_meta[k].corrected_from.value, lang)})`)}</span>}</td>
                  <td><button className="text-[11px] text-brand-700 underline" onClick={() => correct(k, v)}>
                    {VERIFIED.includes(c.fact_meta?.[k]?.source) ? L("Dispute", "आपत्ति") : L("Correct", "सुधारें")}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {c.askable_remaining?.length > 0 && <div className="text-[11px] text-ink-400 mt-2">{L("Next highest-value questions: ", "अगले सबसे उपयोगी सवाल: ")}{c.askable_remaining.map((k: string) => factLabel(reg, k, lang)).join(", ")}</div>}
        </div>
      )}

      {tab === "consents" && (
        <div className="space-y-2">
          {(c.consents || []).map((x: any) => (
            <div key={x.consentId} className="card p-3 text-[13px] flex items-start gap-3">
              <Fingerprint size={16} className="text-brand-600 mt-0.5" />
              <div className="flex-1">
                <div className="font-semibold">{t(x.title, lang)} <span className={`pill ml-1 ${x.status === "ACTIVE" ? "bg-emerald-100 text-emerald-800" : x.status === "REVOKED" ? "bg-rose-100 text-rose-700" : "bg-slate-100"}`}>{consentStatus(x.status, lang)}</span> <SimBadge /></div>
                <div className="text-ink-500">{t(x.purpose.text, lang)} · {L("purpose code", "उद्देश्य कोड")} {x.purpose.code} · {L("expires", "समाप्ति")} {x.expiry?.slice(0, 10)}{x.lender ? ` · ${L("lender", "बैंक")} ${x.lender}` : ""}</div>
                <div className="text-[10.5px] font-mono text-ink-400">artefact {x.consentId} · sig {x.signature}</div>
              </div>
              {x.status === "ACTIVE" && <button className="btn-ghost !py-1 !text-xs text-rose-700" onClick={async () => onCase(await api.revoke(c.id, x.consentId))}>{L("Revoke", "वापस लें")}</button>}
            </div>
          ))}
        </div>
      )}

      {tab === "audit" && audit && (
        <div className="card p-3">
          <div className={`text-sm font-semibold ${audit.verify.ok ? "text-emerald-700" : "text-rose-700"}`}>
            <Link2 size={14} className="inline mr-1" />{audit.verify.ok ? L("Hash chain intact", "हैश श्रृंखला सही-सलामत") : L(`Hash chain BROKEN at #${audit.verify.broken_at}`, `हैश श्रृंखला #${audit.verify.broken_at} पर टूटी`)} · {audit.verify.entries} {L("entries", "प्रविष्टियाँ")}
          </div>
          <div className="text-[10.5px] font-mono text-ink-400 break-all">head {audit.verify.head}</div>
          <div className="mt-2 max-h-[55vh] overflow-y-auto">
            {[...audit.log].reverse().map((e: any) => (
              <div key={e.seq} className="text-[11.5px] py-1 border-b border-slate-50 flex gap-2">
                <span className="text-ink-400 w-8">#{e.seq}</span><span className="w-24 text-ink-500">{e.actor}</span>
                <span className="flex-1 font-mono">{e.action}</span><span className="font-mono text-ink-400">{e.hash.slice(0, 10)}…</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
