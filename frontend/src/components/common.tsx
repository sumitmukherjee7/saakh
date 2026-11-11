import { useState } from "react";
import { BadgeCheck, CircleDot, CircleDashed, ExternalLink, ChevronDown, ChevronRight, Check, X, HelpCircle } from "lucide-react";
import { t, useLang, UI, pct } from "../util";

export function VerBadge({ v }: { v: string }) {
  const { lang } = useLang();
  const map: any = {
    verified: { icon: <BadgeCheck size={12} />, cls: "bg-emerald-50 text-emerald-700 border-emerald-200",
      en: "Verified on official page", hi: "आधिकारिक पेज पर सत्यापित" },
    official_unverified: { icon: <CircleDot size={12} />, cls: "bg-sky-50 text-sky-700 border-sky-200",
      en: "Official source · clause check pending", hi: "आधिकारिक स्रोत · जाँच बाकी" },
    secondary: { icon: <CircleDashed size={12} />, cls: "bg-amber-50 text-amber-700 border-amber-200",
      en: "Secondary source · confirm at branch", hi: "द्वितीयक स्रोत · शाखा से पुष्टि करें" },
  };
  const m = map[v] || map.secondary;
  return <span className={`pill border ${m.cls}`}>{m.icon}{m[lang]}</span>;
}

export function CiteChip({ c, n }: { c: any; n?: number }) {
  const { lang } = useLang();
  const hi = lang === "hi";
  const [open, setOpen] = useState(false);
  if (!c) return null;
  const color = c.verification === "verified" ? "text-emerald-700 bg-emerald-50 border-emerald-200"
    : c.verification === "official_unverified" ? "text-sky-700 bg-sky-50 border-sky-200" : "text-amber-700 bg-amber-50 border-amber-200";
  return (
    <span className="relative inline-block align-middle">
      <button onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className={`ml-1 inline-flex items-center rounded-md border px-1.5 text-[10px] font-semibold ${color}`}
        title={c.title}>
        {n != null ? `[${n}]` : hi ? "स्रोत" : "source"}
      </button>
      {open && (
        <span className="absolute z-30 left-0 top-6 w-72 card p-3 text-left text-xs text-ink-700 leading-snug" onClick={(e) => e.stopPropagation()}>
          <span className="block font-semibold text-ink-900">{c.title}</span>
          <span className="block text-ink-500 mt-0.5">{c.publisher}</span>
          <span className="block mt-1"><span className="label">{hi ? "स्थान" : "Locator"}</span> {c.loc}</span>
          <span className="block mt-1"><VerBadge v={c.verification} /></span>
          <span className="block mt-1 text-ink-400">{hi ? "जाँचा गया" : "Checked"} {c.checked}</span>
          {c.note && <span className="block mt-1 text-amber-700">{c.note}</span>}
          <a className="mt-2 inline-flex items-center gap-1 text-brand-700 font-semibold" href={c.url} target="_blank" rel="noreferrer">
            {hi ? "स्रोत खोलें" : "Open source"} <ExternalLink size={12} /></a>
        </span>
      )}
    </span>
  );
}

export function StatusPill({ s, kind, provisional }: { s: string; kind?: string; provisional?: any[] }) {
  const { lang } = useLang();
  const cls: any = { eligible: "bg-emerald-100 text-emerald-800", needs_info: "bg-amber-100 text-amber-800",
    not_eligible: "bg-slate-100 text-slate-600", lapsed: "bg-rose-100 text-rose-700" };
  let label = t(UI[s], lang) || s;
  if (s === "eligible" && kind === "guarantee") label = lang === "hi" ? "शर्तें पूरी · बैंक तय करेगा" : "Conditions met · lender decides";
  if (s === "eligible" && kind === "entitlement") label = lang === "hi" ? "आप पर लागू" : "Applies to you";
  if (s === "eligible" && kind !== "guarantee" && kind !== "entitlement") label = lang === "hi" ? "शर्तें पूरी" : "Conditions met";
  if (s === "eligible" && provisional?.length) {
    const by = provisional.map((p: any) => t(p.by, lang)).join(", ");
    return <span className="pill bg-amber-100 text-amber-800" title={provisional.map((p: any) => t(p.text, lang)).join("\n")}>
      {lang === "hi" ? `अस्थायी · ${by} सत्यापित करेगा` : `Provisional · ${by} verifies`}</span>;
  }
  return <span className={`pill ${cls[s] || "bg-slate-100"}`}>{label}</span>;
}

