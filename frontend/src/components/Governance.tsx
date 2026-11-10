import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend, ReferenceLine } from "recharts";
import { Scale, Gauge, Filter, BookOpen } from "lucide-react";
import { api } from "../api";
import { pct, t, useLang } from "../util";
import { CiteChip, Stat, VerBadge } from "./common";

export default function Governance() {
  const [tab, setTab] = useState("fairness");
  const [m, setM] = useState<any>(null);
  const [k, setK] = useState<any>(null);
  useEffect(() => { api.model().then(setM); api.schemes().then(setK); }, []);
  return (
    <div className="max-w-[1300px] mx-auto p-3 md:p-4">
      <div className="text-xl font-bold">Governance</div>
      <div className="text-[13px] text-ink-500 mb-3">Everything the problem statement demands, made inspectable: calibrated and fair risk, cited eligibility, and the gates that enforce them.</div>
      <div className="flex gap-1 mb-3 flex-wrap">
        {[["fairness", "Fairness"], ["calibration", "Calibration & accuracy"], ["gates", "Feature gates"], ["scorecard", "Scorecard table"], ["kb", "Scheme rules & sources"]].map(([a, b]) =>
          <button key={a} onClick={() => setTab(a)} className={`tab ${tab === a ? "tab-on" : ""}`}>{b}</button>)}
      </div>
      {m && tab === "fairness" && <Fairness r={m.report} />}
      {m && tab === "calibration" && <Calibration r={m.report} />}
      {m && tab === "gates" && <Gates r={m.report} />}
      {m && tab === "scorecard" && <ScoreTable sc={m.scorecard} />}
      {k && tab === "kb" && <KB k={k} />}
    </div>
  );
}

