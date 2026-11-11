import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend, ReferenceLine } from "recharts";
import { Scale, Gauge, Filter, BookOpen } from "lucide-react";
import { api } from "../api";
import { groupName, pct, reportText, t, useL, useLang } from "../util";
import { CiteChip, Stat, VerBadge } from "./common";

export default function Governance() {
  const L = useL();
  const [tab, setTab] = useState("fairness");
  const [m, setM] = useState<any>(null);
  const [k, setK] = useState<any>(null);
  useEffect(() => { api.model().then(setM); api.schemes().then(setK); }, []);
  const tabs: [string, string][] = [["fairness", L("Fairness", "निष्पक्षता")], ["calibration", L("Calibration & accuracy", "कैलिब्रेशन और सटीकता")],
    ["gates", L("Feature gates", "फ़ीचर जाँच")], ["scorecard", L("Scorecard table", "स्कोरकार्ड तालिका")], ["kb", L("Scheme rules & sources", "योजना नियम और स्रोत")]];
  return (
    <div className="max-w-[1300px] mx-auto p-3 md:p-4">
      <div className="text-xl font-bold">{L("Governance", "शासन")}</div>
      <div className="text-[13px] text-ink-500 mb-3">{L(
        "Everything the problem statement demands, made inspectable: calibrated and fair risk, cited eligibility, and the gates that enforce them.",
        "समस्या-विवरण जो माँगता है, वह सब यहाँ जाँचा जा सकता है: कैलिब्रेटेड और निष्पक्ष जोखिम, स्रोत सहित पात्रता, और इन्हें लागू करने वाली जाँचें।")}</div>
      <div className="flex gap-1 mb-3 flex-wrap">
        {tabs.map(([a, b]) => <button key={a} onClick={() => setTab(a)} className={`tab ${tab === a ? "tab-on" : ""}`}>{b}</button>)}
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
  const L = useL();
  const { lang } = useLang();
  const f = r.fairness, tr = f.traditional_policy, a = r.access;
  const rows = ["female", "male", "rural", "urban", "rural_female", "urban_male", "social_general", "social_obc", "social_sc", "social_st",
    ...Object.keys(f.groups).filter((g) => g.startsWith("zone_"))];
  const decision = f.passed
    ? L("Passed all fairness gates.", "सभी निष्पक्षता जाँचें पास।")
    : L(f.release_decision, "रोका गया (BLOCKED): अलग रखे गए टेस्ट डेटा पर एक निष्पक्षता जाँच विफल हुई। नियम सुरक्षित दिशा में रुकता है: असली बैंक डेटा पर यह मॉडल तब तक लागू नहीं होगा जब तक इस अंतर की जाँच न हो जाए। यहाँ इसका उपयोग केवल प्रदर्शन के लिए है।");
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label={L("Creditworthy borrowers reached", "योग्य उधारकर्ताओं तक पहुँच")} value={pct(a.saakh_good_borrowers_reached, 0)}
          sub={`${L("traditional checklist", "पारंपरिक चेकलिस्ट")}: ${pct(a.traditional_good_borrowers_reached, 0)}`} tone="text-brand-700" />
        <Stat label={L("Default rate among approved", "मंज़ूर ऋणों में डिफ़ॉल्ट दर")} value={pct(a.saakh_default_rate_approved)}
          sub={`${L("traditional", "पारंपरिक")}: ${pct(a.traditional_default_rate_approved)}`} />
        <Stat label={L("Women / men approval ratio", "महिला / पुरुष मंज़ूरी अनुपात")} value={f.summary.female_vs_male.air}
          sub={`${L("traditional", "पारंपरिक")}: ${tr.summary.female_vs_male.air}`} tone="text-emerald-700" />
        <Stat label={L("Fairness gates", "निष्पक्षता जाँचें")} value={f.passed ? L("PASS", "पास") : L("FAIL", "विफल")}
          sub={`AIR ≥ ${f.gates.air_min} · |EOD| ≤ ${f.gates.eod_max} · |cal gap| ≤ ${f.gates.cal_gap_max}`} tone={f.passed ? "text-emerald-700" : "text-rose-700"} />
      </div>
      <div className={`card p-3 text-[13px] ${f.passed ? "" : "border-rose-200 bg-rose-50/40"}`}>
        <div className="font-semibold">{decision}</div>
        {f.messages?.length > 0 && <div className="text-rose-700 mt-1">{L("Failed", "विफल")}: <span className="font-mono text-[12px]">{f.messages.join("; ")}</span></div>}
        {f.replication && (
          <div className="mt-1 text-ink-600">
            {L(`Investigation, re-measured on an independent fresh synthetic draw (n = ${f.replication.fresh_draw_n.toLocaleString()}): `,
               `जाँच: एक नए, स्वतंत्र कृत्रिम नमूने (n = ${f.replication.fresh_draw_n.toLocaleString()}) पर दोबारा मापा गया: `)}
            {Object.entries(f.replication.pairs).map(([k, v]: any) => `${groupName(k, lang)}: EOD ${(v.eod * 100).toFixed(1)}pp, AIR ${v.air}`).join("; ")}.{" "}
            {L("The simulator assigns caste independently of every other variable, so the test-split gap is most likely sampling noise in a small subgroup, but the rule fails closed.",
               "सिम्युलेटर जाति को बाकी सभी चीज़ों से स्वतंत्र रखता है, इसलिए टेस्ट डेटा का यह अंतर संभवतः एक छोटे उप-समूह में नमूने का संयोग है; फिर भी नियम सुरक्षित दिशा में रुकता है।")}</div>)}
        <div className="text-[11px] text-ink-400 mt-1">{L(f.scope,
          "जाँचे गए जोड़े: महिला बनाम पुरुष, ग्रामीण बनाम शहरी, ग्रामीण महिलाएँ बनाम शहरी पुरुष, SC/ST/OBC बनाम सामान्य वर्ग, और सबसे अलग दो क्षेत्र। यह कृत्रिम आबादी है जिसमें असली जोखिम बनावट से ही समूह-निरपेक्ष है, इसलिए अच्छे नतीजे कुछ हद तक इसी बनावट से आते हैं; किसी भी दावे से पहले असली डेटा पर उप-समूह विश्लेषण ज़रूरी है।")}</div>
      </div>
      <div className="card p-3 overflow-x-auto">
        <b className="text-sm">{L("Gated comparisons (test split, with 95% bootstrap intervals)", "जाँचे गए तुलनात्मक जोड़े (टेस्ट डेटा, 95% बूटस्ट्रैप अंतराल सहित)")}</b>
        <table className="w-full text-[12.5px] mt-2">
          <thead><tr className="text-left text-ink-400"><th className="py-1">{L("Pair", "जोड़ा")}</th><th>{L("AIR (approval ratio)", "AIR (मंज़ूरी अनुपात)")}</th><th>95% CI</th>
            <th>{L("EOD (good-borrower gap)", "EOD (अच्छे उधारकर्ताओं में अंतर)")}</th><th>95% CI</th><th>{L("Max calibration gap", "अधिकतम कैलिब्रेशन अंतर")}</th></tr></thead>
          <tbody>{Object.entries(f.summary).map(([k, v]: any) => (
            <tr key={k} className="border-t border-slate-100">
              <td className="py-1">{groupName(k, lang)}</td>
              <td className={v.air < f.gates.air_min ? "text-rose-700 font-semibold" : ""}>{v.air}</td><td className="text-ink-400">{v.air_ci95?.join(" – ")}</td>
              <td className={Math.abs(v.eod) > f.gates.eod_max ? "text-rose-700 font-semibold" : ""}>{(v.eod * 100).toFixed(1)}pp</td>
              <td className="text-ink-400">{v.eod_ci95?.map((x: number) => (x * 100).toFixed(1)).join(" – ")}pp</td>
              <td>{(v.cal_gap_max * 100).toFixed(1)}pp</td></tr>))}</tbody>
        </table>
      </div>
      <div className="card p-3 overflow-x-auto">
        <div className="flex items-center gap-2 mb-2"><Scale size={16} className="text-brand-600" />
          <b className="text-sm">{L("By group; Saakh scorecard vs. traditional document checklist (held-out test set)", "समूह-वार; साख स्कोरकार्ड बनाम पारंपरिक दस्तावेज़ चेकलिस्ट (अलग रखा गया टेस्ट डेटा)")}</b></div>
        <table className="w-full text-[12.5px]">
          <thead><tr className="text-left text-ink-400"><th className="py-1">{L("Group", "समूह")}</th><th>n</th><th>{L("True default rate", "वास्तविक डिफ़ॉल्ट दर")}</th>
            <th>{L("Mean simulated risk", "औसत अनुमानित जोखिम")}</th><th>{L("Calibration gap", "कैलिब्रेशन अंतर")}</th><th>AUC</th>
            <th className="bg-brand-50">{L("Saakh approval", "साख मंज़ूरी")}</th><th className="bg-brand-50">{L("Good borrowers approved", "अच्छे उधारकर्ता मंज़ूर")}</th>
            <th className="bg-slate-50">{L("Traditional approval", "पारंपरिक मंज़ूरी")}</th><th className="bg-slate-50">{L("Good approved", "अच्छे मंज़ूर")}</th></tr></thead>
          <tbody>{rows.filter((g) => f.groups[g]).map((g) => {
            const s = f.groups[g], o = tr.groups[g];
            return (<tr key={g} className="border-t border-slate-100">
              <td className="py-1.5 capitalize">{groupName(g, lang)}</td><td>{s.n}</td><td>{pct(s.default_rate)}</td><td>{pct(s.mean_pd)}</td>
              <td className={Math.abs(s.cal_gap) > 0.02 ? "text-rose-700" : "text-emerald-700"}>{(s.cal_gap * 100).toFixed(2)}pp</td><td>{s.auc?.toFixed(3)}</td>
              <td className="bg-brand-50/40 font-semibold">{pct(s.approval_rate, 0)}</td><td className="bg-brand-50/40">{pct(s.good_approval_rate, 0)}</td>
              <td className="bg-slate-50/60">{pct(o.approval_rate, 0)}</td><td className="bg-slate-50/60">{pct(o.good_approval_rate, 0)}</td></tr>);
          })}</tbody>
        </table>
        <div className="text-[11px] text-ink-400 mt-2">{L("Traditional rule", "पारंपरिक नियम")}: {reportText(tr.rule, lang)}. {L(
          "Gender, caste, religion, zone and rural/urban are never model inputs; they are used only here, to audit outcomes.",
          "लिंग, जाति, धर्म, क्षेत्र और ग्रामीण/शहरी कभी मॉडल में नहीं जाते; इनका उपयोग केवल यहाँ, नतीजों की जाँच के लिए होता है।")}</div>
      </div>
      <div className="card p-3 text-[13px] text-ink-700">
        <b>{L("Why the gap closes:", "अंतर क्यों घटता है:")}</b>{" "}{L(
          "in the synthetic population, true repayment depends on business quality and leverage, not on gender or location, but women and rural owners hold fewer ITRs and less collateral in their name. A document checklist inherits that gap; a cash-flow scorecard that is calibrated within each group does not. This is a synthetic result that demonstrates the pipeline; it must be re-run on lender data before any claim about real borrowers.",
          "कृत्रिम आबादी में असली भुगतान क्षमता व्यवसाय की गुणवत्ता और कर्ज़ के बोझ पर निर्भर है, लिंग या जगह पर नहीं; पर महिलाओं और ग्रामीण मालिकों के नाम पर ITR और गिरवी कम होते हैं। दस्तावेज़ चेकलिस्ट यह अंतर अपना लेती है; हर समूह में कैलिब्रेटेड नकदी-प्रवाह स्कोरकार्ड नहीं अपनाता। यह कृत्रिम नतीजा केवल प्रणाली को दिखाता है; असली उधारकर्ताओं पर कोई दावा करने से पहले इसे बैंक डेटा पर दोबारा चलाना होगा।")}
      </div>
    </div>
  );
}