export function BandChip({ band, pd }: { band: string; pd?: number }) {
  const { lang } = useLang();
  const hi = lang === "hi";
  const cls: any = { A: "bg-emerald-600", B: "bg-emerald-500", C: "bg-amber-500", D: "bg-orange-600", E: "bg-rose-600" };
  return (
    <span className={`pill text-white ${cls[band] || "bg-slate-400"}`}>
      {hi ? "बैंड" : "Band"} {band}{pd != null && <span className="font-normal opacity-90" title={hi ? "कृत्रिम डेटा पर प्रशिक्षित मॉडल का सिम्युलेटेड जोखिम अनुमान" : "Simulated risk estimate from a model trained on synthetic data"}> · {hi ? "सिम. जोखिम" : "sim. risk"} {pct(pd)}</span>}
    </span>
  );
}

const ICON: any = { T: <Check size={13} className="text-emerald-600" />, F: <X size={13} className="text-rose-600" />,
  U: <HelpCircle size={13} className="text-amber-600" /> };

function fmtVal(v: any, lang: string) {
  if (v === true) return lang === "hi" ? "हाँ" : "yes";
  if (v === false) return lang === "hi" ? "नहीं" : "no";
  if (Array.isArray(v)) return v.join(" – ");
  if (typeof v === "number" && v >= 1000) return "₹" + v.toLocaleString("en-IN");
  return String(v);
}

export function ProofTree({ node, depth = 0, cites }: { node: any; depth?: number; cites: any[] }) {
  const { lang } = useLang();
  const [open, setOpen] = useState(depth < 1 || node.status !== "T");
  const idx = (c: any) => (c ? cites.findIndex((x) => x.source === c.source && x.loc === c.loc) + 1 : 0);
  const isLeafLike = node.kind === "leaf" || (node.kind === "implies" && node.text);
  if (isLeafLike) {
    return (
      <div className="flex items-start gap-2 py-1 text-[13px]">
        <span className="mt-0.5">{ICON[node.status]}</span>
        <span className="flex-1">
          {t(node.text, lang)}
          {node.kind === "leaf" && node.actual != null && (
            <span className="ml-1 text-ink-400 text-[11px]">({lang === "hi" ? "आप" : "you"}: {fmtVal(node.actual, lang)})</span>)}
          {node.cite && <CiteChip c={node.cite} n={idx(node.cite) || undefined} />}
        </span>
      </div>
    );
  }
  return (
    <div className={depth ? "ml-3 border-l border-slate-200 pl-2" : ""}>
      {depth > 0 && (
        <button className="flex items-center gap-1 text-xs text-ink-500 py-1" onClick={() => setOpen(!open)}>
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}{ICON[node.status]}
          <span>{node.kind === "any" ? (lang === "hi" ? "इनमें से कोई एक" : "any of") : node.kind === "all" ? (lang === "hi" ? "ये सभी" : "all of") : node.kind === "not" ? (lang === "hi" ? "यह नहीं" : "not") : node.kind}</span>
        </button>
      )}
      {open && (node.children || []).map((c: any) => <ProofTree key={c.id} node={c} depth={depth + 1} cites={cites} />)}
    </div>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: any; sub?: string; tone?: string }) {
  return (
    <div className="card p-3">
      <div className="label">{label}</div>
      <div className={`text-xl font-bold mt-0.5 ${tone || "text-ink-900"}`}>{value}</div>
      {sub && <div className="text-[11px] text-ink-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export function SimBadge() {
  const { lang } = useLang();
  return <span className="pill bg-violet-50 text-violet-700 border border-violet-200">{lang === "hi" ? "सिम्युलेटेड" : "SIMULATED"}</span>;
}
