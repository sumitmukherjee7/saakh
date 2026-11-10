import { useLang } from "../util";

const LAYERS = [
  ["Channels", "Voice-first PWA (Hindi/English) · JanAI Café assisted mode · Branch console · Federation screening"],
  ["Agent runtime", "Goal-driven planner · case memory · retries & fallbacks · human checkpoints (consent, actions, offer, final approval)"],
  ["Guardrails in code", "Tool guard: active consent artefact · approval bound to file hash · go-ahead for outward actions · hash-chained audit"],
  ["Decision engines", "Cited 3-valued scheme rules · value-of-information questions · cash-flow analytics · monotone WoE scorecard · season-matched sizing · document set-cover"],
  ["Integrations (simulated)", "Account Aggregator (ReBIT artefacts) · DigiLocker e-KYC · credit bureau · Udyam · PM SVANidhi LoR · lender LOS"],
];

export default function About() {
  const { lang } = useLang();
  return (
    <div className="max-w-5xl mx-auto p-4 md:p-8 space-y-4">
      <div>
        <div className="text-3xl font-bold">Saakh <span className="text-brand-600">साख</span></div>
        <p className="text-ink-500 mt-1 max-w-3xl">
          {lang === "hi"
            ? "साख का अर्थ है भरोसा। साख एक एजेंट है जो छोटे व्यवसाय की UPI/बैंक लेनदेन को, उसकी अनुमति से, बैंक-योग्य साख में बदलता है, योजनाओं की हर पात्रता का स्रोत बताता है, कृत्रिम डेटा पर प्रशिक्षित एक प्रदर्शन-मॉडल से जोखिम अनुमान दिखाता है (निष्पक्षता जाँच में अभी रुका हुआ, असली भुगतान पर कभी सत्यापित नहीं), और उद्यमी की मंज़ूरी के बाद ही फ़ाइल बैंक तक पहुँचाता है।"
            : "Saakh means creditworthiness; the trust a business has earned. Saakh is an agent that turns a small business's consented UPI and bank flows into bank-ready credit: it cites the source of every scheme-eligibility claim, shows a risk estimate from a demonstration scorecard trained on synthetic data (fairness-gated, currently blocked for real use and never validated on real repayments), and delivers the file, with anything still pending listed, to the branch only after the entrepreneur approves it."}
        </p>
      </div>
      <div className="card p-4">
        <div className="font-semibold mb-2">Architecture</div>
        <div className="space-y-2">
          {LAYERS.map(([k, v], i) => (
            <div key={k} className="flex gap-3 items-stretch">
              <div className={`w-44 shrink-0 rounded-xl px-3 py-2 text-sm font-semibold text-white ${["bg-brand-700", "bg-brand-600", "bg-rose-600", "bg-brand-500", "bg-violet-600"][i]}`}>{k}</div>
              <div className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-[13px] text-ink-700">{v}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div className="card p-4 text-[13px] space-y-1.5">
          <div className="font-semibold mb-1">Boundaries, enforced</div>
          <div>• No data pull without an active, signed, purpose-bound consent, checked before every tool call.</div>
          <div>• No submission unless the entrepreneur approved <i>this exact file</i> (hash-bound); any change voids approval.</div>
          <div>• Every eligibility criterion cites a source; the KB refuses to load an uncited rule; sources carry verification status.</div>
          <div>• Protected attributes never enter the score; fairness and calibration gates run at training time, on synthetic data, and one gate currently fails, so the model is blocked for real use.</div>
          <div>• Revoking consent deletes derived data and withdraws the application from the lender.</div>
        </div>
        <div className="card p-4 text-[13px] space-y-1.5">
          <div className="font-semibold mb-1">Disclosed simulations</div>
          <div>All people, bank statements and bureau records are synthetic. Account Aggregator, DigiLocker, bureau, Udyam, SVANidhi and lender LOS calls are simulated adapters with production-shaped interfaces, and the UI marks them <span className="pill bg-violet-50 text-violet-700 border border-violet-200">SIMULATED</span>. The risk model is trained on a documented synthetic population and must be re-fit on lender data before real use.</div>
        </div>
      </div>
    </div>
  );
}