function Calibration({ r }: { r: any }) {
  const L = useL();
  const mm = r.metrics;
  const curve = r.reliability.overall.map((x: any) => ({ pred: +(x.pred * 100).toFixed(2), obs: +(x.obs * 100).toFixed(2) }));
  const byG = r.reliability.by_group;
  const female = L("female", "महिलाएँ"), male = L("male", "पुरुष");
  const merged = (byG.female || []).map((x: any, i: number) => ({ pred: +(x.pred * 100).toFixed(1), [female]: +(x.obs * 100).toFixed(1), [male]: byG.male?.[i] ? +(byG.male[i].obs * 100).toFixed(1) : null }));
  const method = mm.calibration_choice.method === "identity" ? L("none needed (identity)", "आवश्यक नहीं (identity)") : mm.calibration_choice.method;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Stat label="AUC" value={mm.auc.toFixed(3)} sub={mm.ci95 ? `95% CI ${mm.ci95.auc.join("–")}` : undefined} /><Stat label="KS" value={mm.ks.toFixed(3)} /><Stat label="Brier" value={mm.brier.toFixed(4)} />
        <Stat label="ECE" value={pct(mm.ece_calibrated, 2)} sub={`${L("calibration", "कैलिब्रेशन")}: ${method}`} tone="text-emerald-700" />
        <Stat label="PR-AUC · log loss" value={`${mm.pr_auc?.toFixed(3)} · ${mm.log_loss?.toFixed(3)}`} sub={L("base rate ≈ 8%", "आधार दर ≈ 8%")} />
        <Stat label={L("GBM challenger AUC", "GBM चैलेंजर AUC")} value={mm.auc_gbm_challenger.toFixed(3)} sub={L("black-box ceiling", "ब्लैक-बॉक्स की ऊपरी सीमा")} />
        <Stat label={L("Cost of interpretability", "समझने-योग्य होने की कीमत")} value={`${(Math.max(0, mm.interpretability_cost_auc) * 100).toFixed(1)} ${L("pts", "अंक")}`}
          sub={L("AUC given up for a points table", "पॉइंट तालिका के लिए छोड़ा गया AUC")} tone="text-emerald-700" />
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div className="card p-3"><div className="flex items-center gap-2"><Gauge size={16} className="text-brand-600" />
          <b className="text-sm">{L("Reliability, predicted vs observed default (%)", "विश्वसनीयता: अनुमानित बनाम वास्तविक डिफ़ॉल्ट (%)")}</b></div>
          <div className="h-64 mt-2"><ResponsiveContainer><LineChart data={curve}>
            <CartesianGrid stroke="#eef2f6" /><XAxis dataKey="pred" type="number" tick={{ fontSize: 10 }} domain={[0, "dataMax"]} /><YAxis tick={{ fontSize: 10 }} />
            <Tooltip /><ReferenceLine segment={[{ x: 0, y: 0 }, { x: 40, y: 40 }]} stroke="#cbd5e1" strokeDasharray="4 4" />
            <Line dataKey="obs" stroke="#0f766e" strokeWidth={2} name={L("observed", "वास्तविक")} />
          </LineChart></ResponsiveContainer></div></div>
        <div className="card p-3"><b className="text-sm">{L("Calibration within groups (women vs men)", "समूहों के भीतर कैलिब्रेशन (महिलाएँ बनाम पुरुष)")}</b>
          <div className="h-64 mt-2"><ResponsiveContainer><LineChart data={merged}>
            <CartesianGrid stroke="#eef2f6" /><XAxis dataKey="pred" type="number" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip /><Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 40, y: 40 }]} stroke="#cbd5e1" strokeDasharray="4 4" />
            <Line dataKey={female} stroke="#ea8f12" strokeWidth={2} /><Line dataKey={male} stroke="#0f766e" strokeWidth={2} />
          </LineChart></ResponsiveContainer></div></div>
      </div>
      <div className="card p-3 text-[12.5px] text-ink-500 space-y-1">
        <div><b className="text-ink-700">{L("Target:", "लक्ष्य:")}</b> {L(r.target,
          "कृत्रिम (SIMULATED) डिफ़ॉल्ट लेबल, जो हाथ से तय किए गए जनरेटर (risk/synth.py) से बना है; यह 12 महीने के असली 90+ DPD नतीजे पर आधारित नहीं। नतीजे एक अनुमानित जोखिम हैं, डिफ़ॉल्ट की प्रमाणित संभावना नहीं।")}</div>
        <div><b className="text-ink-700">{L("Protocol:", "प्रक्रिया:")}</b> {L(r.evaluation_protocol,
          "ट्रेन 50% / वैलिडेशन 15% (फ़ीचर और प्रॉक्सी जाँच) / कैलिब्रेशन 15% (2-fold cross-fitting से तरीका चुना) / टेस्ट 20% (अंतिम माप, एक ही बार)। एक ही जनरेटर से रैंडम बँटवारा: कृत्रिम डेटा पर समय-आधारित या बाहरी जाँच संभव नहीं।")}</div>
        <div>{L("Data", "डेटा")}: {r.data.n.toLocaleString()} {L("synthetic businesses", "कृत्रिम व्यवसाय")} ({pct(r.data.composition.female, 0)} {L("women-led", "महिला-संचालित")}, {pct(r.data.composition.rural, 0)} {L("rural", "ग्रामीण")}, {pct(r.data.composition.thin_file, 0)} {L("thin-file", "कम क्रेडिट इतिहास")}) · {L("split", "बँटवारा")} {r.data.train}/{r.data.validation}/{r.data.calibration}/{r.data.test} {L("train/validation/calibration/test", "ट्रेन/वैलिडेशन/कैलिब्रेशन/टेस्ट")} · {L("base default rate", "आधार डिफ़ॉल्ट दर")} {pct(r.data.base_default_rate)} · {L("version", "संस्करण")} {r.version}</div>
      </div>
    </div>
  );
}

