import { useL, useLang } from "../util";
import { SimBadge } from "./common";

export default function About() {
  const { lang } = useLang();
  const L = useL();
  const layers: [string, string][] = [
    [L("Channels", "माध्यम"), L("Voice-first PWA (Hindi/English) · JanAI Café assisted mode · Branch console · Federation screening",
      "आवाज़-प्रथम ऐप (हिन्दी/अंग्रेज़ी) · JanAI कैफ़े सहायता मोड · बैंक शाखा कंसोल · महासंघ जाँच")],
    [L("Agent runtime", "एजेंट"), L("Goal-driven planner · case memory · retries & fallbacks · human checkpoints (consent, actions, offer, final approval)",
      "लक्ष्य-आधारित योजना · मामले की याद · दोबारा प्रयास और विकल्प · इंसानी पड़ाव (सहमति, कदम, ऑफ़र, अंतिम मंज़ूरी)")],
    [L("Guardrails in code", "कोड में सुरक्षा"), L("Tool guard: active consent artefact · approval bound to file hash · go-ahead for outward actions · hash-chained audit",
      "टूल गार्ड: सक्रिय सहमति · फ़ाइल हैश से बँधी मंज़ूरी · बाहरी कदमों के लिए हाँ ज़रूरी · हैश-श्रृंखला वाला ऑडिट")],
    [L("Decision engines", "निर्णय इंजन"), L("Cited 3-valued scheme rules · value-of-information questions · cash-flow analytics · monotone WoE scorecard · season-matched sizing · document set-cover",
      "स्रोत सहित तीन-मान वाले योजना नियम · सबसे उपयोगी सवाल · नकदी-प्रवाह विश्लेषण · एक-दिशा WoE स्कोरकार्ड · मौसम अनुसार ऋण राशि · न्यूनतम दस्तावेज़ सेट")],
    [L("Integrations (simulated)", "जुड़ाव (सिम्युलेटेड)"), L("Account Aggregator (ReBIT artefacts) · DigiLocker e-KYC · credit bureau · Udyam · PM SVANidhi LoR · lender LOS",
      "अकाउंट एग्रीगेटर (ReBIT सहमति) · डिजिलॉकर ई-केवाईसी · क्रेडिट ब्यूरो · उद्यम · पीएम स्वनिधि LoR · बैंक LOS")],
  ];
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
        <div className="font-semibold mb-2">{L("Architecture", "संरचना")}</div>
        <div className="space-y-2">
          {layers.map(([k, v], i) => (
            <div key={i} className="flex gap-3 items-stretch">
              <div className={`w-44 shrink-0 rounded-xl px-3 py-2 text-sm font-semibold text-white ${["bg-brand-700", "bg-brand-600", "bg-rose-600", "bg-brand-500", "bg-violet-600"][i]}`}>{k}</div>
              <div className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-[13px] text-ink-700">{v}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div className="card p-4 text-[13px] space-y-1.5">
          <div className="font-semibold mb-1">{L("Boundaries, enforced", "सीमाएँ, जो लागू होती हैं")}</div>
          <div>• {L("No data pull without an active, signed, purpose-bound consent, checked before every tool call.",
            "सक्रिय, हस्ताक्षरित, एक उद्देश्य वाली सहमति के बिना कोई डेटा नहीं लिया जाता; हर टूल से पहले जाँच होती है।")}</div>
          <div>• {L("No submission unless the entrepreneur approved this exact file (hash-bound); any change voids approval.",
            "उद्यमी की इसी फ़ाइल पर मंज़ूरी (हैश से बँधी) के बिना कुछ जमा नहीं होता; कोई भी बदलाव मंज़ूरी रद्द कर देता है।")}</div>
          <div>• {L("Every eligibility criterion cites a source; the KB refuses to load an uncited rule; sources carry verification status.",
            "हर पात्रता शर्त का स्रोत दिया गया है; बिना स्रोत का नियम लोड नहीं होता; हर स्रोत की सत्यापन स्थिति दर्ज है।")}</div>
          <div>• {L("Protected attributes never enter the score; fairness and calibration gates run at training time, on synthetic data, and one gate currently fails, so the model is blocked for real use.",
            "संरक्षित पहचान (लिंग, जाति, धर्म, स्थान) स्कोर में कभी नहीं जाती; निष्पक्षता और कैलिब्रेशन जाँचें ट्रेनिंग में कृत्रिम डेटा पर चलती हैं, और एक जाँच अभी विफल है, इसलिए मॉडल असली उपयोग के लिए रुका हुआ है।")}</div>
          <div>• {L("Revoking consent deletes derived data and withdraws the application from the lender.",
            "सहमति वापस लेने पर उससे बना डेटा मिट जाता है और आवेदन बैंक से वापस हो जाता है।")}</div>
        </div>
        <div className="card p-4 text-[13px] space-y-1.5">
          <div className="font-semibold mb-1">{L("Disclosed simulations", "बताई गई सिम्युलेशन")}</div>
          <div>{L("All people, bank statements and bureau records are synthetic. Account Aggregator, DigiLocker, bureau, Udyam, SVANidhi and lender LOS calls are simulated adapters with production-shaped interfaces, and the UI marks them",
            "सभी लोग, बैंक विवरण और ब्यूरो रिकॉर्ड कृत्रिम हैं। अकाउंट एग्रीगेटर, डिजिलॉकर, ब्यूरो, उद्यम, स्वनिधि और बैंक LOS असली जैसी बनावट वाले सिम्युलेटेड जुड़ाव हैं, और ऐप इन्हें")}{" "}
            <SimBadge />{" "}
            {L("everywhere. The risk model is trained on a documented synthetic population and must be re-fit on lender data before real use.",
              "से चिह्नित करता है। जोखिम मॉडल एक दर्ज कृत्रिम आबादी पर प्रशिक्षित है और असली उपयोग से पहले इसे बैंक डेटा पर दोबारा प्रशिक्षित करना होगा।")}</div>
        </div>
      </div>
    </div>
  );
}
