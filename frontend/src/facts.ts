// Shared bilingual lookups: fact labels and option values (from /api/facts, fetched once), plus the fixed
// words the backend sends as codes (data sources, consent statuses, document channels, application states).
import { useEffect, useState } from "react";
import { api } from "./api";
import { inr, t, type Lang } from "./util";

let REG: Record<string, any> | null = null;
let loading: Promise<Record<string, any>> | null = null;

/** The fact registry; components re-render once it arrives. */
export function useFactReg(): Record<string, any> {
  const [r, setR] = useState<Record<string, any>>(REG || {});
  useEffect(() => {
    if (REG) return;
    loading = loading || api.facts().then((x: any) => (REG = x));
    loading.then(setR).catch(() => {});
  }, []);
  return r;
}

const pretty = (s: string) => s.replace(/_/g, " ");

export function factLabel(reg: Record<string, any>, k: string, lang: Lang): string {
  const f = reg[k];
  return f ? t(f.label, lang) : pretty(k);
}

export function factValue(reg: Record<string, any>, k: string, v: any, lang: Lang): string {
  if (v == null) return "-";
  const f = reg[k];
  const opt = f?.options?.find((o: any) => o.value === v);
  if (opt) return t(opt.label, lang);
  if (v === true) return lang === "hi" ? "हाँ" : "yes";
  if (v === false) return lang === "hi" ? "नहीं" : "no";
  if (typeof v === "number" && (f?.type === "money" || v > 999)) return inr(v);
  if (Array.isArray(v)) return v.map((x) => pretty(String(x))).join(", ");
  return pretty(String(v));
}

const SOURCE_HI: Record<string, string> = {
  user: "आपने बताया", ekyc: "ई-केवाईसी", aa: "अकाउंट एग्रीगेटर", "aa-inferred": "अकाउंट एग्रीगेटर (अनुमान)",
  bureau: "क्रेडिट ब्यूरो", udyam: "उद्यम", udyam_portal: "उद्यम पोर्टल", derived: "गणना से", statement_upload: "अपलोड विवरण",
  "statement_upload-inferred": "अपलोड विवरण (अनुमान)", svanidhi: "पीएम स्वनिधि पोर्टल", entrepreneur: "उद्यमी", operator: "ऑपरेटर",
  "entrepreneur (said)": "उद्यमी (बातचीत से)", "entrepreneur (correction)": "उद्यमी (सुधार)", "operator (correction)": "ऑपरेटर (सुधार)",
};
export const sourceName = (s: string | undefined, lang: Lang) => (!s ? "" : lang === "hi" ? SOURCE_HI[s] || pretty(s) : pretty(s));

const PROVIDER_HI: Record<string, string> = {
  "DigiLocker (simulated)": "डिजिलॉकर (सिम्युलेटेड)", "Account Aggregator → your bank (simulated)": "अकाउंट एग्रीगेटर → आपका बैंक (सिम्युलेटेड)",
  "Credit bureau (simulated)": "क्रेडिट ब्यूरो (सिम्युलेटेड)", "Udyam portal (simulated)": "उद्यम पोर्टल (सिम्युलेटेड)",
  "Uploaded by you": "आपने अपलोड किया", "Saakh → lender": "साख → बैंक",
};
export const providerName = (p: string, lang: Lang) => (lang === "hi" ? PROVIDER_HI[p] || p : p);