function Fairness({ r }: { r: any }) {
  const f = r.fairness, tr = f.traditional_policy, a = r.access;
  const rows = ["female", "male", "rural", "urban", "rural_female", "urban_male", "social_general", "social_obc", "social_sc", "social_st",
    ...Object.keys(f.groups).filter((g) => g.startsWith("zone_"))];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Creditworthy borrowers reached" value={pct(a.saakh_good_borrowers_reached, 0)} sub={`traditional checklist: ${pct(a.traditional_good_borrowers_reached, 0)}`} tone="text-brand-700" />
        <Stat label="Default rate among approved" value={pct(a.saakh_default_rate_approved)} sub={`traditional: ${pct(a.traditional_default_rate_approved)}`} />
        <Stat label="Women / men approval ratio" value={f.summary.female_vs_male.air} sub={`traditional: ${tr.summary.female_vs_male.air}`} tone="text-emerald-700" />
        <Stat label="Fairness gates" value={f.passed ? "PASS" : "FAIL"} sub={`AIR ≥ ${f.gates.air_min} · |EOD| ≤ ${f.gates.eod_max} · |cal gap| ≤ ${f.gates.cal_gap_max}`} tone={f.passed ? "text-emerald-700" : "text-rose-700"} />
      </div>
      <div className={`card p-3 text-[13px] ${f.passed ? "" : "border-rose-200 bg-rose-50/40"}`}>
        <div className="font-semibold">{f.release_decision}</div>
        {f.messages?.length > 0 && <div className="text-rose-700 mt-1">Failed: {f.messages.join("; ")}</div>}
        {f.replication && (
          <div className="mt-1 text-ink-600">Investigation, re-measured on an independent fresh synthetic draw (n = {f.replication.fresh_draw_n.toLocaleString()}):{" "}
            {Object.entries(f.replication.pairs).map(([k, v]: any) => `${k.replace(/_/g, " ")}: EOD ${(v.eod * 100).toFixed(1)}pp, AIR ${v.air}`).join("; ")}.
            {" "}The simulator assigns caste independently of every other variable, so the test-split gap is most likely sampling noise in a small subgroup, but the rule fails closed.</div>)}
        <div className="text-[11px] text-ink-400 mt-1">{f.scope}</div>
      </div>
      <div className="card p-3 overflow-x-auto">
        <b className="text-sm">Gated comparisons (test split, with 95% bootstrap intervals)</b>
        <table className="w-full text-[12.5px] mt-2">
          <thead><tr className="text-left text-ink-400"><th className="py-1">Pair</th><th>AIR (approval ratio)</th><th>95% CI</th><th>EOD (good-borrower gap)</th><th>95% CI</th><th>Max calibration gap</th></tr></thead>
          <tbody>{Object.entries(f.summary).map(([k, v]: any) => (
            <tr key={k} className="border-t border-slate-100">
              <td className="py-1">{k.replace(/_vs_/, " vs ").replace(/_/g, " ")}</td>
              <td className={v.air < f.gates.air_min ? "text-rose-700 font-semibold" : ""}>{v.air}</td><td className="text-ink-400">{v.air_ci95?.join(" – ")}</td>
              <td className={Math.abs(v.eod) > f.gates.eod_max ? "text-rose-700 font-semibold" : ""}>{(v.eod * 100).toFixed(1)}pp</td>
              <td className="text-ink-400">{v.eod_ci95?.map((x: number) => (x * 100).toFixed(1)).join(" – ")}pp</td>
              <td>{(v.cal_gap_max * 100).toFixed(1)}pp</td></tr>))}</tbody>
        </table>
      </div>
      <div className="card p-3 overflow-x-auto">
        <div className="flex items-center gap-2 mb-2"><Scale size={16} className="text-brand-600" /><b className="text-sm">By group; Saakh scorecard vs. traditional document checklist (held-out test set)</b></div>
        <table className="w-full text-[12.5px]">
          <thead><tr className="text-left text-ink-400"><th className="py-1">Group</th><th>n</th><th>True default rate</th><th>Mean simulated risk</th><th>Calibration gap</th><th>AUC</th>
            <th className="bg-brand-50">Saakh approval</th><th className="bg-brand-50">Good borrowers approved</th><th className="bg-slate-50">Traditional approval</th><th className="bg-slate-50">Good approved</th></tr></thead>
          <tbody>{rows.filter((g) => f.groups[g]).map((g) => {
            const s = f.groups[g], o = tr.groups[g];
            return (<tr key={g} className="border-t border-slate-100">
              <td className="py-1.5 capitalize">{g.replace(/_/g, " ")}</td><td>{s.n}</td><td>{pct(s.default_rate)}</td><td>{pct(s.mean_pd)}</td>
              <td className={Math.abs(s.cal_gap) > 0.02 ? "text-rose-700" : "text-emerald-700"}>{(s.cal_gap * 100).toFixed(2)}pp</td><td>{s.auc?.toFixed(3)}</td>
              <td className="bg-brand-50/40 font-semibold">{pct(s.approval_rate, 0)}</td><td className="bg-brand-50/40">{pct(s.good_approval_rate, 0)}</td>
              <td className="bg-slate-50/60">{pct(o.approval_rate, 0)}</td><td className="bg-slate-50/60">{pct(o.good_approval_rate, 0)}</td></tr>);
          })}</tbody>
        </table>
        <div className="text-[11px] text-ink-400 mt-2">Traditional rule: {tr.rule}. Gender, caste, religion, zone and rural/urban are never model inputs; they are used only here, to audit outcomes.</div>
      </div>
      <div className="card p-3 text-[13px] text-ink-700">
        <b>Why the gap closes:</b> in the synthetic population, true repayment depends on business quality and leverage, not on gender or location, but women and rural owners hold fewer ITRs and less collateral in their name. A document checklist inherits that gap; a cash-flow scorecard that is calibrated within each group does not. This is a <i>synthetic</i> result that demonstrates the pipeline; it must be re-run on lender data before any claim about real borrowers.
      </div>
    </div>
  );
}

