import { createContext, useContext } from "react";

export type Lang = "en" | "hi";
export const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "hi", setLang: () => {} });
export const useLang = () => useContext(LangCtx);

export function t(x: any, lang: Lang): string {
  if (x == null) return "";
  if (typeof x === "string") return x;
  return x[lang] ?? x.en ?? "";
}

/** A scheme's short name in the current language (scheme results carry short/short_hi; offers scheme_short/scheme_short_hi). */
export function sname(x: any, lang: Lang): string {
  if (!x) return "";
  if (lang === "hi") return x.short_hi || x.scheme_short_hi || x.short || x.scheme_short || "";
  return x.short || x.scheme_short || "";
}

/** Inline bilingual text: const L = useL(); L("English", "हिन्दी"). */
export function useL() {
  const { lang } = useLang();
  return (en: string, hi: string) => (lang === "hi" ? hi : en);
}

// Audit groups used in the fairness tables
const GROUPS: Record<string, string> = {
  female: "महिलाएँ", male: "पुरुष", rural: "ग्रामीण", urban: "शहरी", rural_female: "ग्रामीण महिलाएँ", urban_male: "शहरी पुरुष",
  zone_north: "उत्तर क्षेत्र", zone_south: "दक्षिण क्षेत्र", zone_east: "पूर्व क्षेत्र", zone_west: "पश्चिम क्षेत्र",
  zone_central: "मध्य क्षेत्र", zone_northeast: "पूर्वोत्तर क्षेत्र", social_general: "सामान्य वर्ग", social_obc: "ओबीसी",
  social_sc: "अनुसूचित जाति (SC)", social_st: "अनुसूचित जनजाति (ST)",
};
export function groupName(g: string, lang: Lang): string {
  if (lang === "hi") return g.split("_vs_").map((x) => GROUPS[x] || x.replace(/_/g, " ")).join(" बनाम ");
  return g.replace(/_vs_/g, " vs ").replace(/_/g, " ");
}

/** Hindi for the fixed sentence patterns the training report writes; anything else stays as written. */
export function reportText(s: string | null | undefined, lang: Lang): string {
  if (!s || lang !== "hi") return s || "";
  const known: Record<string, string> = {
    "rejected by fairness/accuracy gate": "निष्पक्षता/सटीकता जाँच में अस्वीकार",
    "weak or unstable signal (IV / sign check)": "कमज़ोर या अस्थिर संकेत (IV / दिशा जाँच)",
    "adds predictive value without harming fairness": "निष्पक्षता को नुकसान पहुँचाए बिना अनुमान बेहतर करता है",
    "ITR filed AND collateral AND ≥2 years vintage AND no bounces": "ITR दाखिल, और गिरवी, और कम से कम 2 साल पुराना व्यवसाय, और कोई बाउंस नहीं",
  };
  if (known[s]) return known[s];
  let m = s.match(/^AUC gain ([+\-\d.]+) below ([\d.]+)$/);
  if (m) return `AUC में बढ़त ${m[1]}, सीमा ${m[2]} से कम`;
  m = s.match(/^proxy for a protected group \(AUC ([\d.]+) > ([\d.]+)\) with weak signal \(IV ([\d.]+) < ([\d.]+)\)$/);
  if (m) return `संरक्षित समूह का परोक्ष संकेतक (AUC ${m[1]} > ${m[2]}) और कमज़ोर संकेत (IV ${m[3]} < ${m[4]})`;
  return s;
}

export function kb(bytes: number): string { return bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`; }

export function inr(n: number | null | undefined, short = false): string {
  if (n == null || isNaN(n as number)) return "-";
  const neg = n < 0;
  const v = Math.abs(Math.round(n));
  if (short) {
    if (v >= 1e7) return `${neg ? "-" : ""}₹${(v / 1e7).toFixed(2).replace(/\.00$/, "")} Cr`;
    if (v >= 1e5) return `${neg ? "-" : ""}₹${(v / 1e5).toFixed(2).replace(/\.?0+$/, "")} L`;
  }
  const s = v.toString();
  let out = s;
  if (s.length > 3) {
    const head = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    out = head + "," + s.slice(-3);
  }
  return `${neg ? "-" : ""}₹${out}`;
}

export const pct = (x: number | null | undefined, d = 1) => (x == null ? "-" : `${(x * 100).toFixed(d)}%`);
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const mlabel = (mk: string) => `${MONTHS[parseInt(mk.slice(5, 7)) - 1]} ${mk.slice(2, 4)}`;

export const UI: Record<string, { en: string; hi: string }> = {
  send: { en: "Send", hi: "भेजें" },
  typeHere: { en: "Type or tap the mic…", hi: "लिखें या माइक दबाएँ…" },
  approveSelected: { en: "Allow selected", hi: "चुनी हुई अनुमति दें" },
  skip: { en: "Skip", hi: "छोड़ें" },
  why: { en: "Why we ask", hi: "हम क्यों पूछ रहे हैं" },
  choose: { en: "Choose this", hi: "यह चुनें" },
  seasonal: { en: "Season-matched", hi: "मौसम अनुसार" },
  flat: { en: "Same every month", hi: "हर महीने समान" },
  upload: { en: "Upload photo", hi: "फ़ोटो अपलोड करें" },
  atCafe: { en: "Do at JanAI Café", hi: "JanAI कैफ़े पर करें" },
  approve: { en: "Approve & send", hi: "मंज़ूरी दें और भेजें" },
  notNow: { en: "Not now", hi: "अभी नहीं" },
  doIt: { en: "Yes, do it for me", hi: "हाँ, मेरे लिए करें" },
  later: { en: "Later", hi: "बाद में" },
  eligible: { en: "Eligible", hi: "पात्र" },
  needs_info: { en: "Need info", hi: "जानकारी चाहिए" },
  not_eligible: { en: "Not eligible", hi: "पात्र नहीं" },
  lapsed: { en: "Lapsed", hi: "समाप्त" },
};
