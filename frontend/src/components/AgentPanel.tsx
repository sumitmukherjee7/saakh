import { useEffect, useState } from "react";
import { Bot, Wrench, RefreshCw, ShieldAlert, Brain, UserCheck, LifeBuoy, EyeOff, ListChecks, Link2, Fingerprint } from "lucide-react";
import { api, sendEvent } from "../api";
import { inr, t, useLang } from "../util";
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
  const [tab, setTab] = useState("trace");
  const [audit, setAudit] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { if (tab === "audit") api.audit(c.id).then(setAudit); }, [tab, c]);
  const VERIFIED = ["ekyc", "bureau", "udyam", "udyam_portal", "aa", "aa-inferred", "statement_upload", "statement_upload-inferred"];
  async function correct(k: string, v: any) {
    const sourced = VERIFIED.includes(c.fact_meta?.[k]?.source);
    const nv = window.prompt(sourced
      ? `"${k}" came from ${c.fact_meta[k].source}. Your correction is recorded as a dispute the bank will see; the sourced value stays in use until it is fixed at the source. Value you believe is right:`
      : `New value for "${k}" (now: ${String(v)}):`, String(v ?? ""));
    if (nv === null || nv.trim() === "") return;
    const reason = window.prompt("Reason (optional):", "") || null;
    const val = nv.trim() === "true" ? true : nv.trim() === "false" ? false : nv.trim();
    try { const r = await sendEvent(c.id, { type: "correct", fact: k, value: val, reason }); if (r) onCase(r); }
    catch (e: any) { alert(e.message); }
  }

  const tabs = [["trace", "Agent trace"], ["schemes", "Schemes & proofs"], ["facts", "Facts & provenance"], ["consents", "Consents"], ["audit", "Audit chain"]];
  return (
    <div className="space-y-3">
      <div className="card p-3">
        <div className="flex items-center gap-2">
          <Bot size={18} className="text-brand-600" />
          <div className="font-semibold">Saakh agent</div>
          <span className="text-[12px] text-ink-400">goal: right credit · fair terms · complete file · your approval</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-[12px]">
          <div><div className="label">Waiting on</div><div className="font-semibold">{c.pending?.type?.replace(/_/g, " ") || (c.submission ? "lender" : "-")}</div></div>
          <div><div className="label">Schemes eligible</div><div className="font-semibold">{(c.schemes || []).filter((r: any) => r.eligibility === "eligible").map((r: any) => r.short + (r.provisional?.length ? " (provisional)" : "")).join(", ") || "-"}</div></div>
          <div><div className="label">Simulated risk</div>{c.score ? <BandChip band={c.score.band} pd={c.score.pd} /> : "-"}</div>
          <div><div className="label">Selected</div><div className="font-semibold">{c.selected_offer ? `${c.selected_offer.scheme_short} ${inr(c.selected_offer.amount)}` : "-"}</div></div>
        </div>
      </div>
      <div className="flex gap-1 flex-wrap">{tabs.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`tab ${tab === k ? "tab-on" : ""}`}>{l}</button>)}</div>

      {tab === "trace" && (
        <div className="card p-3">
          <div className="text-[12px] text-ink-400 mb-2">Every step the agent took, tool calls pass a code-level guard (consent, approval hash) before running.</div>
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
          {(c.unlocks || []).length > 0 && <div className="card p-3 text-[13px]"><b>Unlock actions:</b> {c.unlocks.map((u: any) => `${t(u.label, lang)} → ${u.unlocks.map((x: any) => x.short).join(", ")}`).join("; ")}</div>}
          {(c.schemes || []).map((r: any) => <SchemeRow key={r.id} r={r} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} />)}
          {!c.schemes?.length && <div className="card p-3 text-ink-400 text-sm">Schemes appear after consent and data fetch.</div>}
        </div>
      )}

      {tab === "facts" && (
        <div className="card p-3 overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead><tr className="text-left text-ink-400"><th className="py-1">Fact</th><th>Value</th><th>Source</th><th>Evidence</th><th></th></tr></thead>
            <tbody>
              {Object.entries(c.facts || {}).map(([k, v]: any) => (
                <tr key={k} className="border-t border-slate-100">
                  <td className="py-1 font-mono">{k}</td><td>{typeof v === "number" && v > 999 ? inr(v) : String(v)}</td>
                  <td><span className="pill bg-slate-100">{c.fact_meta?.[k]?.source}</span></td>
                  <td className="text-ink-400 text-[11px]">{c.fact_meta?.[k]?.evidence}
                    {c.fact_meta?.[k]?.dispute && <span className="block text-amber-700">disputed: you say {String(c.fact_meta[k].dispute.claimed)}, open</span>}
                    {c.fact_meta?.[k]?.corrected_from && <span className="block">corrected (was {String(c.fact_meta[k].corrected_from.value)})</span>}</td>
                  <td><button className="text-[11px] text-brand-700 underline" onClick={() => correct(k, v)}>
                    {VERIFIED.includes(c.fact_meta?.[k]?.source) ? "Dispute" : "Correct"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {c.askable_remaining?.length > 0 && <div className="text-[11px] text-ink-400 mt-2">Next highest-value questions: {c.askable_remaining.join(", ")}</div>}
        </div>
      )}

      {tab === "consents" && (
        <div className="space-y-2">
          {(c.consents || []).map((x: any) => (
            <div key={x.consentId} className="card p-3 text-[13px] flex items-start gap-3">
              <Fingerprint size={16} className="text-brand-600 mt-0.5" />
              <div className="flex-1">
                <div className="font-semibold">{t(x.title, lang)} <span className={`pill ml-1 ${x.status === "ACTIVE" ? "bg-emerald-100 text-emerald-800" : x.status === "REVOKED" ? "bg-rose-100 text-rose-700" : "bg-slate-100"}`}>{x.status}</span> <SimBadge /></div>
                <div className="text-ink-500">{t(x.purpose.text, lang)} · purpose code {x.purpose.code} · expires {x.expiry?.slice(0, 10)}{x.lender ? ` · lender ${x.lender}` : ""}</div>
                <div className="text-[10.5px] font-mono text-ink-400">artefact {x.consentId} · sig {x.signature}</div>
              </div>
              {x.status === "ACTIVE" && <button className="btn-ghost !py-1 !text-xs text-rose-700" onClick={async () => onCase(await api.revoke(c.id, x.consentId))}>Revoke</button>}
            </div>
          ))}
        </div>
      )}

      {tab === "audit" && audit && (
        <div className="card p-3">
          <div className={`text-sm font-semibold ${audit.verify.ok ? "text-emerald-700" : "text-rose-700"}`}>
            <Link2 size={14} className="inline mr-1" />Hash chain {audit.verify.ok ? "intact" : `BROKEN at #${audit.verify.broken_at}`} · {audit.verify.entries} entries
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