function Calibration({ r }: { r: any }) {
  const mm = r.metrics;
  const curve = r.reliability.overall.map((x: any) => ({ pred: +(x.pred * 100).toFixed(2), obs: +(x.obs * 100).toFixed(2) }));
  const byG = r.reliability.by_group;
  const merged = (byG.female || []).map((x: any, i: number) => ({ pred: +(x.pred * 100).toFixed(1), female: +(x.obs * 100).toFixed(1), male: byG.male?.[i] ? +(byG.male[i].obs * 100).toFixed(1) : null }));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Stat label="AUC" value={mm.auc.toFixed(3)} sub={mm.ci95 ? `95% CI ${mm.ci95.auc.join("–")}` : undefined} /><Stat label="KS" value={mm.ks.toFixed(3)} /><Stat label="Brier" value={mm.brier.toFixed(4)} />
        <Stat label="ECE" value={pct(mm.ece_calibrated, 2)} sub={`calibration: ${mm.calibration_choice.method}`} tone="text-emerald-700" />
        <Stat label="PR-AUC · log loss" value={`${mm.pr_auc?.toFixed(3)} · ${mm.log_loss?.toFixed(3)}`} sub="base rate ≈ 8%" />
        <Stat label="GBM challenger AUC" value={mm.auc_gbm_challenger.toFixed(3)} sub="black-box ceiling" />
        <Stat label="Cost of interpretability" value={`${(Math.max(0, mm.interpretability_cost_auc) * 100).toFixed(1)} pts`} sub="AUC given up for a points table" tone="text-emerald-700" />
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div className="card p-3"><div className="flex items-center gap-2"><Gauge size={16} className="text-brand-600" /><b className="text-sm">Reliability, predicted vs observed default (%)</b></div>
          <div className="h-64 mt-2"><ResponsiveContainer><LineChart data={curve}>
            <CartesianGrid stroke="#eef2f6" /><XAxis dataKey="pred" type="number" tick={{ fontSize: 10 }} domain={[0, "dataMax"]} /><YAxis tick={{ fontSize: 10 }} />
            <Tooltip /><ReferenceLine segment={[{ x: 0, y: 0 }, { x: 40, y: 40 }]} stroke="#cbd5e1" strokeDasharray="4 4" />
            <Line dataKey="obs" stroke="#0f766e" strokeWidth={2} name="observed" />
          </LineChart></ResponsiveContainer></div></div>
        <div className="card p-3"><b className="text-sm">Calibration within groups (women vs men)</b>
          <div className="h-64 mt-2"><ResponsiveContainer><LineChart data={merged}>
            <CartesianGrid stroke="#eef2f6" /><XAxis dataKey="pred" type="number" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip /><Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 40, y: 40 }]} stroke="#cbd5e1" strokeDasharray="4 4" />
            <Line dataKey="female" stroke="#ea8f12" strokeWidth={2} /><Line dataKey="male" stroke="#0f766e" strokeWidth={2} />
          </LineChart></ResponsiveContainer></div></div>
      </div>
      <div className="card p-3 text-[12.5px] text-ink-500 space-y-1">
        <div><b className="text-ink-700">Target:</b> {r.target}</div>
        <div><b className="text-ink-700">Protocol:</b> {r.evaluation_protocol}</div>
        <div>Data: {r.data.n.toLocaleString()} synthetic businesses ({pct(r.data.composition.female, 0)} women-led, {pct(r.data.composition.rural, 0)} rural, {pct(r.data.composition.thin_file, 0)} thin-file) · split {r.data.train}/{r.data.validation}/{r.data.calibration}/{r.data.test} train/validation/calibration/test · base default rate {pct(r.data.base_default_rate)} · version {r.version}</div>
      </div>
    </div>
  );
}

function Gates({ r }: { r: any }) {
  const { lang } = useLang();
  return (
    <div className="space-y-3">
      <div className="card p-3"><div className="flex items-center gap-2 mb-2"><Filter size={16} className="text-brand-600" /><b className="text-sm">Automated feature gates (decided in training, logged)</b></div>
        {r.candidate_gate.map((g: any) => (
          <div key={g.feature} className="border-t border-slate-100 py-2 text-[13px]">
            <span className={`pill mr-2 ${g.decision === "accepted" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-700"}`}>{g.decision}</span>
            <b>{t(g.label, lang)}</b> <span className="font-mono text-[11px] text-ink-400">{g.feature}</span>
            <div className="text-ink-500">{g.reason}{g.auc_gain != null && ` · AUC ${g.auc_without} → ${g.auc_with}`}</div>
          </div>))}
      </div>
      <div className="card p-3 overflow-x-auto"><b className="text-sm">Proxy audit, can a single feature predict a protected group? (AUC; 0.5 = no information)</b>
        <table className="w-full text-[12.5px] mt-2"><thead><tr className="text-left text-ink-400"><th className="py-1">Feature</th><th>→ gender</th><th>→ rural</th><th>In model</th><th>Note</th></tr></thead>
          <tbody>{r.proxy_audit.map((p: any) => (
            <tr key={p.feature} className="border-t border-slate-100"><td className="py-1">{t(p.label, lang)}</td>
              <td className={p.auc_female > 0.6 ? "text-rose-700 font-semibold" : ""}>{p.auc_female}</td><td className={p.auc_rural > 0.6 ? "text-rose-700 font-semibold" : ""}>{p.auc_rural}</td>
              <td>{p.in_model ? "yes" : "no"}</td><td className="text-ink-400 text-[11px]">{p.dropped_reason}</td></tr>))}</tbody></table>
      </div>
    </div>
  );
}