function Gates({ r }: { r: any }) {
  const L = useL();
  const { lang } = useLang();
  const dec: Record<string, string> = { accepted: L("accepted", "स्वीकृत"), rejected: L("rejected", "अस्वीकृत"), removed: L("removed", "हटाया गया") };
  return (
    <div className="space-y-3">
      <div className="card p-3"><div className="flex items-center gap-2 mb-2"><Filter size={16} className="text-brand-600" />
        <b className="text-sm">{L("Automated feature gates (decided in training, logged)", "स्वचालित फ़ीचर जाँच (ट्रेनिंग में तय, दर्ज)")}</b></div>
        {r.candidate_gate.map((g: any) => (
          <div key={g.feature} className="border-t border-slate-100 py-2 text-[13px]">
            <span className={`pill mr-2 ${g.decision === "accepted" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-700"}`}>{dec[g.decision] || g.decision}</span>
            <b>{t(g.label, lang)}</b> <span className="font-mono text-[11px] text-ink-400">{g.feature}</span>
            <div className="text-ink-500">{reportText(g.reason, lang)}{g.auc_gain != null && ` · AUC ${g.auc_without} → ${g.auc_with}`}</div>
          </div>))}
      </div>
      <div className="card p-3 overflow-x-auto"><b className="text-sm">{L("Proxy audit, can a single feature predict a protected group? (AUC; 0.5 = no information)",
        "प्रॉक्सी जाँच: क्या कोई एक फ़ीचर संरक्षित समूह का अनुमान लगा सकता है? (AUC; 0.5 = कोई जानकारी नहीं)")}</b>
        <table className="w-full text-[12.5px] mt-2"><thead><tr className="text-left text-ink-400"><th className="py-1">{L("Feature", "फ़ीचर")}</th>
          <th>→ {L("gender", "लिंग")}</th><th>→ {L("rural", "ग्रामीण")}</th><th>{L("In model", "मॉडल में")}</th><th>{L("Note", "टिप्पणी")}</th></tr></thead>
          <tbody>{r.proxy_audit.map((p: any) => (
            <tr key={p.feature} className="border-t border-slate-100"><td className="py-1">{t(p.label, lang)}</td>
              <td className={p.auc_female > 0.6 ? "text-rose-700 font-semibold" : ""}>{p.auc_female}</td><td className={p.auc_rural > 0.6 ? "text-rose-700 font-semibold" : ""}>{p.auc_rural}</td>
              <td>{p.in_model ? L("yes", "हाँ") : L("no", "नहीं")}</td><td className="text-ink-400 text-[11px]">{reportText(p.dropped_reason, lang)}</td></tr>))}</tbody></table>
      </div>
    </div>
  );
}

