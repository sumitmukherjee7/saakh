import { createContext, useContext } from "react";

export type Lang = "en" | "hi";
export const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "hi", setLang: () => {} });
export const useLang = () => useContext(LangCtx);

export function t(x: any, lang: Lang): string {
  if (x == null) return "";
  if (typeof x === "string") return x;
  return x[lang] ?? x.en ?? "";
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
