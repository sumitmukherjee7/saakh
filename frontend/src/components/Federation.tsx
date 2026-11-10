import { useState } from "react";
import { Users } from "lucide-react";
import { api } from "../api";
import { inr } from "../util";
import { Stat } from "./common";

export default function Federation() {
  const [r, setR] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  async function run() { setBusy(true); setR(await api.screen(40)); setBusy(false); }
  return (
    <div className="max-w-[1200px] mx-auto p-3 md:p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Users className="text-brand-600" /><div className="text-xl font-bold">SHG federation / Bank Mitra, cohort screening</div>
      </div>
      <div className="text-[13px] text-ink-500 max-w-3xl">A federation officer or business correspondent screens a whole member list against every scheme in seconds, using profile facts only (no financial data, so no consent pull). Members with a match are invited to start their own consented Saakh journey.</div>
      <button className="btn-primary" disabled={busy} onClick={run}>{busy ? "Screening…" : "Screen 40 members (synthetic list)"}</button>
      {r && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Members screened" value={r.n} />
            <Stat label="With ≥1 eligible scheme" value={r.with_any} tone="text-brand-700" />
            <Stat label="Est. annual benefit unlocked" value={inr(r.est_annual_value, true)} sub="vs borrowing informally at 30%" tone="text-emerald-700" />
            <Stat label="Need Udyam first" value={r.members.filter((m: any) => m.unlock).length} sub="one free registration unlocks CGTMSE" />
          </div>
          <div className="card p-3">
            <div className="flex flex-wrap gap-2 mb-2">{Object.entries(r.by_scheme).map(([k, v]: any) => <span key={k} className="pill bg-brand-50 text-brand-700">{k}: {v}</span>)}</div>
            <table className="w-full text-[12.5px]">
              <thead><tr className="text-left text-ink-400"><th className="py-1">Member</th><th>Activity</th><th>Need</th><th>Eligible now</th><th>Next action</th></tr></thead>
              <tbody>{r.members.map((m: any) => (
                <tr key={m.id} className="border-t border-slate-100"><td className="py-1">{m.id} · {m.name}</td><td className="capitalize">{m.activity.replace(/_/g, " ")}</td><td>{inr(m.need)}</td>
                  <td>{m.eligible.join(", ") || <span className="text-ink-400">-</span>}</td><td>{m.unlock ? <span className="pill bg-saffron-50 text-saffron-600">Register Udyam</span> : ""}</td></tr>))}</tbody>
            </table>
            <div className="text-[11px] text-ink-400 mt-2">{r.note}</div>
          </div>
        </>
      )}
    </div>
  );
}