const EVID_HI: [RegExp, string][] = [
  [/^DigiLocker \(simulated\)/, "डिजिलॉकर (सिम्युलेटेड)"], [/^Account Aggregator \(simulated FIP\)/, "अकाउंट एग्रीगेटर (सिम्युलेटेड FIP)"],
  [/^Credit bureau \(simulated\)/, "क्रेडिट ब्यूरो (सिम्युलेटेड)"], [/^Udyam API \(simulated\)/, "उद्यम API (सिम्युलेटेड)"],
  [/^Udyam portal \(simulated\)/, "उद्यम पोर्टल (सिम्युलेटेड)"], [/^PM SVANidhi portal \(simulated\)/, "पीएम स्वनिधि पोर्टल (सिम्युलेटेड)"],
  [/, declared investment & turnover/, ", घोषित निवेश और टर्नओवर"], [/\(simulated instant ULB approval\)/, "(सिम्युलेटेड तुरंत ULB मंज़ूरी)"],
  [/^12-month business inflows (.+)$/, "12 महीने की व्यावसायिक आय $1"], [/^(\d+)-month business inflows (.+), annualised$/, "$1 महीने की व्यावसायिक आय $2, सालाना अनुमान"],
  [/^(\d+) payments from business buyers \(e\.g\. (.+)\)$/, "व्यावसायिक ख़रीदारों से $1 भुगतान (जैसे $2)"],
  [/^(\d+) milk-union payments \(e\.g\. (.+)\)$/, "दूध संघ से $1 भुगतान (जैसे $2)"],
];
/** Provenance notes from the integrations and the cash-flow analysis; reference codes inside them stay as they are. */
export function evidenceText(s: string | undefined, lang: Lang): string {
  if (!s || lang !== "hi") return s || "";
  return EVID_HI.reduce((acc, [re, hi]) => acc.replace(re, hi), s);
}

const CONSENT_HI: Record<string, string> = { ACTIVE: "सक्रिय", PENDING: "लंबित", REVOKED: "वापस ली गई", REJECTED: "अस्वीकार", EXPIRED: "समाप्त", PAUSED: "रुकी हुई" };
export const consentStatus = (s: string, lang: Lang) => (lang === "hi" ? CONSENT_HI[s] || s : s);

const VIA_HI: Record<string, string> = {
  DigiLocker: "डिजिलॉकर", "In-app camera": "ऐप कैमरा", "Account Aggregator": "अकाउंट एग्रीगेटर", Generated: "साख ने बनाया",
  Bureau: "ब्यूरो", "Udyam API": "उद्यम API", GSTN: "जीएसटी पोर्टल", Upload: "अपलोड", "CSC / JanAI Café": "CSC / JanAI कैफ़े",
  "Chartered accountant": "चार्टर्ड अकाउंटेंट", "In-app e-sign": "ऐप में ई-साइन", "Income-tax portal": "आयकर पोर्टल",
  "KVIC online EDP": "KVIC ऑनलाइन EDP", "PM SVANidhi portal": "पीएम स्वनिधि पोर्टल", "SRLM / bank": "SRLM / बैंक",
  "Upload / WhatsApp photo": "अपलोड / व्हाट्सऐप फ़ोटो", "Vet visit": "पशु चिकित्सक की जाँच",
};
export const viaName = (v: string | undefined, lang: Lang) => (!v ? "" : lang === "hi" ? VIA_HI[v] || v : v);

const APP_HI: Record<string, string> = {
  submitted: "जमा", sanctioned: "स्वीकृत", sanction: "स्वीकृत", declined: "अस्वीकृत", decline: "अस्वीकृत", query: "सवाल पूछा", withdrawn: "वापस लिया",
  seasonal: "मौसम अनुसार", flat: "हर महीने समान",
};
export const appStatus = (s: string | undefined, lang: Lang) => (!s ? "" : lang === "hi" ? APP_HI[s] || pretty(s) : pretty(s));

const PENDING_HI: Record<string, [string, string]> = {
  intake: ["your words", "आपकी बात"], consent: ["your permission", "आपकी अनुमति"], question: ["your answer", "आपका जवाब"],
  action: ["your go-ahead", "आपकी हाँ"], choose_offer: ["your choice of offer", "ऑफ़र का चुनाव"], documents: ["documents", "दस्तावेज़"],
  approval: ["your final approval", "आपकी अंतिम मंज़ूरी"], fallback_statement: ["a bank statement", "बैंक विवरण"],
};
export const pendingName = (s: string | undefined, lang: Lang) => (!s ? "" : (PENDING_HI[s] ? PENDING_HI[s][lang === "hi" ? 1 : 0] : pretty(s)));