function ScoreTable({ sc }: { sc: any }) {
  const { lang } = useLang();
  return (
    <div className="card p-3 overflow-x-auto">
      <div className="text-[12px] text-ink-400 mb-2">600 points ↔ 30:1 good:bad odds; +40 points doubles the odds. Bins are forced monotone in the economically sensible direction. Calibration: {sc.calibration.method}.</div>
      {sc.features.map((f: any) => (
        <div key={f.name} className="border-t border-slate-100 py-2">
          <div className="text-[13px] font-semibold">{t(f.label, lang)} <span className="text-[11px] text-ink-400 font-normal">IV {f.iv}</span></div>
          <div className="flex flex-wrap gap-1 mt-1">
            {f.points.map((p: number, i: number) => {
              const lo = i === 0 ? "−∞" : f.edges[i - 1].toFixed(2), hi = i === f.edges.length ? "∞" : f.edges[i].toFixed(2);
              return <span key={i} className="pill bg-slate-50 border border-slate-200 font-mono">[{lo}, {hi}) → {p.toFixed(0)} pts · bad {pct(f.bin_bad_rate[i])}</span>;
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function KB({ k }: { k: any }) {
  const { lang } = useLang();
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="space-y-3">
      <div className="card p-3 text-[13px] text-ink-700"><BookOpen size={15} className="inline mr-1 text-brand-600" />
        Rules are data (YAML), not prompts. The engine refuses to load any criterion without a citation. Every source records whether its clause was verified on the official page, and when.</div>
      {k.schemes.map((s: any) => (
        <div key={s.id} className="card p-3">
          <button className="w-full text-left flex items-center gap-2" onClick={() => setOpen(open === s.id ? null : s.id)}>
            <b className="flex-1">{t(s.name, lang)}</b>
            <span className={`pill ${s.availability === "available" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-700"}`}>{s.availability}</span>
            {Object.entries(s.verification).filter(([, n]: any) => n).map(([v, n]: any) => <span key={v} className="text-[11px]">{n}× <VerBadge v={v} /></span>)}
          </button>
          {s.status_note && <div className="text-[12px] text-rose-800 mt-1">{t(s.status_note, lang)} {s.status_cites.map((c: any, i: number) => <CiteChip key={i} c={c} />)}</div>}
          {open === s.id && <div className="mt-2 space-y-1">{s.criteria.map((c: any) => (
            <div key={c.id} className="text-[12.5px] flex gap-2"><span className="font-mono text-[11px] text-ink-400 w-36 shrink-0">{c.id}</span><span className="flex-1">{t(c.text, lang)}<CiteChip c={c.cite} /></span></div>))}
            {s.lender_checks?.length > 0 && <div className="label pt-1">Decided by the lender, not the scheme</div>}
            {s.lender_checks?.map((lc: any, i: number) => (
              <div key={i} className="text-[12.5px] flex gap-2"><span className="w-36 shrink-0" /><span className="flex-1 text-ink-600">{t(lc.text, lang)}<CiteChip c={lc.cite} /></span></div>))}
          </div>}
        </div>
      ))}
      <div className="card p-3 overflow-x-auto"><b className="text-sm">Source registry</b>
        <table className="w-full text-[12px] mt-2"><tbody>{k.sources.map((s: any) => (
          <tr key={s.id} className="border-t border-slate-100"><td className="py-1 font-mono text-[11px] w-44">{s.id}</td><td><a className="text-brand-700" href={s.url} target="_blank" rel="noreferrer">{s.title}</a><div className="text-ink-400">{s.publisher}{s.note ? `, ${s.note}` : ""}</div></td>
            <td className="w-56"><VerBadge v={s.verification} /></td><td className="w-24 text-ink-400">{s.checked}</td></tr>))}</tbody></table>
      </div>
    </div>
  );
}