function ScoreTable({ sc }: { sc: any }) {
  const L = useL();
  const { lang } = useLang();
  const method = sc.calibration.method === "identity" ? L("none needed (identity)", "आवश्यक नहीं (identity)") : sc.calibration.method;
  return (
    <div className="card p-3 overflow-x-auto">
      <div className="text-[12px] text-ink-400 mb-2">{L(
        "600 points ↔ 30:1 good:bad odds; +40 points doubles the odds. Bins are forced monotone in the economically sensible direction.",
        "600 अंक ↔ अच्छे:बुरे का 30:1 अनुपात; +40 अंक पर अनुपात दोगुना। हर फ़ीचर के खाने आर्थिक रूप से सही दिशा में एक-तरफ़ा रखे गए हैं।")}{" "}
        {L("Calibration", "कैलिब्रेशन")}: {method}.</div>
      {sc.features.map((f: any) => (
        <div key={f.name} className="border-t border-slate-100 py-2">
          <div className="text-[13px] font-semibold">{t(f.label, lang)} <span className="text-[11px] text-ink-400 font-normal">IV {f.iv}</span></div>
          <div className="flex flex-wrap gap-1 mt-1">
            {f.points.map((p: number, i: number) => {
              const lo = i === 0 ? "−∞" : f.edges[i - 1].toFixed(2), hi = i === f.edges.length ? "∞" : f.edges[i].toFixed(2);
              return <span key={i} className="pill bg-slate-50 border border-slate-200 font-mono">[{lo}, {hi}) → {p.toFixed(0)} {L("pts", "अंक")} · {L("bad", "बुरे")} {pct(f.bin_bad_rate[i])}</span>;
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function KB({ k }: { k: any }) {
  const L = useL();
  const { lang } = useLang();
  const [open, setOpen] = useState<string | null>(null);
  const avail: Record<string, string> = { available: L("available", "उपलब्ध"), unconfirmed: L("status unconfirmed", "स्थिति अपुष्ट"), unavailable: L("not available", "उपलब्ध नहीं") };
  return (
    <div className="space-y-3">
      <div className="card p-3 text-[13px] text-ink-700"><BookOpen size={15} className="inline mr-1 text-brand-600" />
        {L("Rules are data (YAML), not prompts. The engine refuses to load any criterion without a citation. Every source records whether its clause was verified on the official page, and when.",
           "नियम डेटा (YAML) हैं, प्रॉम्प्ट नहीं। स्रोत के बिना कोई भी शर्त इंजन में लोड नहीं होती। हर स्रोत दर्ज करता है कि उसकी शर्त आधिकारिक पेज पर सत्यापित हुई या नहीं, और कब।")}</div>
      {k.schemes.map((s: any) => (
        <div key={s.id} className="card p-3">
          <button className="w-full text-left flex items-center gap-2" onClick={() => setOpen(open === s.id ? null : s.id)}>
            <b className="flex-1">{t(s.name, lang)}</b>
            <span className={`pill ${s.availability === "available" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-700"}`}>{avail[s.availability] || s.availability}</span>
            {Object.entries(s.verification).filter(([, n]: any) => n).map(([v, n]: any) => <span key={v} className="text-[11px]">{n}× <VerBadge v={v} /></span>)}
          </button>
          {s.status_note && <div className="text-[12px] text-rose-800 mt-1">{t(s.status_note, lang)} {s.status_cites.map((c: any, i: number) => <CiteChip key={i} c={c} />)}</div>}
          {open === s.id && <div className="mt-2 space-y-1">{s.criteria.map((c: any) => (
            <div key={c.id} className="text-[12.5px] flex gap-2"><span className="font-mono text-[11px] text-ink-400 w-36 shrink-0">{c.id}</span><span className="flex-1">{t(c.text, lang)}<CiteChip c={c.cite} /></span></div>))}
            {s.lender_checks?.length > 0 && <div className="label pt-1">{L("Decided by the lender, not the scheme", "योजना नहीं, बैंक तय करता है")}</div>}
            {s.lender_checks?.map((lc: any, i: number) => (
              <div key={i} className="text-[12.5px] flex gap-2"><span className="w-36 shrink-0" /><span className="flex-1 text-ink-600">{t(lc.text, lang)}<CiteChip c={lc.cite} /></span></div>))}
          </div>}
        </div>
      ))}
      <div className="card p-3 overflow-x-auto"><b className="text-sm">{L("Source registry", "स्रोत सूची")}</b>
        <div className="text-[11px] text-ink-400 mt-0.5">{L("Document titles and notes are kept in the language of the source.", "दस्तावेज़ों के शीर्षक और टिप्पणियाँ स्रोत की भाषा में रखी गई हैं।")}</div>
        <table className="w-full text-[12px] mt-2"><tbody>{k.sources.map((s: any) => (
          <tr key={s.id} className="border-t border-slate-100"><td className="py-1 font-mono text-[11px] w-44">{s.id}</td><td><a className="text-brand-700" href={s.url} target="_blank" rel="noreferrer">{s.title}</a><div className="text-ink-400">{s.publisher}{s.note ? `, ${s.note}` : ""}</div></td>
            <td className="w-56"><VerBadge v={s.verification} /></td><td className="w-24 text-ink-400">{s.checked}</td></tr>))}</tbody></table>
      </div>
    </div>
  );
}
